"""Persistent native process, never reuses a gameplay GameWorld or controller."""
from pathlib import Path
import queue
import time
import uuid
from gym_bridge import NativeMatchBackend
from run_match import HERE,read,write


class SessionMatchBackend(NativeMatchBackend):
    def launch_command(self,cmd):
        self.session_directory=self.workspace_root/('s-'+uuid.uuid4().hex[:10])
        cmd[1]=str(HERE/'run_economy_session.py')
        return cmd+['--session-dir',str(self.session_directory)]

    def reset(self,seed):
        self.episode_started=time.monotonic()
        if self.process is None or self.process.poll() is not None:
            return super().reset(seed)
        if self.current is not None or not self.result or not self.result.get('ok'):
            # An explicit Gym reset may abandon an unfinished episode. It is
            # not a training transition: restart cold rather than reuse it.
            self.close();return super().reset(seed)
        if not self.incoming.empty():raise RuntimeError('Stale decision at session boundary')
        self.directory=self.workspace_root/('e-'+uuid.uuid4().hex[:12]);self.directory.mkdir(parents=True,exist_ok=False)
        self.result_path=self.directory/'result.json';self.result=None
        metadata=read(self.session_directory/'metadata.json')
        config=dict(metadata['base_config'],seed=int(seed),out=str(self.result_path.resolve()))
        write(self.session_directory/'command.json',config)
        try:return self._wait(timeout=min(self.timeout,60.))
        except BaseException:self.close();raise

    def _wait(self,timeout=None):
        deadline=min(time.monotonic()+(self.timeout if timeout is None else timeout),self.episode_started+self.episode_timeout)
        while time.monotonic()<deadline:
            try:
                self.current=self.incoming.get(timeout=.02)
                return {'snapshot':self.current.snapshot,'done':False}
            except queue.Empty:pass
            if self.process.poll() is not None:raise RuntimeError('Native session exited; see '+str(self.session_directory/'engine.log'))
            if self.result_path.is_file():
                result=read(self.result_path)
                if not result.get('ok') or 'gym_final' not in result:raise RuntimeError('Native session episode failed: '+str(result.get('error')))
                metadata=read(self.session_directory/'metadata.json')
                result.update(identity=metadata['identity'],process_exit_code=None,persistent_session=True,
                              wall_seconds=time.monotonic()-self.episode_started,
                              model_identity={'controller':'external-gymnasium'})
                write(self.result_path,result);self.result=result
                return {'snapshot':result['gym_final'],'done':True,'reason':result['end_reason']}
        raise TimeoutError('Native session did not reach next decision: '+str(self.directory))

    def close(self):
        if getattr(self,'session_directory',None) and self.process is not None and self.current is None:
            if self.process.poll() is None and self.result and self.result.get('ok'):
                write(self.session_directory/'command.json',{'shutdown':True})
        super().close()
