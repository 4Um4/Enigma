"""USL-2: Очистка historical_age из канонов 5 NPC.

Проблема: LLM извлекла возрастные якоря (historical_age=16, 17, 22, 24...)
из биографий, но game_start_age=null (Master запретил заполнять без авторских
подтверждений). build_seed_memories падает: SeederError "N возраст-якорей
без game_start_age".

Решение: установить historical_age=null для всех EVENT entries в канонах
5 NPC (blacksmith_orm, guard_borko, merchant_goran, tavern_keeper_tornin,
thief_shadow). Это теряет временные якоря, но:
- Не выдумываем game_start_age (соблюдаем Master directive)
- build_seed_memories не падает (anchors=0 → no SeederError)
- EVENT entries с historical_age=null → day=SENTINEL_DAY=-1000
  (как в maid_lusya для events без age)
- События сохраняются, просто без точной даты

maid_lusya НЕ трогаем (game_start_age=14, age anchors валидны).
"""
import json
import shutil
from pathlib import Path

CANON_DIR = Path("../config/npc/chronicles")
NPCS = ["blacksmith_orm", "guard_borko", "merchant_goran",
        "tavern_keeper_tornin", "thief_shadow"]

total_cleared = 0
for npc in NPCS:
    f = CANON_DIR / f"{npc}.json"
    if not f.exists():
        print(f"  {npc}: canon not found")
        continue

    # Backup
    bak = f.with_suffix(".json.bak_age")
    shutil.copy(f, bak)

    with f.open("r", encoding="utf-8-sig") as fh:
        doc = json.load(fh)

    cleared = 0
    for e in doc.get("entries", []):
        if e.get("historical_age") is not None:
            e["historical_age"] = None
            cleared += 1
        # Also clean payload.age (LLM put age in payload too)
        if "payload" in e and "age" in e["payload"] and e["payload"]["age"] is not None:
            e["payload"]["age"] = None
            # Don't double-count (age in payload is separate from historical_age)

    if cleared > 0:
        tmp = f.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
        tmp.replace(f)

    print(f"  {npc}: {cleared} historical_age cleared")
    total_cleared += cleared

print(f"\nTotal cleared: {total_cleared}")