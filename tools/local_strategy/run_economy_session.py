"""One owned native process, isolated fresh GameWorld per episode."""
import os
from pathlib import Path
import subprocess
import sys
from run_match import arguments,engine_path,prepare,write


def main():
    # --session-dir is consumed here; all match flags keep the standard parser.
    argv=sys.argv[1:];index=argv.index('--session-dir');directory=Path(argv[index+1]).resolve()
    del argv[index:index+2];args=arguments(argv);directory.mkdir(parents=True,exist_ok=False)
    runtime=directory/'runtime';runtime.mkdir();engine=engine_path(args.engine_package)
    if args.runtime_cache:
        from runtime_cache import prepare_cached
        identity=prepare_cached(engine,runtime,True,args.runtime_cache)
    else:identity=prepare(engine,runtime,True)
    config={'out':str(args.out.resolve()),'bfme2':str(args.bfme2.resolve()),'rotwk':str(args.rotwk.resolve()),
            'map':args.map,'seed':args.seed,'frames':round(args.duration*5),'time_scale':args.time_scale,'headless':True,
            'factions':args.faction_list,'positions':args.position_list,'teams':[1,2] if len(args.faction_list)==2 else [1,1,1,2,2,2],
            'controllers':args.controller_list,'endpoint':args.controller_endpoint,'gymnasium':True,
            'native_slot_state':{'easy':2,'medium':3,'hard':4,'brutal':5}[args.native_difficulty],
            'controller_timeout':args.controller_timeout,'session_mode':True,'session_command':str(directory/'command.json')}
    write(directory/'metadata.json',{'identity':identity,'base_config':config})
    path=directory/'initial.json';write(path,config)
    command=[str(runtime/'OpenBFME.console.exe'),'--headless','--disable-render-loop','--audio-driver','Dummy',
             '--','--no-update-check','--simulation-config',str(path)]
    environment=dict(os.environ,OPENBFME_AI_LOG_ROOT=str(directory));environment.pop('OPENBFME_AI_TRAINING',None)
    with (directory/'engine.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,cwd=runtime,env=environment,stdout=log,stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:code=process.wait()
        except BaseException:
            if os.name=='nt':subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/taskkill.exe'),'/PID',str(process.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT)
            else:process.kill()
            process.wait(timeout=10);raise
    write(directory/'exit.json',{'process_exit_code':code})
    return code


if __name__=='__main__':raise SystemExit(main())
