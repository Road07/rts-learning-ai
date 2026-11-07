"""Bounded 240-second regression: exercise episode rollover, not full training."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def summarize(output,code,elapsed):
    status=json.loads((output/'run.json').read_text(encoding='utf-8')) if (output/'run.json').exists() else {}
    results=list((output/'training-episodes').glob('worker-*/e-*/result.json'))
    completed=cancelled=failed=0
    steps=0
    for path in results:
        row=json.loads(path.read_text(encoding='utf-8'))
        reward=path.with_name('reward.jsonl')
        records=[json.loads(line) for line in reward.read_text(encoding='utf-8').splitlines()] if reward.exists() else []
        transitions=[record for record in records if record.get('event')=='step'];steps+=len(transitions)
        if row.get('ok'):completed+=1
        # After a successful finite learn(), close() cancels the unfinished
        # HTTP request with 503. This is not a completed or failed rollout.
        elif (code==0 and status.get('status')=='complete' and transitions
              and not transitions[-1].get('terminated') and not transitions[-1].get('truncated')
              and row.get('error')=='Inference failed: [0, 503]'):
            cancelled+=1
        else:failed+=1
    report=dict(exit_code=code,wall_seconds=elapsed,wall_budget=240,completed_episodes=completed,
                failed_episodes=failed,cancelled_at_training_budget=cancelled,recorded_transitions=steps,run=status)
    report['passed']=(code==0 and status.get('transitions',0)>=200 and steps==status.get('transitions')
                      and completed>status.get('parallel',0) and failed==0)
    return report


def main():
    root=Path(__file__).resolve().parents[4]
    output=root/'AI-Test-Sahasi'/('eco-fix-'+time.strftime('%H%M%S'))
    started=time.monotonic()
    with output.with_suffix('.log').open('x',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('train_economy.py')),
                                  '--timesteps','200','--parallel','8','--output',str(output)],stdout=log,stderr=subprocess.STDOUT)
        try:code=process.wait(timeout=240)
        except subprocess.TimeoutExpired:
            kill=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/taskkill.exe'
            subprocess.run([str(kill),'/PID',str(process.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT,timeout=15)
            process.wait(timeout=10);code=124
    report=summarize(output,code,time.monotonic()-started)
    output.mkdir(exist_ok=True)
    (output/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(output),**{k:v for k,v in report.items() if k!='run'}}),flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
