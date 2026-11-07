"""Shared faction-conditioned entity attention + causal GRU policy prototype.

Not a loader/converter for legacy faction-bank checkpoints. Activation is separate.
"""
import torch
from torch import nn
from entity_codec import ENCODING,ENTITY_WIDTH,ACTION_WIDTH,GLOBAL_WIDTH,KINDS

ARCHITECTURE='shared-entity-gru-v1'


class SharedEntityPolicy(nn.Module):
    def __init__(self,templates,width=96,hidden=128):
        super().__init__();self.config={'templates':int(templates),'width':width,'hidden':hidden}
        self.template=nn.Embedding(templates,24)
        self.faction=nn.Embedding(8,16)
        self.relation=nn.Embedding(4,4);self.role=nn.Embedding(9,8)
        self.entity_in=nn.Sequential(nn.Linear(ENTITY_WIDTH+24+16+4+8,width),nn.LayerNorm(width),nn.GELU())
        layer=nn.TransformerEncoderLayer(width,4,width*2,dropout=0.,activation='gelu',batch_first=True)
        self.attention=nn.TransformerEncoder(layer,2,enable_nested_tensor=False)
        self.cls=nn.Parameter(torch.zeros(1,1,width))
        self.context=nn.Sequential(nn.Linear(width+16+GLOBAL_WIDTH,hidden),nn.LayerNorm(hidden),nn.Tanh())
        self.memory=nn.GRUCell(hidden,hidden)
        self.kind=nn.Embedding(len(KINDS),12);self.head=nn.Embedding(2,4)
        self.action=nn.Sequential(nn.Linear(ACTION_WIDTH+24+12+4,64),nn.GELU())
        self.scorer=nn.Sequential(nn.Linear(hidden+2*width+64,128),nn.Tanh(),nn.Linear(128,1))
        self.value=nn.Linear(hidden,1)

    def forward_step(self,frame,heads,memory=None,reset=None):
        """Compute memory ONCE, then score both action heads against that state."""
        raw=frame['entities'];batch=raw.shape[0]
        if memory is None:memory=raw.new_zeros((batch,self.config['hidden']))
        if reset is not None:memory=memory*~reset.bool().unsqueeze(-1)
        entity=self.entity_in(torch.cat([raw,self.template(frame['entity_templates']),self.faction(frame['owner_factions']),self.relation(frame['relations']),self.role(frame['roles'])],-1))
        tokens=torch.cat([self.cls.expand(batch,-1,-1),entity],1)
        padding=torch.cat([torch.zeros((batch,1),device=raw.device,dtype=torch.bool),~frame['entity_valid'].bool()],1)
        encoded=self.attention(tokens,src_key_padding_mask=padding)
        context=self.context(torch.cat([encoded[:,0],self.faction(frame['faction']),frame['globals']],-1))
        memory=self.memory(context,memory)
        objects=encoded[:,1:]*frame['entity_valid'].unsqueeze(-1)
        scores={}
        for name,choices in heads.items():
            index=0 if name=='tactical' else 1 if name=='spend' else None
            if index is None:raise ValueError('Unknown policy head')
            def pool(mask):
                weights=mask.to(objects.dtype)*frame['entity_valid'].unsqueeze(1)
                return torch.bmm(weights,objects)/weights.sum(-1,keepdim=True).clamp_min(1.)
            count=choices['features'].shape[1]
            token=self.action(torch.cat([choices['features'],self.template(choices['templates']),self.kind(choices['kinds']),self.head(torch.full_like(choices['kinds'],index))],-1))
            logits=self.scorer(torch.cat([memory.unsqueeze(1).expand(-1,count,-1),pool(choices['actors']),pool(choices['targets']),token],-1)).squeeze(-1)
            scores[name]=logits.masked_fill(~choices['legal'].bool(),-torch.inf)
        return scores,self.value(memory).squeeze(-1),memory

    def save(self,path,vocabulary,game_rules_sha256,trained=False):
        torch.save({'architecture':ARCHITECTURE,'entity_encoding':ENCODING,'config':self.config,'vocabulary':vocabulary,'game_rules_sha256':game_rules_sha256,'trained':bool(trained),'state_dict':self.state_dict()},path)

    @classmethod
    def load(cls,path,game_rules_sha256,device='cpu'):
        checkpoint=torch.load(path,map_location=device,weights_only=True)
        if checkpoint.get('architecture')!=ARCHITECTURE or checkpoint.get('entity_encoding')!=ENCODING or checkpoint.get('game_rules_sha256')!=game_rules_sha256:raise ValueError('Entity checkpoint interface mismatch')
        if len(checkpoint['vocabulary'])!=checkpoint['config']['templates'] or len(set(checkpoint['vocabulary']))!=len(checkpoint['vocabulary']):raise ValueError('Invalid template vocabulary')
        model=cls(**checkpoint['config']).to(device);model.load_state_dict(checkpoint['state_dict'],strict=True)
        return model,checkpoint


def tensor_frame(encoded,device='cpu'):
    keys=('entities','entity_valid','entity_templates','relations','owner_factions','roles','faction','globals')
    frame={k:torch.as_tensor(encoded[k],device=device).unsqueeze(0) for k in keys}
    heads={name:{k:torch.as_tensor(value,device=device).unsqueeze(0) for k,value in head.items() if k!='ids'} for name,head in encoded['heads'].items()}
    return frame,heads


class MemorySession:
    """One bot/match context. Never share hidden state across players or matches."""
    def __init__(self):self.key=None;self.step=None;self.frame=-1;self.hidden=None;self.output=None
    def clear(self):self.__init__()
    def infer(self,model,encoded,key,step,frame,device='cpu'):
        if self.key==key and self.step==step:
            if frame!=self.frame:raise ValueError('Reused step with a different frame')
            return self.output
        if self.key==key and self.step is not None and step<self.step:raise ValueError('Out-of-order decision step')
        reset=self.key!=key or frame<self.frame
        state,choices=tensor_frame(encoded,device)
        with torch.inference_mode():
            scores,value,hidden=model.forward_step(state,choices,None if reset else self.hidden)
        self.key=key;self.step=step;self.frame=frame;self.hidden=hidden.detach()
        self.output=(scores,value)
        return self.output
