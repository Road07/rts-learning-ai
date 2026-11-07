"""Opt-in process transport; retains SB3's step/reset/seed/mask semantics."""
import os
from pathlib import Path
import subprocess
import sys
import socket
from multiprocessing.connection import Listener
import cloudpickle
from stable_baselines3.common.vec_env import VecEnv, SubprocVecEnv
from economy_resources import close_vector


class ChildProcess:
    def __init__(self, process): self.process = process; self.pid = process.pid
    def join(self, timeout=None):
        try: self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired: pass
    def is_alive(self): return self.process.poll() is None
    def terminate(self): self.process.terminate()


class LightEconomyVecEnv(SubprocVecEnv):
    def __init__(self, env_fns):
        self.waiting = False; self.closed = False
        self.remotes = []; self.processes = []; self.work_remotes = []
        try:
            for factory in env_fns:
                key = os.urandom(32)
                with Listener(('127.0.0.1', 0), authkey=key) as listener:
                    # Fail startup rather than blocking indefinitely on a dead child.
                    listener._listener._socket.settimeout(60)
                    process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).with_name('light_economy_worker.py')),
                                                '--port', str(listener.address[1]), '--auth', key.hex()],
                                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    self.processes.append(ChildProcess(process))
                    remote = listener.accept(); self.remotes.append(remote)
                    sock=socket.socket(fileno=remote.fileno())
                    try:sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                    finally:sock.detach()
                    remote.send(('init', cloudpickle.dumps(factory)))
            self.remotes[0].send(('get_spaces', None))
            if not self.remotes[0].poll(60): raise TimeoutError('Light worker initialization timed out')
            observation_space, action_space = self.remotes[0].recv()
            VecEnv.__init__(self, len(env_fns), observation_space, action_space)
        except BaseException:
            close_vector(self)
            raise
