"""Architecture invariants only. Synthetic examples are never training data."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
import numpy as np
import torch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'service'))
from entity_codec import EntityCodec,FACTIONS,ACTION_FIELDS
from entity_policy import SharedEntityPolicy,MemorySession,tensor_frame
from public_game_rules import PublicGameRules
ROOT=Path(__file__).resolve().parents[4]

class EntityPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2);torch.manual_seed(7)
        config=json.loads((ROOT/'AI-Yeni-Model/ai-service/runtime.json').read_text(encoding='utf-8-sig'))
        cls.rules=PublicGameRules(config['game_rules']);cls.codec=EntityCodec(cls.rules)
        cls.model=SharedEntityPolicy(len(cls.codec.vocabulary)).eval()
        cls.observation={'faction':FACTIONS[0],'decision_frame':10,'money':1000,'entity_state':{'encoding':'rts-entities-v1','source':'native_fog_filtered','frame':10,'map_extent':{'extent_x':4000,'extent_y':4000},'entities':[
          {'id':1,'template':'unknown1','relation':'self','faction':FACTIONS[0],'visible':True,'x':200,'y':300,'health_ratio':1,'hero':False},
          {'id':2,'template':'unknown2','relation':'enemy','faction':FACTIONS[4],'visible':True,'x':400,'y':600,'health_ratio':.4}]}}
        cls.choices={'tactical':[{'id':'a','kind':'attack','units':[1],'target':2,'x':400,'y':600},{'id':'b','kind':'scout','units':[1],'x':900,'y':600}], 'spend':[{'id':'none','kind':'wait'},{'id':'train:test','kind':'train','producer':1,'template':'unknown1','cost':100}]}
    def encoded(self):return self.codec.encode(copy.deepcopy(self.observation),copy.deepcopy(self.choices))
    def test_fog_missing_and_frame(self):
        for change in ('hidden','frame','missing'):
            obs=copy.deepcopy(self.observation)
            if change=='hidden':obs['entity_state']['entities'][1]['visible']=False
            if change=='frame':obs['entity_state']['frame']=9
            if change=='missing':obs.pop('entity_state')
            with self.assertRaises(ValueError):self.codec.encode(obs,self.choices)
    def test_permutation_and_id_invariance(self):
        encoded=self.encoded();f,h=tensor_frame(encoded)
        obs=copy.deepcopy(self.observation);choices=copy.deepcopy(self.choices)
        # Rename and reverse entity order, retaining action references.
        obs['entity_state']['entities'][0]['id']=11;obs['entity_state']['entities'][1]['id']=10
        obs['entity_state']['entities'].reverse()
        for cs in choices.values():
            for c in cs:
                if 'units' in c:c['units']=[11]
                if 'producer' in c:c['producer']=11
                if c.get('target')==2:c['target']=10
        f2,h2=tensor_frame(self.codec.encode(obs,choices))
        with torch.no_grad():
            a,_,ma=self.model.forward_step(f,h);b,_,mb=self.model.forward_step(f2,h2)
        torch.testing.assert_close(ma,mb,atol=1e-6,rtol=1e-5)
        for key in a:torch.testing.assert_close(a[key],b[key],atol=1e-6,rtol=1e-5)
    def test_empty_padding_and_legal_mask(self):
        obs=copy.deepcopy(self.observation);obs['entity_state']['entities']=[]
        f,h=tensor_frame(self.codec.encode(obs,{'tactical':self.choices['tactical'],'spend':[]}))
        h['tactical']['legal'][0,1]=False
        with torch.no_grad():scores,value,m=self.model.forward_step(f,h)
        self.assertTrue(torch.isfinite(value).all() and torch.isfinite(m).all())
        self.assertTrue(torch.isneginf(scores['spend']).all())
        self.assertEqual(scores['tactical'].argmax(-1).item(),0)
    def test_recurrent_reset_and_sessions(self):
        e=self.encoded();f,h=tensor_frame(e)
        with torch.no_grad():
            _,_,m1=self.model.forward_step(f,h)
            _,_,m2=self.model.forward_step(f,h,m1)
            _,_,mr=self.model.forward_step(f,h,m1,torch.tensor([True]))
        self.assertFalse(torch.allclose(m1,m2));torch.testing.assert_close(m1,mr)
        a=MemorySession();b=MemorySession()
        a.infer(self.model,e,('match',1),1,10);first=a.hidden.clone()
        a.infer(self.model,e,('match',1),1,10);torch.testing.assert_close(first,a.hidden)
        a.infer(self.model,e,('match',1),2,11)
        b.infer(self.model,e,('match',2),1,10);torch.testing.assert_close(first,b.hidden)
        a.infer(self.model,e,('newmatch',1),1,10);torch.testing.assert_close(first,a.hidden)
        with self.assertRaises(ValueError):a.infer(self.model,e,('newmatch',1),0,11)
    def test_capping_and_action_variants(self):
        codec=EntityCodec(self.rules,max_entities=1);e=codec.encode(self.observation,self.choices)
        self.assertEqual(e['dropped_entities'],1)
        coverage=e['heads']['tactical']['features'][0,2*ACTION_FIELDS.index('actor_coverage')]
        self.assertTrue(0<=coverage<=1)
        choices={'spend':[{'id':'s1','kind':'stance','variant':1},{'id':'s2','kind':'stance','variant':2}]}
        v=self.codec.encode(self.observation,choices)['heads']['spend']['features']
        self.assertFalse(np.array_equal(v[0],v[1]))
    def test_shared_gradients_and_checkpoint(self):
        model=SharedEntityPolicy(len(self.codec.vocabulary));f,h=tensor_frame(self.encoded())
        scores,_,_=model.forward_step(f,h)
        loss=sum(torch.nn.functional.cross_entropy(v,torch.tensor([0])) for v in scores.values());loss.backward()
        for module in (model.faction,model.entity_in[0],model.attention.layers[0].self_attn,model.memory,model.scorer[0]):
            self.assertTrue(any(p.grad is not None and p.grad.abs().sum()>0 for p in module.parameters()))
        self.assertFalse(hasattr(model,'factions'))
        with tempfile.TemporaryDirectory(dir=ROOT/'AI-PyTorch') as d:
            p=Path(d)/'test.pt';model.save(p,self.codec.vocabulary,self.rules.sha256)
            loaded,meta=SharedEntityPolicy.load(p,self.rules.sha256)
            for k,v in model.state_dict().items():torch.testing.assert_close(v,loaded.state_dict()[k])
            self.assertFalse(meta['trained'])
            with self.assertRaises(ValueError):SharedEntityPolicy.load(p,'bad-catalog')
    def test_bc_rejects_fixture_and_split_leak(self):
        from train_entity_bc import load_sequences,sequence_loss
        row={'schema':'bc-demonstration-v1','source_kind':'human','fixture':False,'training_eligible':True,'execution_evidence':'native_queue_inserted','game_rules_sha256':self.rules.sha256,'session':'s','match':'m','player':1,'command_id':1,'split':'train','frame':10,'head':'spend','observation':self.observation,'candidates':self.choices['spend'],'selected_index':1,'selected_id':'train:test'}
        with tempfile.TemporaryDirectory(dir=ROOT/'AI-PyTorch') as d:
            path=Path(d)/'rows.jsonl';fixture=dict(row,fixture=True)
            path.write_text(json.dumps(fixture),encoding='utf-8')
            seq,report=load_sequences(path,self.codec);self.assertFalse(seq)
            path.write_text(json.dumps(row)+'\n'+json.dumps(dict(row,split='test',command_id=2)),encoding='utf-8')
            with self.assertRaises(ValueError):load_sequences(path,self.codec)
        # Local tensor/gradient check only; no dataset/checkpoint written.
        model=copy.deepcopy(self.model);optimizer=torch.optim.AdamW(model.parameters(),lr=1e-4)
        report=sequence_loss(model,self.codec,[row]*3,'cpu',optimizer,window=2)
        self.assertEqual(report['examples'],3);self.assertTrue(np.isfinite(report['loss']))

    def test_gpu_forward_backward(self):
        if not torch.cuda.is_available():self.skipTest('CUDA unavailable')
        model=copy.deepcopy(self.model).cuda();e=self.encoded();f,h=tensor_frame(e,'cuda')
        scores,_,_=model.forward_step(f,h)
        sum(torch.nn.functional.cross_entropy(v,torch.tensor([0],device='cuda')) for v in scores.values()).backward()
        self.assertTrue(torch.isfinite(model.memory.weight_ih.grad).all())
        with torch.no_grad():
            gpu,_,_=model.forward_step(f,h)
            cpu,_,_=self.model.forward_step(*tensor_frame(e))
        for key in cpu:torch.testing.assert_close(cpu[key],gpu[key].cpu(),atol=1e-5,rtol=1e-4)

if __name__=='__main__':unittest.main()
