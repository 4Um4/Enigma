# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/micro/test_ue_d4_kernel_red.py
Назначение: UX-UE-01 Этап 1, ④ (мини-ADR D4, вариант A, GO Тай) — красные
    фиксаторы обхода fail-closed S346 на авторитетных путях исполнения:
    (1) S122-труба: PLAYER_ATTACKED при non-RESOLVED ATTACK;
    (2) M1: ActionConsequenceCompiler при non-RESOLVED HELP;
    (3) Rules/экономика: синтез rules-события при non-RESOLVED.
    R1 (Тай): покрытия три — одного PLAYER_ATTACKED недостаточно.
    Паттерн safety_red: xfail(strict=True) — красные ДО D4-фикса
    (фикс = ОТДЕЛЬНЫЙ мини-ADR/дифф в ядре, не UX-патч); XPASS = защита
    заработала — снять xfail. Положительные контроли — зелёные всегда
    (регрессия боя/последствий запрещена, S346). dm_ctx-ветка закрывается
    общей границей _phase_1_input_merge:1382 (мини-ADR) — стаб не дублирует.
Зависимости: app.services.tick_orchestrator, app.services.game_loop.turn_pipeline,
    app.services.game_loop.phase_1_input, app.domain.intent_profile
Запуск: cd backend; python -m pytest tests/sandbox/micro/test_ue_d4_kernel_red.py -v; cd ..
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.domain.intent_profile import ActionType, IntentSemanticField
from app.services.game_loop.phase_1_input import resolve_player_intent
from app.services.game_loop.turn_pipeline import TurnPipeline
from app.services.tick_orchestrator import TickOrchestrator

_SCENE = {
    "npc_positions": {
        "guard_gate": {"name": "стражник у ворот", "x": 10.0, "y": 10.0},
        "guard_market": {"name": "стражник на рынке", "x": 40.0, "y": 10.0},
    },
    "location_id": "tavern",
}


class _SpyBus:
    def __init__(self) -> None:
        self.published: list = []

    def publish(self, event: object) -> None:
        self.published.append(event)


def _partial_resolution():
    """Живая PARTIAL-классификация NEG-04 через фабрику (§13.4)."""
    sf = IntentSemanticField(action=ActionType.ATTACK, raw_text="Не бей его.")
    return resolve_player_intent(
        raw_action="Не бей его.", action_type="player_attacks", target="",
        player_dict=None, scene_context=_SCENE, semantic_field=sf,
    )


def _res_stub(readiness: str) -> SimpleNamespace:
    """Стаб resolution: ядро читает только intent_readiness; производство
    классификации заперто сьютой S346 (block3_gate), здесь не дублируется."""
    return SimpleNamespace(
        original_intent=SimpleNamespace(
            parameters=SimpleNamespace(intent_readiness=readiness)
        )
    )


def _run_player_action(sem_action: str, readiness: str, resolution=None) -> _SpyBus:
    bus = _SpyBus()
    ctx = SimpleNamespace(
        tick_number=1,
        scene_state={"game_time_seconds": 0.0},
        all_npcs_raw=[],
        delta_buffer=[],
        mvp_controller=None,
        shared_context=SimpleNamespace(
            action_rejected=False,
            intent_resolution=(resolution if resolution is not None else _res_stub(readiness)),
        ),
    )
    interv = SimpleNamespace(
        source="player",
        payload={"text": "stub", "player_name": "p", "semantic_action": sem_action,
                 "target_id": "guard_gate", "target_reference": "стражник", "tick": 1},
    )
    TickOrchestrator._process_player_action(SimpleNamespace(_event_bus=bus), ctx, interv)
    return bus


def _attack_events(bus: _SpyBus) -> list:
    return [e for e in bus.published if "attack" in str(getattr(e, "type", "")).lower()]


# ── (1) S122-труба ─────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="D4: PLAYER_ATTACKED при PARTIAL — мини-ADR ④")
def test_red_s122_partial_attack_not_published():
    bus = _run_player_action("ATTACK", "PARTIAL")
    assert not _attack_events(bus), (
        "PLAYER_ATTACKED опубликован при PARTIAL (NEG-04) — обход fail-closed S346"
    )


@pytest.mark.xfail(strict=True, reason="D4: PLAYER_ATTACKED при REFERENCE_AMBIGUOUS — мини-ADR ④")
def test_red_s122_reference_ambiguous_attack_not_published():
    bus = _run_player_action("ATTACK", "REFERENCE_AMBIGUOUS")
    assert not _attack_events(bus), "PLAYER_ATTACKED при REFERENCE_AMBIGUOUS (REF-01)"


def test_control_s122_resolved_attack_published():
    bus = _run_player_action("ATTACK", "RESOLVED")
    assert _attack_events(bus), "RESOLVED-атака обязана исполняться (регрессия боя)"


def test_control_s122_live_partial_resolution():
    res = _partial_resolution()
    assert res.original_intent.parameters.intent_readiness == "PARTIAL"


# ── (2) M1: ActionConsequenceCompiler ──────────────────────────────

def _run_help(readiness: str) -> list:
    calls: list = []
    compiler = SimpleNamespace(process_action=lambda a: (calls.append(a) or None))
    bus = _SpyBus()
    ctx = SimpleNamespace(
        tick_number=1, scene_state={"game_time_seconds": 0.0},
        all_npcs_raw=[], delta_buffer=[],
        mvp_controller=SimpleNamespace(action_compiler=compiler),
        shared_context=SimpleNamespace(action_rejected=False, intent_resolution=_res_stub(readiness)),
    )
    interv = SimpleNamespace(
        source="player",
        payload={"text": "stub", "player_name": "p", "semantic_action": "HELP",
                 "target_id": "guard_gate", "target_reference": "стражник", "tick": 1},
    )
    TickOrchestrator._process_player_action(SimpleNamespace(_event_bus=bus), ctx, interv)
    return calls


@pytest.mark.xfail(strict=True, reason="D4: M1 компилирует при non-RESOLVED — мини-ADR ④")
def test_red_m1_partial_help_not_compiled():
    assert not _run_help("PARTIAL"), "ActionConsequenceCompiler вызван при PARTIAL HELP"


def test_control_m1_resolved_help_compiled():
    assert _run_help("RESOLVED"), "RESOLVED HELP обязан компилироваться (регрессия)"


# ── (3) Rules/экономика: _finalize ─────────────────────────────────

def _run_finalize(readiness: str, monkeypatch) -> list:
    calls: list = []

    class _SpyRules:
        def handle(self, event, snapshot):
            calls.append(event)
            return None

    # Локальный импорт в _finalize резолвится в рантайме — патч модуля работает
    monkeypatch.setattr("app.services.events.rules_subscriber.RulesSubscriber", _SpyRules)
    import app.services.game_loop.turn_pipeline as _tp

    monkeypatch.setattr(_tp, "R3_DIRECT_MODE", False)

    self_stub = SimpleNamespace(
        dm_orchestrator=SimpleNamespace(_router=SimpleNamespace(get_rules_action_type=lambda t: t)),
        avatar_service=SimpleNamespace(load_state=lambda c, n: None),
        _rel_store=None,
        _svc=SimpleNamespace(get_state_appliculator=None) if False else SimpleNamespace(get_state_applicator=lambda c: None),
        _get_life_engine=lambda: None,
    )
    ctx = SimpleNamespace(all_npcs_raw=[], scene_state={"location_id": "tavern"})
    shared = SimpleNamespace(
        action_type="player_attacks", intent_resolution=_res_stub(readiness),
        current_tick=1, scene_state={"active_traversals": {}},
        player_target_id="guard_gate",  # turn_pipeline:155 — payload rules-события
    )
    actions = [SimpleNamespace(player_name="p", action="Не бей его.")]
    player_result = SimpleNamespace(observed_facts=[], npc_contexts=[])
    # Метод async (turn_pipeline:127): без await тело не исполняется вовсе —
    # урок прогона (XPASS-strict поймал coroutine-never-awaited)
    asyncio.run(
        TurnPipeline._finalize_pipeline_and_build_dm_frame(
            self_stub, shared, ctx, "c1", actions, player_result
        )
    )
    return calls


@pytest.mark.xfail(strict=True, reason="D4: Rules-событие при non-RESOLVED — мини-ADR ④")
def test_red_rules_partial_not_synthesized(monkeypatch):
    assert not _run_finalize("PARTIAL", monkeypatch), "Rules синтезирован при PARTIAL"


def test_control_rules_resolved_synthesized(monkeypatch):
    assert _run_finalize("RESOLVED", monkeypatch), "RESOLVED обязан синтезировать rules (регрессия)"