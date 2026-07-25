# path: backend/tests/sandbox/micro/test_run_turn_e2e.py
"""
E2E тест для S128 FIX: Проверка run_turn с поднятым LLM-сервером и Eavesdrop.
Гарантирует, что player_recognition переживает коммит, а журнал заполняется,
включая подслушанные реплики NPC-NPC.

Запуск: cd backend; python tests/sandbox/micro/test_run_turn_e2e.py
"""

import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Пропатчим sys.path
_BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND))


async def _run_e2e_test():
    from app.core.config import settings
    from app.domain.events import EventDTO
    from app.main import _kill_llama_server, _restart_llama_server
    from app.models.schemas import ChatTurnRequest, PlayerAction
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType
    from app.services.game_loop_builder import build_game_loop

    print("--- [1/6] Инициализация GameLoop ---")
    temp_saves = tempfile.mkdtemp(prefix="e2e_saves_")
    settings.saves_dir = temp_saves
    data_dir = Path(settings.data_dir)
    game_loop = build_game_loop(data_dir)
    campaign_id = "Open_road"

    # Запускаем idle_tick, чтобы инициализировать spatial_service
    game_loop.idle_tick(campaign_id)

    print("--- [2/6] Запуск llama-server (может занять до 120 сек) ---")
    if not _restart_llama_server():
        print("❌ ТЕСТ ПРОВАЛЕН: LLM сервер не стартовал.")
        _kill_llama_server()
        return False

    print("--- [3/6] Прогон run_turn (Игрок: 'Люся, привет') ---")
    req = ChatTurnRequest(
        campaign_id=campaign_id,
        world_id="world_1",
        location="tavern_silver_wolf",
        actions=[PlayerAction(player_name="Tester", action="Люся, привет")]
    )

    try:
        response = await game_loop.run_turn(req)
    except Exception as e:
        print(f"❌ ТЕСТ ПРОВАЛЕН: Ошибка во время run_turn: {e}")
        _kill_llama_server()
        return False
    finally:
        print("--- [4/6] Остановка llama-server ---")
        _kill_llama_server()

    print("--- [5/6] Проверка базовых артефактов (Journal + Recognition) ---")
    
    # Проверка 1: Журнал не пуст
    journal = game_loop.avatar_service.get_journal(campaign_id)
    if not journal:
        print("❌ ТЕСТ ПРОВАЛЕН: Журнал пуст после run_turn.")
        return False
    print(f"✓ Журнал содержит {len(journal)} записей.")

    # Проверка 2: player_recognition сохранён в scene_state
    from app.core.constants import DEFAULT_LOCATION_ID
    scene = game_loop.scene_manager.get_scene_state(campaign_id, DEFAULT_LOCATION_ID)
    if not scene or "player_recognition" not in scene:
        print("❌ ТЕСТ ПРОВАЛЕН: player_recognition отсутствует в сохранённом scene_state.")
        return False

    recog_map = scene.get("player_recognition", {})
    recognized = any(v.get("confidence", 0.0) > 0 for v in recog_map.values())
    if not recognized:
        print(f"❌ ТЕСТ ПРОВАЛЕН: Ни один NPC не распознан. recog_map={recog_map}")
        return False
    print("✓ player_recognition успешно персистится после run_turn.")

    print("--- [6/6] Проверка механики Eavesdrop (NPC-NPC) ---")
    # Получаем шину событий
    bus = get_event_bus()
    
    # Вызываем idle_tick, чтобы обновить spatial_query
    game_loop.idle_tick(campaign_id)

    # Диагностика: проверяем расстояние до maid_lusya
    _sq = getattr(game_loop, "_current_spatial_query", None)
    if _sq:
        _dists = _sq.player_distances(["maid_lusya", "borko"])
        print(f"[DIAG_EAVESDROP] dists = {_dists}")
    else:
        print("[DIAG_EAVESDROP] _current_spatial_query is None!")

    # S128: Используем maid_lusya как спикера, так как она ближе к игроку
    event = EventDTO(
        id="test-eavesdrop-1",
        type=EventType.NPC_SPOKE.value,
        source="maid_lusya",
        timestamp=datetime.now(timezone.utc).timestamp(),
        payload={
            "target_id": "borko",
            "text": "Борко, я видела, как Горан прятал товар в подвале.",
            "tone": "SUSPICIOUS",
            "topic": "goran_contraband"
        },
        visibility="public",
        radius=5.0,
        persistence_level="session"
    )

    # Публикуем событие
    bus.publish(event)
    
    # Проверяем, что реплика попала в журнал игрока
    journal_after_eavesdrop = game_loop.avatar_service.get_journal(campaign_id)
    
    eavesdrop_found = any(
        entry.get("speaker") == "maid_lusya" and "подвале" in entry.get("text", "")
        for entry in journal_after_eavesdrop
    )
    
    if not eavesdrop_found:
        print("❌ ТЕСТ ПРОВАЛЕН: Подслушанная реплика NPC-NPC не попала в журнал.")
        print(f"Журнал: {journal_after_eavesdrop}")
        return False

    print("✓ Eavesdrop работает: подслушанная реплика Люси добавлена в журнал.")
    print("\n🎉 E2E ТЕСТ ПРОЙДЕН УСПЕШНО!")
    return True

if __name__ == "__main__":
    success = asyncio.run(_run_e2e_test())
    sys.exit(0 if success else 1)