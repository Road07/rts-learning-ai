"""Conservative launch budget; does not alter observations, actions or rewards."""
import ctypes
import os
import subprocess


def available_commit():
    if os.name != 'nt':
        return None
    class Status(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in
            ('physical', 'free_physical', 'commit', 'free_commit', 'virtual', 'free_virtual', 'extended')]
    status = Status(); status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError()
    return status.free_commit


def worker_budget(requested, free_bytes):
    if free_bytes is None:
        return requested
    # Leave 4 GiB for desktop/PPO and allow 3 GiB per native+Python worker.
    slots = int((free_bytes - 4 * 1024**3) // (3 * 1024**3))
    if slots < 1:
        raise RuntimeError('Insufficient available commit memory: close applications before training')
    return min(requested, slots)


def light_worker_budget(requested,memory):
    # Measured 5-env economy probe: max environment private 1.23 GiB;
    # reserve 1.5 GiB commit per worker. Physical incremental budget includes
    # shared image pages; the 5-env native+auto-reset probe retained 4.86 GiB.
    # Keep 3 GiB RAM + .75 GiB for parent/model, 1 GiB commit + 1.5 GiB parent.
    gib=1024**3
    ram=int((memory['free_physical']-3.75*gib)//(1.25*gib))
    commit=int((memory['free_commit']-2.5*gib)//(1.5*gib))
    slots=min(requested,5,ram,commit)
    if slots<1:raise RuntimeError('Insufficient memory for light workers with 3 GiB RAM reserve')
    return slots


def close_vector(vector):
    """Never wait forever in SB3.close() after a worker pipe has failed."""
    if vector is None or vector.closed:
        return
    for remote in vector.remotes:
        try:
            if vector.waiting and remote.poll(.1):
                remote.recv()
            remote.send(('close', None))
        except (OSError, EOFError):
            pass
    for process in vector.processes:
        process.join(timeout=3)
        if process.is_alive():
            if os.name == 'nt':
                from pathlib import Path
                kill = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/taskkill.exe'
                subprocess.run([str(kill), '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            else:
                process.terminate()
            process.join(timeout=5)
    for remote in vector.remotes:
        remote.close()
    vector.closed = True
