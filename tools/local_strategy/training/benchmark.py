"""Pinned, resumable evaluation against native Brutal AI. No training/activation.

Creating a suite only writes a schedule. run is explicit and bounded by max-games.
"""
import argparse
from contextlib import contextmanager
import csv
from datetime import datetime,timezone
import hashlib
import html
import json
import msvcrt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE.parent/'service'))
from benchmark_metrics import metrics,aggregate,SCHEMA
FACTIONS=['FactionMen','FactionElves','FactionDwarves','FactionWild','FactionMordor','FactionIsengard','FactionAngmar']

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);temp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');temp.replace(p)
@contextmanager
def lock(p):
    with Path(p).open('a+b') as f:
        f.seek(0)
        if not f.read(1):f.write(b'0');f.flush()
        f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        try:yield
        finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)

def source_manifest():
    b=HERE.parent
    paths=list((b/'arena').glob('*.gd'))+list((b/'team_ai').rglob('*.gd'))+list((b/'team_ai').rglob('*.json'))+list((b/'service').glob('*.py'))
    paths += [b/'arena/run.py',b/'arena/scenarios.json',b/'model_only_controller.gd',b/'decision_trial.py',b/'general_strategy.gd']
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))}

def create(config,output,games=200,simulation_seconds=1800,wall_seconds=1800,seed=47000,smoke=False):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Use a new suite directory')
    if not 1<=games<=10000 or not 1<=simulation_seconds<=7200 or not 1<=wall_seconds<=1800:raise ValueError('Invalid benchmark budget')
    if smoke and (games!=1 or wall_seconds>6 or simulation_seconds>24):raise ValueError('Smoke is one bounded 6-second run')
    c=read(config);state=read(ROOT/'AI-Motor-Guncellemeleri/engine-state.json')
    manifest={'schema':SCHEMA,'created_utc':datetime.now(timezone.utc).isoformat(),'smoke_only':smoke,'native_difficulty':'Brutal','map':read(HERE.parent/'arena/scenarios.json')['map'],'engine':state,'source_manifest':source_manifest(),'game_rules_sha256':c['game_rules_sha256'],'reward_sha256':c['reward_sha256'],'simulation_frames':int(round(simulation_seconds*5)),'wall_seconds':wall_seconds,'plan':[{'index':i,'seed':seed+i,'model_team':1+i%2,'factions':[FACTIONS[(i+j)%7] for j in range(6)]} for i in range(games)],'checkpoints':[]}
    manifest['conditions_id']=hashlib.sha256(json.dumps({k:v for k,v in manifest.items() if k not in ('created_utc','checkpoints')},sort_keys=True).encode()).hexdigest()
    output.mkdir(parents=True);write(output/'suite.json',manifest)
    add(output,config,'initial')
    return output

def add(suite,config,label,step=None,weights=None,spend=None):
    suite=Path(suite).resolve()
    with lock(suite/'registry.lock'):
        manifest=read(suite/'suite.json');c=read(config)
        if source_manifest()!=manifest['source_manifest']:raise ValueError('Evaluation source changed; create a new suite')
        if c['game_rules_sha256']!=manifest['game_rules_sha256'] or c['reward_sha256']!=manifest['reward_sha256']:raise ValueError('Catalogue/reward conditions changed; create a new suite')
        if c.get('model')!='openbfme-decision-net-v0':raise ValueError('New shared recurrent runtime is not yet connected; no fake benchmark')
        tactic=Path(weights or c['weights']);purchase=Path(spend or c['spend_weights'])
        if tactic.suffix!='.npz' or purchase.suffix!='.npz':raise ValueError('Unsupported checkpoint runtime')
        if not weights and sha(tactic)!=c['sha256']:raise ValueError('Tactic checkpoint hash mismatch')
        if not spend and sha(purchase)!=c['spend_sha256']:raise ValueError('Spend checkpoint hash mismatch')
        identity=hashlib.sha256((sha(tactic)+sha(purchase)).encode()).hexdigest()[:20]
        for previous in manifest['checkpoints']:
            if previous['id']==identity:return previous
        dest=suite/'checkpoints'/identity;dest.mkdir(parents=True,exist_ok=True)
        for key,digest_key,source,name in [('weights','sha256',tactic,'tactic.npz'),('spend_weights','spend_sha256',purchase,'spend.npz')]:
            target=dest/name
            if target.exists() and sha(target)!=sha(source):raise ValueError('Immutable checkpoint collision')
            if not target.exists():shutil.copy2(source,target)
            c[key]=str(target);c[digest_key]=sha(target)
        c.update(auto_engine_update=False,arena_engine_directory=manifest['engine']['directory'],arena_benchmark=True)
        write(dest/'runtime.json',c)
        entry={'id':identity,'label':str(label),'training_step':step,'ordinal':len(manifest['checkpoints']),'config':str(dest/'runtime.json'),'config_sha256':sha(dest/'runtime.json'),'tactic_sha256':c['sha256'],'spend_sha256':c['spend_sha256'],'registered_utc':datetime.now(timezone.utc).isoformat()}
        manifest['checkpoints'].append(entry);write(suite/'suite.json',manifest)
    summarize(suite)
    return entry

def run(suite,checkpoint=None,max_games=1):
    suite=Path(suite).resolve();m=read(suite/'suite.json')
    if max_games<1:raise ValueError('max-games must be positive')
    if source_manifest()!=m['source_manifest']:raise ValueError('Evaluation source changed; create a new fixed suite')
    engine=Path(m['engine']['directory'])
    for name,digest in m['engine']['files'].items():
        if sha(engine/name)!=digest:raise ValueError('Pinned engine changed')
    choices=[c for c in m['checkpoints'] if checkpoint is None or c['id']==checkpoint]
    if not choices:raise ValueError('Unknown checkpoint')
    completed=0
    with lock(ROOT/'AI-Test-Sahasi/training.lock'):
        for cp in choices:
            base=read(cp['config'])
            if sha(cp['config'])!=cp['config_sha256']:raise ValueError('Pinned checkpoint config changed')
            for path,digest_key in [('weights','sha256'),('spend_weights','spend_sha256'),('game_rules','game_rules_sha256'),('reward_config','reward_sha256')]:
                if sha(base[path])!=base[digest_key]:raise ValueError('Pinned input changed: '+path)
            for game in m['plan']:
                dest=suite/'games'/cp['id']/('%04d'%game['index']);result=dest/'metrics.json'
                if result.exists():continue
                if completed>=max_games:return summarize(suite)
                dest.mkdir(parents=True,exist_ok=True)
                config=dict(base,arena_factions=game['factions'],benchmark_team=game['model_team'],arena_sim_frames=m['simulation_frames'])
                write(dest/'runtime.json',config);episode=dest/'episode'
                # Recover interrupted attempts without overwriting their evidence.
                if episode.exists():episode.rename(dest/('interrupted-'+uuid.uuid4().hex[:8]))
                cmd=[sys.executable,str(HERE.parent/'service/decision_host.py'),'--config',str(dest/'runtime.json'),'--arena','opening','--arena-case','baseline','--seconds',str(m['wall_seconds']),'--episode-dir',str(episode),'--episode-seed',str(game['seed']),'--episode-mode','evaluate']
                env=dict(os.environ);env.pop('OPENBFME_AI_TRAINING',None)
                env['PYTHONPATH']=str(HERE)+os.pathsep+env.get('PYTHONPATH','')
                with (dest/'process.log').open('w',encoding='utf-8') as log:
                    proc=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                    try:code=proc.wait(timeout=120+m['wall_seconds']*1.5)
                    except BaseException:
                        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT);proc.wait(timeout=10)
                        raise
                report_path=episode/'arena/opening.json'
                if code==0 and report_path.exists():
                    report=read(report_path);b=report.get('benchmark',{})
                    expected=sorted(p['player'] for p in report.get('model_only_validation',{}).get('players',[]) if p.get('model_only'))
                    if not b or sorted(b['model_players'])!=expected:raise ValueError('Native opponent authority was not proven')
                    rows=[json.loads(x) for x in Path(b['telemetry']).read_text(encoding='utf-8-sig').splitlines() if x.strip()]
                    measured=metrics(report,rows)
                else:measured={'schema':SCHEMA,'outcome':'invalid','economy':{'players':[]},'build_order':[],'model_players':[],'exit_code':code}
                measured.update(checkpoint=cp['id'],conditions_id=m['conditions_id'],game=game,smoke_only=m['smoke_only'])
                write(result,measured);completed+=1;summarize(suite)
    return summarize(suite)

def summarize(suite):
    suite=Path(suite);m=read(suite/'suite.json');curve=[]
    for cp in m['checkpoints']:
        games=[]
        for game in m['plan']:
            p=suite/'games'/cp['id']/('%04d'%game['index'])/'metrics.json'
            if p.exists():
                row=read(p)
                if row.get('conditions_id')!=m['conditions_id'] or row.get('checkpoint')!=cp['id'] or row.get('game')!=game:raise ValueError('Benchmark result identity mismatch')
                games.append(row)
        curve.append({'checkpoint':cp['id'],'label':cp['label'],'ordinal':cp['ordinal'],'training_step':cp['training_step'],'planned_games':len(m['plan']),'pending_games':len(m['plan'])-len(games),**aggregate(games)})
    report={'schema':SCHEMA,'conditions_id':m['conditions_id'],'smoke_only':m['smoke_only'],'checkpoints':curve,'strength_claim':False,'scope':'Same fixed native opponent suite; no update/activation. New architecture requires a connected trained runtime. Missing and truncated games are explicit.'}
    write(suite/'learning-curve.json',report)
    with (suite/'learning-curve.csv').open('w',newline='',encoding='utf-8-sig') as f:
        keys=['checkpoint','label','ordinal','training_step','planned_games','pending_games','attempted','completed','completion_fraction','win_rate_completed','wilson_95_completed','win_fraction_all_attempts'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for r in curve:w.writerow({k:r[k] for k in keys})
    with (suite/'faction-metrics.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['checkpoint','faction','metric','ordinal','n','mean','median','min','max'])
        for cp in curve:
            for faction,d in cp['income_per_minute_by_faction'].items():w.writerow([cp['checkpoint'],faction,'income_per_minute','',*[d[k] for k in ('n','mean','median','min','max')]])
            for d in cp['build_milestones']:w.writerow([cp['checkpoint'],d['faction'],d['kind'],d['ordinal'],*[d[k] for k in ('n','mean','median','min','max')]])
    def chart(values):
        pts=[]
        for i,value in values:
            if value is not None:pts.append((50+650*i/max(1,len(curve)-1),210-170*value))
        return '<svg viewBox="0 0 750 250" role="img" aria-label="Completed match win rate"><path d="M50 30V210H720" fill="none" stroke="#718096"/><text x="10" y="38">100%</text><text x="20" y="212">0%</text><polyline fill="none" stroke="#60a5fa" stroke-width="2" points="'+ ' '.join(f'{x},{y}' for x,y in pts)+'"/>'+''.join(f'<circle cx="{x}" cy="{y}" r="4" fill="#93c5fd"/>' for x,y in pts)+'</svg>'
    body='<h1>Checkpoint değerlendirmesi / Checkpoint evaluation</h1><p>'+('Yalnız kısa altyapı kontrolü — öğrenme eğrisi değildir.' if m['smoke_only'] else 'Sabit native Brutal AI. Kazanma oranı yalnız biten maçlar içindir; yarım kalanları ayrıca inceleyin.')+'</p>'
    body+=chart([(r['ordinal'],r['win_rate_completed']) for r in curve]) if not m['smoke_only'] else ''
    body+='<table><tr><th>Checkpoint</th><th>Biten / Denenen / Planlanan</th><th>Kazanma</th><th>%95 aralık</th><th>Yarım</th><th>Hata</th></tr>'
    for r in curve:
        rate='—' if r['win_rate_completed'] is None else f"{100*r['win_rate_completed']:.1f}%"
        ci='—' if r['wilson_95_completed'] is None else ' – '.join(f'{100*x:.1f}%' for x in r['wilson_95_completed'])
        body+=f"<tr><td>{html.escape(r['label'])}</td><td>{r['completed']} / {r['attempted']} / {r['planned_games']}</td><td>{rate}</td><td>{ci}</td><td>{r['outcomes'].get('truncated',0)}</td><td>{r['outcomes'].get('invalid',0)}</td></tr>"
    body+='</table><p>Gelir ve ilk tamamlanma zamanları fraksiyon bazında faction-metrics.csv; ayrıntılar learning-curve.json. Eksik veri sıfır sayılmaz. X: checkpoint kayıt sırası; eğitim adımı CSV içinde ayrı saklanır. Farklı tamamlanma kapsamları doğrudan iyileşme kanıtı değildir.</p>'
    (suite/'learning-curve.html').write_text('<!doctype html><html lang="tr"><meta charset="utf-8"><title>AI evaluation</title><style>body{font:16px system-ui;background:#101827;color:#e2e8f0;max-width:1000px;margin:40px auto;padding:20px}svg{max-width:750px}text{fill:#cbd5e1;font-size:12px}td,th{padding:12px;border-bottom:1px solid #334155;text-align:left}p{line-height:1.6}</style>'+body+'</html>',encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('create');c.add_argument('--config',type=Path,required=True);c.add_argument('--output',type=Path,required=True);c.add_argument('--games',type=int,default=200);c.add_argument('--simulation-seconds',type=float,default=1800);c.add_argument('--wall-seconds',type=int,default=1800);c.add_argument('--seed',type=int,default=47000);c.add_argument('--smoke',action='store_true')
    a=sub.add_parser('add');a.add_argument('--suite',type=Path,required=True);a.add_argument('--config',type=Path,required=True);a.add_argument('--label',required=True);a.add_argument('--step',type=int)
    r=sub.add_parser('run');r.add_argument('--suite',type=Path,required=True);r.add_argument('--checkpoint');r.add_argument('--max-games',type=int,default=1)
    s=sub.add_parser('summary');s.add_argument('--suite',type=Path,required=True)
    a=p.parse_args()
    if a.command=='create':print(create(a.config,a.output,a.games,a.simulation_seconds,a.wall_seconds,a.seed,a.smoke))
    elif a.command=='add':print(json.dumps(add(a.suite,a.config,a.label,a.step),ensure_ascii=False))
    elif a.command=='run':print(json.dumps(run(a.suite,a.checkpoint,a.max_games),ensure_ascii=False))
    else:print(json.dumps(summarize(a.suite),ensure_ascii=False))
