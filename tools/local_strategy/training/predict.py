"""Offline inference with our trained network; reads an exported observed-state row."""
import argparse
import json
from pathlib import Path
from decision_net import DecisionNet

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--model", type=Path, required=True)
parser.add_argument("--example", type=Path, required=True, help="JSONL exported decision data")
parser.add_argument("--row", type=int, default=0)
args = parser.parse_args()
row = json.loads(args.example.read_text(encoding="utf-8").splitlines()[args.row])
network = DecisionNet.load(args.model)
print(json.dumps({"candidate_id": network.predict(row["observation"], row["candidates"]),
                  "backend": "openbfme-decision-net-v0", "model_required": False}))
