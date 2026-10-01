# path: /project/backend/tests/sandbox/g3_execution_probe.py
# Назначение: G3 (ADR-O-410) Этап 1 — приёмка ИСПОЛНИТЕЛЬНОГО ЯДРА живым
#     production-контуром: spawn → resolve → STEAL(windup-инжект) → TAKE →
#     HELD_BY-мутация → THEFT-событие. A/B-пара ON/OFF — дифференциальное
#     доказательство INV-G3-NOOP (OFF = событие есть, мутации НЕТ).
#     GC-00-стандарт: production-path ONLY (idle_tick), temp-saves изоляция,
#     INVALID RUN-guard (равные краши ≠ совпадение).
# Зависимости: tests.gameplay.harness (production build_game_loop),
#     app.services.world (store, g3_executor), app.domain (communication,
#     action_windup), app.services.events (event_bus, event_types)
# Основные сущности: _inject_steal_windup, _run_rail, main
# Запуск: cd backend; python -m tests.sandbox.g3_execution_probe; cd ..
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_ROOT / "backend"))

from tests.gameplay.harness import TavernGameplayHarness  # noqa: E402

_CAMPAIGN = "Open_road"
_LOCATION = "tavern_silver_wolf"
_ACTOR = "thief_shadow"
_CHAIR_ID = "wo_g3_probe_chair"
_WINDUP_KEY = f"{_CAMPAIGN}::{_ACTOR}"
_STEAL_WINDUP_TICKS = 2


def _inject_steal_windup(
    scene: Dict[str, Any], tick: int
) -> Optional[str]:
    """Инжект PENDING-steal-windup + held-intent в scene_state (Э6-путь
    S203.4; commitment-зеркало обходим — гейтовано чужими env-флагами;
    для ядра достаточно windup+held). Возвращает held_intent_id."""
    from app.domain.action_windup import ActionWindup, WindupStatus
    from app.domain.communication import CommunicationIntent, ExposureLevel

    _intent = CommunicationIntent(
        speaker=_ACTOR,
        audience="all",
        topic="кража_стула",
        intent_type="steal",
        emotional_state="нейтральное",
        exposure_level=ExposureLevel.from_semantic("whisper"),
        target_id=_CHAIR_ID,
    )
    _intent_id = f"probe-{tick}-g3-{_ACTOR}"
    scene.setdefault("windup_held_intents", {})[_intent_id] = _intent.to_dict()
    _windup = ActionWindup(
        actor_id=_ACTOR,
        target_id=_CHAIR_ID,
        action_type="steal",
        started_tick=tick,
        duration_ticks=_STEAL_WINDUP_TICKS,
        status=WindupStatus.PENDING,
        held_intent_id=_intent_id,
    )
    scene.setdefault("windup_registry", {}).setdefault(_WINDUP_KEY, []).append(
        _windup.to_dict()
    )
    return _intent_id


def _sub_theft(sink: List[str]) -> None:
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType

    def _on_theft(event: Any) -> None:
        _payload = getattr(event, "payload", {}) or {}
        _src = getattr(event, "source", "")
        if _src == _ACTOR or _payload.get("source") == _ACTOR:
            _target = _payload.get("target_id", "")
            if _target == _CHAIR_ID:
                sink.append(_target)

    get_event_bus().subscribe(EventType.THEFT, _on_theft)


def _holder_of(scene: Optional[Dict[str, Any]]) -> Optional[str]:
    if not scene:
        return None
    _raw = (scene.get("world_objects") or {}).get(_CHAIR_ID)
    if not _raw:
        return None
    return _raw.get("holder")


def _run_rail(flag: str) -> Dict[str, Any]:
    import os

    os.environ["W3_G3_ENABLED"] = flag
    _theft: List[str] = []
    _report: Dict[str, Any] = {"rail": flag}
    try:
        with TavernGameplayHarness() as _h:
            _sub_theft(_theft)
            # Прогрев: сцена локации поднимается лениво первым idle_tick
            # (GC-00: build_game_loop не материализует сцену; get_scene_state
            # вне тика до первого тика = None — прецедент S239-H1 класса
            # «вне тика перезаливает из persistence», здесь — создания нет).
            _h.advance_ticks(1)
            # Фактический ключ сцены — из живого post-tick слепка
            # (S242-fix-прецедент: константа харнесса не является ключом).
            _loc_key = (
                _h._last_tick_scene.get("location_id")
                if isinstance(_h._last_tick_scene, dict)
                else None
            ) or _LOCATION
            _scene = _h.game_loop.scene_manager.get_scene_state(
                _CAMPAIGN, _loc_key
            )
            if not isinstance(_scene, dict):
                # Честная диагностика вместо NPE (L4): сцена не поднялась.
                _report["spawned"] = False
                _report["scene_none_after_warmup"] = True
                _report["holder_after"] = None
                _report["theft_events"] = 0
                _report["chair_exists"] = False
                return _report
            _tick = int(_scene.get("tick", 0) or 0) + 1
            _report["spawned"] = _h.spawn_world_object(
                _CHAIR_ID, "chair", (8.2, 12.8)
            )
            # Спавн сохраняет сцену; пере-читаем канон (tick мог двинуться
            # при save-контуре — берём свежий dict).
            _scene = _h.game_loop.scene_manager.get_scene_state(
                _CAMPAIGN, _loc_key
            ) or _scene
            _inject_steal_windup(_scene, _tick)
            _h.game_loop.scene_manager.save_scene_state(_CAMPAIGN, _scene)
            # Окно windup (2 тика) + релиз + commit.
            _h.advance_ticks(_STEAL_WINDUP_TICKS + 2)
            _fresh = _h.get_scene_fresh() or _h.get_scene()
            _report["holder_after"] = _holder_of(_fresh)
            _report["theft_events"] = len(_theft)
            _report["chair_exists"] = bool(
                (_fresh or {}).get("world_objects", {}).get(_CHAIR_ID)
            )
    finally:
        os.environ.pop("W3_G3_ENABLED", None)
    return _report


def main() -> int:
    _off = _run_rail("0")
    _on = _run_rail("1")
    # INVALID RUN-guard: отсутствие спавна/объекта = инфраструктурный сбой,
    # не поведенческий результат (урок S237 v1: два одинаковых краша ≠ GREEN).
    for _r in (_off, _on):
        if not _r.get("spawned") or not _r.get("chair_exists"):
            print(f"[G3-PROBE] INVALID RUN: {_r}")
            return 1
    _ok_off = _off["holder_after"] is None and _off["theft_events"] >= 1
    _ok_on = _on["holder_after"] == _ACTOR and _on["theft_events"] >= 1
    print(f"[G3-PROBE] OFF: {_off}")
    print(f"[G3-PROBE] ON:  {_on}")
    print(
        f"[G3-PROBE] verdict: "
        f"{'GREEN' if (_ok_off and _ok_on) else 'RED'}"
    )
    return 0 if (_ok_off and _ok_on) else 1


if __name__ == "__main__":
    raise SystemExit(main())