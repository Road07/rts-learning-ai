"""Score observed legal recruits within one idle producer. Log only, no orders."""
import hashlib
from collections import defaultdict
import numpy as np
from human_state_policy import encode as state_encode

INPUTS=170


def flags(knowledge,name):
    seen=set(); words=set()
    while name and name not in seen:
        seen.add(name); obj=knowledge.template(name)
        if not obj: return None
        for value in obj["fields"].get("KindOf",[]): words.update(str(value["value"]).split())
        name=obj["parent"]
    return words


def regular_unit(knowledge,name):
    kind=flags(knowledge,name)
    return kind is not None and not (kind & {"HERO","DOZER","STRUCTURE"}) and not name.startswith("CreateAHero")


ROLES=["swords","pikes","ranged","cavalry","siege","other"]

def role(knowledge,name):
    kind=flags(knowledge,name)
    if not kind or kind & {"HERO","DOZER","STRUCTURE"}: return 5
    if "CAVALRY" in kind: return 3
    if "PIKE" in kind: return 1
    if "ARCHER" in kind: return 2
    if "SIEGEENGINE" in kind or "SIEGE_ENGINE" in kind: return 4
    # Summoners and special units are not silently treated as swordsmen.
    obj=knowledge.template(name)
    if obj and "HORDE" not in kind and any("ThrallMaster" in str(f["value"]) for r in obj["rules"] for f in r["fields"]): return 5
    if "INFANTRY" in kind and "CAN_ATTACK" in kind: return 0
    return 5

def role_counts(knowledge,templates):
    counts=np.zeros(6,np.float32)
    for name,n in templates.items(): counts[role(knowledge,name)]+=n
    return counts

def encode(features,option,knowledge):
    x=np.zeros(INPUTS,np.float32)
    own=role_counts(knowledge,features["own_templates"])
    enemy=role_counts(knowledge,features["visible_enemy_templates"])
    x[:4]=np.minimum(1,np.log1p(own[:4])/np.log(33))
    x[4:8]=np.minimum(1,np.log1p(enemy[:4])/np.log(33))
    money=float(features["money"]);cost=float(option["cost"])
    if not np.isfinite(cost) or cost<0: raise ValueError("Invalid option price")
    x[8:12]=[min(1,np.log1p(money)/np.log(100001)),min(1,features["cp_used"]/2000),min(1,features["cp_limit"]/2000),min(1,max(0,features["cp_limit"]-features["cp_used"])/1000)]
    category=role(knowledge,option["template"]);x[12+category]=1
    duration=knowledge.declared_scalar(option["template"],"BuildTime")
    x[18:26]=[min(1,np.log1p(cost)/np.log(10001)),min(1,cost/max(1,money)),min(1,np.log1p(duration["value"])/np.log(301)) if duration else 0,float(duration is not None),min(1,np.log1p(own[category])/np.log(33)),min(1,np.log1p(enemy[category])/np.log(33)),float(option.get("queue_count",0)==0),float(category<4)]
    if not np.isfinite(x).all(): raise ValueError("Invalid role production features")
    return x


class ProductionPolicy:
    def __init__(self,path,knowledge):
        self.knowledge=knowledge
        with np.load(path,allow_pickle=False) as data:
            if int(data["schema"])!=1 or "feature_encoding" not in data or str(data["feature_encoding"].item())!="roles-v2": raise ValueError("Invalid production checkpoint")
            self.factions=["FactionMen","FactionElves","FactionDwarves","FactionWild","FactionMordor","FactionIsengard","FactionAngmar"]
            self.model_name=str(data["model_name"].item())
            self.w={key:data[key].copy() for key in ["w1","b1","w2","b2"]}
        expected={"w1":(INPUTS,24),"b1":(24,),"w2":(24,1),"b2":(1,)}
        if any(v.shape!=expected[k] or not np.isfinite(v).all() for k,v in self.w.items()): raise ValueError("Invalid production weights")

    def scores(self,features,options):
        x=np.stack([encode(features,o,self.knowledge) for o in options])
        s=(np.tanh(x@self.w["w1"]+self.w["b1"])@self.w["w2"]+self.w["b2"]).ravel()
        p=np.exp(s-s.max());return p/p.sum()

    def shadow(self,features,options):
        result={"model":self.model_name,"mode":"shadow","controls_game":False,"producers":[]}
        if not isinstance(features,dict) or features.get("faction") not in self.factions:
            return {**result,"ready":False,"reason":"missing_state_or_untrained_faction"}
        groups=defaultdict(list);seen=set()
        for o in options:
            if o.get("kind")!="train" or int(o.get("queue_count",-1))!=0 or o["cost"]>features["money"] or not regular_unit(self.knowledge,o["template"]): continue
            key=(o["producer"],o["template"])
            if key in seen: continue
            seen.add(key)
            groups[o["producer"]].append(o)
        for producer,choices in groups.items():
            if len(choices)<2: continue  # No credit for a forced choice.
            p=self.scores(features,choices); chosen=choices[int(p.argmax())]
            result["producers"].append({"producer":producer,"recommended_id":chosen["id"],"template":chosen["template"],"role":ROLES[role(self.knowledge,chosen["template"])] ,
                                         "alternatives":[{"id":o["id"],"template":o["template"],"probability":float(v)} for o,v in zip(choices,p)]})
        return {**result,"ready":bool(result["producers"]),"reason":"observed_choices" if result["producers"] else "no_idle_producer_with_multiple_choices"}
