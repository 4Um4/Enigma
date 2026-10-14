from __future__ import annotations

# reports/det1_close.py
"""
Одноразовый доковый скрипт закрытия DET-1 (§17.8 + §10-строка журнала).
Гейты: якорь-строки ровно 1 раз; ABORT до записи; пары БЫЛО/СТАЛО.
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


DET1_OLD = "- [ ] **DET-1 [реализуется] Аудит детерминизма AdaptiveTickLoader** — проверка корректности, не фича: найти все точки throttling/LOD-решений (`backend/app/services/adaptive_tick_loader.py:11`; wiring `tick_orchestrator.py:725-726`; первый подозреваемый — M-24-комментарий `tick_orchestrator.py:744` «восстанавливаем измерение времени… (LOD throttling)»); трассировка источников каждого входа: детерминированные (состояние мира + номер тика) vs wall-clock; воспроизводимый тест доказывает или опровергает расхождение replay при другой машине/нагрузке; при доказанном баге — решение переводится на детерминированные входы, wall-clock остаётся телеметрией (§15 Устава); если уже обеспечено порогами по состоянию сцены — зафиксировать доказательство тестом, исправное не переписывать."
DET1_NEW = "- [x] **DET-1 [закрыт: реализуется→проверено]** ✅ Аудит детерминизма AdaptiveTickLoader (сессия S351-хвост, ветка Б): карт точек решений — 2, обе в TickOrchestrator (:730-742 tick_fully; :744-768 запись); баг M-24 ДОКАЗАН кодом и тестом: LOD-решение управлялось wall-clock (длительность исполнения) → replay на другой машине/нагрузке получал другой набор исполняемых фаз = другой мир (M-24-комментарий «не влияет на детерминизм» был ошибочен); сопутствующий дефект: record_tick в finally кормил гистерезис длительностью упавшего тика. Фикс: вход = npc_count (детерминирован состоянием мира; NPC_LOAD_THRESHOLD=12 CALIBRATION_CANDIDATE — стартовая точка калибровки, прецедент ADR-O-383; гистерезис 5/50 и топология соседей сохранены), duration_ms — только телеметрия §15.2; упавший тик не кормит LOD (_tick_errored). Доказательный тест test_det1_lod_determinism 4/4 (та же нагрузка — то же LOD на любой машине; 999999мс при малом мире не активирует; мир-размер — единственный вход; топология не тронута); профильное ядро тика 1 passed/1 skipped; IPT 53/0; INV-WALL-CLOCK не задет (clock-протокол легален §15.2)."

JOURNAL_ANCHOR = "- ✅ **COV-1 Шаг 1 (D58, GC-01)** — ADR-O-426: MigrationRunner + bootstrap + бэкап + стампинг живых БД (memory v2 / runtime v1 / replay v1, базлайн-штампы, 3 бэкапа) + lint_sqlite_registry + INV-SQLITE-REGISTRY (IPT 53/0) + burial ExpectationStore (D100); микротесты 23/23; полный сьют 2435/1-известный-RED(А); коммиты 813407e9, 450931cd, d1a7a5de, 83e316b5."
JOURNAL_LINE = "- ✅ **DET-1 (§17.8 / вердикт III.1)** — детерминизм AdaptiveTickLoader: баг M-24 доказан (LOD-решение на wall-clock → другой мир при replay на другой машине/нагрузке) и закрыт — вход npc_count, wall-clock = телеметрия §15.2, упавший тик не кормит гистерезис; тест 4/4; IPT 53/0."


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
    print("[DET-1] Доковое закрытие (§17.8 чекбокс + §10-строка)")
    if "DET-1 [закрыт" in Path(ROADMAP).read_text(encoding="utf-8-sig"):
        _abort("маркер закрытия DET-1 уже в файле — скрипт уже исполнен")
    text, bom = _load(ROADMAP)

    text = _sub_once(text, DET1_OLD, DET1_NEW, "§17.8 DET-1 чекбокс")

    if text.count(JOURNAL_ANCHOR) != 1:
        _abort(f"§10-якорь журнала найден {text.count(JOURNAL_ANCHOR)} раз")
    print()
    print("══ §10-строка — СТАЛО (вставка после якоря) ══")
    print(JOURNAL_LINE)
    text = text.replace(JOURNAL_ANCHOR, JOURNAL_ANCHOR + "\n" + JOURNAL_LINE, 1)

    _save(ROADMAP, text, bom)
    print()
    print("[OK] Записано: DET-1 [x] + §10-строка.")
    print()
    print('git add docs/ENIGMA_ROADMAP_v4_7.md reports/det1_close.py')
    print('git commit -m "DET-1 закрытие (§17.8 чекбокс + §10-строка): детерминизм AdaptiveTickLoader доказан и закрыт — баг M-24 (LOD на wall-clock) пойман, фикс на npc_count, тест 4/4; ветка Б" -- docs/ENIGMA_ROADMAP_v4_7.md reports/det1_close.py')


if __name__ == "__main__":
    main()