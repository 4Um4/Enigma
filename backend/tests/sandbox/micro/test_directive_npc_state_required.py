"""
path: backend/tests/sandbox/micro/test_directive_npc_state_required.py
Назначение: Верификация Rule 10 (DirectiveSubscriber требует npc_state) и NPIC Gate
Зависимости: app.services.social.directive_interpretation_subscriber
Основные сущности: DirectiveInterpretationSubscriber

Запуск: cd backend; python -m pytest tests/sandbox/micro/test_directive_npc_state_required.py -v --tb=short; cd ..
"""

import types

from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber


def _make_event(target_id="npc_ghost", semantic_action="MOVE", social_pressure=0.8):
    """Фабрика событий директивы."""
    return types.SimpleNamespace(
        source="player",
        payload={
            "semantic_action": semantic_action,
            "target_id": target_id,
            "social_pressure": social_pressure,
        },
    )


class TestDirectiveNPCStateRequired:
    """Rule 10: DirectiveInterpretationSubscriber не работает без валидного npc_state."""

    def test_directive_subscriber_requires_npc_state(self):
        """ДОКАЗЫВАЕТ: Если целевой NPC отсутствует в npc_states, директива отклоняется."""
        sub = DirectiveInterpretationSubscriber()
        event = _make_event(target_id="npc_missing")

        # Передаём пустой список NPC — целевой NPC не найден
        deltas = sub.handle(event, [])

        assert deltas == [], "Rule 10 Нарушено: Директива обработана без состояния NPC (логический призрак)"

    def test_directive_subscriber_requires_body_state(self):
        """ДОКАЗЫВАЕТ: Если у NPC нет body_state (бестелесный призрак), директива отклоняется."""
        sub = DirectiveInterpretationSubscriber()
        event = _make_event(target_id="npc_bodiless")

        # NPC есть в списке, но без body_state
        npc_bodiless = {
            "npc_id": "npc_bodiless",
            "name": "Призрак",
            "social_stats": {"fear_of_player": 0.8, "trust": 0.0},
        }
        deltas = sub.handle(event, [npc_bodiless])

        assert deltas == [], "NPIC Gate Нарушен: Директива обработана для бестелесного NPC"

    def test_directive_subscriber_blocks_shocked_npc(self):
        """ДОКАЗЫВАЕТ: NPC в состоянии шока (shock > 0.7) не может интерпретировать директивы."""
        sub = DirectiveInterpretationSubscriber()
        event = _make_event(target_id="npc_shocked")

        # NPC с шоком выше порога
        npc_shocked = {
            "npc_id": "npc_shocked",
            "name": "Шокированный",
            "social_stats": {"fear_of_player": 0.8, "trust": 0.0},
            "body_state": {"disabled": False, "shock_impulse": 0.8},
        }
        deltas = sub.handle(event, [npc_shocked])

        assert deltas == [], "Somatic Gate Нарушен: Шокированный NPC обрабатывает директиву"

    def test_directive_subscriber_blocks_disabled_body(self):
        """ДОКАЗЫВАЕТ: NPC с disabled body_state не может интерпретировать директивы."""
        sub = DirectiveInterpretationSubscriber()
        event = _make_event(target_id="npc_disabled")

        # NPC с отключенным телом
        npc_disabled = {
            "npc_id": "npc_disabled",
            "name": "Мёртвый",
            "social_stats": {"fear_of_player": 0.8, "trust": 0.0},
            "body_state": {"disabled": True, "shock_impulse": 0.0},
        }
        deltas = sub.handle(event, [npc_disabled])

        assert deltas == [], "NPIC Gate Нарушен: Отключённый NPC обрабатывает директиву"
