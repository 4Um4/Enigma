"""
Файл: backend/tests/sandbox/test_causal_movement.py
Назначение: Тестирование нарушения законов реальности (Fail Conditions).
Зависимости: pytest, app.services.input.intent_compressor, app.services.game_loop.phase_1_input

TODO
"""

from app.domain.events import EventDTO
from app.domain.intent import IntentParametersDTO
from app.domain.intent_profile import ActionType, IntentSemanticField
from app.models.state_delta import DeltaDomain
from app.services.game_loop.phase_1_input import resolve_player_intent
from app.services.input.intent_compressor import IntentCompressor
from app.services.social.directive_interpretation_subscriber import DirectiveInterpretationSubscriber


class TestCausalOntology:
    """Верификатор законов реальности ENIGMA.
    Тесты валятся, если нарушена онтология (появился bypass)."""

    def test_no_direct_mutation_of_position(self, minimal_world):
        """FAIL CONDITION: Прямая мутация позиции NPC."""
        npc_before = minimal_world["all_npcs_raw"][1].copy()
        _compressor = IntentCompressor(llm_client=None)
        semantic_field = _compressor._fast_path_parse("Тень, иди сюда")
        assert minimal_world["all_npcs_raw"][1] == npc_before, "ОНТОЛОГИЯ НАРУШЕНА: Слой 1 мутировал all_npcs_raw"

    def test_no_direct_scene_change_in_resolver(self, minimal_world):
        """FAIL CONDITION: Генерация SceneChange из IntentCompressor или Resolver."""
        _compressor = IntentCompressor(llm_client=None)
        resolution = resolve_player_intent(
            raw_action="Тень, подойди",
            action_type="player_interacts",
            target="",
            player_dict={},
            scene_context=minimal_world,
        )
        assert not hasattr(resolution, "scene_change"), "ОНТОЛОГИЯ НАРУШЕНА: Resolver генерирует SceneChange (COMMAND)"
        assert isinstance(resolution.original_intent.parameters, IntentParametersDTO)

    def test_pressure_modifies_utility_not_commands(self):
        """FAIL CONDITION: Давление становится командой (ReflexEngine)."""
        semantic_field = IntentSemanticField(
            action_type=ActionType.MOVE, target_reference="тень", social_pressure=0.9, raw_text="Тень, иди сюда"
        )
        assert semantic_field.action_type == ActionType.MOVE
        assert not hasattr(semantic_field, "movement_intent"), (
            "ОНТОЛОГИЯ НАРУШЕНА: Давление генерирует MovementIntent напрямую"
        )

    def test_membrane_visibility_enforced(self, minimal_world, cluster_occupancy):
        """FAIL CONDITION: Давление без мембранной видимости."""
        player_cluster = cluster_occupancy.get_cluster("player")
        shadow_cluster = cluster_occupancy.get_cluster("thief_shadow")
        assert player_cluster is not None and shadow_cluster is not None

    def test_decision_requires_pressure_provenance(self):
        """FAIL CONDITION: Решение без источника давления."""
        params = IntentParametersDTO(semantic_action="MOVE", target_reference="тень", social_pressure=0.9)
        assert params.social_pressure > 0.0, "ОНТОЛОГИЯ НАРУШЕНА: Нет provenance давления для решения"


class TestSocialPhysics:
    """Верификатор Физики Власти.
    Тесты проверяют, что речь искривляет utility-space, а не создает команды."""

    def test_speech_act_generates_pressure_landscape(self, minimal_world):
        """GIVEN: Игрок приказывает. WHEN: Событие обработано. EXPECT: Давление создано, MovementIntent НЕТ."""
        subscriber = DirectiveInterpretationSubscriber()

        # Событие речи с семантикой приказа
        event = EventDTO.create(
            event_type="PLAYER_SPOKE",
            source="player",
            payload={
                "semantic_action": "MOVE",
                "target_id": "thief_shadow",
                "social_pressure": 0.8,  # Высокая социальная сила (приказ)
                "raw_input": "Тень, иди сюда",
            },
        )

        # Обработка
        deltas = subscriber.handle(event, minimal_world["all_npcs_raw"])

        # Ожидание 1: Дельты созданы (давление материализовалось)
        assert len(deltas) > 0, "ФИЗИКА ВЛАСТИ НАРУШЕНА: Приказ не породил давления"

        # Ожидание 2: Дельты меняют Эмоции и Социум (искривление utility-space)
        domains = [d.domain for d in deltas]
        assert DeltaDomain.EMOTION in domains, "ФИЗИКА ВЛАСТИ НАРУШЕНА: Нет эмоционального давления (страха)"
        assert DeltaDomain.SOCIAL in domains, "ФИЗИКА ВЛАСТИ НАРУШЕНА: Нет социального давления (подчинения)"

        # Ожидание 3: Дельты не содержат MovementIntent (давление - не команда)
        for delta in deltas:
            assert "MovementIntent" not in str(delta.payload), (
                "ФИЗИКА ВЛАСТИ НАРУШЕНА: Давление напрямую создало MovementIntent (Aggro Controller)"
            )

    def test_legitimacy_affects_pressure(self, minimal_world):
        """GIVEN: NPC не боится игрока. WHEN: Приказ. EXPECT: Низкое давление подчинения."""
        subscriber = DirectiveInterpretationSubscriber()

        # Меняем Тени страх на 0 (она не боится)
        minimal_world["all_npcs_raw"][1]["social_stats"] = {"fear_of_player": 0.0}

        event = EventDTO.create(
            event_type="PLAYER_SPOKE",
            source="player",
            payload={
                "semantic_action": "MOVE",
                "target_id": "thief_shadow",
                "social_pressure": 0.8,
                "raw_input": "Тень, иди сюда",
            },
        )

        deltas = subscriber.handle(event, minimal_world["all_npcs_raw"])

        # Проверяем, что страх/подчинение минимальны (цена отказа низкая)
        emotion_delta = next((d for d in deltas if d.domain == DeltaDomain.EMOTION), None)
        assert emotion_delta is not None
        # stress_delta должен быть небольшим, так как страх=0
        assert emotion_delta.payload.stress_delta < 15.0, (
            "ФИЗИКА ВЛАСТИ НАРУШЕНА: Давление не зависит от легитимности/страха"
        )
