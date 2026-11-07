"""Read-only feedback coverage, never a playing-strength or expert-data label."""
from collections import Counter, defaultdict


def build(learners, traces, credit, events):
    learners=set(map(int,learners))
    submitted={(int(e['player']),int(e['observed_frame']),str(e['head'])) for e in events if e.get('submitted')}
    groups={}
    for head,items in traces.items():
        for trace in items:
            obs=trace['observation'];player=int(obs['player_index'])
            identity=(player,int(obs.get('decision_frame',-1)),head)
            group=groups.setdefault((player,head,str(obs['faction'])),{
                'player':player,'head':head,'faction':str(obs['faction']),
                'learner':player in learners,'counts':Counter(),
                'selected_kinds':Counter(),'submitted_kinds':Counter(),
                'nonzero_components':Counter(),'zero_credit_reasons':Counter(),
                'modes':Counter()})
            group['counts']['decisions']+=1
            mode=trace.get('mode','unknown');group['modes'][mode]+=1
            if len(trace['candidates'])>1:
                group['counts']['multichoice']+=1
                if mode=='sample':group['counts']['sample_multichoice']+=1
            choice=trace['candidates'][int(trace['selected_index'])]
            kind=str(choice.get('kind',str(choice.get('id',head)).split('_',1)[0]))
            group['selected_kinds'][kind]+=1
            if identity in submitted:
                group['counts']['submitted']+=1;group['submitted_kinds'][kind]+=1
            value=credit.get(identity)
            if value is not None:group['counts']['matched_credit']+=1
            if value and value.get('matured'):group['counts']['matured']+=1
            components={k:float(v) for k,v in (value or {}).get('components',{}).items() if abs(float(v))>1e-10}
            for name in components:group['nonzero_components'][name]+=1
            if components:group['counts']['local_feedback']+=1
            reward=float((value or {}).get('reward',0))
            if abs(reward)>1e-10:group['counts']['nonzero_reward']+=1
            else:
                reason=('no_dispatch' if identity not in submitted else
                        'no_credit_match' if value is None else
                        'unmatured' if not value.get('matured') else
                        'offsetting_components' if components else
                        'matured_without_measured_local_effect')
                group['zero_credit_reasons'][reason]+=1
            if not components and abs(float((value or {}).get('terminal_share',0)))>1e-10:
                group['counts']['terminal_only']+=1
    all_players=defaultdict(lambda:{'decisions':0,'nonzero_components':Counter()})
    for (player,_,_),value in credit.items():
        all_players[player]['decisions']+=1
        for name,amount in value.get('components',{}).items():
            if abs(float(amount))>1e-10:all_players[player]['nonzero_components'][name]+=1
    return {'schema':'decision-feedback-audit-v1','learner_players':sorted(learners),
            'trace_groups':[dict(g,**{k:dict(v) for k,v in g.items() if isinstance(v,Counter)}) for _,g in sorted(groups.items())],
            'all_player_credit':[dict(v,player=p,learner=p in learners,nonzero_components=dict(v['nonzero_components'])) for p,v in sorted(all_players.items())],
            'interpretation':'Feedback coverage only. Submitted orders are not completions. Missing local credit is not a success/failure label. Evaluation and fixture samples are not training updates.'}
