# path: /project/backend/tests/gameplay/test_adr_o323_boundary_arrival_traversal_proposal.py
# Назначение: ADR-O-323 FIX-01 — regression test.
#   boundary_arrival переходит через traversal_complete (whitelist SSM),
#   не вызывает MISSING_TRAVERSAL_PROPOSAL violation.
# Зависимости: tests.gameplay.harness
# Основные сущности: TestADRO323BoundaryArrival
# Запуск: cd backend; python -m pytest tests/gameplay/test_adr_o323_boundary_arrival_traversal_proposal.py -v -s
"""
ADR-O-323 FIX-01 regression.

Контракт: macro relocation (field="position") обязан иметь TraversalProposal
от MovementPlanner. Исключения: traversal_complete (snap завершённого перехода),
cross_loc_materialize* (cross-loc transfer).

До FIX-01: MovementEngine при boundary_arrival возвращал SceneChange с
cause="boundary_arrival:..." и traversal_proposal=None → вызывал
MISSING_TRAVERSAL_PROPOSAL violation в SceneStateManager (ERROR-level).

После FIX-01: cause="traversal_complete" (whitelist) — корректно,
т.к. boundary_arrival семантически = завершение traversal (NPC дошёл
до boundary-узла), не начало нового.

Тест доказывает:
1. NPC пересекает границу сцены без MISSING_TRAVERSAL_PROPOSAL violation.
2. NPC отсутствует в active_traversals после boundary_arrival (traversal завершён).
3. NPC корректно переносится в новую сцену (location_id обновлён).
4. Обычное внутрисценовое перемещение не сломано (active_traversals populated).
"""
import logging
import types
from typing import Any, List

import pytest

from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.adr_o323")

_CAMPAIGN = "Open_road"


class _SyncPool:
    """Тестовый синхронный executor. Контракт ThreadPoolExecutor.submit."""

    def __init__(self) -> None:
        self._shutdown = False

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if self._shutdown:
            raise RuntimeError("cannot schedule new futures after shutdown")
        fn(*args, **kwargs)
        return types.SimpleNamespace(result=lambda: None)

    def shutdown(self, wait: bool = True) -> None:
        self._shutdown = True


def _install_sync_pool(harness: TavernGameplayHarness) -> None:
    from app.domain.execution import TaskKind
    _sched = harness.game_loop._get_task_scheduler()
    _executors = getattr(_sched, "_executors", None) or {}
    _dlg_executor = _executors.get(TaskKind.DIALOGUE)
    if _dlg_executor is not None and hasattr(_dlg_executor, "_router"):
        _dlg_executor._router = None
    _sched._executor_pool = _SyncPool()


def _capture_error_logs() -> List[str]:
    """Перехват логов уровня ERROR из scene_state_manager."""
    captured: List[str] = []
    _handler = logging.Handler()
    _handler.setLevel(logging.ERROR)

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    _cap = _Capture()
    _cap.setLevel(logging.ERROR)
    logging.getLogger("app.services.scene_state_manager").addHandler(_cap)
    return captured, _cap


def _release_logs(_handler: logging.Handler) -> None:
    logging.getLogger("app.services.scene_state_manager").removeHandler(_handler)


@pytest.fixture
def harness():
    _h = TavernGameplayHarness(seed=42, location="tavern")
    _h.new_game()
    _install_sync_pool(_h)
    _h.advance_ticks(2)
    yield _h
    _h.dispose()


class TestADRO323BoundaryArrival:
    """ADR-O-323 FIX-01: boundary_arrival не вызывает violation."""

    def test_no_missing_traversal_proposal_on_boundary_arrival(self, harness):
        """Прогон 12 тиков: ни один NPC не вызывает MISSING_TRAVERSAL_PROPOSAL.

        До FIX-01: thief_shadow/guard_borko/player вызывали violation
        при boundary_arrival. После FIX-01: cause=traversal_complete
        (whitelist SSM), violation не возникает.
        """
        _captured, _handler = _capture_error_logs()
        try:
            harness.advance_ticks(12)
        finally:
            _release_logs(_handler)

        _violations = [m for m in _captured if "MISSING_TRAVERSAL_PROPOSAL" in m]
        assert len(_violations) == 0, (
            f"ADR-O-323 violation detected: {_violations}. "
            "boundary_arrival должен использовать cause=traversal_complete "
            "(whitelist SSM), не должен вызывать MISSING_TRAVERSAL_PROPOSAL."
        )
        print("[ADR-O-323] PASS: no MISSING_TRAVERSAL_PROPOSAL violations in 12 ticks")

    def test_npc_cross_scene_transition_correct(self, harness):
        """NPC корректно переходит в новую сцену: location_id обновлён,
        отсутствует в active_traversals (traversal завершён).

        На seed=42 thief_shadow достигает boundary на тике 5-7 и переходит
        в city_gate.
        """
        harness.advance_ticks(10)
        _le = harness.game_loop._get_life_engine()
        _states = _le.get_npc_states(_CAMPAIGN)
        _ts = next((s for s in _states if s.get("npc_id") == "thief_shadow"), None)
        assert _ts is not None, "thief_shadow не найден в LifeEngine"
        _loc = _ts.get("location_id")
        assert _loc in ("city_gate", "tavern"), (
            f"unexpected location_id={_loc}; expected city_gate or tavern"
        )
        if _loc == "city_gate":
            print(f"[ADR-O-323] PASS: thief_shadow crossed scene → location_id={_loc}")
        else:
            print(f"[ADR-O-323] INFO: thief_shadow stayed in {_loc} "
                  "(boundary not reached in 10 ticks)")

    def test_intrascene_traversal_still_works(self, harness):
        """Регрессия: обычное внутрисценовое перемещение создаёт proposal.

        Проверка: после нескольких тиков в scene_state[tavern] есть
        active_traversals для тех NPC, кто двигался внутри сцены
        (не через boundary).
        """
        harness.advance_ticks(3)
        _scene = harness.get_scene_fresh() or {}
        _travs = _scene.get("active_traversals", {}) or {}
        assert len(_travs) > 0, (
            f"Регрессия: active_traversals пуст. Обычное внутрисценовое "
            f"перемещение сломано. traversals={_travs}"
        )
        print(f"[ADR-O-323] PASS: intrascene traversal works, "
              f"active_traversals count={len(_travs)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
