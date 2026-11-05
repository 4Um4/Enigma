"""USL-2 / ТЗ АРХИТЕКТОРУ: Задача A — точная правка guard_borko DESIRE_SEED #24.

Прошлый скрипт (_fix_guard_borko_draft.py) нашёл ПЕРВОЕ совпадение по строке
"хочет наблюдать за насилием без участия в нём" — но это была PORTRET entry #23
(не DESIRE_SEED). DESIRE_SEED #24 имеет entry_id=c5a0511cd1aa062e115a4e62c37ebdcd.

Этот скрипт:
1. Находит DESIRE_SEED по entry_id (точный идентификатор)
2. Проверяет, что kind=DESIRE_SEED (не PORTRET)
3. Восстанавливает оба компонента желания (наблюдать + мастурбировать)
4. Сохраняет provenance (не придумывает мотивы/причины)
5. Выводит diff before/after
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DRAFT_PATH = Path("saves/Open_road/chronicle_drafts/guard_borko.json")
TARGET_ENTRY_ID = "c5a0511cd1aa062e115a4e62c37ebdcd"
EXPECTED_KIND = "DESIRE_SEED"

OLD_STATEMENT = "хочет наблюдать за насилием без участия в нём"
NEW_STATEMENT = "хочет снова наблюдать за этим зрелищем и мастурбировать, не участвуя непосредственно в насилии"


def main() -> int:
    if not DRAFT_PATH.exists():
        print(f"Draft не найден: {DRAFT_PATH}", file=sys.stderr)
        return 1

    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        draft = json.load(f)

    print(f"[1] Загружен draft: {len(draft['entries'])} entries")
    print(f"[2] Поиск DESIRE_SEED по entry_id={TARGET_ENTRY_ID}")

    target = None
    for e in draft["entries"]:
        if e.get("entry_id") == TARGET_ENTRY_ID:
            target = e
            break

    if target is None:
        print(f"  Entry с entry_id={TARGET_ENTRY_ID} НЕ НАЙДЕНА")
        return 2

    print(f"  Найдена:")
    print(f"    kind: {target.get('kind')}")
    print(f"    entry_id: {target.get('entry_id')}")
    print(f"    current statement: {target.get('payload', {}).get('statement', '?')}")
    print(f"    provenance: {target.get('provenance')}")

    if target.get("kind") != EXPECTED_KIND:
        print(f"  ⚠ kind != {EXPECTED_KIND} (фактически {target.get('kind')})")
        print(f"     Это НЕ DESIRE_SEED — возможно, past script уже что-то сделал")
        return 3

    current_stmt = target.get("payload", {}).get("statement", "")
    if OLD_STATEMENT not in current_stmt:
        print(f"  ⚠ Старая строка '{OLD_STATEMENT}' не найдена в statement")
        print(f"     Возможно уже исправлено или statement другой")
        print(f"     Current: {current_stmt}")
        return 4

    print(f"\n[3] Применение правки:")
    print(f"  OLD: {OLD_STATEMENT}")
    print(f"  NEW: {NEW_STATEMENT}")

    target["payload"]["statement"] = NEW_STATEMENT
    print(f"  ✅ statement обновлён")

    # Сохранение (atomic)
    tmp_path = DRAFT_PATH.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(draft, f, ensure_ascii=False, indent=2)
    tmp_path.replace(DRAFT_PATH)
    print(f"\n[4] Draft сохранён: {DRAFT_PATH}")

    # Верификация
    with DRAFT_PATH.open("r", encoding="utf-8-sig") as f:
        verify = json.load(f)
    for e in verify["entries"]:
        if e.get("entry_id") == TARGET_ENTRY_ID:
            print(f"\n[5] Верификация:")
            print(f"  kind: {e.get('kind')}")
            print(f"  statement: {e.get('payload', {}).get('statement')}")
            if "мастурбировать" in e.get("payload", {}).get("statement", ""):
                print(f"  ✅ «мастурбировать» присутствует")
            else:
                print(f"  ⚠ «мастурбировать» ОТСУТСТВУЕТ")
            break

    print(f"\n[6] Дополнительно: ВСЕ entries со словом «мастурбир» (для аудита ТЗ):")
    found = 0
    for e in verify["entries"]:
        payload_str = json.dumps(e.get("payload", {}), ensure_ascii=False)
        if "мастурбир" in payload_str.lower():
            found += 1
            print(f"  [{found}] kind={e.get('kind')}, entry_id={e.get('entry_id')[:12]}...")
            print(f"      payload: {payload_str[:200]}")
    print(f"  Всего: {found}")

    return 0


if __name__ == "__main__":
    sys.exit(main())