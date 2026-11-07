"""Checkpoint benchmark metrics. Descriptive, held-out, never reward/training labels."""
from collections import Counter,defaultdict
import math
from economy_evaluation import evaluate
SCHEMA='fixed-native-benchmark-v1'

def outcome(report):
    b=report.get('benchmark',{});v=b.get('victory',{})
    if not report.get('ok') or report.get('script_errors',0):return 'invalid'
    if not v.get('ok') or not v.get('single_alliance'):return 'truncated'
    model=set(map(int,b['model_players']));native=set(map(int,b['native_players']))
    winners={int(e['player']) for e in v.get('events',[]) if e.get('kind')=='alliance_victory'}
    if winners and winners<=model:return 'win'
    if winners and winners<=native:return 'loss'
    return 'unresolved_terminal'

def metrics(report,rows):
    economy=evaluate(rows);timings=[]
    for p in economy['players']:
        player=p['player'];seen=set();baseline=False;previous=None;counts=Counter();events=[];minutes=defaultdict(float);cursor=None;complete=True
        for r in sorted((r for r in rows if int(r['player'])==player),key=lambda r:int(r['frame'])):
            frame=int(r['frame']);assets=r.get('own_assets',[])
            if previous is not None and frame<=previous:continue
            if not baseline:
                seen={int(a['id']) for a in assets if a.get('complete')};baseline=True
                cursor=int(r.get('income_cursor',-1));previous=frame;continue
            for a in assets:
                oid=int(a['id'])
                if not a.get('complete') or oid in seen:continue
                seen.add(oid)
                if a.get('builder'):continue
                kind='farm' if a.get('economy') else 'factory' if a.get('factory') else 'hero' if a.get('hero') else 'army' if a.get('mobile') and not a.get('structure') else 'structure'
                counts[kind]+=1
                events.append({'kind':kind,'ordinal':counts[kind],'template':a['template'],'object':oid,'first_completed_observed_seconds':frame/5.,'completion_interval_seconds':[previous/5.,frame/5.]})
            next_cursor=int(r.get('income_cursor',-1));valid=bool(r.get('income_complete')) and next_cursor>=cursor
            complete &= valid
            if valid:
                accepted=set()
                for payment in r.get('income_payments',[]):
                    serial=int(payment['serial'])
                    if serial in accepted or not cursor<serial<=next_cursor:continue
                    accepted.add(serial)
                    if p['start_frame']<int(payment['frame'])<=frame:minutes[int(payment['frame'])//300]+=float(payment['amount'])
            cursor=max(cursor,next_cursor);previous=frame
        per_minute=[]
        if complete:
            first=p['start_frame']/5.;last=p['end_frame']/5.
            for minute in range(int(first//60),int(last//60)+1):
                duration=max(0.,min(last,(minute+1)*60)-max(first,minute*60))
                if duration:per_minute.append({'minute':minute,'observed_seconds':duration,'real_income':minutes[minute],'income_per_minute':minutes[minute]*60/duration,'full_minute':duration>=60})
        p['real_income_per_minute']=None if p['real_income_per_second'] is None else p['real_income_per_second']*60
        p['minute_income']=per_minute if complete else None
        timings.append({'player':player,'faction':p['faction'],'events':events,'measurement':'First observed completion, not accepted order; intervals may span observation gaps. Initial objects excluded. Containment/transfers may affect unit appearances.'})
    return {'schema':SCHEMA,'outcome':outcome(report),'economy':economy,'build_order':timings,'model_players':report.get('benchmark',{}).get('model_players',[]),'affects_training':False}

def wilson(wins,n):
    if not n:return None
    z=1.959963984540054;p=wins/n;d=1+z*z/n
    middle=(p+z*z/(2*n))/d;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0.,middle-half),min(1.,middle+half)]

def aggregate(games):
    outcomes=Counter(g['outcome'] for g in games);n=outcomes['win']+outcomes['loss'];income=defaultdict(list);milestones=defaultdict(list)
    for g in games:
        own=set(g['model_players'])
        for p in g['economy']['players']:
            if p['player'] in own and p['sufficient_window'] and p['real_income_per_minute'] is not None:income[p['faction']].append(p['real_income_per_minute'])
        for p in g['build_order']:
            if p['player'] not in own:continue
            for e in p['events']:
                if e['ordinal']<=3:milestones[(p['faction'],e['kind'],e['ordinal'])].append(e['first_completed_observed_seconds'])
    def distribution(values):
        values=sorted(values);n=len(values)
        return {'n':n,'mean':sum(values)/n,'median':(values[(n-1)//2]+values[n//2])/2,'min':values[0],'max':values[-1]}
    return {'attempted':len(games),'outcomes':dict(outcomes),'completed':n,'completion_fraction':n/len(games) if games else None,'win_rate_completed':outcomes['win']/n if n else None,'wilson_95_completed':wilson(outcomes['win'],n),'win_fraction_all_attempts':outcomes['win']/len(games) if games else None,'income_per_minute_by_faction':{f:distribution(v) for f,v in income.items()},'build_milestones':[{'faction':f,'kind':k,'ordinal':o,**distribution(v)} for (f,k,o),v in sorted(milestones.items())],'interpretation':'Win rate denominator is completed games; inspect truncation separately. One 3v3 game is one outcome, not three independent wins. No automatic strength claim.'}
