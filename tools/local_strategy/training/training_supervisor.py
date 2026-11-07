"""Continuous, resumable local training. Started and owned by the desktop launcher."""
import argparse
from datetime import datetime
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
RUNS=ROOT / "AI-Egitim/otomatik-dongu"
SCHEDULE=[("middle","pressure"),("opening","baseline"),("middle","counters"),
          ("late","team"),("middle","baseline"),("late","baseline")]


def emit(event,**fields):
    print(json.dumps({"event":event,**fields},ensure_ascii=False),flush=True)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_write(path,value):
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(path)


def checked_run(folder):
    """Resume only a fully finished, unchanged pair; partial runs are never selected."""
    folder=Path(folder).resolve()
    report=read(folder / "report.json")
    if report.get("status")!="complete" or not report.get("rounds"): raise ValueError("Eğitim kaydı tamamlanmamış")
    if (report["rounds"][-1].get("reward_breakdown") or {}).get("version")!="bfme-outcome-reward-v3":
        raise ValueError("Eğitim kaydının ödül sürümü uyumsuz")
    if digest(folder / "candidate.npz")!=report["candidate_sha256"]: raise ValueError("Taktik checkpoint değişmiş")
    if digest(folder / "spend-candidate.npz")!=report["rounds"][-1]["spend_sha256"]: raise ValueError("Komut checkpoint değişmiş")
    meta=read(folder / "spend-metadata.json")
    if meta.get("encoding")!="spend-v2": raise ValueError("Komut özellikleri uyumsuz")
    return report


def latest_completed():
    if not RUNS.exists(): return None
    for folder in sorted((p for p in RUNS.iterdir() if p.is_dir()),key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            checked_run(folder)
            return folder
        except (OSError,ValueError,KeyError,TypeError): continue
    return None


def load_progress(path):
    if path.exists():
        state=read(path)
        if state.get("schema")!=1: raise ValueError("Başlatıcı kayıt sürümü uyumsuz")
        if state.get("last_completed_run"): checked_run(state["last_completed_run"])
        if not isinstance(state.get("completed"),int) or state["completed"]<0: raise ValueError("Geçersiz tur sayısı")
        if not isinstance(state.get("next_seed"),int) or not 0<=state["next_seed"]<2000000000: raise ValueError("Geçersiz başlangıç tohumu")
        if not isinstance(state.get("schedule_index"),int) or state["schedule_index"]<0: raise ValueError("Geçersiz senaryo sırası")
        # If the GUI closed after a run finished but before its progress commit,
        # recover that complete pair; an interrupted report never advances state.
        if state.get("pending_run"):
            try:
                recovered=checked_run(state["pending_run"])
                state.update(completed=state["completed"]+1,next_seed=state["next_seed"]+1,
                    schedule_index=state["schedule_index"]+1,last_completed_run=state["pending_run"],
                    last_reward=recovered["rounds"][-1]["reward"])
                state.pop("pending_run",None)
            except (OSError,ValueError,KeyError,TypeError):
                try:
                    from automatic_training import resumable_evaluation
                    resumable_evaluation(state["pending_run"],ROOT/"AI-Yeni-Model/ai-service/runtime.json")
                except (OSError,ValueError,KeyError,TypeError): state.pop("pending_run",None)
            atomic_write(path,state)
        return state
    previous=latest_completed()
    seed=int(time.time())%1000000000
    if previous:
        old=checked_run(previous)
        seed=int(old["settings"]["seed"])+len(old["rounds"])
    return {"schema":1,"completed":0,"next_seed":seed,"schedule_index":0,
            "last_completed_run":str(previous) if previous else None}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state",type=Path,default=RUNS / "launcher-state.json")
    parser.add_argument("--gate",type=Path)
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--minutes",type=int,choices=[3,5,15,30],default=3,
                        help="Simulation duration of each headless training rollout")
    parser.add_argument("--time-scale",type=float,default=10.)
    args=parser.parse_args()
    if not 0.25<=args.time_scale<=100:parser.error("time-scale: 0.25..100")
    # The GUI assigns this process to its private kill-on-close Job before opening
    # the gate. No child process can escape ownership during launcher startup.
    if args.gate:
        deadline=time.monotonic()+20
        while not args.gate.is_file():
            if time.monotonic()>deadline: raise RuntimeError("Başlatıcı süreç sahipliğini kuramadı")
            time.sleep(.05)
    args.state=args.state.resolve()
    args.state.parent.mkdir(parents=True,exist_ok=True)
    lock=args.state.with_suffix(".lock").open("a+b")
    lock.seek(0)
    if not lock.read(1): lock.write(b"0"); lock.flush()
    lock.seek(0)
    try: msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError: raise RuntimeError("Otomatik eğitim zaten açık")
    try:
        state=load_progress(args.state)
        if not args.smoke:
            sys.path.insert(0,str(HERE.parent))
            from engine_update import start_background
            start_background()
        if not args.smoke:
            game_config=read(ROOT / "AI-Yeni-Model/ai-service/runtime.json")
            published=game_config.get("model_activation",{})
            published_run=Path(published["source_run"]) if published.get("source_run") else None
            previous=Path(state["last_completed_run"]) if state["last_completed_run"] else None
            if published_run and (previous is None or published_run.stat().st_ctime_ns>previous.stat().st_ctime_ns):
                published_report=checked_run(published_run)
                if published_report["candidate_sha256"]!=game_config["sha256"] or published_report["rounds"][-1]["spend_sha256"]!=game_config["spend_sha256"]:
                    raise ValueError("Yayımlanan model devam kaydıyla eşleşmiyor")
                state["last_completed_run"]=str(published_run)
                atomic_write(args.state,state)
        if not args.smoke and state["last_completed_run"]:
            from model_activation import activate
            activate(state["last_completed_run"], ROOT / "AI-Yeni-Model/ai-service/runtime.json")
        emit("ready",completed=state["completed"],resume=bool(state["last_completed_run"]),last_reward=state.get("last_reward"))
        while True:
            number=state["completed"]+1
            stage,case=("middle","pressure") if args.smoke else SCHEDULE[state["schedule_index"]%len(SCHEDULE)]
            seconds=6 if args.smoke else args.minutes*60
            evaluation=not args.smoke and number%5==0
            parent=args.state.parent / "runs" if args.smoke else RUNS
            parent.mkdir(parents=True,exist_ok=True)
            output=parent / ("auto-"+datetime.now().strftime("%Y%m%d-%H%M%S-%f")+"-"+str(number))
            pending=state.get("pending_run")
            if pending and not args.smoke:
                output=Path(pending)
            command=[sys.executable,str(HERE / "automatic_training.py"),"--cycles","1","--seconds",str(seconds),
                     "--stage",stage,"--case",case,"--seed",str(state["next_seed"]),"--output",str(output),"--headless-training","--time-scale",str(args.time_scale)]
            if state["last_completed_run"]:
                previous=Path(state["last_completed_run"])
                checked_run(previous)
                command += ["--resume",str(previous / "candidate.npz"),"--resume-spend",str(previous / "spend-candidate.npz")]
            if evaluation: command.append("--evaluate")
            if pending and not args.smoke: command.append("--resume-evaluation")
            if args.smoke: command.append("--no-activate")
            if not args.smoke: command.append("--rotate-factions")
            state["pending_run"]=str(output)
            atomic_write(args.state,state)
            emit("running",round=number,completed=state["completed"],stage=stage,case=case,seconds=seconds,evaluation=evaluation,headless=True,time_scale=args.time_scale,duration_basis="simulation")
            with (args.state.parent / "launcher-session.log").open("a",encoding="utf-8",buffering=1) as log:
                process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                         text=True,encoding="utf-8",creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    for line in process.stdout:
                        log.write(line)
                        try:
                            row=json.loads(line)
                            if row.get("event")=="episode_phase": emit("episode_phase",phase=row["phase"],seconds=row["seconds"])
                        except (ValueError,KeyError,TypeError): pass
                    code=process.wait()
                except BaseException:
                    if process.poll() is None:
                        subprocess.run(["taskkill","/PID",str(process.pid),"/T","/F"],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                        process.wait(timeout=10)
                    raise
            if code:
                report_path = output / "report.json"
                detail = json.loads(report_path.read_text(encoding="utf-8")).get("error", "") if report_path.is_file() else ""
                raise RuntimeError("Eğitim turu başarısız. " + str(detail) + " Ayrıntılar: " + str(report_path))
            report=checked_run(output)
            state.update(completed=number,next_seed=state["next_seed"]+1,
                         schedule_index=state["schedule_index"]+1,last_completed_run=str(output))
            state["last_reward"]=report["rounds"][-1]["reward"]
            state["last_evaluation"]=report.get("evaluation")
            state.pop("pending_run",None)
            atomic_write(args.state,state)
            emit("completed",round=number,completed=number,reward=state["last_reward"],
                 evaluation=state["last_evaluation"],checkpoint=str(output))
            if args.smoke: return 0
    finally: lock.close()


if __name__=="__main__":
    try: sys.exit(main())
    except (Exception,KeyboardInterrupt) as error:
        emit("error",message=str(error) or "Eğitim durduruldu")
        sys.exit(1)
