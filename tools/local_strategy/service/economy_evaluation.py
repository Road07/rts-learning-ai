"""Descriptive economy/production measurements, never policy rewards or advice."""
import math

VERSION = "economy-production-eval-v1"


def number(value):
    value = float(value)
    if not math.isfinite(value) or value < 0: raise ValueError("Invalid economy measurement")
    return value


def ratio(total, denominator):
    return total / denominator if denominator else None


class EconomyEvaluation:
    def __init__(self):
        self.players = {}

    def observe(self, row):
        data = row.get("economy_evaluation")
        if not data or data.get("schema") != VERSION or not row.get("ok"): return
        player, frame = int(row["player"]), number(row["frame"])
        farms = [o for o in row.get("own_assets", []) if o.get("economy") and o.get("complete")]
        factories = [o for o in row.get("own_assets", []) if o.get("factory") and o.get("complete") and not o.get("factory_disabled")]
        army = [o for o in row.get("own_assets", []) if o.get("mobile") and not o.get("builder") and not o.get("structure")]
        sample = {"frame":frame, "farms":len(farms),
                  "share_sum":sum(number(o["resource_share"]) for o in farms),
                  "factories":len(factories), "busy":sum(int(o.get("queue_count",0)) > 0 for o in factories),
                  "money":number(row["money"]), "cp_used":number(data["cp_used"]), "cp_limit":number(data["cp_limit"]),
                  "army_value":sum(number(o["cost"])*number(o["health"]) for o in army),
                  "army_groups":len(army)}
        state = self.players.get(player)
        if state is None:
            state = {"faction":row["faction"], "first":sample, "last":sample, "samples":1,
                     "covered":0., "farm_seconds":0., "share_seconds":0., "factory_seconds":0.,
                     "busy_seconds":0., "money_seconds":0., "cp_blocked_seconds":0.,
                     "income":0., "income_complete":bool(row.get("income_complete")), "cursor":int(row.get("income_cursor",-1)), "max_gap":0.}
            self.players[player] = state
            return
        if frame <= state["last"]["frame"]: return  # Duplicate initial/final sample.
        previous = state["last"]
        seconds = (frame - previous["frame"]) / 5.
        state["max_gap"] = max(state["max_gap"], seconds)
        # Do not invent observation coverage across a stalled/disconnected host.
        if seconds <= 10:
            state["covered"] += seconds
            for key, field in [("farm_seconds","farms"),("share_seconds","share_sum"),
                               ("factory_seconds","factories"),("busy_seconds","busy"),("money_seconds","money")]:
                state[key] += previous[field]*seconds
            if previous["cp_limit"] > 0 and previous["cp_used"] >= previous["cp_limit"]:
                state["cp_blocked_seconds"] += seconds
        cursor = int(row.get("income_cursor",-1))
        complete = bool(row.get("income_complete")) and cursor >= state["cursor"]
        state["income_complete"] &= complete
        if complete:
            # Native monotonically identified payments, not cash deltas/refunds.
            seen = set()
            for payment in row.get("income_payments", []):
                serial = int(payment["serial"])
                if serial in seen or not state["cursor"] < serial <= cursor: continue
                seen.add(serial)
                if state["first"]["frame"] < int(payment["frame"]) <= frame:
                    state["income"] += number(payment["amount"])
        state.update(last=sample, samples=state["samples"]+1, cursor=max(cursor,state["cursor"]))

    def summary(self):
        players = []
        for player, state in sorted(self.players.items()):
            first, last = state["first"], state["last"]
            seconds = (last["frame"]-first["frame"])/5.
            covered = state["covered"]
            players.append({"player":player,"faction":state["faction"],"start_frame":first["frame"],
                "end_frame":last["frame"],"observed_seconds":seconds,"covered_seconds":covered,"samples":state["samples"],
                "coverage_fraction":ratio(covered,seconds),"max_sample_gap_seconds":state["max_gap"],
                "farm_share_time_mean":ratio(state["share_seconds"],state["farm_seconds"]),
                "farm_count_start":first["farms"],"farm_count_end":last["farms"],
                "real_income":state["income"] if state["income_complete"] else None,
                "real_income_per_second":ratio(state["income"],seconds) if state["income_complete"] else None,
                "income_complete":state["income_complete"],
                "factory_busy_fraction":ratio(state["busy_seconds"],state["factory_seconds"]),
                "factory_idle_seconds":state["factory_seconds"]-state["busy_seconds"],
                "average_cash":ratio(state["money_seconds"],covered),
                "cp_blocked_fraction":ratio(state["cp_blocked_seconds"],covered),
                "army_value_start":first["army_value"],"army_value_end":last["army_value"],
                "net_army_value_change":last["army_value"]-first["army_value"],
                "army_groups_start":first["army_groups"],"army_groups_end":last["army_groups"],
                "sufficient_window":seconds>=120 and bool(covered) and covered/seconds>=.9 and state["income_complete"]})
        return {"schema":VERSION,"players":players,"status":"measured" if players else "missing_telemetry",
                "affects_rewards":False,"sufficient_to_claim_strength":False,
                "interpretation":"Idle factories/cash are contextual, not automatic errors; net army value includes combat, healing and transfers, not gross production."}


def evaluate(rows, events=()):
    evaluation = EconomyEvaluation()
    for row in sorted(rows,key=lambda r:(int(r["frame"]),int(r["player"]))): evaluation.observe(row)
    result=evaluation.summary()
    seen=set()
    for player in result["players"]:
        orders={"accepted_train_orders":0,"accepted_train_nominal_cost":0.,"accepted_farm_orders":0,
                "farm_order_share_mean":None,"cancel_orders":0,"refused_orders":0}
        shares=[]
        for event in events:
            if event.get("head")!="spend" or int(event["player"])!=player["player"]: continue
            identity=(int(event["player"]),int(event.get("observed_frame",event["frame"])))
            if identity in seen: continue
            seen.add(identity)
            operation=event.get("operation",{})
            if not event.get("submitted"):
                orders["refused_orders"]+=1
                continue
            if operation.get("kind")=="train":
                orders["accepted_train_orders"]+=1
                orders["accepted_train_nominal_cost"]+=number(operation.get("cost",0))
            if operation.get("kind")=="build" and operation.get("economy"):
                orders["accepted_farm_orders"]+=1
                shares.append(number(operation["farm_share"]))
            if operation.get("kind")=="cancel": orders["cancel_orders"]+=1
        orders["farm_order_share_mean"]=ratio(sum(shares),len(shares))
        orders["interpretation"]="Accepted orders are not completed units/buildings or confirmed cash expenditure."
        player["dispatch"]=orders
    return result


def compare(baseline, candidate):
    left = {r["player"]:r for r in baseline["players"]}
    right = {r["player"]:r for r in candidate["players"]}
    comparable = bool(left) and left.keys()==right.keys() and all(
        left[p]["faction"]==right[p]["faction"] and abs(left[p]["start_frame"]-right[p]["start_frame"])<=5
        and abs(left[p]["end_frame"]-right[p]["end_frame"])<=5 for p in left)
    deltas = []
    if comparable:
        for p in left:
            metrics = {}
            for key in ("farm_share_time_mean","real_income_per_second","factory_busy_fraction",
                        "average_cash","cp_blocked_fraction","net_army_value_change"):
                a,b = left[p][key],right[p][key]
                metrics[key] = b-a if a is not None and b is not None else None
            for key in ("farm_order_share_mean","accepted_train_orders","accepted_train_nominal_cost"):
                a,b=left[p].get("dispatch",{}).get(key),right[p].get("dispatch",{}).get(key)
                metrics[key]=b-a if a is not None and b is not None else None
            deltas.append({"player":p,"faction":left[p]["faction"],"candidate_minus_baseline":metrics})
    return {"schema":VERSION,"matched_roster_and_window":comparable,"players":deltas,
            "sufficient_window":comparable and all(r["sufficient_window"] for r in list(left.values())+list(right.values())),
            "pairs":1,"sufficient_to_claim_strength":False,"automatic_winner":None}
