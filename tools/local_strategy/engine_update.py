"""Follow locally installed OpenBFME releases; rebuild the AI fork before activation.

No stock DLL is substituted for the AI bridge. Immutable engine packages and a
separate pointer leave model weights, running games and official installs intact.
"""
import argparse
import difflib
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
WORK=ROOT/'AI-Motor-Guncellemeleri'
SOURCE=WORK/'source'
OFFICIAL=Path.home()/'AppData/Roaming/OpenBFMELauncher'
STATE=WORK/'engine-state.json'

def git_executable():
    found=shutil.which('git')
    if found:return found
    # The GUI can inherit an older PATH than the shell. Use the installed local
    # runtime's Git without hardcoding a versioned WindowsApps directory.
    for path in (Path(sys.executable).parent.parent/'native/git/cmd/git.exe',
                 Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe'):
        if path.is_file():return str(path)
    raise FileNotFoundError('Git bulunamadı; motor güncellemesi için kurulu Git gerekli')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)


def release_order(tag):
    match=re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)(?:-nightly\.(\d+))?',tag)
    if not match:raise ValueError('Unsupported version: '+tag)
    major,minor,patch,night=match.groups()
    return (int(major),int(minor),int(patch),0 if night else 1,int(night or 0))


def installed():
    selected=''
    if (OFFICIAL/'state.cfg').exists():
        match=re.search(r'^selected="([^"\r\n]*)"', (OFFICIAL/'state.cfg').read_text(encoding='utf-8'),re.M)
        if match:selected=match[1]
    choices=[]
    for path in (OFFICIAL/'versions').glob('*'):
        if not (path/'manifest.json').is_file() or not (path/'game/VERSION').is_file():continue
        try:choices.append((release_order(path.name),path))
        except ValueError:continue
    if selected:
        chosen=[p for _,p in choices if p.name==selected]
        return chosen[0] if chosen else None
    return max(choices)[1] if choices else None


def verify_release(path):
    manifest=read(path/'manifest.json')
    if manifest.get('version')!=path.name or manifest.get('repo')!='Open-BFME/openbfme-godot':raise ValueError('Release identity mismatch')
    commit=manifest.get('commit','')
    if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('Release commit missing')
    if ('commit '+commit) not in (path/'game/VERSION').read_text(encoding='utf-8'):raise ValueError('VERSION commit mismatch')
    inventory=manifest['assets']['game']['windows-x64']['files']
    game=(path/'game').resolve()
    for name,info in inventory.items():
        file=(game/name).resolve()
        if not file.is_relative_to(game) or not file.is_file():raise ValueError('Incomplete release file: '+name)
        if file.stat().st_size!=info['size'] or digest(file)!=info['sha256']:raise ValueError('Release file integrity mismatch: '+name)
    return commit,inventory


def git(*args,check=True):
    return subprocess.run([git_executable(),'-c','filter.lfs.process=','-c','filter.lfs.smudge=','-c','filter.lfs.required=false','-C',str(SOURCE),*args],check=check,stdout=subprocess.PIPE,stderr=subprocess.PIPE)


def merge_text(current,base,changed,scratch):
    current,base,changed=(data.replace(b'\r\n',b'\n') for data in (current,base,changed))
    if current==base:return changed
    if changed==base or current==changed:return current
    scratch.mkdir(parents=True,exist_ok=True)
    names=[scratch/n for n in ['current.txt','base.txt','ai.txt']]
    for p,b in zip(names,[current,base,changed]):p.write_bytes(b)
    merged=subprocess.run([git_executable(),'merge-file','-p',*map(str,names)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if merged.returncode:raise RuntimeError('AI script/source merge requires review')
    return merged.stdout


def merge_game_hooks(current,base,changed):
    """The two reviewed additive hooks; retain the new upstream game script."""
    old=base.decode('utf-8').splitlines(keepends=True)
    custom=changed.decode('utf-8').splitlines(keepends=True)
    fresh=current.decode('utf-8')
    for kind,a,b,c,d in difflib.SequenceMatcher(None,old,custom,autojunk=False).get_opcodes():
        if kind=='equal':continue
        if kind!='insert':raise RuntimeError('Unreviewed game script modification')
        addition=''.join(custom[c:d])
        if a>0 and old[a-1]=='func _process(delta: float) -> void:\n' and 'general_ai_driver' in addition:
            anchor=old[a-1]
            if fresh.count(anchor)!=1:raise RuntimeError('Game tick hook changed')
            fresh=fresh.replace(anchor,anchor+addition)
        elif a<len(old) and old[a]=='\tvar spec := {\n' and '--general-matrix' in addition:
            anchor=old[a]
            if fresh.count(anchor)!=1:raise RuntimeError('Game setup hook changed')
            fresh=fresh.replace(anchor,addition+anchor)
        else:raise RuntimeError('Unreviewed game hook insertion')
    return fresh.encode('utf-8')


def import_ai_changes():
    """Reconcile subsequent local AI edits against their last imported contents."""
    baseline_path=WORK/'ai-source-baseline.json';baseline=read(baseline_path)
    canonical=ROOT/'ai-mod-source'
    names=set(baseline)
    changed=subprocess.check_output([git_executable(),'-C',str(canonical),'diff','HEAD','--name-only','--','engine']).decode().splitlines()
    names.update(changed)
    pending={}
    for name in sorted(names):
        incoming=canonical/name;target=SOURCE/name
        if not incoming.is_file():continue
        text=incoming.read_text(encoding='utf-8')
        if name in baseline and baseline[name]==text:continue
        if name in baseline:base=baseline[name].encode()
        else:
            old=subprocess.run([git_executable(),'-C',str(canonical),'show','HEAD:'+name],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            base=old.stdout if old.returncode==0 else b''
        ours=target.read_bytes() if target.is_file() else b''
        pending[name]=(text,merge_text(ours,base,text.encode(),WORK/'merge'))
    for name,(text,merged) in pending.items():
        path=SOURCE/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(merged);baseline[name]=text
        git('add','--',name)
    if pending:git('-c','user.name=RTS AI integration','-c','user.email=local@invalid','commit','-m','Import local AI integration changes','--','engine')
    write(baseline_path,baseline)


def package(release,inventory,commit):
    from make_rescue_scenario import pck_entries,pack
    # The baseline is the official package the original mod was built against.
    base=dict(pck_entries((ROOT/'OpenBFME.pck').read_bytes()))
    fresh=dict(pck_entries((release/'game/OpenBFME.pck').read_bytes()))
    integration=digest(ROOT/'AI-Yeni-Model/OpenBFME.pck')[:12]
    key=commit[:12]+'-'+git('rev-parse','HEAD').stdout.decode().strip()[:12]+'-'+integration
    dest=WORK/'packages'/key;dest.mkdir(parents=True,exist_ok=True)
    for name in inventory:
        if name in ['OpenBFME.pck','openbfme.windows.template_debug.x86_64.dll'] or 'Launcher' in name:continue
        source=release/'game'/name;target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for label,ai_path,output in [('arena',ROOT/'AI-Genel/OpenBFME.pck','arena-base.pck'),('game',ROOT/'AI-Yeni-Model/OpenBFME.pck','OpenBFME.pck')]:
        entries=dict(fresh)
        for name,data in pck_entries(ai_path.read_bytes()):
            if name not in base:entries[name]=data
            elif data!=base[name]:
                entries[name]=merge_game_hooks(fresh[name],base[name],data) if name=='scripts/game.gd' else merge_text(fresh[name],base[name],data,WORK/'merge')
        (dest/output).write_bytes(pack(list(entries.items())))
    shutil.copy2(SOURCE/'godot/bin/openbfme.windows.template_debug.x86_64.dll',dest/'openbfme.windows.template_debug.x86_64.dll')
    return dest


def active():
    if not STATE.is_file():return None
    state=read(STATE);path=Path(state['directory'])
    for name,expected in state['files'].items():
        if not (path/name).is_file() or digest(path/name)!=expected:raise ValueError('Managed engine damaged: '+name)
    return state


def start_background():
    WORK.mkdir(exist_ok=True)
    # A job runs only in response to local installed versions/source changes;
    # no update downloads or model training are started here.
    with (WORK/'auto-update.log').open('a',encoding='utf-8') as log:
        subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--sync'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)


def sync(validation_case='mechanics'):
    WORK.mkdir(exist_ok=True)
    with (WORK/'update.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        release=installed()
        if release is None:return
        commit,inventory=verify_release(release)
        if not (SOURCE/'.git').exists() or not (WORK/'ai-source-baseline.json').exists():raise RuntimeError('AI engine integration source is not initialized')
        import_ai_changes()
        previous=active()
        source_head=git('rev-parse','HEAD').stdout.decode().strip()
        integration=digest(ROOT/'AI-Yeni-Model/OpenBFME.pck')
        if previous and previous['upstream_commit']==commit and previous['integration_commit']==source_head and previous.get('integration_package')==integration:
            write(WORK/'update-status.json',{'status':'ready','version':previous['version'],'reason':'already_current'})
            return
        if previous and release_order(release.name)<release_order(previous['version']):
            write(WORK/'update-status.json',{'status':'retained','reason':'older_launcher_selection','version':previous['version']});return
        validation_hash=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((HERE/'arena').glob('*.gd')))+(HERE/'arena/run.py').read_bytes()).hexdigest()
        attempt={'requested_version':release.name,'input_source_commit':source_head,'integration_package':integration,'updater_sha256':digest(Path(__file__)),'validation_case':validation_case,'validation_sha256':validation_hash}
        status_path=WORK/'update-status.json'
        status=read(status_path) if status_path.exists() else {}
        if status.get('status')=='failed' and all(status.get(k)==v for k,v in attempt.items()):return
        write(status_path,dict(attempt,status='preparing'))
        if git('merge-base','--is-ancestor',commit,'HEAD',check=False).returncode:
            git('fetch','--depth','256','https://github.com/Open-BFME/openbfme-godot.git',commit)
            merged=git('-c','user.name=RTS AI integration','-c','user.email=local@invalid','merge','--no-edit',commit,check=False)
            if merged.returncode:
                if (SOURCE/'.git/MERGE_HEAD').exists():git('merge','--abort',check=False)
                raise RuntimeError('New OpenBFME source conflicts with AI integration; previous engine retained')
        build=SOURCE/'tools/build_ai_engine.cmd'
        required=git('ls-tree','HEAD','engine/thirdparty/godot-cpp').stdout.decode().split()[2]
        actual=subprocess.check_output([git_executable(),'-C',str((SOURCE/'engine/thirdparty/godot-cpp').resolve()),'rev-parse','HEAD']).decode().strip()
        if required!=actual:raise RuntimeError('Godot binding revision changed; previous engine retained')
        shutil.copy2(ROOT/'ai-mod-source/tools/build_ai_engine.cmd',build)
        with (WORK/'build.log').open('w',encoding='utf-8') as log:
            subprocess.run(['cmd','/c',str(build)],check=True,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,AI_BUILD_PARALLEL='2'))
        dest=package(release,inventory,commit)
        # Exactly one bounded private mechanics check. Never activate model weights.
        env=dict(os.environ,OPENBFME_ENGINE_CANDIDATE=str(dest))
        checkdir=WORK/'checks'/dest.name
        checkdir.mkdir(parents=True,exist_ok=True)
        config=read(ROOT/'AI-Yeni-Model/ai-service/runtime.json')
        config['arena_sim_frames']=120
        if validation_case=='benchmark':config.update(arena_benchmark=True,benchmark_team=1)
        config['arena_engine_directory']=str(dest)
        write(checkdir/'runtime.json',config)
        episode=checkdir/('episode-'+str(time.time_ns()))
        with (ROOT/'AI-Test-Sahasi/training.lock').open('a+b') as guard:
            guard.seek(0)
            if not guard.read(1):guard.write(b'0');guard.flush()
            guard.seek(0)
            try:msvcrt.locking(guard.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:
                write(WORK/'update-status.json',{'status':'deferred','reason':'training_is_open'});return
            result=subprocess.run([sys.executable,str(ROOT/'AI-Yeni-Model/ai-service/host.py'),'--config',str(checkdir/'runtime.json'),'--arena','opening' if validation_case=='benchmark' else 'middle','--arena-case','baseline' if validation_case=='benchmark' else validation_case,'--seconds','6','--episode-dir',str(episode),'--episode-mode','evaluate'],env=env,cwd=ROOT,timeout=150)
        if result.returncode:raise RuntimeError('New engine mechanics check failed; previous engine retained')
        report_file=episode/'arena'/('opening.json' if validation_case=='benchmark' else 'middle.json')
        report=read(report_file)
        if not report.get('ok') or report.get('script_errors'):raise RuntimeError('New engine mechanics report failed')
        state={'version':release.name,'upstream_commit':commit,'integration_commit':git('rev-parse','HEAD').stdout.decode().strip(),'integration_package':integration,'directory':str(dest),'files':{name:digest(dest/name) for name in ['OpenBFME.exe','OpenBFME.console.exe','OpenBFME.pck','arena-base.pck','openbfme.windows.template_debug.x86_64.dll']},'validation':str(report_file)}
        write(STATE,state);write(WORK/'update-status.json',{'status':'ready','version':release.name})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--sync',action='store_true');parser.add_argument('--validation-case',choices=['mechanics','human-log','benchmark'],default='mechanics');args=parser.parse_args()
    if args.sync:
        try:sync(args.validation_case)
        except Exception as error:
            status=read(WORK/'update-status.json') if (WORK/'update-status.json').exists() else {}
            write(WORK/'update-status.json',dict(status,status='failed',error=str(error),previous_engine_retained=True));print(str(error),flush=True);sys.exit(1)
