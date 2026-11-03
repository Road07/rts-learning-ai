"""Outcome-only team reward. No command-count, spending or refund bonuses."""
from collections import Counter
import json
import math
from pathlib import Path

COUNTERS=("enemy_units","enemy_structures","own_units_lost","own_structures_lost")


def number(value, minimum=0, maximum=None):
    value=float(value)
    if not math.isfinite(value) or value<minimum or (maximum is not None and value>maximum):
        raise ValueError("Invalid reward measurement")
    return value


class RewardLedger:
    def __init__(self, tuning):
        self.tuning=tuning
        if tuning.get("schema")!=1 or tuning.get("id")!="bfme-outcome-reward-v3": raise ValueError("Unknown reward configuration")
        expected=set(COUNTERS)|{"income","hero_deaths","base_health","hero_health","visible_damage","discovery"}
        if set(tuning["weights"])!=expected or set(tuning["caps"])!=expected: raise ValueError("Incomplete reward components")
        for key,value in tuning["weights"].items(): number(value,-100,100)
        for key,value in tuning["caps"].items(): number(value,0,100)
        for key in ("value_scale","shaping_cap","terminal_win"): number(tuning[key],.00001)
        number(tuning["terminal_loss"],-100,-.00001)
        self.players={}
        self.teams={}

    @classmethod
    def load(cls,path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def summary(self,team):
        state=self.teams[team]
        components={key:max(-self.tuning["caps"][key],min(self.tuning["caps"][key],value)) for key,value in state["raw"].items()}
        shaping=max(-self.tuning["shaping_cap"],min(self.tuning["shaping_cap"],sum(components.values())))
        terminal=self.tuning["terminal_win"] if state["outcome"]=="win" else self.tuning["terminal_loss"] if state["outcome"]=="loss" else 0.0
        return {"version":self.tuning["id"],"team":team,"components":components,"shaping":shaping,
            "terminal":terminal,"outcome":state["outcome"],"total":shaping+terminal,
            "samples":state["samples"],"attribution":"shared observed team outcomes, not causal action labels"}

    def observe(self,row):
        if not row.get("ok") or not row.get("income_complete"): raise ValueError("Missing or truncated reward telemetry")
        player=int(number(row["player"]))
        frame=int(number(row["frame"]))
        members=tuple(sorted(set(int(number(p)) for p in row["team_members"])))
        if player not in members: raise ValueError("Reward player is outside its team")
        team=":".join(map(str,members))
        cursor=int(number(row["income_cursor"]))
        income=number(row["income_delta"])
        counters={k:number(row[k]) for k in COUNTERS}
        bases={int(o["id"]):number(o["health"],0,1) for o in row["bases"]}
        heroes={int(o["id"]):number(o["health"],0,1) for o in row["heroes"]}
        dead=Counter(str(x) for x in row["dead_heroes"])
        visible={}
        for enemy in row["visible_enemies"]:
            visible[int(enemy["id"])]=(str(enemy["template"]),number(enemy["health"],0,1),number(enemy["cost"]))
        state=self.teams.setdefault(team,{"raw":{k:0.0 for k in self.tuning["weights"]},"members":members,
            "seen":set(),"minimum":{},"samples":0,"outcome":"ongoing"})
        old=self.players.get(player)
        if old and old["team"]!=team: raise ValueError("Reward team changed during a match")
        if old and (frame<old["frame"] or cursor<old["cursor"]): raise ValueError("Reward timeline went backwards")
        if old and frame==old["frame"] and cursor==old["cursor"]: return self.summary(team)
        weight=self.tuning["weights"]
        if old:
            if any(value<old["counters"][key] for key,value in counters.items()): raise ValueError("Reward counter reset")
            for key,value in counters.items():
                state["raw"][key]+=(value-old["counters"][key])*weight[key]
            state["raw"]["income"]+=income/self.tuning["value_scale"]*weight["income"]
            deaths=sum(max(0,count-old["dead"].get(name,0)) for name,count in dead.items())
            state["raw"]["hero_deaths"]+=deaths*weight["hero_deaths"]
            for key,current in (("base_health",bases),("hero_health",heroes)):
                previous=old[key]
                change=sum(health-previous[id] for id,health in current.items() if id in previous)
                if key=="base_health" and counters["own_structures_lost"]>old["counters"]["own_structures_lost"]:
                    change-=sum(health for id,health in previous.items() if id not in current)
                state["raw"][key]+=change*weight[key]
        for id,(template,health,cost) in visible.items():
            key=(id,template)
            minimum=state["minimum"].get(key,health)
            previous=old["visible"].get(id) if old else None
            if old and previous and previous[0]==template:
                state["raw"]["visible_damage"]+=max(0,minimum-health)*cost/self.tuning["value_scale"]*weight["visible_damage"]
            # A lower health after fog is a new baseline, never credited as damage.
            state["minimum"][key]=min(minimum,health)
            if id not in state["seen"]:
                state["seen"].add(id)
                if old: state["raw"]["discovery"]+=weight["discovery"]
        self.players[player]={"team":team,"frame":frame,"cursor":cursor,"counters":counters,
            "base_health":bases,"hero_health":heroes,"dead":dead,"visible":visible,"won":bool(row["won"]),"defeated":bool(row["defeated"])}
        if row["won"]: state["outcome"]="win"
        elif row.get("team_defeated",False) or all(p in self.players and self.players[p]["defeated"] for p in members): state["outcome"]="loss"
        state["samples"]+=1
        return self.summary(team)


def calculate_episode(tuning,rows,learners):
    ledger=RewardLedger(tuning)
    learner_team=None
    for row in sorted(rows,key=lambda r:(r["frame"],r["player"],r["income_cursor"])):
        if int(row["player"]) not in learners: continue
        result=ledger.observe(row)
        if learner_team is not None and learner_team!=result["team"]: raise ValueError("Learners span multiple reward teams")
        learner_team=result["team"]
    if learner_team is None or not set(learners).issubset(ledger.players): raise ValueError("Missing learner reward observations")
    return ledger.summary(learner_team)
