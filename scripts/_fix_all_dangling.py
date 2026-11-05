"""P0 FIX v2: blacksmith_orm — найти и заменить ВСЕ dangling WHITE_SPOT refs.

Проблема: мои AUTHOR_AUTHORED entries создавали WHITE_SPOT object_id для
NPC, которые известны в roster (maid_lusya, tavern_keeper_tornin).
Валидатор validate_document ловит dangling white_spot — нет WhiteSpot entity.

Фикс: заменить все WHITE_SPOT refs на RESOLVED для известных NPC.
"""
import json
import shutil
import sys
from pathlib import Path

DRAFT_PATH = Path("../saves/Open_road/chronicle_drafts/blacksmith_orm.json")

# Known NPC ids in roster
KNOWN_NPCS = {"maid_lusya", "guard_borko", "blacksmith_orm", "merchant_goran",
              "tavern_keeper_tornin", "thief_shadow"}

# Map name_hint → npc_id (для white_spot refs с name_hint)
NAME_HINT_TO_NPC = {
    "Люся": "maid_lusya",
    "Торнин": "tavern_keeper_tornin",
    "Борко": "guard_borko",
    "Орм": "blacksmith_orm",
    "Горан": "merchant_goran",
    "Тень": "thief_shadow",
}


def main():
    if not DRAFT_PATH.exists():
        print(f"Draft не найден: {DRAFT_PATH}", file=sys.stderr)
        return 1

    bak = DRAFT_PATH.with_suffix(".json.bak_dangling_v2")
    shutil.copy(DRAFT_PATH, bak)
    print(f"[0] Backup: {bak}")

    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        draft = json.load(f)

    print(f"[1] Загружен draft: {len(draft['entries'])} entries")

    # Найти все entries с object_id.white_spot_id (WHITE_SPOT ref)
    fixed = 0
    for e in draft["entries"]:
        obj = e.get("object_id")
        if not obj or not isinstance(obj, dict):
            continue
        if obj.get("ref_kind") != "WHITE_SPOT":
            continue

        ws_id = obj.get("white_spot_id", "")
        name_hint = obj.get("name_hint", "")

        # Проверить — есть ли WhiteSpot entity с этим white_spot_id?
        ws_exists = any(ws.get("id") == ws_id for ws in draft.get("white_spots", []))
        if ws_exists:
            continue  # WhiteSpot entity существует — не dangling

        # Dangling — попробовать разрешить через name_hint
        npc_id = NAME_HINT_TO_NPC.get(name_hint)
        if npc_id and npc_id in KNOWN_NPCS:
            print(f"  FIXED entry_id={e.get('entry_id', '?')[:12]}... "
                  f"WHITE_SPOT '{ws_id}' → RESOLVED {npc_id}")
            e["object_id"] = {
                "ref_kind": "RESOLVED",
                "npc_id": npc_id,
                "white_spot_id": None,
                "name_hint": "",
            }
            fixed += 1
        else:
            print(f"  ⚠ UNRESOLVED entry_id={e.get('entry_id', '?')[:12]}... "
                  f"WHITE_SPOT '{ws_id}' name_hint='{name_hint}' — нет в roster")
            # Оставить как есть — нужен manual resolve или WhiteSpot entity

    # Сохранить
    tmp = DRAFT_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    tmp.replace(DRAFT_PATH)
    print(f"\n[2] Draft сохранён. Fixed: {fixed}")

    # Верификация
    import subprocess
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); "
         "from app.api.routes_chronicle import _get_store; "
         "from app.services.chronicle.chronicle_store import validate_document; "
         "store = _get_store(); doc = store.load_draft('Open_road', 'blacksmith_orm'); "
         "validate_document(doc, require_canonical_clean=False); "
         "print('VALIDATE: OK')"],
        capture_output=True, text=True, cwd=str(Path(__file__).parent.parent / "backend"),
        timeout=10
    )
    print(f"\n[3] Верификация:")
    print(f"  stdout: {result.stdout.strip()}")
    if result.returncode != 0:
        print(f"  stderr: {result.stderr.strip()[:500]}")
    return 0 if fixed > 0 or result.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())