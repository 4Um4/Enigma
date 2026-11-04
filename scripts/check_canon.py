import json
from pathlib import Path
from collections import Counter

canon_path = Path("config/npc/chronicles/maid_lusya.json")
with open(canon_path, "r", encoding="utf-8-sig") as f:
    canon = json.load(f)

print("Canon entries: " + str(len(canon["entries"])))
print("canonical_version: " + str(canon.get("canonical_version")))
print("")
print("=== Kinds ===")
kinds = Counter(e["kind"] for e in canon["entries"])
for k, v in kinds.most_common():
    print("  " + k + ": " + str(v))
print("")

rel_resolved = sum(1 for e in canon["entries"] if e["kind"] == "RELATIONSHIP" and e.get("object_id") and e["object_id"].get("ref_kind") == "RESOLVED")
rel_total = sum(1 for e in canon["entries"] if e["kind"] == "RELATIONSHIP")
print("RELATIONSHIP resolved: " + str(rel_resolved) + " / " + str(rel_total))

trauma_triggers = sum(1 for e in canon["entries"] if e["kind"] == "EFFECT" and e.get("payload", {}).get("effect_kind") == "trauma" and e.get("payload", {}).get("triggers"))
trauma_total = sum(1 for e in canon["entries"] if e["kind"] == "EFFECT" and e.get("payload", {}).get("effect_kind") == "trauma")
print("trauma with triggers: " + str(trauma_triggers) + " / " + str(trauma_total))

beliefs_type = sum(1 for e in canon["entries"] if e["kind"] == "BELIEF_SEED" and e.get("payload", {}).get("belief_type"))
beliefs_total = sum(1 for e in canon["entries"] if e["kind"] == "BELIEF_SEED")
print("BELIEF_SEED with type: " + str(beliefs_type) + " / " + str(beliefs_total))
