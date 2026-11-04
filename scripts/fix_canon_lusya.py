import json
from pathlib import Path

canon_path = Path("config/npc/chronicles/maid_lusya.json")
with open(canon_path, "r", encoding="utf-8-sig") as f:
    canon = json.load(f)

# maid_lusya game_start_age = 14 (известно из старого канона)
old_game_start_age = canon.get("game_start_age")
print("Current game_start_age: " + str(old_game_start_age))

if old_game_start_age is None:
    canon["game_start_age"] = 14
    print("Restored game_start_age = 14")
else:
    print("game_start_age already set: " + str(old_game_start_age))

# Также чиним valence для RELATIONSHIP с neutral/None → positive/negative
fixed_valence = 0
for entry in canon["entries"]:
    if entry["kind"] == "RELATIONSHIP":
        payload = entry.get("payload", {})
        valence = payload.get("valence")
        nature = payload.get("nature", "")
        if valence in (None, "neutral", ""):
            # Эвристика: если nature содержит негативные слова → negative, иначе positive
            negative_markers = ["вражда", "страх", "зависимость", "покорность"]
            if any(m in nature.lower() for m in negative_markers):
                payload["valence"] = "negative"
            else:
                payload["valence"] = "positive"
            fixed_valence += 1
            print("  Fixed valence for " + entry["entry_id"] + ": nature=" + nature + " -> " + payload["valence"])

print("Total valence fixed: " + str(fixed_valence))

with open(canon_path, "w", encoding="utf-8-sig") as f:
    json.dump(canon, f, ensure_ascii=False, indent=2)
print("Canon saved")
