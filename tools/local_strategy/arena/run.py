"""Build and run the isolated, bounded 3v3 AI arena from current local sources."""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from make_rescue_scenario import ROOT, pack, pck_entries, Mount

DEST = ROOT / 'AI-Test-Sahasi'
ALIASES = {'baslangic':'opening','orta':'middle','son':'late','hepsi':'all'}

def prepare(config):
    DEST.mkdir(exist_ok=True)
    entries = dict(pck_entries((ROOT/'AI-Genel/OpenBFME.pck').read_bytes()))
    # Always use current source scripts, rather than a possibly stale deployed controller.
    for name in ['general_strategy.gd','strategic_support.gd','combat_policy.gd','rescue_order_policy.gd','human_training_log.gd']:
        entries['scripts/'+name] = (HERE.parent/name).read_bytes()
    for path in (HERE.parent/'team_ai').rglob('*'):
        if path.suffix in ['.gd','.json']:
            entries['scripts/team_ai/'+path.relative_to(HERE.parent/'team_ai').as_posix()] = path.read_bytes()
    driver=entries['scripts/general_strategy.gd'].decode('utf-8')
    driver=driver.replace('func request_plan(bot: Dictionary, frame: int) -> void:\n', 'func request_plan(bot: Dictionary, frame: int) -> void:\n\tif OS.get_cmdline_user_args().has("--arena-model=off"): return\n')
    entries['scripts/general_strategy.gd']=driver.encode('utf-8')
    if os.environ.get('OPENBFME_AI_BACKEND') == 'decision_net_v0':
        from decision_trial import patch_entries
        patch_entries(entries)
    mount = Mount('D:/Games/RotWK','D:/Games/BFME2')
    templates = re.findall(r'(?m)^PlayerTemplate\s+(\w+)',mount.get(r'data\ini\playertemplate.ini').decode('latin1'))
    config['template_indices'] = {name:templates.index(name) for name in config['factions']}
    entries['data/arena.json'] = json.dumps(config,ensure_ascii=False).encode('utf-8')
    entries['scripts/arena.gd'] = (HERE/'arena.gd').read_bytes()
    entries['scripts/arena_competitive_checks.gd'] = (HERE/'competitive_checks.gd').read_bytes()
    entries['scripts/support_dispatch_checks.gd'] = (HERE/'support_dispatch_checks.gd').read_bytes()
    entries['scripts/model_access_checks.gd'] = (HERE/'model_access_checks.gd').read_bytes()
    entries['scenes/game.tscn'] = b'[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://scripts/arena.gd" id="1"]\n[node name="Arena" type="Node3D"]\nscript = ExtResource("1")\n'
    (DEST/'OpenBFME.pck').write_bytes(pack(list(entries.items())))
    for name in ['OpenBFME.exe','OpenBFME.console.exe']:
        if not (DEST/name).exists(): shutil.copy2(ROOT/name,DEST/name)
    native = ROOT/'ai-mod-source/godot/bin/openbfme.windows.template_debug.x86_64.dll'
    shutil.copy2(native,DEST/native.name)
    source = (ROOT/'AI-Genel/ai-mod/data/ini/default/skirmishaidata.ini').read_bytes().decode('latin1')
    if os.environ.get('OPENBFME_AI_BACKEND') == 'decision_net_v0':
        source = source.replace('EnhancedCounterProduction = Yes', 'EnhancedCounterProduction = Yes\n\tClassicOpening = Yes')
    for stage, values in config['stages'].items():
        ini = source
        for key,value in [('Rush',values['rush_duration']),('MidGame',values['mid_duration'])]:
            ini, count = re.subn(r'(PhaseDuration_'+key+r'\s*=\s*)[0-9.]+',lambda m:m[1]+str(value),ini)
            if count < 7: raise RuntimeError('Missing phase timing fields: '+key)
        path = DEST/'mods'/stage/'data/ini/default/skirmishaidata.ini'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(ini.encode('latin1'))
    return {'native_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),'package_sha256':hashlib.sha256((DEST/'OpenBFME.pck').read_bytes()).hexdigest()}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',nargs='?',default='opening')
    parser.add_argument('--case',choices=['baseline','pressure','counters','tunnels','hero','siege','team','human-log','sequence','production','access'],default='baseline')
    parser.add_argument('--seconds',type=float,default=6)
    parser.add_argument('--speed',type=float,default=4)
    parser.add_argument('--seed',type=int)
    parser.add_argument('--output-dir',type=Path,help='Private report directory for a training episode.')
    parser.add_argument('--view',action='store_true')
    parser.add_argument('--screenshot',action='store_true',help='Save a rendered arena/HUD image and exit after the short timer.')
    parser.add_argument('--factions',help='Six comma-separated canonical faction names; first three are team 1.')
    parser.add_argument('--model',choices=['on','off'],default='off')
    args=parser.parse_args()
    args.stage=ALIASES.get(args.stage,args.stage)
    if args.stage not in ['opening','middle','late','all']: parser.error('stage: baslangic/orta/son/hepsi')
    if not 1 <= args.seconds <= 1800 or not 0.25 <= args.speed <= 16: parser.error('seconds: 1..1800; speed: 0.25..16')
    if (args.view or args.screenshot) and args.stage=='all': parser.error('View one stage at a time.')
    config=json.loads((HERE/'scenarios.json').read_text(encoding='utf-8'))
    if args.seed is not None: config['seed']=args.seed
    if args.factions:
        config['slots']=args.factions.split(',')
        if len(config['slots'])!=6 or any(f not in config['factions'] for f in config['slots']): parser.error('Supply six known factions.')
    identity=prepare(config)
    run_dir=args.output_dir.resolve() if args.output_dir else DEST/'results'/(time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid()))
    run_dir.mkdir(parents=True)
    stages=list(config['stages']) if args.stage=='all' else [args.stage]
    summaries=[]
    for stage in stages:
        report=run_dir/(stage+'.json')
        command=[str(DEST/'OpenBFME.console.exe')]
        if not args.view and not args.screenshot: command+=['--headless']
        command+=['--','--no-update-check','-mod',str(DEST/'mods'/stage),'--arena-stage='+stage,'--arena-case='+args.case,'--arena-seconds='+str(args.seconds),'--arena-speed='+str(args.speed),'--arena-model='+args.model,'--arena-report='+str(report)]
        if args.view: command+=['--arena-view']
        if args.screenshot: command+=['--arena-view','--arena-screenshot='+str(run_dir/(stage+'.png'))]
        print('ARENA '+stage+' / '+args.case,flush=True)
        with (run_dir/(stage+'.log')).open('w',encoding='utf-8') as log:
            process=subprocess.Popen(command,cwd=DEST,stdout=log,stderr=subprocess.STDOUT)
            try:
                code=process.wait(timeout=None if args.view else 55+args.seconds)
            except subprocess.TimeoutExpired:
                # The console launcher owns a child game executable on Windows.
                if os.name=='nt': subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=log,stderr=subprocess.STDOUT)
                else: process.kill()
                process.wait(timeout=10)
                code=124
        result=json.loads(report.read_text(encoding='utf-8')) if report.exists() else {'ok':False,'error':'No report (see log)','stage':stage}
        log_text=(run_dir/(stage+'.log')).read_text(encoding='utf-8',errors='replace')
        result['script_errors']=len(re.findall('SCRIPT ERROR:',log_text))
        result['model_backend'] = os.environ.get('OPENBFME_AI_BACKEND', 'model' if args.model == 'on' else 'off')
        result.update(identity)
        result['exit_code']=code
        result['ok']=bool(result.get('ok')) and code==0 and result['script_errors']==0
        if args.case == 'human-log':
            from human_log_checks import check
            result['human_logging_validation'] = check(DEST, result)
            result['ok'] = result['ok'] and result['human_logging_validation']['ok']
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        summaries.append(result)
        print(stage+': '+('PASS' if result['ok'] else 'FAIL')+' - '+str(report),flush=True)
    summary={'ok':all(r['ok'] for r in summaries),'scope':'Fixture/runtime smoke checks, not proof that all AI behaviors passed. Model off skips HTTP only.','results':summaries}
    (run_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (DEST/'latest-result.txt').write_text(str(run_dir),encoding='utf-8')
    return 0 if summary['ok'] else 1

if __name__=='__main__': sys.exit(main())
