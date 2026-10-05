"""path: /project/reports/p0_gen_oracle_labels.py

Назначение: генерация gold-меток oracle-роутера (SR-1 Phase 1) из
    ЕДИНОГО источника ground truth — p0_rc_baseline (аудит P0-1,
    заморожен вердиктами Q-1/Q-2). Метки живут в экспериментальной зоне.
    Выход: reports/p0_oracle_labels.json {текст: PROV|ID|EMPTY|BOUNDARY};
    счётчики сверяются fail-loud (PROV=22, ID=3, EMPTY=55, BOUNDARY=10).
Зависимости: p0_rc_baseline (ground truth), stdlib.
Запуск: python reports/p0_gen_oracle_labels.py
"""

import json
from pathlib import Path
from typing import Dict

from p0_rc_baseline import _EXPECTED_COUNTS, _assert_invariants, _gold, _load_corpus

_OUT = Path(__file__).resolve().parent / "p0_oracle_labels.json"


def main() -> None:
    entries = _load_corpus()
    _assert_invariants(entries)
    labels: Dict[str, str] = {}
    counts: Dict[str, int] = {}
    for cls, text, _expected in entries:
        family = _gold(cls, text)
        # Дубль-текст («Ты знаешь, что меня зовут Мю?» в META и AB-META)
        # имеет одну gold-семью — консистентность гарантирует invariants.
        labels[text] = family
        counts[family] = counts.get(family, 0) + 1
    if counts != dict(_EXPECTED_COUNTS):
        raise RuntimeError(f"счётчики дрейфнули: {counts} (ожидалось {_EXPECTED_COUNTS})")
    _OUT.write_text(
        json.dumps(labels, ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )
    print(f"ИТОГО labels: {counts} -> {_OUT}")


if __name__ == "__main__":
    main()