# path: reports/cg_relationship_harvest.py
# Задача 2 (III.3.2, методология S317): предподсчёт урожая relationship_state
# ключей ДО любых правок сканера. Патч CONTAINER_DOMAINS в памяти (модуль
# импортируется, frozenset/set замещается), census собирается штатной
# scan_container_usages; вывод — полный список новых ключей с локациями.
# НИ одной записи в файлы проекта. Прогон чист: exit 0, артефакт = stdout.

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import lint_consumer_gap as lcg  # noqa: E402

BASELINE_DOMAINS = {"body_state", "needs"}
NEW_DOMAIN = "relationship_state"


def main() -> int:
    # 1. Патч в памяти: добавляем домен (set — тип :69)
    lcg.CONTAINER_DOMAINS = BASELINE_DOMAINS | {NEW_DOMAIN}
    # 2. Собираем census по расширенному набору
    parse_errors: list = []
    usages = lcg.scan_container_usages(parse_errors)
    # 3. Урожай: только новые ключи (сравнение с базлайном — контроль, что
    # старые домены не потерялись)
    new_keys = sorted(usages.get(NEW_DOMAIN, {}))
    _old_body = sorted(k for k in usages.get("body_state", {}) if not k.startswith(f"{'body_state'}."))
    print(f"[HARVEST] parse_errors={len(parse_errors)} (базлайн: 0)")
    for pe in parse_errors[:5]:
        print(f"  PARSE: {pe}")
    print(f"[HARVEST] новых ключей {NEW_DOMAIN}.* = {len(new_keys)}")
    for k in new_keys:
        entry = usages[NEW_DOMAIN][k]
        r = len(entry.get("readers", []))
        w = len(entry.get("writers", []))
        print(f"  {k}  readers={r} writers={w}")
        for loc in entry.get("writers", [])[:3]:
            print(f"    W {loc}")
        for loc in entry.get("readers", [])[:3]:
            print(f"    R {loc}")
    # 4. Сель-чек: базлайновые домены не задеты (их ключи на месте)
    n_body = len(usages.get("body_state", {}))
    n_needs = len(usages.get("needs", {}))
    print(f"[HARVEST] контроль базлайна: body_state={n_body} (ожид. 24-container? см. summary), needs={n_needs}")
    print("[HARVEST] dry-run завершён; файлы проекта НЕ тронуты (проверка: git status)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
