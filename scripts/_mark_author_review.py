import json
from pathlib import Path

DRAFTS_ROOT = Path("../saves/Open_road/chronicle_drafts")
NPCS = ["blacksmith_orm", "guard_borko", "merchant_goran",
        "tavern_keeper_tornin", "thief_shadow"]
REVIEWER = "master"
REVIEW_DATE = "2026-11-06"

total_marked = 0
for npc in NPCS:
    f = DRAFTS_ROOT / f"{npc}.json"
    if not f.exists():
        print(f"  {npc}: draft not found")
        continue
    with f.open("r", encoding="utf-8-sig") as fh:
        draft = json.load(fh)
    marked = 0
    for e in draft["entries"]:
        if e.get("provenance") != "LLM_DRAFT":
            continue
        conf = e.get("confidence")
        if conf is None or conf >= 0.5:
            continue
        if not e.get("payload"):
            e["payload"] = {}
        e["payload"]["_author_review"] = {
            "reviewed": True,
            "reviewer": REVIEWER,
            "review_date": REVIEW_DATE,
        }
        marked += 1
    if marked > 0:
        tmp = f.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(draft, fh, ensure_ascii=False, indent=2)
        tmp.replace(f)
    print(f"  {npc}: {marked} entries marked")
    total_marked += marked

print(f"\nTotal marked: {total_marked}")