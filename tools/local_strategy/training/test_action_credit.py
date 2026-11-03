import copy
import unittest
from test_rewards import sample,TUNING
from action_credit import calculate, key


def asset(id=1, **extra):
    result={"id":id,"template":"unit","health":1.,"cost":200.,"structure":False,"economy":False,"complete":True,"combat":True,"x":0.,"y":0.}
    result.update(extra); return result


def row(frame, **extra):
    result=sample(frame)
    result.update(credit_schema="action-credit-v1",own_assets=[asset()],ally_assets=[],owned_present_ids=[1],income_payments=[])
    result["visible_enemies"][0].update(x=0,y=0)
    result.update(extra); return result


def event(kind="attack",head="tactical",frame=0, **extra):
    operation={"kind":kind,"units":[1],"target":99,"x":0,"y":0}
    operation.update(extra)
    return {"player":3,"observed_frame":frame,"frame":frame,"head":head,"submitted":True,"operation":operation}


class CreditChecks(unittest.TestCase):
    def test_actor_scope_and_real_costs_determine_trade_value(self):
        end=row(60,own_assets=[asset(health=.7,cost=3000)])
        end["visible_enemies"][0].update(health=.5,cost=100)
        values,_=calculate(TUNING,[row(0,own_assets=[asset(cost=3000)]),end],[event()])
        result=values[key(3,0,"tactical")]
        self.assertLess(result["reward"],0)
        self.assertAlmostEqual(result["components"]["combat_value"],.05)
        end["own_assets"][0]["combat"]=False
        values,_=calculate(TUNING,[row(0,own_assets=[asset(cost=3000)]),end],[event()])
        self.assertNotIn("combat_value",values[key(3,0,"tactical")]["components"])

    def test_fog_discovery_and_missing_units_never_fabricate_damage(self):
        hidden=row(20,visible_enemies=[],own_assets=[],owned_present_ids=[1],own_units_lost=1)
        revealed=row(40,own_units_lost=1); revealed["visible_enemies"][0]["health"]=.1
        values,_=calculate(TUNING,[row(0),hidden,revealed,row(60,visible_enemies=[],own_units_lost=1)],[event()])
        self.assertEqual(values[key(3,0,"tactical")]["reward"],0)

    def test_income_requires_birth_payment_and_long_enough_horizon(self):
        farm=asset(2,template="farm",structure=True,economy=True,combat=False,cost=300)
        payment={"serial":1,"object":2,"frame":10,"amount":25}
        rows=[row(0),row(5,own_assets=[asset(),farm]),row(10,own_assets=[asset(),farm],income_payments=[payment]),row(30,own_assets=[asset(),farm],income_payments=[payment])]
        build=event("build","spend",template="farm",before_ids=[1],cost=300)
        values,_=calculate(TUNING,rows,[build])
        self.assertFalse(values[key(3,0,"spend")]["matured"])
        self.assertEqual(values[key(3,0,"spend")]["reward"],0)
        values,_=calculate(TUNING,rows+[row(900,own_assets=[asset(),farm])],[build])
        self.assertAlmostEqual(values[key(3,0,"spend")]["components"]["economy_return"],25/1300)
        self.assertAlmostEqual(values[key(3,0,"spend")]["realized_roi"],25/300)
        values,_=calculate(TUNING,[row(0),row(900,money=100000,earned=100000)],[build])
        self.assertEqual(values[key(3,0,"spend")]["reward"],0)

    def test_power_needs_trigger_and_observed_effect(self):
        spell=event("power","spend",producer=1,template="blast",power_before=0)
        end=row(60,own_assets=[asset(combat=False)]); end["visible_enemies"][0]["health"]=.5
        values,_=calculate(TUNING,[row(0,own_assets=[asset(combat=False)]),end],[spell])
        self.assertEqual(values[key(3,0,"spend")]["reward"],0)
        end["power_triggers"]=[{"source":1,"name":"blast","triggers":1}]
        values,_=calculate(TUNING,[row(0,own_assets=[asset(combat=False)]),end],[spell])
        self.assertGreater(values[key(3,0,"spend")]["reward"],0)

    def test_heal_cycles_cannot_exceed_once_observed_hostile_damage(self):
        spell=event("power","spend",frame=1,producer=1,template="heal",power_before=0,target=1)
        powers=[{"source":1,"name":"heal","triggers":1}]
        rows=[row(0),row(2,own_assets=[asset(health=.5)],power_triggers=powers)]
        for frame,hp in [(3,1),(4,.5),(5,1),(6,.5),(7,1)]: rows.append(row(frame,own_assets=[asset(health=hp)],power_triggers=powers))
        rows.append(row(61,power_triggers=powers))
        values,_=calculate(TUNING,rows,[spell])
        result=values[key(3,1,"spend")]
        self.assertAlmostEqual(result["components"]["verified_repair_recovery"],.05)
        values,_=calculate(TUNING,[row(0,own_assets=[asset(health=.5)]),row(61,power_triggers=powers)],[spell])
        self.assertEqual(values[key(3,1,"spend")]["reward"],0)

    def test_shaping_budget_and_terminal_mass_do_not_grow_with_commands(self):
        end=row(120,won=True); end["visible_enemies"][0]["health"]=0.
        events=[event(frame=i) for i in range(50)]
        values,_=calculate(TUNING,[row(0),row(55),end],events)
        self.assertAlmostEqual(sum(v["terminal_share"] for v in values.values()),10.)
        self.assertLessEqual(sum(sum(abs(x) for x in v["components"].values()) for v in values.values()),1.+1e-10)

    def test_partial_or_rejected_actions_do_not_receive_local_credit(self):
        end=row(60); end["visible_enemies"][0]["health"]=.2
        rejected=event(); rejected["submitted"]=False
        values,_=calculate(TUNING,[row(0),end],[rejected])
        self.assertEqual(values[key(3,0,"tactical")]["reward"],0)
        broken=row(60,income_complete=False)
        with self.assertRaises(ValueError): calculate(TUNING,[row(0),broken],[event()])

    def test_produced_unit_contribution_is_split_without_double_reward(self):
        factory=asset(10,template="factory",structure=True,combat=False)
        recruit=asset(2,template="recruit")
        rows=[row(0,own_assets=[factory]),row(5,own_assets=[factory,recruit])]
        hit=row(20,own_assets=[factory,dict(recruit,x=2000)]); hit["visible_enemies"][0].update(health=.5,x=2000)
        end=copy.deepcopy(hit); end.update(frame=450,income_cursor=450)
        train=event("train","spend",producer=10,template="recruit",before_ids=[10])
        attack=event(frame=10,units=[2])
        values,_=calculate(TUNING,rows+[hit,end],[train,attack])
        self.assertAlmostEqual(values[key(3,0,"spend")]["components"]["production_combat_value"],.15)
        self.assertAlmostEqual(values[key(3,10,"tactical")]["components"]["combat_value"],.35)

    def test_scout_information_only_pays_when_used(self):
        scout=event("scout")
        start=row(0,visible_enemies=[],own_assets=[asset(combat=False)])
        seen=row(10,own_assets=[asset(combat=False)])
        hit=row(20); hit["visible_enemies"][0]["health"]=.5
        end=copy.deepcopy(hit); end.update(frame=150,income_cursor=150)
        values,_=calculate(TUNING,[start,seen,row(150,own_assets=[asset(combat=False)])],[scout])
        self.assertEqual(values[key(3,0,"tactical")]["reward"],0)
        values,_=calculate(TUNING,[start,seen,hit,end],[scout,event(frame=15)])
        self.assertGreater(values[key(3,0,"tactical")]["components"]["information_used_in_combat"],0)

    def test_support_measures_combat_and_home_cost(self):
        home=asset(3,structure=True,combat=False,cost=500)
        ally=asset(4,structure=True,combat=False)
        start=row(0,own_assets=[asset(),home],ally_assets=[ally])
        hit=row(20,own_assets=[asset(),dict(home,health=.5)],ally_assets=[ally])
        hit["visible_enemies"][0]["health"]=.8
        end=copy.deepcopy(hit); end.update(frame=90,income_cursor=90)
        values,_=calculate(TUNING,[start,hit,end],[event("help")])
        components=values[key(3,0,"tactical")]["components"]
        self.assertGreater(components["ally_support_value"],0)
        self.assertLess(components["support_home_cost"],0)


if __name__ == "__main__": unittest.main()
