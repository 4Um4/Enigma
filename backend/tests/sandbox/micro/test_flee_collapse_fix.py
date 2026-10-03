"""
path: backend/tests/sandbox/micro/test_flee_collapse_fix.py
Назначение: Верификация P0 фикса — Universal Flee-Collapse
Зависимости: app.services.npc.decision_hub, app.services.social.social_decay_handler
Основные сущности: TestFleeCollapseFix

Запуск: python -m pytest backend/tests/sandbox/micro/test_flee_collapse_fix.py -v --tb=short

TODO:
"""

import types
from typing import cast

from app.models.idle_tick import NPCStateSnapshot
from app.models.npc_state import NPCState
from app.domain.events import EventDTO


def _make_state(
    npc_id="maid_lusya",
    fear=0.0,
    trust=0.0,
    threat_gradient=0.0,
    narrative_cache=None,
):
    """Создаёт минимальный duck-typed NPCState для risk-контракта.

    Подмножество полей, которые читает compute_objective_risk
    (relationship_cache / narrative_cache). cast снимает ложный
    Pylance-конфликт SimpleNamespace vs NPCState — рантайм-объект
    тот же (прецедент S315: Pylance-шум ≠ поведение).
    """
    ns = types.SimpleNamespace(
        npc_id=npc_id,
        relationship_cache={"player": {"fear": fear, "trust": trust}},
        emotion="neutral",
        perceptual_kernel=types.SimpleNamespace(threat_gradient=threat_gradient),
        narrative_cache=narrative_cache or [],
        temporary_drives=[],
        intent_target="player",
    )
    return cast(NPCState, ns)


def _make_event(event_type="player_interacts", witness_count=6, distance=1.5):
    """Создаёт минимальный EventContext."""
    return types.SimpleNamespace(
        event_type=event_type,
        witness_count=witness_count,
        distance=distance,
        success=True,
        visible_threat_markers=[],
        scene_flags=set(),
        intensity=0.5,
    )


def _collect_payload_attr(deltas: list, attr: str) -> list:
    """M1b.3.6 (малый ремонт): getattr-фильтрация по union-payload — Pylance
    не сужает hasattr по union of *Payload. Семантика прежняя: значения
    атрибута у дельт, чей payload его имеет."""
    out = []
    for d in deltas:
        payload = getattr(d, "payload", None)
        if payload is not None and hasattr(payload, attr):
            out.append(getattr(payload, attr))
    return out


class TestComputeRisk:
    """Fix 3+5: player_interacts = LOW risk, даже с memory/pressure."""

    def test_player_interacts_base_risk_is_low(self):
        from app.services.npc.decision.risk import compute_objective_risk

        ev = _make_event("player_interacts")
        state = _make_state()
        risk = compute_objective_risk(ev, state)
        assert risk <= 0.2, f"player_interacts risk={risk}, expected <= 0.2"

    def test_player_interacts_ignores_memory_penalty(self):
        from app.services.npc.decision.risk import compute_objective_risk

        ev = _make_event("player_interacts")
        # Память о насилии НЕ должна влиять на мирный разговор.
        # M1b.3.6: nested-канон — давление лежит там, куда читает
        # compute_objective_risk; прежний плоский ключ был мёртв
        state = _make_state(
            narrative_cache=[
                types.SimpleNamespace(importance=0.9, event_type="player_attacks")
            ]
        )
        state.relationship_cache["player"]["recent_pressure"] = 0.5
        risk = compute_objective_risk(ev, state)
        assert risk <= 0.2, f"player_interacts with memory risk={risk}, expected <= 0.2"

    def test_player_attacks_has_high_risk(self):
        from app.services.npc.decision.risk import compute_objective_risk

        ev = _make_event("player_attacks")
        state = _make_state()
        risk = compute_objective_risk(ev, state)
        assert risk > 0.3, f"player_attacks risk={risk}, expected > 0.3"


class TestFleeNoDoubleFear:
    """Fix 2: fear НЕ входит дважды в FLEE score."""

    def test_flee_risk_penalty_excludes_fear(self):
        from app.services.npc.decision_hub import DecisionHub

        hub = DecisionHub()
        import inspect

        src = inspect.getsource(hub._score_components)
        # Формула должна содержать только _perceived_threat, не fear
        assert "_perceived_threat * risk" in src, "FLEE risk_penalty должен использовать только threat_gradient"
        assert "fear + _perceived_threat" not in src, "fear НЕ должен дублироваться в risk_penalty"


class TestSocialDecayIncludesFear:
    """Fix 4: SocialDecayHandler decay'ит fear к нулю."""

    def test_fear_decay_to_zero(self):
        from app.services.social.social_decay_handler import SocialDecayHandler

        handler = SocialDecayHandler()
        npcs = [
            {
                "npc_id": "maid_lusya",
                "relationship_cache": {"player": {"trust": 30.0, "fear": 50.0, "base_trust": 50.0}},
                "base_values": {"player": 50.0},
            }
        ]
        # Duck-typed снапшоты (хендлер читает .get по ключам): cast снимает
        # Pylance-шум инвариантности List[TypedDict] (прецедент S315)
        results = handler.handle(
            cast("list[NPCStateSnapshot]", npcs), "test_campaign", current_tick=1
        )
        # Должен быть fear_delta < 0 (drift к нулю)
        fear_deltas = _collect_payload_attr(results, "fear_delta")
        assert len(fear_deltas) > 0, "SocialDecayHandler должен генерить fear_delta"
        assert fear_deltas[0] < 0, f"fear_delta={fear_deltas[0]}, expected < 0 (decay к нулю)"

    def test_trust_decay_still_works(self):
        from app.services.social.social_decay_handler import SocialDecayHandler

        handler = SocialDecayHandler()
        npcs = [
            {
                "npc_id": "maid_lusya",
                "relationship_cache": {"player": {"trust": 30.0, "fear": 0.0, "base_trust": 50.0}},
                "base_values": {"player": 50.0},
            }
        ]
        results = handler.handle(
            cast("list[NPCStateSnapshot]", npcs), "test_campaign", current_tick=1
        )
        trust_deltas = _collect_payload_attr(results, "trust_delta")
        assert len(trust_deltas) > 0, "SocialDecayHandler должен генерить trust_delta"
        assert trust_deltas[0] > 0, f"trust_delta={trust_deltas[0]}, expected > 0 (drift к base)"


class TestDirectiveNoFearOnSummon:
    """Fix 1 revised: MOVE (подзыв) не генерирует fear_delta, угрозы генерируют.
    Тест проверяет каузальный эффект (DTO контракт), а не наличие строк в исходниках."""

    def _make_subscriber(self):
        from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber

        return DirectiveInterpretationSubscriber()

    def _make_event(self, semantic_action, target_id="npc_2", social_pressure=0.8, source="player"):
        return types.SimpleNamespace(
            payload={"semantic_action": semantic_action, "target_id": target_id, "social_pressure": social_pressure},
            source=source,
        )

    def _make_npc_states(self, npc_id="npc_2", fear=0.5, trust=0.0):
        return [
            {
                "npc_id": npc_id,
                "social_stats": {"fear_of_player": fear, "trust": trust},
                "body_state": {"disabled": False, "shock_impulse": 0.0},
            }
        ]

    def test_summon_generates_zero_fear(self):
        sub = self._make_subscriber()
        event = self._make_event(semantic_action="MOVE")
        npc_states = self._make_npc_states(fear=0.8)  # Высокий страх, чтобы гарантированно войти в ветку Obedience

        deltas = sub.handle(cast(EventDTO, event), npc_states)

        for fear_val in _collect_payload_attr(deltas, "fear_delta"):
            assert fear_val == 0.0, (
                f"MOVE (подзыв) не должен генерировать fear_delta, получено {fear_val}"
            )

    def test_threaten_still_generates_fear(self):
        sub = self._make_subscriber()
        event = self._make_event(semantic_action="THREATEN")
        npc_states = self._make_npc_states(fear=0.8)  # Высокий страх для Obedience

        deltas = sub.handle(cast(EventDTO, event), npc_states)

        total_fear = sum(_collect_payload_attr(deltas, "fear_delta"))

        assert total_fear > 0.0, f"THREATEN должен генерировать fear_delta, получено {total_fear}"
