"""Fixed five-seed random masked-action baseline for the economy task."""
import argparse
import json
from pathlib import Path
from economy_common import ROOT,TASK,task_config,engine_path,init_csv,evaluate,write_config

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task',type=Path,default=TASK)
    p.add_argument('--output',type=Path,default=ROOT/'AI-Egitim/economy-random');args=p.parse_args()
    args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False)
    task=task_config(args.task);engine=str(engine_path())
    write_config(args.output/'run.json',{'policy':'random','task':task,'engine':engine,'training_performed':False,'activated':False})
    init_csv(args.output/'evaluation.csv')
    print(json.dumps(evaluate(task,args.output/'episodes',engine,args.output/'evaluation.csv')))

if __name__=='__main__':main()
