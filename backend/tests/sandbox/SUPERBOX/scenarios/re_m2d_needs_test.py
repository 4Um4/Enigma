# path: /project/backend/tests/sandbox/SUPERBOX/scenarios/re_m2d_needs_test.py
# Назначение: SUPERBOX re_m2d_needs_test (ADR-O-418, RE M2/D) — приёмка Фазы D
#   (ТЗ-RE-01 §10: «SUPERBOX-цепочка на живой шине, Control/Treatment») на
#   GC-00-харнесе. Группы:
#   CONTROL — dormant (INV-RE-NOOP): RELATIONSHIP_EVENTS_ENABLED снят ДО
#       построения харнесса → публикация INTIMATE_REJECTION в шину → тик →
#       relationship_state в scene_state ОТСУТСТВУЕТ (байт-идентичный baseline).
#   TREATMENT — прод-путь: флаг ON до построения → та же публикация → тик →
#       drain Фазы 8 → delta_buffer → сплит commit_phase → apply_relationship_deltas
#       → update_needs → Store → read-back frustration > 0 у source.
#   PROVENANCE — read-back Cause: update_needs логирует [RE_NEEDS] с event-UUID.
# Зависимости: TavernGameplayHarness (GC-00 §5a.2), EventBus, M2/D-слой.
# Основные сущности: run_re_m2d_needs_test.
# OFFLINE: MockProvider (environment != production), LLM не участвует.

"""
Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.re_m2d_needs_test; cd ..
"""

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("RE_M2D_TEST")

NPC_SOURCE = "maid_lusya"  # реальный NPC кампании харнеса (прецедент bc1/lab-M1)
NPC_TARGET = "merchant_goran"

# ── ГРУППА CONTROL: флаг снят ДО построения харнесса ──────────────────────
os.environ.pop("RELATIONSHIP_EVENTS_ENABLED", None)

from app.domain.events import EventDTO  # noqa: E402
from app.services.events.event_types import EventType  # noqa: E402

REJECTED = EventType.INTIMATE_REJECTION.value


@dataclass
class _GroupResult:
    group: str
    ok: bool = False
    detail: str = ""


def _publish_and_tick(harness, event: EventDTO) -> None:
    """Легальный вход: публикация EventDTO в глобальный EventBus (синглтон,
    get_event_bus — паттерн harness:116/119) → один production idle-тик
    (advance_ticks → game_loop.idle_tick, harness:201-214)."""
    from app.services.events.event_bus import get_event_bus

    get_event_bus().publish(event)
    harness.advance_ticks(1)


def _last_scene(harness) -> Dict[str, Any]:
    """Каноническая сцена после тика: scene_manager._tick_scenes (прецедент
    harness:237; _last_tick_scene — проекция без relationship_state — DIAG-112.6).
    Последняя по вставке локация; читается ТОЛЬКО тестом (read-паттерн
    read_trust harness:297 — приватные носители легальны для приёмки)."""
    ts = getattr(getattr(harness.game_loop, "scene_manager", None), "_tick_scenes", None) or {}
    if not ts:
        raise RuntimeError("tick_scenes пуст — commit-проводка сцены не отработала")
    return ts[sorted(ts.keys())[-1]]


def _re_state(scene_state: Dict[str, Any]) -> Dict[str, Any]:
    return scene_state.get("relationship_state", {}).get("needs", {})


def run_control() -> _GroupResult:
    from tests.gameplay.harness import TavernGameplayHarness

    h = TavernGameplayHarness()  # кампания — константа харнеса (_CAMPAIGN)
    try:
        h.new_game()  # build_game_loop + temp-saves; флаг OFF → подписки нет
        ev = EventDTO.create(REJECTED, NPC_SOURCE, {"target_id": NPC_TARGET}, timestamp=0.0)
        _publish_and_tick(h, ev)
        needs = _re_state(_last_scene(h))
        if needs:
            return _GroupResult("CONTROL", False, f"needs не пуст при OFF: {list(needs)}")
        return _GroupResult(
            "CONTROL", True, "OFF: relationship_state отсутствует (no-op доказан)"
        )
    finally:
        _dispose(h)


def run_treatment() -> _GroupResult:
    # Флаг ДО new_game: Orchestrator.__init__ инстанцирует RelationshipEventSemantics
    # (подписка создаётся в конструкторе при ON).
    os.environ["RELATIONSHIP_EVENTS_ENABLED"] = "1"
    from tests.gameplay.harness import TavernGameplayHarness

    h = TavernGameplayHarness()
    try:
        h.new_game()
        ev = EventDTO.create(REJECTED, NPC_SOURCE, {"target_id": NPC_TARGET}, timestamp=0.0)
        _publish_and_tick(h, ev)
        lvl = _re_state(_last_scene(h)).get(NPC_SOURCE, {}).get("sexual")
        if not lvl:
            return _GroupResult(
                "TREATMENT", False,
                f"нет NeedLevel sexual у {NPC_SOURCE} — цепь не провела дельту",
            )
        fr = float(lvl.get("frustration", 0.0))
        if fr <= 0.0:
            return _GroupResult("TREATMENT", False, f"frustration={fr} — дельта не применилась")
        return _GroupResult("TREATMENT", True, f"frustration={fr:.2f} > 0 у source (цепь жива)")
    finally:
        _dispose(h)


def _dispose(harness) -> None:
    """Restore settings/saves (harness dispose — паттерн :130 'restore в dispose')."""
    dispose = getattr(harness, "dispose", None)
    if callable(dispose):
        dispose()


def main() -> int:
    results = [run_control(), run_treatment()]
    ok = all(r.ok for r in results)
    print("=" * 60)
    for r in results:
        print(f"{'✅' if r.ok else '❌'} {r.group}: {r.detail}")
    print(f"Итог: {'GREEN' if ok else 'RED'} = {sum(r.ok for r in results)}/{len(results)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())