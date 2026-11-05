"""P0 FIX: blacksmith_orm draft — dangling white_spot 'assault_on_lusya_target'.

Мой AUTHOR_AUTHORED EVENT (Q1 fix) создал object_id с WHITE_SPOT ref,
но не создал WhiteSpot entity в doc.white_spots.
Валидатор validate_document (line 362) ловит dangling white_spot.

Фикс: заменить WHITE_SPOT ref на RESOLVED maid_lusya (maid_lusya — известный NPC в roster).
"""
import json, shutil, sys
from pathlib import Path

DRAFT_PATH = Path("saves/Open_road/chronicle_drafts/blacksmith_orm.json")
TARGET_ENTRY_ID = "aaabe6ecd6b33576641e21b62d5430f8"

def main():
    if not DRAFT_PATH.exists():
        print(f"Draft не найден: {DRAFT_PATH}", file=sys.stderr)
        return 1
    bak = DRAFT_PATH.with_suffix(".json.bak_dangling")
    shutil.copy(DRAFT_PATH, bak)
    print(f"[0] Backup: {bak}")
    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        draft = json.load(f)
    print(f"[1] Загружен draft: {len(draft['entries'])} entries")
    for e in draft["entries"]:
        if e.get("entry_id") == TARGET_ENTRY_ID:
            old_obj = e.get("object_id", {})
            print(f"  OLD object_id: {old_obj}")
            e["object_id"] = {"ref_kind": "RESOLVED", "npc_id": "maid_lusya", "white_spot_id": None, "name_hint": ""}
            print(f"  NEW object_id: {e['object_id']}")
            break
    tmp = DRAFT_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    tmp.replace(DRAFT_PATH)
    print(f"[2] Draft сохранён")
    return 0

if __name__ == "__main__":
    sys.exit(main())