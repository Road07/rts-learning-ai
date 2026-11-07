"""Bounded recorded-fixture interface/CUDA check; does not train or activate."""
import json
from pathlib import Path
import sys
import time
import torch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'service'))
from public_game_rules import PublicGameRules
from entity_codec import EntityCodec,ENTITY_WIDTH,ACTION_WIDTH
from entity_policy import SharedEntityPolicy,tensor_frame,MemorySession
from train_entity_bc import train
ROOT=Path(__file__).resolve().parents[4]
c=json.loads((ROOT/'AI-Yeni-Model/ai-service/runtime.json').read_text(encoding='utf-8-sig'))
state=json.loads((ROOT/'AI-Motor-Guncellemeleri/engine-state.json').read_text(encoding='utf-8-sig'))
validation=json.loads(Path(state['validation']).read_text(encoding='utf-8-sig'))
paths=validation['human_logging_validation']['files'];rules=PublicGameRules(c['game_rules']);codec=EntityCodec(rules)
model=SharedEntityPolicy(len(codec.vocabulary)).cuda().eval();snapshots=[];checks=[]
for path in paths:
 for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
  row=json.loads(line);d=row.get('data',{})
  if d.get('event',row.get('event'))!='human_policy_snapshot':continue
  obs=d['policy_observation'];raw=d['payload']['observation'];entities=obs['entity_state']['entities']
  expected={int(o['id']) for p in raw['players'] for o in p['objects']}
  assert {int(e['id']) for e in entities}==expected
  assert all(e['visible'] for e in entities)
  encoded=codec.encode(obs,{'tactical':d['tactical_candidates'],'spend':d['spend_candidates']})
  f,h=tensor_frame(encoded,'cuda')
  with torch.inference_mode():scores,value,memory=model.forward_step(f,h)
  assert torch.isfinite(value).all() and torch.isfinite(memory).all()
  for head,logits in scores.items():
   if h[head]['legal'].any():assert torch.isfinite(logits[h[head]['legal']]).all()
  checks.append({'frame':obs['decision_frame'],'entities':len(entities),'dropped':encoded['dropped_entities'],'heads':{k:len(v['ids']) for k,v in encoded['heads'].items()}})
  snapshots.append(encoded)
assert snapshots and validation['ok'] and validation['human_logging_validation']['checks']['hidden_enemy_excluded']
f,h=tensor_frame(snapshots[0],'cuda')
with torch.inference_mode():
 for _ in range(5):model.forward_step(f,h)
 torch.cuda.synchronize();start=time.perf_counter()
 for _ in range(20):model.forward_step(f,h)
 torch.cuda.synchronize();milliseconds=(time.perf_counter()-start)*1000/20
cpu=model.cpu();torch.set_num_threads(2);fc,hc=tensor_frame(snapshots[0])
with torch.inference_mode():
 for _ in range(5):cpu.forward_step(fc,hc)
 start=time.perf_counter()
 for _ in range(20):cpu.forward_step(fc,hc)
 cpu_ms=(time.perf_counter()-start)*1000/20
out=ROOT/'AI-PyTorch/data-readiness';i=0
while out.exists():i+=1;out=ROOT/f'AI-PyTorch/data-readiness-{i}'
readiness=train(ROOT/'AI-Egitim/bc-demonstrations-v1/demonstrations.jsonl',c['game_rules'],out)
assert not readiness['training_performed']
report={'architecture':'shared-entity-gru-v1','torch':torch.__version__,'cuda':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name(0),'parameters':sum(p.numel() for p in model.parameters()),'entity_width':ENTITY_WIDTH,'action_width':ACTION_WIDTH,'template_vocabulary':len(codec.vocabulary),'mean_forward_ms':milliseconds,'cpu_mean_forward_ms':cpu_ms,'peak_tensor_mib':torch.cuda.max_memory_allocated()/1024**2,'timing_scope':'Single recorded fixture, 20 warmed GPU forwards; excludes JSON/codec/IPC and CUDA context memory. Not playing strength.','arena_report':state['validation'],'arena_ok':validation['ok'],'snapshot_checks':checks,'bc_readiness':str(out/'report.json'),'trained':False,'activated':False,'legacy_tactic_sha256':c['sha256'],'legacy_spend_sha256':c['spend_sha256']}
(ROOT/'ai-mod-source/entity-architecture-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
