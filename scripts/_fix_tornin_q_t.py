"""USL-2 / ТЗ АРХИТЕКТОРУ: правки нового draft tavern_keeper_tornin Q-T3 + Q-T4.

Q-T3 (a): entry [12] EFFECT «Торнин избивает себя» — физическое самоповреждение.
  Автор fragment 22: «Тогда он бил не Люсю — он избивал себя» — ПСИХОЛОГИЧЕСКАЯ МЕТАФОРА.
  Master: «восстановить психологический смысл, не буквальное действие.
           Не создавать физическое событие самоповреждения.»
  Фикс: изменить kind на PORTRET + переформулировать statement на психологический смысл.

Q-T4 (a): entry [1] RELATIONSHIP «Торнин — человек, знакомый персонажа» — SPURIOUS_REFERENCE.
  Автор fragment 1: «Хозяин таверны» — нет «знакомый персонажа».
  Master: «удалить из активного draft».
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

DRAFT_PATH = Path("saves/Open_road/chronicle_drafts/tavern_keeper_tornin.json")


def main() -> int:
    if not DRAFT_PATH.exists():
        print(f"Draft не найден: {DRAFT_PATH}", file=sys.stderr)
        return 1

    bak_path = DRAFT_PATH.with_suffix(".json.bak_v2")
    shutil.copy(DRAFT_PATH, bak_path)
    print(f"[0] Backup: {bak_path}")

    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        draft = json.load(f)

    entries = draft["entries"]
    print(f"[1] Загружен draft: {len(entries)} entries")
    fixed = 0
    deleted = 0

    # Q-T3: найти entry с «избивает себя» (EFFECT) — изменить на PORTRET с психологическим смыслом
    print(f"\n[Q-T3] Фикс EFFECT «избивает себя» → PORTRET (психологический смысл):")
    for e in entries:
        text = json.dumps(e.get("payload", {}), ensure_ascii=False)
        if "избивает себя" in text and e.get("kind") == "EFFECT":
            old_sum = e.get("payload", {}).get("summary", "")
            print(f"  OLD kind=EFFECT, summary: {old_sum[:120]}...")
            # Меняем kind на PORTRET (psychological insight, не физическое действие)
            e["kind"] = "PORTRET"
            e["payload"] = {
                "statement": "Торнин бил не Люсю — он избивал себя (метафора вины: мозг зацепился за кружку как повод не сойти с ума от убийства двоих людей; кружка — это знак, повод выплеснуть ужас на того, кто слабее, потому что видеть причину в себе — значит повеситься на собственной стойке)",
                "traits": ["вина", "самообман", "психологическая метафора"],
                "_provenance": {
                    "source": "author_text fragment 22",
                    "note": "метафора саморазрушения — не физическое самоповреждение; автор: «он бил не Люсю — он избивал себя»",
                },
            }
            print(f"  NEW kind=PORTRET, statement: {e['payload']['statement'][:120]}...")
            fixed += 1
            break

    # Q-T4: найти entry [1] «Торнин — человек, знакомый персонажа» — удалить
    print(f"\n[Q-T4] Удаление SPURIOUS_REFERENCE entry «знакомый персонажа»:")
    new_entries = []
    for e in entries:
        text = json.dumps(e.get("payload", {}), ensure_ascii=False)
        if "знакомый персонажа" in text:
            print(f"  УДАЛЁН entry_id={e.get('entry_id', '?')[:12]}...")
            s = e.get("payload", {}).get("summary", "")
            print(f"  summary: {s}")
            deleted += 1
            continue
        new_entries.append(e)
    draft["entries"] = new_entries

    # Сохранение
    tmp_path = DRAFT_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    tmp_path.replace(DRAFT_PATH)
    print(f"\n[2] Draft сохранён: {DRAFT_PATH}")
    print(f"  Fixed: {fixed}, Deleted: {deleted}")

    # Верификация
    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        verify = json.load(f)
    print(f"\n[3] Верификация: {len(verify['entries'])} entries (было {len(entries)})")

    # Проверка Q-T3
    found_qt3 = False
    for e in verify["entries"]:
        text = json.dumps(e.get("payload", {}), ensure_ascii=False)
        if "избивает себя" in text or "избивал себя" in text:
            if e.get("kind") == "EFFECT":
                print(f"  ⚠ Q-T3: EFFECT «избивает себя» всё ещё в draft")
                found_qt3 = True
            elif e.get("kind") == "PORTRET":
                print(f"  ✅ Q-T3: изменено на PORTRET (психологический смысл)")
                found_qt3 = True
    if not found_qt3:
        print(f"  ✅ Q-T3: нет EFFECT «избивает себя» — решено")

    # Проверка Q-T4
    found_qt4 = False
    for e in verify["entries"]:
        text = json.dumps(e.get("payload", {}), ensure_ascii=False)
        if "знакомый персонажа" in text:
            found_qt4 = True
            break
    if not found_qt4:
        print(f"  ✅ Q-T4: SPURIOUS_REFERENCE удалена")
    else:
        print(f"  ⚠ Q-T4: SPURIOUS_REFERENCE всё ещё в draft")

    # Распределение по kind
    kinds = {}
    for e in verify["entries"]:
        k = e["kind"]
        kinds[k] = kinds.get(k, 0) + 1
    print(f"  Распределение: {kinds}")

    return 0


if __name__ == "__main__":
    sys.exit(main())