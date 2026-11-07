"""Unattended isolated OpenBFME match, with native fixed logic steps.

No assets/checkpoints bundled. No arguments delegate to the unchanged normal game.
"""
import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from match_pack import unpack,pack
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FACTIONS=('FactionMen','FactionElves','FactionDwarves','FactionWild','FactionMordor','FactionIsengard','FactionAngmar')

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path=Path(path);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');temp.replace(path)

def engine_path(value=None):
    if value:return Path(value).resolve()
    if os.environ.get('OPENBFME_ENGINE_PACKAGE'):return Path(os.environ['OPENBFME_ENGINE_PACKAGE']).resolve()
    state=ROOT/'AI-Motor-Guncellemeleri/engine-state.json'
    if state.exists():return Path(read(state)['directory'])
    raise ValueError('Supply --engine-package with your installed OpenBFME integration package')

def prepare(engine,runtime,model):
    for name in ('OpenBFME.exe','OpenBFME.console.exe','OpenBFME.pck','openbfme.windows.template_debug.x86_64.dll'):
        if not (engine/name).is_file():raise ValueError('Missing installed engine file: '+str(engine/name))
    entries=unpack((engine/'OpenBFME.pck').read_bytes())
    entries['scenes/game_normal.tscn']=entries['scenes/game.tscn']
    entries['scenes/game.tscn']=b'[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://scripts/simulation_match.gd" id="1"]\n[node name="SimulationMatch" type="Node3D"]\nscript = ExtResource("1")\n'
    entries['scripts/simulation_match.gd']=(HERE/'arena/simulation_match.gd').read_bytes()
    release='scripts/release/release.gd'
    if release in entries:
        text=entries[release].decode('utf-8');marker='func _ready() -> void:\n'
        if text.count(marker)!=1:raise ValueError('Release bootstrap changed; cannot safely isolate shared UI/logs')
        text=text.replace(marker,marker+'\tif OS.get_cmdline_user_args().has("--simulation-config"):\n\t\tset_process(false)\n\t\treturn\n',1)
        init='func _init() -> void:\n'
        if text.count(init)!=1:raise ValueError('Release init changed; cannot isolate user-data logs')
        text=text.replace(init,init+'\tif OS.get_cmdline_user_args().has("--simulation-config"): return\n',1)
        entries[release]=text.encode('utf-8')
    if model:
        if 'scripts/general_strategy_legacy.gd' not in entries:raise ValueError('Model-only integration is absent from engine package')
        entries['scripts/general_strategy.gd']=(HERE/'model_only_controller.gd').read_bytes()
        entries['scripts/ai_diagnostics.gd']=(HERE/'ai_diagnostics.gd').read_bytes()
        for p in (HERE/'team_ai').rglob('*'):
            if p.is_file() and p.suffix in ('.gd','.json'):entries['scripts/team_ai/'+p.relative_to(HERE/'team_ai').as_posix()]=p.read_bytes()
    else:
        # The result counter uses the same native filtered observer contract.
        entries['scripts/team_ai/contracts.gd']=(HERE/'team_ai/contracts.gd').read_bytes()
    (runtime/'OpenBFME.pck').write_bytes(pack(entries))
    for name in ('OpenBFME.exe','OpenBFME.console.exe','openbfme.windows.template_debug.x86_64.dll'):shutil.copy2(engine/name,runtime/name)
    return {'engine_executable_sha256':sha(engine/'OpenBFME.exe'),'native_sha256':sha(engine/'openbfme.windows.template_debug.x86_64.dll'),'base_pck_sha256':sha(engine/'OpenBFME.pck'),'harness_sha256':sha(HERE/'arena/simulation_match.gd'),'runtime_pck_sha256':sha(runtime/'OpenBFME.pck')}

@contextmanager
def inference(config_path,external_endpoint=None):
    if external_endpoint is not None:
        yield external_endpoint,{'controller':'external-gymnasium'};return
    if config_path is None:yield None,{};return
    # Import NumPy/model code ONLY for an explicit model controller.
    os.environ.setdefault('OPENBLAS_NUM_THREADS','1');os.environ.setdefault('OMP_NUM_THREADS','1')
    sys.path.insert(0,str(HERE/'training'));sys.path.insert(0,str(HERE/'service'))
    import numpy as np
    from decision_net import load_tactical_model
    from spend_policy import load_spend_model,legal_spend_options,spend_features
    from public_game_rules import PublicGameRules
    c=read(config_path)
    if c.get('model')!='openbfme-decision-net-v0':raise ValueError('Only the active NumPy model runtime is supported; recurrent PPO is not connected yet')
    for path,digest in [('weights','sha256'),('spend_weights','spend_sha256'),('game_rules','game_rules_sha256')]:
        value=Path(c[path]);value=value if value.is_absolute() else Path(config_path).resolve().parent/value;c[path]=str(value)
        if sha(value)!=c[digest]:raise ValueError('Pinned model/catalogue mismatch: '+path)
    model=load_tactical_model(c['weights']).ensure_factions();spend=load_spend_model(c['spend_weights']).ensure_factions();rules=PublicGameRules(c['game_rules'])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            code=200
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16*1024*1024:raise ValueError('Invalid observation size')
                body=json.loads(self.rfile.read(length));obs=body['observation'];choices=body['candidates'];purchases=legal_spend_options(body.get('production_options',[]),float(obs.get('money',0)))
                if not choices:raise ValueError('Missing tactical choices')
                rules.attach(obs,choices,purchases)
                selected=model.predict(obs,choices);scores,_=spend.for_faction(obs['faction']).forward(np.stack([spend_features(obs,p) for p in purchases]))
                answer={'candidate_id':selected['id'] if isinstance(selected,dict) else selected,'production_id':purchases[int(np.argmax(scores))]['id']}
                result={'done':True,'message':{'content':json.dumps(answer)}}
            except Exception as error:code=500;result={'error':str(error)}
            data=json.dumps(result).encode();self.send_response(code);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield 'http://127.0.0.1:%d/api/chat'%server.server_port,{k:c[k] for k in ('sha256','spend_sha256','game_rules_sha256')}
    finally:server.shutdown();server.server_close();thread.join(timeout=5)

def arguments(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--headless',action='store_true');p.add_argument('--time-scale',type=float,default=1.);p.add_argument('--duration',type=float,default=180.)
    p.add_argument('--faction1',choices=FACTIONS,default='FactionDwarves');p.add_argument('--faction2',choices=FACTIONS,default='FactionWild')
    p.add_argument('--factions',help='Optional six-faction 3v3 roster, first three allied')
    p.add_argument('--positions',help='Comma-separated map start indices; defaults to slot order')
    p.add_argument('--map',default='maps/map wor lostriand/map wor lostriand.map');p.add_argument('--seed',type=int,default=271026);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--runtime-cache',type=Path,help='Opt-in immutable package cache; fresh process for every match')
    p.add_argument('--engine-package',type=Path);p.add_argument('--bfme2',type=Path,default=Path(os.environ.get('BFME2_INSTALL','D:/Games/BFME2')));p.add_argument('--rotwk',type=Path,default=Path(os.environ.get('ROTWK_INSTALL','D:/Games/RotWK')))
    p.add_argument('--controllers',help='native/model per player (default all native)');p.add_argument('--model-config',type=Path);p.add_argument('--timeout',type=float,help='Wall-clock safety limit including engine loading')
    p.add_argument('--controller-endpoint',help='Explicit local Gymnasium controller; no model weights loaded')
    p.add_argument('--native-difficulty',choices=['easy','medium','hard','brutal'],default='brutal')
    p.add_argument('--controller-timeout',type=float,default=300.)
    a=p.parse_args(argv)
    if not math.isfinite(a.duration) or not .2<=a.duration<=86400 or not math.isclose(a.duration*5,round(a.duration*5),abs_tol=1e-8):p.error('duration must be a positive multiple of 0.2 simulation seconds')
    if not math.isfinite(a.time_scale) or not .01<=a.time_scale<=1000:p.error('time-scale must be 0.01..1000')
    if not 0<=a.seed<=2147483647:p.error('seed must be 0..2147483647')
    if a.timeout is not None and (not math.isfinite(a.timeout) or a.timeout<=0):p.error('timeout must be positive')
    if not math.isfinite(a.controller_timeout) or not 1<=a.controller_timeout<=86400:p.error('controller-timeout must be 1..86400')
    factions=a.factions.split(',') if a.factions else [a.faction1,a.faction2]
    if len(factions) not in (2,6) or any(f not in FACTIONS for f in factions):p.error('Supply two factions or a six-faction roster')
    controllers=a.controllers.split(',') if a.controllers else ['native']*len(factions)
    if len(controllers)!=len(factions) or any(c not in ('native','model') for c in controllers):p.error('One native/model controller per player required')
    if a.controller_endpoint:
        endpoint=re.fullmatch(r'http://127\.0\.0\.1:([0-9]{1,5})/api/chat',a.controller_endpoint)
        if endpoint is None or not 0<int(endpoint[1])<=65535:p.error('Controller endpoint must be an explicit localhost port /api/chat')
        if a.model_config or controllers.count('model')!=1:p.error('External controller requires exactly one model slot and no --model-config')
    if 'model' in controllers and not a.model_config and not a.controller_endpoint:p.error('model controller requires --model-config')
    if a.model_config and 'model' not in controllers:p.error('--model-config requires at least one model controller')
    try:positions=list(map(int,a.positions.split(','))) if a.positions else list(range(len(factions)))
    except ValueError:p.error('positions must be integers')
    if len(positions)!=len(factions) or len(set(positions))!=len(positions) or any(n<0 or n>7 for n in positions):p.error('Invalid or duplicate start positions')
    a.faction_list=factions;a.controller_list=controllers;a.position_list=positions
    return a

def run(a):
    start=time.perf_counter();out=a.out.resolve();out.parent.mkdir(parents=True,exist_ok=True)
    reservation=out.with_name(out.name+'.lock')
    # No global port, runtime folder, package mutation, lock or latest-result file.
    with reservation.open('x',encoding='utf-8') as lock:lock.write(str(os.getpid()))
    runtime=out.parent/(out.stem+'-runtime-'+uuid.uuid4().hex[:10]);runtime.mkdir()
    try:
        if out.exists():raise FileExistsError('Refusing to overwrite existing result: '+str(out))
        for folder in (a.bfme2,a.rotwk):
            if not folder.is_dir():raise ValueError('Retail install not found; provide --bfme2/--rotwk: '+str(folder))
        engine=engine_path(a.engine_package)
        if getattr(a,'runtime_cache',None):
            from runtime_cache import prepare_cached
            identity=prepare_cached(engine,runtime,'model' in a.controller_list,a.runtime_cache)
        else:identity=prepare(engine,runtime,'model' in a.controller_list)
        with inference(a.model_config,a.controller_endpoint) as (endpoint,model_identity):
            config={'out':str(out),'bfme2':str(a.bfme2.resolve()),'rotwk':str(a.rotwk.resolve()),'map':a.map,'seed':a.seed,'frames':round(a.duration*5),'time_scale':a.time_scale,'headless':a.headless,'factions':a.faction_list,'positions':a.position_list,'teams':[1,2] if len(a.faction_list)==2 else [1,1,1,2,2,2],'controllers':a.controller_list,'endpoint':endpoint}
            config['gymnasium']=bool(a.controller_endpoint)
            config['native_slot_state']={'easy':2,'medium':3,'hard':4,'brutal':5}[a.native_difficulty]
            config['controller_timeout']=a.controller_timeout
            path=runtime/'match-config.json';write(path,config)
            command=[str(runtime/'OpenBFME.console.exe')]
            if a.headless:command+=['--headless','--disable-render-loop']
            command+=['--audio-driver','Dummy','--','--no-update-check','--simulation-config',str(path)]
            env=dict(os.environ,OPENBFME_AI_LOG_ROOT=str(runtime));env.pop('OPENBFME_AI_TRAINING',None)
            with (out.parent/(out.name+'.engine.log')).open('w',encoding='utf-8') as log:
                process=subprocess.Popen(command,cwd=runtime,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' and a.headless else 0)
                try:code=process.wait(timeout=a.timeout or max(120.,60+3*a.duration/a.time_scale))
                except BaseException:
                    if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT)
                    else:process.kill()
                    process.wait(timeout=10);raise
            logtext=(out.parent/(out.name+'.engine.log')).read_text(encoding='utf-8',errors='replace')
            script_errors=len(re.findall(r'SCRIPT ERROR:',logtext))
            result=read(out) if out.exists() else {'schema':'rts-headless-match-v1','ok':False,'winner':None,'seed':a.seed,'players':[],'error':'Engine did not produce a result; see engine log'}
            if code or script_errors:result.update(ok=False,error=result.get('error','Engine/script failure'))
            result.update(identity=identity,model_identity=model_identity,process_exit_code=code,script_errors=script_errors,wall_seconds=time.perf_counter()-start,runtime_directory=str(runtime))
            write(out,result)
            return result
    except FileExistsError:
        raise
    except (Exception,KeyboardInterrupt) as error:
        result={'schema':'rts-headless-match-v1','ok':False,'error':str(error) or type(error).__name__,'winner':None,'seed':a.seed,'players':[],'wall_seconds':time.perf_counter()-start,'runtime_directory':str(runtime)};write(out,result)
        if isinstance(error,KeyboardInterrupt):raise
        return result
    finally:reservation.unlink(missing_ok=True)

def main(argv=None):
    argv=sys.argv[1:] if argv is None else argv
    if not argv:
        engine=engine_path();return subprocess.call([str(engine/'OpenBFME.exe')],cwd=engine)
    a=arguments(argv);result=run(a);print(json.dumps(result,ensure_ascii=False));return 0 if result['ok'] else 1
if __name__=='__main__':sys.exit(main())
