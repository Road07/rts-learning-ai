"""Public retail rule retrieval; never pretends source declarations are live stats."""
import json
from pathlib import Path


class MechanicsKnowledge:
    def __init__(self,path):
        self.data=json.loads(Path(path).read_text(encoding="utf-8"))
        if self.data.get("schema")!=1 or len(self.data.get("factions",{}))!=7:
            raise ValueError("Invalid mechanics catalogue")

    def template(self,name):
        return self.data["objects"].get(name)

    def declared_scalar(self,name,key):
        # Only a single local declaration with a literal/resolved macro is exposed.
        entry=self.template(name)
        if not entry or entry["kind"]!="Object": return None
        values=entry["fields"].get(key,[])
        if len(values)!=1 or not isinstance(values[0]["value"],(int,float)): return None
        return values[0]

    def armor_fraction(self,name,damage_type):
        armor=self.data["armor"].get(name)
        if not armor: return None
        value=armor.get(damage_type,armor.get("DEFAULT"))
        return value["percent"]/100 if value else None

    def context(self,features):
        if not isinstance(features,dict): return {"ready":False,"reason":"missing_observation"}
        result={"ready":True,"catalogue":self.data["id"],"mode":"public_source_facts",
                "faction":features.get("faction"),"own":{},"visible_enemy":{},"unresolved":[],
                "affects_orders":False,"neural_weights_changed":False,"native_cost_checks":[]}
        for key,out in [("own_templates","own"),("visible_enemy_templates","visible_enemy")]:
            for name in sorted(features.get(key,{}))[:24]:
                entry=self.template(name)
                if not entry:
                    result["unresolved"].append(name); continue
                result[out][name]={"count":features[key][name],"kind":entry["kind"],"parent":entry["parent"],
                                  "declared_cost":self.declared_scalar(name,"BuildCost"),
                                  "declared_build_time":self.declared_scalar(name,"BuildTime"),
                                  "armor_sets":entry["armor_sets"],"weapon_sets":entry["weapon_sets"],
                                  "runtime_effective_stats_verified":False}
                cost=self.declared_scalar(name,"BuildCost")
                native=features.get("public_template_costs",{}).get(name)
                if cost and native is not None:
                    result["native_cost_checks"].append({"template":name,"declared":cost["value"],"native":native,"match":cost["value"]==native})
        return result
