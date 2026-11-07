"""Hard-bounded two-minute smoke only; never starts the default 200k budget."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--parallel',type=int,default=8)
    p.add_argument('--light-workers',action='store_true');p.add_argument('--reuse-package',action='store_true')
    p.add_argument('--persistent-games',action='store_true');args=p.parse_args()
    started=time.monotonic();output=args.output.resolve()
    if output.exists():p.error('Use a new smoke output directory')
    output.parent.mkdir(parents=True,exist_ok=True)
    logfile=output.with_suffix('.process.log')
    with logfile.open('x',encoding='utf-8') as log:
        command=[sys.executable,str(Path(__file__).with_name('train_economy.py')),'--smoke','--parallel',str(args.parallel),'--output',str(output)]
        command += [flag for flag,enabled in [('--light-workers',args.light_workers),('--reuse-package',args.reuse_package),('--persistent-games',args.persistent_games)] if enabled]
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:code=proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            if os.name=='nt':subprocess.run([str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/taskkill.exe'),'/PID',str(proc.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT)
            else:proc.kill()
            proc.wait(timeout=10);code=124
    row={'process_exit_code':code,'hard_wall_seconds':time.monotonic()-started,'wall_limit_seconds':120,'log':str(logfile)}
    if (output/'run.json').exists():row['run']=json.loads((output/'run.json').read_text(encoding='utf-8'))
    row['passed']=code==0 and row.get('run',{}).get('optimizer_updates',0)>=1 and row.get('run',{}).get('transitions',0)>=200
    output.mkdir(exist_ok=True);(output/'smoke-verification.json').write_text(json.dumps(row,indent=2),encoding='utf-8')
    print(json.dumps(row,ensure_ascii=False));return 0 if row['passed'] else 1

if __name__=='__main__':sys.exit(main())
