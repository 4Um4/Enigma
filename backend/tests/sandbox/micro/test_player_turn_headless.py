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
    all_npcs_raw = game_loop._load_npcs_with_runtime(campaign_id)
    
    # Если аватар не был загружен (нет активной сессии), добавляем его вручную для теста
    if not any(n.get("npc_id") == "player" for n in all_npcs_raw):
        from app.models.npc_state import BODY_STATE_HEALTHY
        all_npcs_raw.append({
            "id": "player",
            "npc_id": "player",
            "name": "Tester",
            "type": "player_avatar",
            "archetype": "Drifter",
            "temperament": "Stoic",
            "body_profile": {},
            "body_state": dict(BODY_STATE_HEALTHY),
            "psyche": {"stress": 0.0, "fear": 0.0, "willpower": 1.0, "emotion": "NEUTRAL"},
            "social_stats": {"trust": 50.0, "fear_of_player": 0.0, "debt": 0.0},
            "status_profile": {"faction_rank": {}}
        })
    
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