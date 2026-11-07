"""Explicit offline BC for shared entity/GRU policy. Never activates a model.

Uses only exact, verified human demonstrations. Legacy aggregates, fixtures,
model outputs and missing entities cannot be relabelled into expert sequences.
"""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import random
import sys
import torch
from torch.nn import functional as F
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'service'))
from entity_codec import EntityCodec,FACTIONS
from entity_policy import SharedEntityPolicy,tensor_frame
from public_game_rules import PublicGameRules


def load_sequences(path,codec):
    groups=defaultdict(list);rejected=Counter();identities={};seen=set();factions=Counter()
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        row=json.loads(line)
        if row.get('schema')!='bc-demonstration-v1' or row.get('source_kind')!='human' or row.get('fixture') or row.get('training_eligible') is not True:
            rejected['not_verified_human']+=1;continue
        if row.get('execution_evidence') not in ('native_queue_inserted','native_queue_removed'):
            rejected['missing_native_evidence']+=1;continue
        if row.get('game_rules_sha256')!=codec.rules.sha256:raise ValueError('Mixed rules catalogue')
        session=(row['session'],row['match']);split=row['split']
        if split not in ('train','validation','test'):raise ValueError('Invalid dataset split')
        if session in identities and identities[session]!=split:raise ValueError('Session leaks between dataset splits')
        identities[session]=split
        key=(row['session'],row['match'],int(row['player']));identity=key+(row['command_id'],)
        if identity in seen:raise ValueError('Duplicate demonstration')
        seen.add(identity)
        if int(row['frame'])!=int(row['observation']['decision_frame']):raise ValueError('Demonstration frame mismatch')
        head=row['head'];index=int(row['selected_index']);choices=row['candidates']
        if head not in ('tactical','spend') or not 0<=index<len(choices) or choices[index]['id']!=row['selected_id']:raise ValueError('Selected action mismatch')
        if len(choices)<2:rejected['single_choice']+=1;continue
        try:encoded=codec.encode(row['observation'],{head:choices})
        except (ValueError,KeyError,TypeError) as error:
            rejected['invalid_or_missing_entities']+=1;continue
        # Do not train on a target/actor whose observation was truncated.
        selected=choices[index];required=set(map(int,selected.get('units',[])))
        required.update(int(selected.get(k,0)) for k in ('producer','target'));required.discard(0)
        present={int(e['id']) for e in row['observation']['entity_state']['entities']}
        from entity_codec import ACTION_FIELDS
        coverage=encoded['heads'][head]['features'][index,2*ACTION_FIELDS.index('actor_coverage')]
        target_present=encoded['heads'][head]['features'][index,2*ACTION_FIELDS.index('target_present')]
        if not required<=present or coverage<1 or (int(selected.get('target',0))>0 and target_present<1):
            rejected['selected_reference_not_encoded']+=1;continue
        groups[(split,key)].append(row);factions[row['observation']['faction']]+=1
    sequences=defaultdict(list)
    for (split,key),rows in groups.items():
        rows.sort(key=lambda r:(int(r['frame']),int(r['command_id'])))
        sequences[split].append(rows)
    return sequences,{'rejected':dict(rejected),'factions':dict(factions),'sequences':{k:len(v) for k,v in sequences.items()},'rows':{k:sum(map(len,v)) for k,v in sequences.items()}}


def sequence_loss(model,codec,rows,device,optimizer=None,window=16):
    memory=None;previous=None;losses=[];total=0.;count=0;correct=0
    def flush():
        nonlocal memory,losses
        if not losses:return
        if optimizer:
            optimizer.zero_grad(set_to_none=True);torch.stack(losses).mean().backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.,error_if_nonfinite=True);optimizer.step()
        if memory is not None:memory=memory.detach()
        losses=[]
    for row in rows:
        frame=int(row['frame']);delta=0. if previous is None else (frame-previous)/5.
        if previous is None or delta>30.:
            flush();memory=None
        head=row['head'];encoded=codec.encode(row['observation'],{head:row['candidates']},delta)
        f,h=tensor_frame(encoded,device);scores,_,memory=model.forward_step(f,h,memory)
        logits=scores[head];target=torch.tensor([row['selected_index']],device=device)
        loss=F.cross_entropy(logits,target)
        if not torch.isfinite(loss):raise ValueError('Nonfinite BC loss')
        losses.append(loss);total+=loss.detach().item();count+=1;correct+=int(logits.argmax(-1).item()==target.item())
        if len(losses)>=window:flush()
        previous=frame
    flush()
    return {'loss':total/max(1,count),'accuracy':correct/max(1,count),'examples':count}


def train(data,rules_path,output,epochs=1,device='auto'):
    if epochs<1 or epochs>100:raise ValueError('Epochs must be 1..100')
    output=Path(output)
    if output.exists() and any(output.iterdir()):raise ValueError('Output must be new or empty')
    if device=='auto':device='cuda' if torch.cuda.is_available() else 'cpu'
    rules=PublicGameRules(rules_path);codec=EntityCodec(rules);sequences,coverage=load_sequences(data,codec)
    output.mkdir(parents=True,exist_ok=True)
    report={'architecture':'shared-entity-gru-v1','coverage':coverage,'device':device,'training_performed':False,'activated':False,'game_rules_sha256':rules.sha256,'history':[]}
    if any(not sequences.get(k) for k in ('train','validation','test')):
        report['blocked']='Need disjoint real human train/validation/test sessions with current entity snapshots.'
        (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        return report
    torch.manual_seed(7);rng=random.Random(7)
    model=SharedEntityPolicy(len(codec.vocabulary)).to(device);optimizer=torch.optim.AdamW(model.parameters(),lr=3e-4)
    best=float('inf')
    for epoch in range(epochs):
        model.train();rows=list(sequences['train']);rng.shuffle(rows)
        training=[sequence_loss(model,codec,r,device,optimizer) for r in rows]
        model.eval()
        with torch.no_grad():validation=[sequence_loss(model,codec,r,device) for r in sequences['validation']]
        def combine(metrics):
            n=sum(x['examples'] for x in metrics)
            return {k:sum(x[k]*x['examples'] for x in metrics)/n for k in ('loss','accuracy')}|{'examples':n}
        record={'epoch':epoch+1,'train':combine(training),'validation':combine(validation)};report['history'].append(record)
        if record['validation']['loss']<best:
            best=record['validation']['loss'];model.save(output/'candidate.pt',codec.vocabulary,rules.sha256,trained=True)
    model,_=SharedEntityPolicy.load(output/'candidate.pt',rules.sha256,device);model.eval()
    with torch.no_grad():report['test']=combine([sequence_loss(model,codec,r,device) for r in sequences['test']])
    report['training_performed']=True;report['scope']='Event-sampled human BC; accuracy is not playing strength. No RL, activation or legacy-weight conversion.'
    report['parameters']=sum(p.numel() for p in model.parameters())
    (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--rules',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--epochs',type=int,default=1);p.add_argument('--device',choices=['auto','cpu','cuda'],default='auto');a=p.parse_args()
    print(json.dumps(train(a.data,a.rules,a.output,a.epochs,a.device),ensure_ascii=False))
