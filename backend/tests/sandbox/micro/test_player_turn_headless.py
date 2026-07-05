"""
Sandbox Test: Player Turn Pipeline (Headless).
Проверяет, что InterventionEvent от игрока доходит до ядра и возвращает TickResultDTO.
Не требует LLM-сервера. Запускается аналогично DriftLaboratory.

Запуск:
cd backend
python -c "from tests.sandbox.micro.test_player_turn_headless import run_player_turn_test; run_player_turn_test()"
"""
import sys
import logging
from pathlib import Path

# Добавляем backend/ в path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

logger = logging.getLogger("PlayerTurnTest")
logging.basicConfig(level=logging.WARNING, format='%(message)s')

def run_player_turn_test():
    try:
        from app.core.config import settings
        from app.services.game_loop_builder import build_game_loop
        from app.services.npc.life_engine import get_life_engine
        from app.services.game_loop.scene_init import ensure_scene_initialized
        from app.services.tick_orchestrator import TickOrchestrator
        from app.contracts.interventions import InterventionEvent
        from app.services.spatial.spatial_factory import SpatialFactory
        from app.services.npc.npc_tick_contracts import NpcTickServices
        from app.services.events.event_bus import get_event_bus
    except ImportError as e:
        print(f"[ERROR] Импорт не удался. {e}")
        return False

    print("=== ИНИЦИАЛИЗАЦИЯ ТЕСТА ТРУБЫ ИГРОКА ===")
    
    data_dir = Path(settings.data_dir)
    game_loop = build_game_loop(data_dir)
    engine = get_life_engine()

    campaign_id = "Open_road"
    world_id = "Open_road"
    location = "tavern_silver_wolf"
    player_name = "Tester"

    print(f"[SETUP] Загрузка кампании {campaign_id}...")
    game_loop.load_campaign(campaign_id, world_id)
    ensure_scene_initialized(game_loop, campaign_id)

    # S115 FIX: Инъекция аватара через штатный API, а не хардкод списка.
    # Это гарантирует, что LifeEngine кэширует аватара, и TickOrchestrator найдёт его.
    from app.services.player_session_service import player_session_service
    player_session_service.select_player(campaign_id, player_name)
    
    # 1. Создаем CharacterSheet, чтобы _load_npcs_with_runtime нашёл его
    from app.services.character_service import CharacterService
    from app.models.schemas import CharacterSheet
    _char_svc = CharacterService(root=str(game_loop._saves_dir))
    _sheet = CharacterSheet(name=player_name, archetype="Drifter", temperament="Stoic")
    _char_svc.upsert_character(campaign_id, _sheet)
    
    # 2. Сохраняем начальное состояние аватара (тело/психика), чтобы load_state() его подобрал
    from app.models.npc_state import NPCState, BODY_STATE_HEALTHY
    _avatar_state = NPCState(npc_id=player_name)
    _avatar_state.drives = {"control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25}
    _avatar_state.psyche = {"willpower": 50, "breakpoint": 70, "loyalty_true": 0}
    _avatar_state.body_state = dict(BODY_STATE_HEALTHY)
    game_loop.avatar_service.save_state(campaign_id, _avatar_state)

    print("\n=== ВЫПОЛНЕНИЕ ТИКА С INTERVENTION EVENT ===")
    
    # 1. Создаём InterventionEvent от игрока (ATTACK)
    _intervention = InterventionEvent(
        source="player",
        payload={
            "text": "ударить вора",
            "player_name": player_name,
            "semantic_action": "ATTACK",
            "target_id": "thief_shadow",
            "tick": 1,
        },
        tick=1,
    )

    # 2. Подготавливаем зависимости для TickOrchestrator (аналогично npc_orchestration.py)
    scene_state = game_loop.scene_manager.get_scene_state(campaign_id, location)
    
    # Загружаем всех NPC, включая аватар игрока (ADR-030)
    # S115 FIX: Сессия инициализирована выше, аватар подгрузится автоматически
    all_npcs_raw = game_loop._load_npcs_with_runtime(campaign_id)
    
    if not any(n.get("npc_id") == "player" for n in all_npcs_raw):
        print("[FAIL] Аватар игрока не загружен через _load_npcs_with_runtime!")
        return False
    _spatial_svc = SpatialFactory.build_for_campaign(
        campaign_id=campaign_id,
        location_id=location,
        scene_state=scene_state or {},
    )
    
    _npc_svc = NpcTickServices(
        memory_manager=game_loop.memory_manager,
        relationship_store=game_loop.memory_manager._relationships,
        social_engine=game_loop._svc.get_social_engine(campaign_id),
        reputation_engine=game_loop._svc.get_reputation_engine(),
        economic_profiles=game_loop._svc.get_or_create_economic_profiles(campaign_id),
        event_bus=get_event_bus(),
        spatial_service=_spatial_svc,
        spatial_query=None, # Simplified for test
    )

    # 3. Вызываем TickOrchestrator.execute()
    tick_orch = game_loop._tick_orch
    try:
        result = tick_orch.execute(
            campaign_id=campaign_id,
            scene_state=scene_state,
            tick_number=1,
            interventions=[_intervention],
            npc_services=_npc_svc,
            spatial_service=_spatial_svc,
            all_npcs_raw=all_npcs_raw,
        )
        
        if result is None:
            print("[FAIL] execute() вернул None")
            return False
            
        if not hasattr(result, 'status'):
            print(f"[FAIL] execute() вернул {type(result).__name__} без поля 'status'")
            return False

        print(f"[PASS] execute() вернул статус: {result.status}")
        print(f"[PASS] execute() вернул тип: {type(result).__name__}")
        
        # Проверяем наличие npc_contexts (должны быть, так как DecisionHub работает)
        if hasattr(result, 'npc_contexts'):
            print(f"[PASS] npc_contexts count: {len(result.npc_contexts)}")
        
        return True

    except AttributeError as e:
        print(f"[FAIL] AttributeError: {e}")
        return False
    except TypeError as e:
        print(f"[FAIL] TypeError: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Неожиданная ошибка: {e}")
        return False

if __name__ == "__main__":
    success = run_player_turn_test()
    if success:
        print("\n=== ТЕСТ ПРОЙДЕН ===")
    else:
        print("\n=== ТЕСТ ПРОВАЛЕН ===")