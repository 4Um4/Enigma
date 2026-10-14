from __future__ import annotations

# reports/det2_close.py
"""
Одноразовый доковый скрипт закрытия DET-2 (§17.8 чекбокс с числами и
ограничениями + §10-строка). Гейты: якорь-строки ровно 1 раз; ABORT до
записи; пары БЫЛО/СТАЛО. После коммита НЕ перезапускать.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "ENIGMA_ROADMAP_v4_7.md"


def _abort(msg: str) -> None:
    print(f"[ABORT] {msg}")
    print("[ABORT] Стоп ДО записи: файл не изменён.")
    sys.exit(1)


def _load(p: Path) -> tuple[str, bool]:
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig" if bom else "utf-8"), bom


def _save(p: Path, text: str, bom: bool) -> None:
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))


DET2_OLD = "- [ ] **DET-2 [реализуется] Дешёвый детерминированный checksum** — первое действие = собственное измерение стоимости (число «2,4% тика» — из формулировки вердикта; грепом reports/ не локализовано, до измерения считать неподтверждённым); канонический контракт состояния (какие поля входят); стабильное представление без зависимости от порядка словарей и особенностей сериализации; бинарная канонизация/инкрементный хеш — только по измерениям на репрезентативной сцене; критерий принятия: доказанное равенство хешей эквивалентного состояния + обнаружение внесённых изменений + приемлемая стоимость; при подтверждении — частота проверки 1/100 → 1/1."
DET2_NEW = "- [x] **DET-2 [закрыт: реализуется→проверено]** ✅ Дешёвый детерминированный checksum (код-коммит 83b092af): измерение reports/det2_measure.json — median_tick_ms=38.47; share_json_1of1=0.583%; share_sha_1of1=0.521%; условия: сцена 6 NPC, MockProvider, production idle_tick, медианы; прежний claim «~2.4%» (tick_orchestrator:2325-комментарий, S265) НЕ подтверждён для этих условий (завышение ~4x) — НЕ объявляется ложным для других машин/сцен, не экстраполируется; при масштабировании мира стоимость перепроверяется на репрезентативной сцене. Решение (по числам, вердикт Мастера): probe INV-TEMPORAL-ISOLATION 1/100 → 1/1; builtin hash() → hashlib.sha256 (стабильный межпроцессный дайджест); контракт сериализации подтверждён зондом (payload 1945 значений — 100% стабильный JSON, OTHER=0; sort_keys=True закрывает порядок словарей; default=str — страховка вне фактического payload); бинарная канонизация НЕ требуется по измерению (msgpack/struct не вносятся). Тесты 4/4: детект изменения поля; эквивалентность порядка вставки; одинаковый снимок в 3 процессах с разными PYTHONHASHSEED; probe фактически 1/1. Свидетельство 1/1: det2_evidence.json (счётчик _state_hash_ticks, живой прогон 20/20). Оговорка (вердикт п.3): частота 1/1 — сплошная ЧАСТОТА probe, НЕ полнота самого инварианта. ReplayRecorder и :1925 (телеметрия drift-сводки) не тронуты. CI-тест стоимости не добавлен — артефакт фактом, не гейтом."

JOURNAL_ANCHOR = "- ✅ **DET-1 (§17.8 / вердикт III.1)** — детерминизм AdaptiveTickLoader: баг M-24 доказан (LOD-решение на wall-clock → другой мир при replay на другой машине/нагрузке) и закрыт — вход npc_count, wall-clock = телеметрия §15.2, упавший тик не кормит гистерезис;тест 4/4; IPT 53/0."
JOURNAL_LINE = "- ✅ **DET-2 (§17.8 / вердикт III.2)** — checksum: измерение (тик 38.47 мс; 1/1 = 0.58%/0.52% json/sha256; claim 2.4% не подтверждён для условий замера, не экстраполируется) → probe 1/100→1/1, hash()→sha256 (стабилен межпроцессно, доказано 3 seed); контракт сериализации — зонд 1945/0-OTHER; свидетельство 1/1: 20/20; тесты 4/4; 1/1 — частота, не полнота инварианта; код 83b092af."


def _sub_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        _abort(f"{label}: якорь найден {count} раз (ожидался 1)")
    print(f"══ {label} — БЫЛО ══")
    print(old[:200] + "…")
    print(f"══ {label} — СТАЛО ══")
    print(new[:200] + "…")
    return text.replace(old, new, 1)


def main() -> None:
    print("[DET-2] Доковое закрытие (§17.8 чекбокс + §10-строка)")
    if "DET-2 [закрыт" in Path(ROADMAP).read_text(encoding="utf-8-sig"):
        _abort("маркер закрытия DET-2 уже в файле — скрипт уже исполнен")
    text, bom = _load(ROADMAP)

    text = _sub_once(text, DET2_OLD, DET2_NEW, "§17.8 DET-2 чекбокс")

    if text.count(JOURNAL_ANCHOR) != 1:
        _abort(f"§10-якорь (DET-1-строка журнала) найден {text.count(JOURNAL_ANCHOR)} раз")
    print()
    print("══ §10-строка — СТАЛО (вставка после DET-1-строки) ══")
    print(JOURNAL_LINE)
    text = text.replace(JOURNAL_ANCHOR, JOURNAL_ANCHOR + "\n" + JOURNAL_LINE, 1)

    _save(ROADMAP, text, bom)
    print()
    print("[OK] Записано: DET-2 [x] + §10-строка.")
    print()
    print('git add docs/ENIGMA_ROADMAP_v4_7.md reports/det2_close.py')
    print('git commit -m "DET-2 закрытие (§17.8 чекбокс + §10-строка): checksum 1/1 + sha256; числа измерения и оговорки зафиксированы (claim 2.4% не подтверждён для условий замера, не экстраполируется; 1/1 — частота, не полнота инварианта); код-коммит 83b092af; ветка Б" -- docs/ENIGMA_ROADMAP_v4_7.md reports/det2_close.py')


if __name__ == "__main__":
    main()
