"""Windows read-only memory sampler for owned benchmark processes."""
import ctypes as c
from ctypes import wintypes as w
import os
import threading
import time


class MemoryStatus(c.Structure):
    _fields_=[('length',w.DWORD),('load',w.DWORD)]+[(n,c.c_ulonglong) for n in
        ('physical','free_physical','commit','free_commit','virtual','free_virtual','extended')]


def system_memory():
    if os.name!='nt':return {}
    status=MemoryStatus();status.length=c.sizeof(status)
    if not c.windll.kernel32.GlobalMemoryStatusEx(c.byref(status)):raise c.WinError()
    return {key:int(getattr(status,key)) for key in ('physical','free_physical','commit','free_commit')}


class ProcessEntry(c.Structure):
    _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',c.c_size_t),('module',w.DWORD),
              ('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),('flags',w.DWORD),('exe',w.WCHAR*260)]


class Counters(c.Structure):
    _fields_=[('cb',w.DWORD),('faults',w.DWORD)]+[(n,c.c_size_t) for n in
        ('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]


def processes():
    k=c.WinDLL('kernel32',use_last_error=True);p=c.WinDLL('psapi',use_last_error=True)
    k.CreateToolhelp32Snapshot.restype=w.HANDLE;k.Process32FirstW.argtypes=[w.HANDLE,c.POINTER(ProcessEntry)]
    k.Process32NextW.argtypes=k.Process32FirstW.argtypes;k.CloseHandle.argtypes=[w.HANDLE]
    k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
    p.GetProcessMemoryInfo.argtypes=[w.HANDLE,c.POINTER(Counters),w.DWORD]
    snapshot=k.CreateToolhelp32Snapshot(2,0);entry=ProcessEntry();entry.size=c.sizeof(entry);rows=[]
    try:
        ok=k.Process32FirstW(snapshot,c.byref(entry))
        while ok:
            row={'pid':int(entry.pid),'parent':int(entry.parent),'exe':entry.exe}
            handle=k.OpenProcess(0x410,False,entry.pid)
            if handle:
                try:
                    counters=Counters();counters.cb=c.sizeof(counters)
                    if p.GetProcessMemoryInfo(handle,c.byref(counters),c.sizeof(counters)):
                        row.update(private=int(counters.private),ws=int(counters.ws))
                finally:k.CloseHandle(handle)
            rows.append(row);ok=k.Process32NextW(snapshot,c.byref(entry))
    finally:k.CloseHandle(snapshot)
    return rows


class Sampler:
    def __init__(self):
        self.stop=threading.Event();self.samples=0;self.minimum={};self.peak_game_private=0;self.peak_game_ws=0
        self.peak_owned_private=0;self.peak_games=0;self.thread=threading.Thread(target=self.loop,daemon=True)
        self.worker_roots=[];self.peak_environment_private=0;self.peak_environment_ws=0
    def loop(self):
        while not self.stop.is_set():
            memory=system_memory()
            for key in ('free_physical','free_commit'):
                self.minimum[key]=min(self.minimum.get(key,memory[key]),memory[key])
            rows=processes();owned={os.getpid()}
            while True:
                updated=owned|{r['pid'] for r in rows if r['parent'] in owned}
                if updated==owned:break
                owned=updated
            rows=[r for r in rows if r['pid'] in owned]
            games=[r for r in rows if r['exe'].lower()=='openbfme.exe']
            self.peak_games=max(self.peak_games,len(games))
            self.peak_owned_private=max(self.peak_owned_private,sum(r.get('private',0) for r in rows))
            for root in self.worker_roots:
                family={root}
                while True:
                    updated=family|{r['pid'] for r in rows if r['parent'] in family}
                    if updated==family:break
                    family=updated
                members=[r for r in rows if r['pid'] in family]
                self.peak_environment_private=max(self.peak_environment_private,sum(r.get('private',0) for r in members))
                self.peak_environment_ws=max(self.peak_environment_ws,sum(r.get('ws',0) for r in members))
            for row in games:
                self.peak_game_private=max(self.peak_game_private,row.get('private',0))
                self.peak_game_ws=max(self.peak_game_ws,row.get('ws',0))
            self.samples+=1;self.stop.wait(.2)
    def start(self):self.thread.start()
    def finish(self):
        self.stop.set();self.thread.join(timeout=5)
        return {'samples':self.samples,'minimum_free':self.minimum,'peak_game_private':self.peak_game_private,
                'peak_game_ws':self.peak_game_ws,'peak_owned_private':self.peak_owned_private,'peak_simultaneous_games':self.peak_games,
                'peak_environment_private':self.peak_environment_private,'peak_environment_ws':self.peak_environment_ws}
