"""Mod-owned local inference runtime; only its own server/process tree is stopped."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import msvcrt
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


class ServerJob:
    """Windows closes the private server and runners even if this host crashes."""
    def __init__(self):
        class Basic(ctypes.Structure):
            _fields_ = [("user", ctypes.c_int64), ("job_user", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t),
                        ("max_ws", ctypes.c_size_t), ("processes", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]
        class Info(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", ctypes.c_uint64 * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.SetInformationJobObject.restype = wintypes.BOOL
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.AssignProcessToJobObject.restype = wintypes.BOOL
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle: raise ctypes.WinError(ctypes.get_last_error())
        info = Info()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def api(base, path, data=None, timeout=5):
    request = urllib.request.Request(base + path,
        data=None if data is None else json.dumps(data).encode(),
        headers={"Content-Type": "application/json"})
    # Ignore machine proxy settings for the loopback-only backend.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--arena", choices=["opening", "middle", "late"])
    parser.add_argument("--seconds", type=int, default=6)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    folder = args.config.resolve().parent
    logs = folder / "logs"
    logs.mkdir(exist_ok=True)
    lock = (folder / "runtime.lock").open("a+b")
    lock.seek(0)
    if lock.read(1) == b"":
        lock.write(b"0"); lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        if not args.arena: ctypes.windll.user32.MessageBoxW(None, "Mod zaten açık veya yapay zekâ hazırlanıyor.", "OpenBFME AI", 0x40)
        lock.close()
        return 2

    log_path = logs / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + str(os.getpid()) + ".log")
    server = None
    job = None
    state = {"host_pid": os.getpid(), "model": config["model"], "log": str(log_path), "game_pid": None}
    def status(phase, **fields):
        state.update(fields, phase=phase, updated_utc=datetime.now(timezone.utc).isoformat())
        temporary = folder / "status.tmp"
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(folder / "status.json")

    code = 1
    failure = None
    with log_path.open("w", encoding="utf-8", buffering=1) as log:
        try:
            status("starting")
            runtime = Path(config["runtime_executable"])
            models = Path(config["model_directory"])
            if not runtime.is_file(): raise RuntimeError("LocalModel motoru bulunamadı. LocalModel kurulumunu koru ve modu yeniden paketle.")
            manifest = models / "manifests/registry.model.ai/library" / config["model"].replace(":", "/")
            if not manifest.is_file(): raise RuntimeError("Modun yerel modeli bulunamadı: " + config["model"])
            # Release only this mod's configured model from the old default service.
            # Never terminate the desktop app, its server, or unrelated models.
            try:
                loaded = api("http://127.0.0.1:11434", "/api/ps")
            except urllib.error.URLError:
                loaded = {"models": []}
            for model in loaded.get("models", []):
                if model.get("name") == config["model"]:
                    api("http://127.0.0.1:11434", "/api/generate", {"model": config["model"], "keep_alive": 0}, timeout=30)
                    print("Released configured model from default service before private load.", file=log)
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            base = "http://127.0.0.1:" + str(port)
            env = os.environ.copy()
            env.update(LOCAL_MODEL_HOST="127.0.0.1:" + str(port), LOCAL_MODEL_MODELS=str(models),
                       LOCAL_MODEL_NUM_PARALLEL="1", LOCAL_MODEL_MAX_LOADED_MODELS="1", LOCAL_MODEL_MAX_QUEUE="2",
                       LOCAL_MODEL_CONTEXT_LENGTH=str(config["num_ctx"]), LOCAL_MODEL_KEEP_ALIVE="15m",
                       LOCAL_MODEL_NO_CLOUD="1", LOCAL_MODEL_NOPRUNE="1")
            job = ServerJob()
            server = subprocess.Popen([str(runtime), "serve"], env=env, stdout=log, stderr=subprocess.STDOUT,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
            job.assign(server)
            status("starting", server_pid=server.pid, endpoint=base)
            deadline = time.monotonic() + 15
            while True:
                if server.poll() is not None: raise RuntimeError("Özel AI motoru açılamadı; ayrıntılar servis logunda.")
                try:
                    api(base, "/api/version", timeout=1)
                    break
                except (urllib.error.URLError, TimeoutError):
                    if time.monotonic() >= deadline: raise RuntimeError("AI motoru zamanında hazırlanamadı.")
                    time.sleep(0.1)
            status("loading")
            api(base, "/api/generate", {"model": config["model"], "stream": False, "keep_alive": "15m",
                "options": {"num_ctx": config["num_ctx"]}}, timeout=60)
            loaded = api(base, "/api/ps")
            if len(loaded.get("models", [])) != 1 or loaded["models"][0]["name"] != config["model"]:
                raise RuntimeError("Beklenen tek model yüklenemedi.")
            status("ready", loaded_models=loaded["models"])
            game_env = os.environ.copy()
            game_env["OPENBFME_AI_URL"] = base
            game_env["OPENBFME_AI_MANAGED"] = "1"
            if args.arena:
                command = [sys.executable, config["arena_script"], args.arena, "--seconds", str(args.seconds), "--model", "on"]
            else:
                command = [config["game_executable"], "--", "--no-update-check", "-mod", config["mod_directory"]]
            game = subprocess.Popen(command, cwd=config["game_directory"], env=game_env,
                                    stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            status("running", game_pid=game.pid)
            code = game.wait()
            print("Game exited:", code, file=log)
        except Exception as error:
            failure = str(error)
            print(type(error).__name__ + ": " + str(error), file=log)
            status("error", error=str(error))
        finally:
            status("stopping", exit_code=code)
            if job: job.close()  # also kills the model runner's GPU context
            if server:
                if server.poll() is None: server.terminate()
                server.wait(timeout=10)
            status("stopped", exit_code=code, loaded_models=[], last_server_pid=state.get("server_pid"), server_pid=None,
                   last_game_pid=state.get("game_pid"), game_pid=None)
            lock.close()
    if failure and not args.arena:
        ctypes.windll.user32.MessageBoxW(None, failure + "\n\nKayıt: " + str(log_path), "OpenBFME AI", 0x10)
    return code


if __name__ == "__main__":
    sys.exit(main())
