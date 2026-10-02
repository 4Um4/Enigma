# path: backend/tests/test_tick_orchestrator_full_loop.py
# Назначение: Сквозной дым-тест (Smoke Test) TickOrchestrator.execute()
# Зависимости: pytest, unittest.mock, app.services.*
# Основные сущности: test_tick_orchestrator_full_loop_player_attacks
"""
Сквозной тест для TickOrchestrator.execute() с событием player_attacks.

TODO:
- Добавить больше сценариев (player_intimidates, player_flees и т.д.)
- Проверить, что реакции NPC корректно влияют на их состояние (stress, drives и т.д.)
- В будущем: интеграционные тесты с реальными LLM (можно пометить как @pytest.mark.integration) для проверки всей цепочки от восприятия до генерации реакций.

Запуск: cd backend; python -m pytest tests/test_tick_orchestrator_full_loop.py -v; cd ..
"""

from unittest.mock import MagicMock

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.domain.events import EventDTO
from app.services.events.event_bus import EventBus
from app.services.events.event_types import EventType
from app.services.memory.memory_manager import MemoryManager
from app.services.memory.relationship_store import RelationshipStore
from app.services.npc.state_applicator import StateApplicator
from app.services.tick_orchestrator import TickOrchestrator


def _make_npc(npc_id: str = "npc_1", stress: float = 30.0) -> dict:
    """Создаёт тестовый NPC dict (аналог _make_npc из test_reaction_subscriber)."""
    return {
        "id": npc_id,
        "location_id": "test_room",  # P2-fix (ТЗДНЯ): фильтр локации отсеивает NPC без location_id
        "psyche": {
            "stress": stress,
            "willpower": 50.0,
        },
        "drives": {
            "control": 0.25,
            "significance": 0.25,
            "fear": 0.25,
            "desire": 0.25,
        },
    }


def _make_scene_state() -> dict:
    """Создаёт минимальный SceneState для Фазы 0."""
    return {
        "location_id": "test_room",
        "environment": {"light_level": "bright", "noise_level": "quiet"},
        "environment_modifiers": {},
        "objects": {},
        "spatial_walls": [],
        "spatial_obstacles": [],
        "npc_positions": {
            # P2-fix (ТЗДНЯ): без позиции игрока дистанция атаки = 999 → miss,
            # физические дельты и шок не рождаются.
            "player": {
                "location_id": "test_room",
                "position": "",
                "activity": "idle",
                "visible": True,
                "local_position": {"x": 6.0, "y": 4.0},
            },
            "npc_1": {
                "location_id": "test_room",
                "position": "",
                "activity": "idle",
                "visible": True,
                "local_position": {"x": 6.0, "y": 5.0},
            }
        },
    }


def test_tick_orchestrator_full_loop_player_attacks():
    """Сквозной тест: player_attacks -> EventBus -> PerceptionSubscriber -> StateDeltas -> StateApplicator.

    Проверяет полный idle-цикл (Фазы 0-10) оркестратора.
    Моки только на LLM (нет) и I/O (SqlitePersist/YAML через scene_manager).
    """
    # 1. Подготовка реальных сервисов и моков
    event_bus = EventBus()

    # MemoryManager реальный, но с моком LayeredMemory (нет I/O)
    memory_manager = MemoryManager(layered_memory=MagicMock(), data_dir="test_data")

    # Мок SceneManager (чтобы не гонять I/O в Фазе 10)
    scene_manager = MagicMock()
    scene_manager.commit.return_value = 1
    scene_manager.apply_changes = MagicMock()

    # Оркестратор
    orchestrator = TickOrchestrator(
        scene_manager=scene_manager,
        memory_manager=memory_manager,
        event_bus=event_bus,
    )

    # Инжекция реального StateApplicator (единый мутатор по ADR-002)
    rel_store = RelationshipStore(data_dir="test_data")
    state_applicator = StateApplicator(relationship_store=rel_store)
    orchestrator._state_applicator = state_applicator

    # Мок LifeEngine: возвращает нашего NPC через get_npc_states()
    npc_raw = _make_npc(stress=30.0)
    all_npcs = [npc_raw]  # P2-fix (ТЗДНЯ, факт 4): собственная ссылка для финального утверждения
    life_engine_mock = MagicMock()
    life_engine_mock.tick.return_value = ([], [])  # Фаза 0: нет физ. изменений, нет life_intents
    life_engine_mock.get_npc_states.return_value = [npc_raw]
    life_engine_mock.tick_decisions.return_value = ([], [], [])  # Фаза 5: нет решений (decisions, comms, movements)
    life_engine_mock.get_idle_pressure_map.return_value = {}  # FIX: Возвращает пустой dict, а не MagicMock
    orchestrator._life_engine = life_engine_mock

    # P2-fix (ТЗДНЯ): стаб _get_npc_runtime_path удалён — метода больше нет
    # в TickOrchestrator (проверено Select-String, 0 вхождений).

    # Мок SnapshotBuilder (Фаза 9)
    snapshot_builder_mock = MagicMock()
    snapshot_builder_mock.build.return_value = {}
    orchestrator._snapshot_builder = snapshot_builder_mock

    # 2. Публикация события player_attacks (до execute)
    # Событие попадёт в буфер PerceptionSubscriber, а в Фазе 8 будет обработано
    event = EventDTO.create(
        event_type=EventType.PLAYER_ATTACKS.value,
        source="player",
        payload={"intensity": 1.0, "actor_id": "player", "target_id": "npc_1"},
    )
    event_bus.publish(event)

    # 3. Выполнение полного idle-тика (Фазы 0-10)
    result = orchestrator.execute(
        campaign_id="test_campaign",
        scene_state=_make_scene_state(),
        all_npcs_raw=all_npcs,  # P2-fix (ТЗДНЯ): контракт S113 — явная передача NPC в Фазу 8
        tick_number=1,
    )

    # 4. Ассерты
    assert result.status == "ok", f"Тик завершился с ошибкой: {getattr(result, 'error', None)}"

    # Проверяем, что стресс NPC увеличился (ReactionSubscriber генерирует stress_delta)
    # Если ctx.all_npcs_raw не был синхронизирован с ctx.npc_states, мутация не применится!
    # Этот тест ДОЛЖЕН упасть, обнаружив баг с пустым all_npcs_raw в idle-тикете.
    # P2-fix (ТЗДНЯ, вердикт зонда v2): дельты применяются к нормализованным
    # копиям (L2.2 Entity Birth Contract); входной all_npcs_raw ядро НЕ мутирует
    # (ADR-TZ09-1 pure reducer, L3: результат возвращается значением).
    # Авторитетный пост-тик словарь — TickResultDTO.all_npcs_raw.
    final_npcs = getattr(result, "all_npcs_raw", None) or []
    final_npc = next(
        (
            n
            for n in final_npcs
            if n.get("id") == "npc_1" or n.get("npc_id") == "npc_1"
        ),
        None,
    )
    assert final_npc is not None, (
        "npc_1 отсутствует в TickResultDTO.all_npcs_raw — контракт результата ядра нарушен."
    )
    assert final_npc["psyche"]["stress"] > 30.0, (
        "Стресс NPC не увеличился — дельта из Phase 8 не применена в Phase 10! Вероятно, ctx.all_npcs_raw не заполнен."
    )
