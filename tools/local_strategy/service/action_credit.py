"""Bounded outcome association by actor, target and time; never counterfactual causality."""
from collections import defaultdict
from bisect import bisect_left, bisect_right
import math

VERSION = "action-credit-v1"
DEFAULTS = {"logic_fps":5,"shaping_budget":1.,"radius":650.,"value_scale":1000.,
            "horizons_seconds":{"attack":12,"defend":12,"help":18,"scout":30,"wait":12,
              "build":180,"train":90,"hero":180,"research":180,"science":60,"power":12,
              "enter":15,"exit":15,"stance":12,"formation":12,"cancel":12,"stop":12}}


def key(player, frame, head): return (int(player),int(frame),str(head))
def objects(row, field): return {int(o["id"]):o for o in row.get(field,[])}
def near(a,b,radius): return (float(a.get("x",0))-float(b.get("x",0)))**2+(float(a.get("y",0))-float(b.get("y",0)))**2 <= radius**2
def health(o):
    value=float(o["health"])
    if not math.isfinite(value) or not 0 <= value <= 1: raise ValueError("Invalid credit health")
    return value
def cost(o):
    value=float(o.get("cost",0))
    if not math.isfinite(value) or value<0: raise ValueError("Invalid credit cost")
    return value


def calculate(tuning, rows, events):
    cfg=dict(DEFAULTS,**tuning.get("decision_credit",{}))
    fps, radius, scale = float(cfg["logic_fps"]),float(cfg["radius"]),float(cfg["value_scale"])
    budget=float(cfg["shaping_budget"])
    if fps!=5 or not 0<budget<=1 or radius<=0 or scale<=0: raise ValueError("Invalid credit tuning")
    timeline=defaultdict(list)
    for row in sorted(rows,key=lambda r:(int(r["frame"]),int(r["player"]),int(r["income_cursor"]))):
        if row.get("credit_schema")!=VERSION: continue
        if not row.get("ok") or not row.get("income_complete"): raise ValueError("Incomplete credit telemetry")
        player=int(row["player"])
        if timeline[player] and (row["frame"],row["income_cursor"])==(timeline[player][-1]["frame"],timeline[player][-1]["income_cursor"]): continue
        timeline[player].append(row)
    actions={}
    by_player=defaultdict(list)
    for event in events:
        player=int(event["player"])
        if player not in timeline: continue
        if int(event["frame"])>int(timeline[player][-1]["frame"]): continue
        if int(event["observed_frame"])>int(event["frame"]): raise ValueError("Decision precedes its observation")
        identity=key(player,event["observed_frame"],event["head"])
        if identity in actions: raise ValueError("Duplicate decision-credit event")
        operation=event["operation"]
        kind=str(operation.get("kind","wait"))
        frame=int(event["frame"])
        end=frame+int(fps*cfg["horizons_seconds"].get(kind,30))
        team=tuple(sorted(map(int,timeline[player][0]["team_members"])))
        final=timeline[player][-1]
        terminal=bool(final.get("won") or final.get("team_defeated"))
        action={"id":identity,"player":player,"head":event["head"],"frame":frame,"end":end,
                "operation":operation,"kind":kind,"submitted":bool(event.get("submitted")),"team":team,
                "matured":int(final["frame"])>=end or terminal,"components":defaultdict(float),"observed_events":0}
        actions[identity]=action; by_player[player].append(action)
    for values in by_player.values(): values.sort(key=lambda a:a["frame"])
    times={p:[a["frame"] for a in values] for p,values in by_player.items()}
    max_window=int(fps*max(cfg["horizons_seconds"].values()))

    def active(player, frame, predicate):
        stamps=times.get(player,[])
        recent=by_player[player][bisect_left(stamps,frame-max_window):bisect_right(stamps,frame)]
        return [a for a in recent if a["submitted"] and frame<=a["end"] and predicate(a)]
    def latest(values): return max(values,key=lambda a:a["frame"]) if values else None
    def add(action, component, value):
        if action is None or not action["matured"] or not math.isfinite(value) or abs(value)<1e-12: return
        action["components"][component]+=value; action["observed_events"]+=1

    birth_parents={}; income_seen=set(); enemy_min={}; own_min={}; repair_paid={}; discoveries={}; recoverable=defaultdict(float)
    economy_loss={}; ally_min={}
    metrics=defaultdict(float)
    previous_by_player={}
    ordered=sorted((r for samples in timeline.values() for r in samples),key=lambda r:(int(r['frame']),int(r['player']),int(r['income_cursor'])))
    for row in ordered:
        player=int(row['player'])
        previous=previous_by_player.get(player)
        frame=int(row["frame"]); team=tuple(sorted(map(int,row["team_members"])))
        own=objects(row,"own_assets"); allies=objects(row,"ally_assets"); enemies=objects(row,"visible_enemies")
        old_own=objects(previous,"own_assets") if previous else {}
        old_enemy=objects(previous,"visible_enemies") if previous else {}
        if previous and row["own_structures_lost"]>previous["own_structures_lost"]:
            if any(o.get("economy") and oid not in own and oid not in row.get("owned_present_ids",[]) for oid,o in old_own.items()): economy_loss[player]=frame
        for oid,o in allies.items():
            identity=(team,oid,str(o.get("template","")))
            minimum=ally_min.get(identity,health(o))
            metrics["observed_ally_value_damage"]+=max(0.,minimum-health(o))*cost(o)
            ally_min[identity]=min(minimum,health(o))
        triggers={(int(p["source"]),str(p["name"])):int(p["triggers"]) for p in row.get("power_triggers",[])}
        # Object births, not purchase requests, establish production provenance.
        for oid,o in own.items():
            if previous and oid not in old_own and (player,oid) not in birth_parents:
                choices=active(player,frame,lambda a:a["head"]=="spend" and a["kind"] in ("build","train","hero") and a["operation"].get("template")==o.get("template") and oid not in a["operation"].get("before_ids",[]))
                candidates=[]
                for a in choices:
                    at=a["operation"] if a["kind"]=="build" else own.get(int(a["operation"].get("producer",0)),{})
                    if at and near(at,o,radius): candidates.append(a)
                parent=latest(candidates)
                if parent: birth_parents[player,oid]=parent
        # Only real, cursor-identified economy payments; refunds are absent.
        for payment in row.get("income_payments",[]):
            serial=(player,int(payment["serial"]))
            if serial in income_seen: continue
            income_seen.add(serial)
            oid=int(payment["object"]); parent=birth_parents.get((player,oid))
            source=own.get(oid,old_own.get(oid,{}))
            if parent and source.get("economy") and parent["frame"]<=int(payment["frame"])<=parent["end"]:
                paid=float(payment["amount"])
                if not math.isfinite(paid) or paid<0: raise ValueError("Invalid economy payment")
                component="economy_recovery_return" if parent["frame"]>=economy_loss.get(player,10**18) else "economy_return"
                invested=cost(parent["operation"])
                add(parent,component,paid/(scale+invested))
                parent["income_received"]=parent.get("income_received",0.)+paid
                metrics["attributed_income"]+=paid

        def own_effect(oid, value, component):
            tactical=latest(active(player,frame,lambda a:a["head"]=="tactical" and oid in a["operation"].get("units",[])))
            parent=birth_parents.get((player,oid))
            if parent and frame>parent["end"]: parent=None
            if tactical and parent:
                add(tactical,component,value*.7); add(parent,"production_"+component,value*.3)
            else: add(tactical or parent,component,value)

        def own_price(o):
            parent=birth_parents.get((player,int(o["id"])))
            return cost(parent["operation"]) if parent and "cost" in parent["operation"] else cost(o)

        # Own health high-water losses; disappearing/tunnel units are not deaths.
        losses_confirmed=previous and (float(row["own_units_lost"])>float(previous["own_units_lost"]) or float(row["own_structures_lost"])>float(previous["own_structures_lost"]))
        for oid,o in own.items():
            if not o.get("complete",True): continue
            identity=(player,oid,str(o.get("template","")))
            minimum=own_min.get(identity,health(o))
            if oid in old_own and old_own[oid].get("complete",True):
                damage=max(0.,minimum-health(o))*own_price(o)/scale
                if damage and any(near(e,o,radius) for e in enemies.values()): recoverable[player,oid]+=damage
                own_effect(oid,-damage,"hero_cost_lost" if o.get("hero") else "asset_cost_lost")
                # An observed defensive loss may expose a production delay; cash alone never does.
                if damage and o.get("structure") and any(near(e,o,radius) for e in enemies.values()):
                    defender=latest(active(player,frame,lambda a:a["head"]=="tactical" and a["kind"]=="defend" and near(a["operation"],o,radius)))
                    add(defender,"defense_asset_cost",-damage*.2)
                    a=latest(active(player,frame,lambda a:a["head"]=="spend" and a["operation"].get("affordable_military") and a["kind"] in ("wait","build","research","science")))
                    add(a,"defense_opportunity_cost",-damage*.2)
                    helper=latest(active(player,frame,lambda a:a["kind"]=="help"))
                    add(helper,"support_home_cost",-damage*.2)
            own_min[identity]=min(minimum,health(o))
        if losses_confirmed:
            for oid,o in old_own.items():
                counter="own_structures_lost" if o.get("structure") else "own_units_lost"
                if oid not in own and oid not in row.get("owned_present_ids",[]) and row[counter]>previous[counter]:
                    identity=(player,oid,str(o.get("template","")))
                    own_effect(oid,-own_min.get(identity,health(o))*own_price(o)/scale,"confirmed_asset_loss")
                    if o.get("structure"):
                        helper=latest(active(player,frame,lambda a:a["kind"]=="help"))
                        add(helper,"support_home_cost",-own_min.get(identity,health(o))*own_price(o)/scale*.2)
                    own_min[identity]=0.

        for eid,enemy in enemies.items():
            identity=(team,eid,str(enemy.get("template","")))
            minimum=enemy_min.get(identity,health(enemy))
            if identity not in discoveries:
                scout=latest(active(player,frame,lambda a:a["kind"]=="scout" and any(oid in own and near(own[oid],enemy,radius) for oid in a["operation"].get("units",[]))))
                discoveries[identity]=scout
            # Continuous observed damage only; fog disappearance/reappearance earns nothing.
            damage=max(0.,minimum-health(enemy))*cost(enemy)/scale if eid in old_enemy else 0.
            enemy_min[identity]=min(minimum,health(enemy))
            if damage:
                metrics["observed_enemy_value_damage"]+=damage*scale
                actors=[o for o in own.values() if not o.get("structure") and o.get("combat") and near(o,enemy,radius)]
                powers=active(player,frame,lambda a:a["kind"]=="power" and triggers.get((int(a["operation"].get("producer",0)),str(a["operation"].get("template",""))),0)>int(a["operation"].get("power_before",10**9)) and (int(a["operation"].get("target",0))==eid or near(a["operation"],enemy,radius)))
                power=latest(powers)
                assigned=damage if not actors else damage*.4
                if power: add(power,"verified_spell_damage",assigned)
                remaining=damage-(assigned if power else 0.)
                scout=discoveries.get(identity)
                if actors and scout and frame<=scout["end"]:
                    add(scout,"information_used_in_combat",remaining*.05); remaining*=.95
                for actor in actors:
                    component="raid_value" if enemy.get("economy") else "combat_value"
                    protected=[o for o in own.values() if o.get("structure") and near(o,enemy,radius)]
                    ally_protected=[o for o in allies.values() if o.get("structure") and near(o,enemy,radius)]
                    if ally_protected: component="ally_support_value"
                    elif protected: component="base_defense_value"
                    if actor.get("hero"): component="hero_"+component
                    own_effect(int(actor["id"]),remaining/len(actors),component)
        # Repair/heal only after an actual trigger, bounded by previously observed low HP.
        for action in active(player,frame,lambda a:a["kind"]=="power"):
            op=action["operation"]; trigger=(int(op.get("producer",0)),str(op.get("template","")))
            if triggers.get(trigger,0)<=int(op.get("power_before",10**9)): continue
            for oid,o in own.items():
                if oid not in old_own or not o.get("complete",True) or not old_own[oid].get("complete",True) or not (int(op.get("target",0))==oid or near(op,o,radius)): continue
                recovered=max(0.,health(o)-health(old_own[oid]))*own_price(o)/scale
                paid_key=(team,oid); maximum=recoverable[player,oid]
                amount=min(recovered,max(0.,maximum-repair_paid.get(paid_key,0.)))
                if amount:
                    add(action,"verified_repair_recovery",amount*.5)
                    repair_paid[paid_key]=repair_paid.get(paid_key,0.)+amount
        previous_by_player[player]=row
    # A finite per-team shaping budget: many commands/actors cannot multiply reward.
    team_totals=defaultdict(float); team_counts=defaultdict(int); terminal={}
    for a in actions.values():
        team_totals[a["team"]]+=sum(abs(x) for x in a["components"].values())
        team_counts[a["team"]]+=1
    for player,samples in timeline.items():
        final=samples[-1]; team=tuple(sorted(map(int,final["team_members"])))
        if final.get("won"): terminal[team]=float(tuning["terminal_win"])
        elif final.get("team_defeated"): terminal[team]=float(tuning["terminal_loss"])
    result={}
    for identity,a in actions.items():
        factor=min(1.,budget/max(team_totals[a["team"]],1e-12))
        components={k:v*factor for k,v in a["components"].items()}
        outcome=terminal.get(a["team"],0.)/max(1,team_counts[a["team"]])
        result[identity]={"version":VERSION,"components":components,"matured":a["matured"],
                          "observed_events":a["observed_events"],"horizon_end":a["end"],
                          "terminal_share":outcome,"reward":sum(components.values())+outcome,
                          "attribution":"observed actor/target/time association, not proven causality"}
        if a.get("income_received") is not None and cost(a["operation"])>0:
            result[identity]["realized_roi"]=a["income_received"]/cost(a["operation"])
    return result,dict(metrics)
