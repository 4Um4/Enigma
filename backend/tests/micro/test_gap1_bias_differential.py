"""
path: backend/tests/micro/test_gap1_bias_differential.py
Назначение: GAP-1 (RE-D8-класс): relationship_cache nested, reader flat.
    Дифференциальное доказательство (вердикт Мастера): одинаковая ситуация +
    разные отношения → РАЗНЫЕ interpretation values.
    Ось fear: непрерывный дифференциал threat_bias (fear × THREAT_AMPLIFICATION
    FACTOR=0.15; значения выбраны внутри клампа ±1: 5.0→0.75, 2.0→0.30).
    Ось trust: дизъюнкция distrust-ветки (порог DISTRUST_STRESS_THRESHOLD=-30;
    константа -0.2 бинарна по построению существующего контракта — порог и
    формула не трогаются; NPC(-60)→-0.2 vs NPC(+60)→0.0).
Зависимости: pytest, interpretation_engine, decision_hub.EventContext,
    npc_loader.NPCStateAdapter (фабрика from_legacy — §12.3)
Основные сущности: TestGap1BiasDifferential
Запуск: cd backend ; python -m pytest tests/micro/test_gap1_bias_differential.py -v
"""
from __future__ import annotations

import pytest

from app.models.npc_state import NPCStateAdapter
from app.services.npc.interpretation_engine import InterpretationEngine


_TRUST_NEG = -60.0   # < DISTRUST_STRESS_THRESHOLD(-30) → distrust-ветка активна
_TRUST_POS = 60.0    # ≥ порога → ветка молчит
_FEAR_HIGH = 5.0     # 5.0 × 0.15 = 0.75 — внутри клампа [-1, +1]
_FEAR_LOW = 2.0      # 2.0 × 0.15 = 0.30 — внутри клампа


def _make_npc_state(npc_id: str, trust: float, fear: float):
    """NPCState через фабрику: ВЛОЖЕННЫЙ relationship_cache — формат всех
    прод-писателей (loader:205, V2 get_all_for_source, snapshot-merge)."""
    legacy = {
        "id": npc_id,
        "psyche": {"stress": 20.0, "willpower": 50.0, "loyalty_true": 50.0},
        "social_stats": {"trust": 0.0, "fear_of_player": 0.0, " debt": 0.0},
        "relationship_cache": {
            "player": {"trust": trust, "fear": fear},
        },
    }
    state = NPCStateAdapter.from_legacy(legacy)
    # Контракт P1 ARCH (npc_state:1264): from_legacy НЕ восстанавливает кэш —
    # кэш эфемерный и заполняется обогащением (npc_tick_pipeline:287/:306,
    # in-place setdefault/update). Тест воспроизводит enrichment-фазу
    # тем же паттерном — иначе читатель тестируется на объекте вне lifecycle.
    state.relationship_cache["player"] = {"trust": trust, "fear": fear}
    return state


def _player_event():
    """EventContext с actor_id='player' — активирует bias-ветки (:90)."""
    from app.services.events.event_types import EventType
    from app.services.npc.decision_hub import EventContext

    return EventContext(
        event_type=EventType.PLAYER_SPOKE,
        actor_id="player",
        success=True,
        intensity=0.5,
        distance=2.0,
        witness_count=0,
        location="tavern",
        scene_flags=set(),
        scene_facts=[],
    )


class TestGap1BiasDifferential:
    def test_fear_axis_threat_bias_differential(self):
        """fear=5.0 vs fear=2.0 → threat_bias 0.75 vs 0.30. RED сейчас (0.0 vs 0.0)."""
        engine = InterpretationEngine()
        state_a = _make_npc_state("npc_a", trust=0.0, fear=_FEAR_HIGH)
        state_b = _make_npc_state("npc_b", trust=0.0, fear=_FEAR_LOW)
        event = _player_event()

        result_a = engine.compute(state=state_a, event=event)
        result_b = engine.compute(state=state_b, event=event)

        assert result_a.bias.threat_bias == pytest.approx(0.75)
        assert result_b.bias.threat_bias == pytest.approx(0.30)

    def test_trust_axis_distrust_disjunction(self):
        """trust=-60 → trust_bias=-0.2; trust=+60 → 0.0. RED сейчас (0.0 vs 0.0)."""
        engine = InterpretationEngine()
        state_a = _make_npc_state("npc_a", trust=_TRUST_NEG, fear=0.0)
        state_b = _make_npc_state("npc_b", trust=_TRUST_POS, fear=0.0)
        event = _player_event()

        result_a = engine.compute(state=state_a, event=event)
        result_b = engine.compute(state=state_b, event=event)

        assert result_a.bias.trust_bias == pytest.approx(-0.2)
        assert result_b.bias.trust_bias == pytest.approx(0.0)

    def test_neutral_cache_no_bias_change(self):
        """Отсутствие записи player (Vacuum) → bias 0.0 — семантика Vacuum не изобретается."""
        engine = InterpretationEngine()
        legacy = {
            "id": "npc_v",
            "psyche": {"stress": 20.0, "willpower": 50.0, "loyalty_true": 50.0},
            "social_stats": {"trust": 0.0, "fear_of_player": 0.0, "debt": 0.0},
            "relationship_cache": {"other_npc": {"trust": -80.0, "fear": 50.0}},
        }
        state = NPCStateAdapter.from_legacy(legacy)
        event = _player_event()

        result = engine.compute(state=state, event=event)

        assert result.bias.threat_bias == 0.0
        assert result.bias.trust_bias == 0.0