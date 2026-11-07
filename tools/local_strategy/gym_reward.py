"""Privileged potential shaping. Never constructs or enriches agent observations."""
from dataclasses import dataclass,asdict
import math

SCHEMA='gym-potential-v1'

@dataclass(frozen=True)
class PotentialConfig:
    a: float=1e-4
    b: float=.01
    c: float=1e-4
    gamma: float=.99
    def __post_init__(self):
        if any(not math.isfinite(v) for v in asdict(self).values()) or not 0<=self.gamma<=1:
            raise ValueError('Potential weights must be finite; gamma must be 0..1')

class PotentialReward:
    def __init__(self,config):self.config=config;self.previous=None;self.roster=None

    def potential(self,state,player,frame):
        if not isinstance(state,dict) or not state.get('ok') or state.get('schema')!='gym-reward-state-v1' or state.get('frame')!=frame:
            raise ValueError('Missing or misaligned privileged reward measurements')
        rows=state.get('players',[])
        ids=[r.get('player') for r in rows]
        if len(set(ids))!=len(ids) or ids.count(player)!=1:raise ValueError('Invalid reward player identities')
        roster=tuple(sorted((r['player'],r['team']) for r in rows))
        if self.roster is not None and roster!=self.roster:raise ValueError('Reward roster/team changed')
        for row in rows:
            if not row.get('army_complete'):raise ValueError('Unknown native unit cost; no army value imputation')
            for key in ('total_income','building_count','army_value'):
                if not isinstance(row.get(key),(int,float)) or not math.isfinite(row[key]) or row[key]<0:raise ValueError('Invalid reward statistic: '+key)
        own=next(r for r in rows if r['player']==player);enemies=[r for r in rows if r['team']!=own['team']]
        if not enemies:raise ValueError('No opposing players in reward state')
        coefficients={'income':('total_income',self.config.a),'buildings':('building_count',self.config.b),'army':('army_value',self.config.c)}
        parts={name:weight*(own[key]-sum(r[key] for r in enemies)/len(enemies)) for name,(key,weight) in coefficients.items()}
        if any(not math.isfinite(v) for v in parts.values()):raise ValueError('Nonfinite potential')
        return parts,roster

    def reset(self,state,player,frame):
        self.previous,self.roster=self.potential(state,player,frame)
        return dict(self.previous)

    def step(self,state,player,frame,terminal_reward,terminated,truncated):
        if self.previous is None:raise RuntimeError('Initialize reward potential at reset')
        if terminated and truncated:raise ValueError('Conflicting episode boundary')
        current,_=self.potential(state,player,frame)
        # Absorbing true terminal has Phi=0; truncation retains its real Phi.
        effective={key:0. if terminated else value for key,value in current.items()}
        shape={key:self.config.gamma*effective[key]-self.previous[key] for key in current}
        components={'terminal':float(terminal_reward),**{'potential_'+key:value for key,value in shape.items()},
                    'shaping':sum(shape.values()),'truncated_result':max(-1.,min(1.,sum(current.values()))) if truncated else 0.}
        components['total']=components['terminal']+components['shaping']+components['truncated_result']
        if any(not math.isfinite(v) for v in components.values()):raise ValueError('Nonfinite reward')
        details={'potential_old':dict(self.previous),'potential_new':current,'effective_potential_new':effective}
        self.previous=current
        return components,details
