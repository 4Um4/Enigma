# path: backend/tests/sandbox/SUPERBOX/scenarios/re_gh_dynamics_test.py
# Назначение: ADR-O-419 (RE G/H) — time-driven динамика потребностей на живом
#   harness. Control: флаг OFF — книга контура не создаётся (байт-идентичный
#   baseline). Treatment: флаг ON — ≥1 кванта: отметка коммитится, давление
#   растёт по gen_rate·Δt, клампы [0,1] живы.
# Зависимости: TavernGameplayHarness (GC-00 §5a.2), Store frozen-read
#   (приватные носители легальны для приёмки — I.4).
# Основные сущности: run_control, run_treatment, main

import os
import sys
from dataclasses import dataclass
from typing import Any, Dict

_REL_KEY = "relationship_state"
_BOOK_KEY = "dynamics"
_MARK_KEY = "last_quantum_seconds"


@dataclass
class _GroupResult:
    name: str
    ok: bool
    detail: str


def _last_scene(harness) -> Dict[str, Any]:
    """Канон приёмки (harness:237 / read_trust:297): _tick_scenes — полная сцена
    тика (проекция _last_tick_scene не содержит relationship_state — DIAG-112.6)."""
    ts = getattr(getattr(harness.game_loop, "scene_manager", None), "_tick_scenes", None) or {}
    if not ts:
        raise AssertionError("re_gh: _tick_scenes пуст — сцена не коммитилась")
    return list(ts.values())[0]


def run_control() -> _GroupResult:
    from tests.gameplay.harness import TavernGameplayHarness

    os.environ.pop("RELATIONSHIP_DYNAMICS_ENABLED", None)
    h = TavernGameplayHarness()
    try:
        h.new_game()
        h.advance_ticks(24)
        scene = _last_scene(h)
        root = scene.get(_REL_KEY) or {}
        book = root.get(_BOOK_KEY)
        return _GroupResult(
            "control_flag_off",
            book is None,
            f"книга контура {'НЕ создана (OK)' if book is None else f'создана при OFF: {book}'}",
        )
    finally:
        h.dispose()


def run_treatment() -> _GroupResult:
    from app.services.social.relationship_state_store import RelationshipStateStore
    from tests.gameplay.harness import TavernGameplayHarness

    os.environ["RELATIONSHIP_DYNAMICS_ENABLED"] = "1"
    try:
        h = TavernGameplayHarness()
        try:
            h.new_game()
            h.advance_ticks(400)  # 400 тиков × 10 с = 4000 с > кванта 3600 с
            scene = _last_scene(h)
            book = (scene.get(_REL_KEY) or {}).get(_BOOK_KEY)
            if book is None:
                return _GroupResult("treatment_flag_on", False, "книга не создана — контур мёртв")
            mark = float(book.get(_MARK_KEY, -1.0))
            if mark < 3600.0:
                return _GroupResult("treatment_flag_on", False, f"mark={mark} < кванта")
            levels = RelationshipStateStore.get_need_levels(scene, "maid_lusya")
            level = levels.get("sexual")
            p_after = level.current_intensity if level else 0.0
            if not (0.0 < p_after <= 1.0):
                return _GroupResult(
                    "treatment_flag_on", False,
                    f"sexual.pressure={p_after} — gen_rate-канал не вырос/вне [0,1]",
                )
            return _GroupResult(
                "treatment_flag_on", True,
                f"mark={mark}, p_sexual={p_after:.4f} (>0, клампы живы)",
            )
        finally:
            h.dispose()
    finally:
        os.environ.pop("RELATIONSHIP_DYNAMICS_ENABLED", None)


def main() -> int:
    results = [run_control(), run_treatment()]
    for r in results:
        print(f"[RE_GH] {r.name}: {'OK' if r.ok else 'FAIL'} — {r.detail}")
    ok = all(r.ok for r in results)
    print(f"Итог: {'GREEN' if ok else 'RED'} = {sum(r.ok for r in results)}/{len(results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())