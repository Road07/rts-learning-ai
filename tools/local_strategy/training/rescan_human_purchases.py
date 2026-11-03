"""Add genuine pre-dispatch human purchase attempts, without requiring future state."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from export_action_outcomes import features
from train_replay_sequence import LOOKUP


def identity(r):
    return (r["session_group"],r["match"],r["action"]["player"],r["action"]["id"])


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--base",type=Path,required=True)
    cli.add_argument("--logs",type=Path,action="append",required=True)
    cli.add_argument("--review-pending",type=Path,required=True)
    cli.add_argument("--output",type=Path,required=True)
    cli.add_argument("--all-families",action="store_true",help="Preserve whole-match command distribution, excluding reviewed/known-broken commands")
    args=cli.parse_args()
    if args.output.exists(): raise ValueError("New output directory required")
    rows=[json.loads(line) for line in args.base.open(encoding="utf-8")]
    known={identity(r) for r in rows}
    pending={identity(json.loads(line)) for line in args.review_pending.open(encoding="utf-8")}
    groups={}; sources=[]; counts=Counter(); additions=Counter()
    purchase_names={"MSG_DOZER_CONSTRUCT","MSG_FOUNDATION_CONSTRUCT","MSG_QUEUE_UNIT_CREATE","MSG_QUEUE_UPGRADE"}
    # Only retain small purchase-specific pre-states in memory, not entire match histories.
    for folder in args.logs:
        for path in sorted(folder.glob("*.jsonl")):
            raw=path.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
            sources.append({"path":str(path.resolve()),"sha256":digest})
            for number,line in enumerate(raw.decode("utf-8").splitlines(),1):
                row=json.loads(line); d=row["data"]; event=d.get("event")
                group=groups.setdefault((row["session"],row["match"]),{"pre":{},"actions":{},"results":{},"header":{},"gap":False})
                ref={"path":str(path.resolve()),"line":number}
                key=(d.get("player"),d.get("command_id",d.get("id")))
                if event=="human_session_start": group["header"]=d
                elif event=="capture_gap": group["gap"]=True
                elif event=="human_state" and d.get("reason")=="before_command":
                    group["pre"][key]={"frame":d["frame"],"features":features(d),"source":ref}
                elif event=="human_command" and d["command"] in (LOOKUP if args.all_families else purchase_names): group["actions"][key]=(d,ref)
                elif event=="human_command_result": group["results"][key]=(d,ref)
    for (session,match),g in groups.items():
        h=g["header"]
        if g["gap"] or h.get("fixture") or h.get("scope")!="fresh_local_human" or h.get("fog")!="own_and_living_allied_vision":
            counts["unsafe_sessions_skipped"]+=1; continue
        for key,(action,ref) in g["actions"].items():
            ident=(session,match,action["player"],action["id"])
            if ident in known: counts["existing_command_not_duplicated"]+=1; continue
            if ident in pending: counts["review_pending_skipped"]+=1; continue
            if action["command"] in {"MSG_EXIT","MSG_EVACUATE","MSG_EVACUATE_CONTESTERS"}:
                counts["unverified_tunnel_exit_skipped"]+=1; continue
            pre=g["pre"].get(key); result=g["results"].get(key)
            if not pre or not result or pre["frame"]!=action["frame"]:
                counts["unpaired_skipped"]+=1; continue
            immediate,result_ref=result
            if immediate.get("dispatcher_error") or (action["command"] in purchase_names and immediate["money"]>=action["money"]):
                counts["error_or_no_spend_skipped"]+=1; continue
            rows.append({"schema":1,"session_group":session,"match":match,"player":action["player"],
                         "source":ref,"state_source":pre["source"],"features":pre["features"],"action":action,
                         "immediate_result":immediate,"result_source":result_ref,"future_observations":[],
                         "match_result":None,"quality":{"source":"human_player","fixture":False,"fog_filtered":True,
                         "good_move_verified":False,"execution_success_verified":False,"causal_reward_available":False,"split_group":session}})
            known.add(ident); additions[action["command"]]+=1
    args.output.mkdir(parents=True)
    with (args.output/"observed-transitions.jsonl").open("w",encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")
    manifest={"review_pending_sha256":hashlib.sha256(args.review_pending.read_bytes()).hexdigest(),"base_sha256":hashlib.sha256(args.base.read_bytes()).hexdigest(),"sources":sources,"counts":dict(counts),
              "added_commands":dict(additions),"all_families":args.all_families,"total":len(rows),"independent_matches":len(set((r["session_group"],r["match"]) for r in rows)),
              "policy":"Only human command records, no bot/LocalModel labels. Purchases require spend evidence, not completion or quality. No future state needed to imitate pre-command family."}
    (args.output/"inventory.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:manifest[k] for k in ("counts","added_commands","total","independent_matches")}))


if __name__=="__main__": main()
