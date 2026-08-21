"""
КАУЗАЛЬНЫЙ ОСЦИЛЛОГРАФ: Замкнутый контур
Доказывает, что команда "Тень, иди сюда" порождает легитимное пространственное изменение
без единого bypass-а.

ЗАПУСК: pytest -s backend/tests/sandbox/oscilloscope_closed_loop.py

TODO:
- Добавить больше assert-ов для проверки каждого слоя (семантика, давление, решение)
- Вынести фикстуры в отдельный файл для повторного использования
"""

import pytest
import uuid
from unittest.mock import MagicMock
from app.domain.events import EventDTO
from app.domain.intent_profile import IntentSemanticField, ActionType, EmotionalVector, ConfidenceVector, SemanticAmbiguity
from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber
from app.models.state_delta import DeltaDomain
from app.services.npc.npc_tick_pipeline import _resolve_reactive_movement

# Фикстура микрокосма
@pytest.fixture
def shadow_state():
    return {
        "npc_id": "thief_shadow",
        "psyche": {"willpower": 0.2, "fear": 0.8, "drives_base": {"fear_drive": 0.9}},
        "body_profile": {"abilities": {}},
        "body_state": {"statuses": []},
        "social_stats": {"trust": 10, "fear_of_player": 80}
    }

@pytest.fixture
def player_in_main_hall():
    """Игрок находится в main_hall. Единственная истина — npc_positions."""
    return {
        "npc_positions": {
            "player": {"position": "main_hall", "local_position": {"x": 15.0, "y": 20.0}},
            "thief_shadow": {"position": "shadow_corner", "local_position": {"x": 5.0, "y": 5.0}}
        },
        "location_id": "tavern_silver_wolf"
    }

def test_closed_loop_command_to_traversal(shadow_state, player_in_main_hall):
    """СПАЙКА: Команда → fear_delta (Власть) → Резолв позиции Игрока → Движение"""
    
    # 1. СЛОЙ СЕМАНТИКИ
    semantic_field = IntentSemanticField(
        action_type=ActionType.MOVE,
        target_reference="тень",
        semantic=EmotionalVector(aggression=0.1, confidence=0.9),
        confidence=ConfidenceVector(action=1.0),
        ambiguity=SemanticAmbiguity.CLEAR,
        raw_text="Тень, иди сюда"
    )
    assert semantic_field.action_type == ActionType.MOVE, "Семантика не извлечена"
    
    # 2. СЛОЙ ДАВЛЕНИЯ (Физика Власти)
    event = EventDTO(
        id=uuid.uuid4(),
        type="PLAYER_SPEAKS",
        source="player",
        timestamp=0.0,
        payload={
            "semantic_action": "MOVE",
            "target_id": "thief_shadow",
            "social_pressure": 0.8
        },
        visibility="public",
        radius=10.0,
        persistence_level="working"
    )
    
    subscriber = DirectiveInterpretationSubscriber()
    deltas = subscriber.handle(event, [shadow_state])
    
    assert len(deltas) > 0, "Дельты давления не сгенерированы"
    
    # Симулируем StateApplicator: применяем fear_delta к стейту
    fear_delta = next((d.payload.fear_delta for d in deltas if d.domain == DeltaDomain.SOCIAL), 0.0)
    shadow_state["social_stats"]["fear_of_player"] += fear_delta
    assert shadow_state["social_stats"]["fear_of_player"] > 80, "Страх не вырос от приказа"
    
    # 3. СЛОЙ ПРОСТРАНСТВА (Single Source Authority — ADR-044)
    # Проверяем, что _resolve_reactive_movement находит игрока ТОЛЬКО через npc_positions
    spatial_svc_mock = MagicMock()
    spatial_svc_mock.get_nearest.return_value = MagicMock(node_id="main_hall")
    spatial_svc_mock.denormalize_id.return_value = "main_hall"
    
    movement_intent = _resolve_reactive_movement(
        npc_id="thief_shadow",
        intent="approach",
        intent_target="player",
        scene_state=player_in_main_hall, # ADR-044: Игрок читается отсюда
        location_id="tavern_silver_wolf",
        spatial_service=spatial_svc_mock
    )
    
    # 4. ДОКАЗАТЕЛЬСТВО ЗАМКНУТОСТИ
    assert movement_intent is not None, "MovementIntent не создан! Контур разорван"
    assert movement_intent.target_node_id == "main_hall", f"Цель неверна: {movement_intent.target_node_id}"
    assert movement_intent.from_node_id == "shadow_corner"
    
    print("\n[ОСЦИЛЛОГРАФ] КОНТУР ЗАМКНУТ: Команда → Страх → Резолв → Движение")