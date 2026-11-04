import json
from pathlib import Path

draft_path = Path("saves/silver_wolf/chronicle_drafts/maid_lusya.json")
with open(draft_path, "r", encoding="utf-8") as f:
    draft = json.load(f)

forced = 0
for entry in draft["entries"]:
    if entry.get("provenance") == "LLM_DRAFT":
        print("  Force-confirm: " + entry["entry_id"] + " (kind=" + entry["kind"] + ", confidence=" + str(entry.get("confidence")) + ")")
        entry["provenance"] = "AUTHOR_CONFIRMED"
        entry["confidence"] = None
        forced += 1

print("Total forced: " + str(forced))

with open(draft_path, "w", encoding="utf-8") as f:
    json.dump(draft, f, ensure_ascii=False, indent=2)
print("Draft saved")
