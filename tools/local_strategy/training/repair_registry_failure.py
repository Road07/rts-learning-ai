"""Finalize only a fully written run stopped by the known benchmark import error.

No rollout, gradient update, evaluation or inferred completion. Original report
is preserved; partial training or pending evaluation is rejected.
"""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import shutil
from automatic_training import ROOT,read_json,sha,write_json
from checkpoint_registry import add,module
from model_activation import activate,validate_network
from decision_net import features
from spend_policy import spend_features,WAIT

def validate(folder):
    report=read_json(folder/'report.json');settings=report['settings'];rounds=report.get('rounds',[])
    if report.get('status')!='failed' or not report.get('error','').startswith("cannot import name 'add' from 'benchmark'"):
        raise ValueError('This tool repairs only the recorded benchmark-name collision')
    if settings.get('evaluate') or len(rounds)!=int(settings['cycles']) or not rounds:
        raise ValueError('Training/evaluation is incomplete; cannot finalize')
    for i,row in enumerate(rounds):
        if sha(folder/('checkpoint-%03d.npz'%i))!=row['checkpoint_sha256'] or sha(folder/('spend-checkpoint-%03d.npz'%i))!=row['spend_sha256']:
            raise ValueError('Saved checkpoint differs from committed round')
        episode=folder/('train-%03d'%i)
        arena=read_json(episode/'arena'/(settings['stage']+'.json'))
        if not arena.get('ok') or arena.get('script_errors') or arena.get('exit_code'):
            raise ValueError('Native episode did not complete cleanly')
        headless=arena.get('headless_training',{})
        if settings.get('headless_training') and headless.get('simulation_seconds')!=settings['seconds']:
            raise ValueError('Recorded simulation budget is incomplete')
        for name in ('experience.json','economy-evaluation.json','feedback-audit.json'):read_json(episode/name)
    if sha(folder/'candidate.npz')!=rounds[-1]['checkpoint_sha256'] or sha(folder/'spend-candidate.npz')!=rounds[-1]['spend_sha256']:
        raise ValueError('Final pair differs from last completed round')
    initial=Path(settings['resume']) if settings.get('resume') else folder/'baseline.npz'
    if sha(initial)!=report['initial_candidate_sha256']:raise ValueError('Original input checkpoint changed')
    validate_network(folder/'candidate.npz',len(features({}, {'id':'none'})))
    validate_network(folder/'spend-candidate.npz',len(spend_features({},WAIT)))
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--config',type=Path,default=ROOT/'AI-Yeni-Model/ai-service/runtime.json');p.add_argument('--activate',action='store_true');args=p.parse_args()
    folder=args.run.resolve()
    with module().lock(ROOT/'AI-Test-Sahasi/training.lock'):
        report=validate(folder);config=read_json(args.config)
        if config['sha256']!=report['baseline_sha256']:raise ValueError('Live baseline changed; refuse automatic recovery')
        backup=folder/'report.before-registry-repair.json'
        if backup.exists():raise ValueError('A repair backup already exists; inspect rather than overwrite')
        shutil.copy2(folder/'report.json',backup)
        for i,row in enumerate(report['rounds']):
            if config.get('benchmark_suite'):
                row['benchmark_registration']=add(config['benchmark_suite'],args.config,folder.name+'/'+str(i),weights=folder/('checkpoint-%03d.npz'%i),spend=folder/('spend-checkpoint-%03d.npz'%i))
        report['repair']={'reason':report.pop('error'),'at_utc':datetime.now(timezone.utc).isoformat(),'retrained':False,'replayed_episode':False}
        report.update(status='complete',candidate_sha256=sha(folder/'candidate.npz'),source_checkpoint_unchanged=True,live_model_unchanged=True)
        write_json(folder/'report.json',report)
        if args.activate:
            try:
                report['activation']=activate(folder,args.config);report['activated']=bool(report['activation'].get('changed'))
                report['live_model_unchanged']=not report['activated']
            finally:write_json(folder/'report.json',report)
    print('Completed saved round finalized; retraining=false; activated='+str(report.get('activated',False)))

if __name__=='__main__':main()
