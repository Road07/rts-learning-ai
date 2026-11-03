"""Attributed, evidence-scoped YouTube notes. Never supplies action labels/orders."""
import json
from pathlib import Path


class YouTubeKnowledge:
    def __init__(self,path):
        self.data=json.loads(Path(path).read_text(encoding="utf-8"))
        if self.data.get("schema")!=1 or self.data.get("id")!="youtube-lessons-v1":
            raise ValueError("Invalid YouTube evidence catalogue")

    def context(self,features):
        if not isinstance(features,dict): return {"ready":False,"reason":"missing_observation"}
        seen=set(features.get("own_templates",{}))|set(features.get("visible_enemy_templates",{}))
        lessons=[x for x in self.data["lessons"] if not x["related_templates"] or seen.intersection(x["related_templates"])]
        faction={"FactionMen":"men","FactionDwarves":"dwarves","FactionWild":"goblins","FactionAngmar":"angmar"}.get(features.get("faction"))
        topics=[s for s in self.data["sources"] if s["id"]==faction]
        return {"ready":True,"catalogue":self.data["id"],"lesson_ids":[x["id"] for x in lessons],
                "source_links":[x["discussion_url"] for x in lessons],"guide_topic_count":sum(len(x["chapters"]) for x in topics),
                "affects_orders":False,"neural_weights_changed":False,"evidence":"source-scoped notes; no full transcript or video-state labels"}
