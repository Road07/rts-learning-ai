"""One isolated native match, paused at each externally controlled decision."""
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time
import uuid
from run_match import HERE,ROOT,engine_path,read

@dataclass
class Exchange:
    snapshot: dict
    reply: queue.Queue

class NativeMatchBackend:
    def __init__(self,*,factions,agent_index,map_name,duration,time_scale,workspace_root,
                 engine_package=None,timeout=120.,episode_timeout=3600.,bfme2='D:/Games/BFME2',rotwk='D:/Games/RotWK',
                 native_difficulty='brutal',positions=None,runtime_cache=None):
        self.settings=dict(factions=list(factions),agent_index=agent_index,map_name=map_name,duration=duration,time_scale=time_scale,
                           engine_package=str(engine_path(engine_package)),bfme2=str(bfme2),rotwk=str(rotwk),
                           native_difficulty=native_difficulty,positions=positions)
        self.workspace_root=Path(workspace_root);self.timeout=timeout;self.episode_timeout=episode_timeout
        self.runtime_cache=runtime_cache
        self.process=None;self.server=None;self.thread=None;self.log=None;self.current=None;self.result=None
        self.stop=threading.Event();self.incoming=queue.Queue(maxsize=1)

    def reset(self,seed):
        # Retry only startup, before any transition is returned. Reuse the exact
        # seed, never turn a failed mid-episode step into synthetic experience.
        for attempt in range(2):
            try:return self._reset_once(seed)
            except (RuntimeError,TimeoutError) as error:
                self.close()
                print('Native startup failed (attempt %d/2, seed %s): %s' % (attempt+1,seed,error),flush=True)
                if attempt:raise

    def _reset_once(self,seed):
        self.close();self.stop=threading.Event();self.incoming=queue.Queue(maxsize=1);self.result=None
        # Keep nested native DLL paths below Windows' loader path limit.
        self.directory=self.workspace_root/('e-'+uuid.uuid4().hex[:12])
        if os.name=='nt' and len(str(self.directory.resolve()/'result-runtime-0123456789'/'bin'/'openbfme.windows.template_debug.x86_64.dll'))>=260:
            raise ValueError('Output path too long for native Windows DLL loading; choose a shorter workspace_root')
        self.directory.mkdir(parents=True,exist_ok=False);self.result_path=self.directory/'result.json'
        backend=self
        # Retain this episode's objects even if a backend is explicitly reused.
        # A cancelled old HTTP handler can never enqueue into a later reset.
        episode_stop=self.stop;episode_incoming=self.incoming
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*unused):pass
            def do_POST(self):
                code=200
                try:
                    if self.path!='/api/chat':raise ValueError('Unknown route')
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=16*1024*1024:raise ValueError('Invalid request size')
                    payload=json.loads(self.rfile.read(length))
                    if not isinstance(payload,dict) or not isinstance(payload.get('observation'),dict):raise ValueError('Missing observation')
                    exchange=Exchange(payload,queue.Queue(maxsize=1))
                    episode_incoming.put(exchange,timeout=backend.timeout)
                    deadline=time.monotonic()+backend.timeout
                    while not episode_stop.is_set():
                        try:answer=exchange.reply.get(timeout=.1);break
                        except queue.Empty:
                            if time.monotonic()>deadline:raise TimeoutError('Gym agent did not supply an action')
                    else:raise RuntimeError('Environment closed')
                    response={'done':True,'message':{'content':json.dumps(answer)}}
                except Exception as error:
                    code=503;response={'error':str(error)}
                raw=json.dumps(response,separators=(',',':')).encode()
                try:
                    self.send_response(code);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
                except (OSError,ConnectionError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.05},daemon=True);self.thread.start()
        s=self.settings;controllers=['native']*len(s['factions']);controllers[s['agent_index']]='model'
        cmd=[sys.executable,str(HERE/'run_match.py'),'--headless','--duration',str(s['duration']),
             '--time-scale',str(s['time_scale']),'--map',s['map_name'],'--seed',str(seed),'--out',str(self.result_path),
             '--factions',','.join(s['factions']),'--controllers',','.join(controllers),
             '--controller-endpoint','http://127.0.0.1:%d/api/chat'%self.server.server_port,
             '--engine-package',s['engine_package'],'--bfme2',s['bfme2'],'--rotwk',s['rotwk'],'--timeout',str(self.episode_timeout)]
        cmd+=['--native-difficulty',s['native_difficulty']]
        cmd+=['--controller-timeout',str(self.timeout+30)]
        if self.runtime_cache is not None:cmd+=['--runtime-cache',str(self.runtime_cache)]
        if s['positions'] is not None:cmd+=['--positions',','.join(map(str,s['positions']))]
        cmd=self.launch_command(cmd)
        self.log=(self.directory/'bridge.log').open('w',encoding='utf-8')
        try:
            self.process=subprocess.Popen(cmd,cwd=ROOT,stdout=self.log,stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,start_new_session=os.name!='nt')
            return self._wait(timeout=min(self.timeout,60.))
        except BaseException:self.close();raise

    def launch_command(self,cmd):return cmd

    def _wait(self,timeout=None):
        deadline=time.monotonic()+(self.timeout if timeout is None else timeout)
        while time.monotonic()<deadline:
            try:
                self.current=self.incoming.get(timeout=.05)
                return {'snapshot':self.current.snapshot,'done':False}
            except queue.Empty:pass
            if self.process.poll() is not None:
                self.result=read(self.result_path) if self.result_path.is_file() else {}
                if self.process.returncode or not self.result.get('ok') or 'gym_final' not in self.result:
                    raise RuntimeError('Native Gym match failed: %s; exit=%s; logs=%s' % (self.result.get('error','Unknown error'),self.result.get('process_exit_code'),self.directory))
                return {'snapshot':self.result['gym_final'],'done':True,'reason':self.result['end_reason']}
        raise TimeoutError('Native Gym match did not reach the next decision: '+str(self.directory))

    def step(self,answer):
        if self.current is None:raise RuntimeError('No pending native decision')
        exchange=self.current;self.current=None;exchange.reply.put_nowait(answer)
        try:return self._wait()
        except BaseException:self.close();raise

    def close(self):
        self.stop.set();self.current=None
        if self.process is not None:
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                if os.name=='nt':
                    kill=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/taskkill.exe'
                    subprocess.run([str(kill),'/PID',str(self.process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                else:os.killpg(self.process.pid,signal.SIGTERM)
                self.process.wait(timeout=10)
            self.process=None
        if self.server is not None:self.server.shutdown();self.server.server_close();self.server=None
        if self.thread is not None:self.thread.join(timeout=2);self.thread=None
        if self.log is not None:self.log.close();self.log=None
        # These four generated files cost ~123 MiB per episode. Keep results,
        # configs and diagnostics; remove only private, reproducible binaries.
        if hasattr(self,'directory'):
            episode=self.directory.resolve()
            for runtime in episode.glob('result-runtime-*'):
                if runtime.resolve().parent!=episode or runtime.is_symlink():continue
                for name in ('OpenBFME.exe','OpenBFME.console.exe','OpenBFME.pck','openbfme.windows.template_debug.x86_64.dll'):
                    try:(runtime/name).unlink(missing_ok=True)
                    except OSError:pass
