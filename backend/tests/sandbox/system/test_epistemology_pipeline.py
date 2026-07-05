# backend/tests/sandbox/system/test_epistemology_pipeline.py
"""
Sandbox Test: Epistemology Pipeline & DM Contract v2.
Прогоняет 3 тика, извлекает ObservedFacts и ответ DM.

Запуск:
cd backend
python -c "from tests.sandbox.system.test_epistemology_pipeline import run_epistemology_test; run_epistemology_test()"
"""
import logging
import asyncio
import subprocess
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger("EpistemologyTest")
logging.basicConfig(level=logging.WARNING, format='%(message)s')

def _start_llama_server(settings) -> subprocess.Popen:
    print("[SETUP] Запуск llama-server...")
    try:
        urllib.request.urlopen(f"{settings.llama_cpp_server_url}/health", timeout=2)
        print("[SETUP] llama-server уже запущен (внешний инстанс).")
        return None
    except Exception:
        pass

    cmd = [
        settings.llama_cpp_server_executable,
        "-m", settings.llama_cpp_model_path,
        "--port", settings.llama_cpp_server_url.split(":")[-1],
        "--host", "localhost",
        "-ngl", str(settings.gpu_layers),
        "-c", str(settings.ctx_size),
        "-t", str(settings.threads),
    ]
    
    logs_dir = Path("backend/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    stderr_path = logs_dir / "llama_server_stderr.log"
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=open(stderr_path, "a", encoding="utf-8"),
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
    )
    
    print(f"[SETUP] Ожидание загрузки модели (до {settings.model_load_timeout_sec}с)...")
    for _attempt in range(int(settings.model_load_timeout_sec / 2)):
        try:
            urllib.request.urlopen(f"{settings.llama_cpp_server_url}/health", timeout=2)
            print("[SETUP] llama-server запущен и готов.")
            return proc
        except Exception:
            time.sleep(2)
            
    print("[ERROR] llama-server не смог запуститься. Проверь logs/llama_server_stderr.log")
    proc.terminate()
    raise RuntimeError("LLM Server failed to start")

def run_epistemology_test():
    try:
        from app.core.config import settings
        from app.services.game_loop_builder import build_game_loop
        from app.models.schemas import ChatTurnRequest, PlayerAction
        from app.services.npc.life_engine import get_life_engine
        from app.services.game_loop.scene_init import ensure_scene_initialized
    except ImportError as e:
        print(f"[ERROR] Импорт не удался. {e}")
        return

    # 1. Запуск LLM сервера
    server_proc = _start_llama_server(settings)
    
    print("=== ИНИЦИАЛИЗАЦИЯ ТЕСТА МАШИНЫ ЭПИСТЕМОЛОГИИ ===")
    
    # Sprint P9: Инициализируем LLM-роутер и пул моделей
    from app.services.llm import initialize_router
    print("[SETUP] Инициализация LLM роутера...")
    initialize_router()
    print("[SETUP] LLM роутер готов.")

    data_dir = Path(settings.data_dir)
    game_loop = build_game_loop(data_dir)
    engine = get_life_engine()

    # ВАЖНО: Правильный регистр и конкретная локация
    campaign_id = "Open_road"
    world_id = "Open_road"
    location = "tavern_silver_wolf"
    player_name = "Венус"

    print(f"[SETUP] Загрузка кампании {campaign_id}...")
    game_loop.load_campaign(campaign_id, world_id)
    
    # Инициализируем сессию игрока, чтобы GameLoop добавил аватар в all_npcs_raw
    from app.services.player_session_service import player_session_service
    player_session_service.select_player(campaign_id, player_name)
    
    ensure_scene_initialized(game_loop, campaign_id)

    print("\n=== ЗАПУСК 3 ТИКОВ С LLM ===")
    
    _actions = [
        "осмотреться",
        "подойти к Люсе и спросить: 'Что здесь происходит?'",
        "обратиться к Торнину: 'Налей-ка мне эля, хозяин.'"
    ]
    
    for tick in range(3):
        print(f"\n--- TICK {tick+1} ---")
        player_action = PlayerAction(player_name=player_name, action=_actions[tick])
        req = ChatTurnRequest(
            world_id=world_id,
            campaign_id=campaign_id, 
            location=location,
            actions=[player_action],
            player_position=(5.0, 5.0)  # Гарантируем валидную позицию для DM-валидатора
        )
        
        try:
            # GameLoop.run_turn возвращает ChatTurnResponse
            result = asyncio.run(game_loop.run_turn(req))
            
            if result and hasattr(result, 'observed_facts'):
                print(f"📊 [OBSERVED FACTS BUNDLE] ({len(result.observed_facts)} фактов донесено до DM):")
                if result.observed_facts:
                    for fact_str in result.observed_facts:
                        print(f"   {fact_str}")
                else:
                    print("   (Пусто - игрок ничего не заметил)")
            else:
                print("⚠️ В ответе нет поля observed_facts")
            
            if result and hasattr(result, 'dm_response') and result.dm_response:
                print(f"\n🗣️ [DM RESPONSE]:")
                print(result.dm_response.strip())
                
        except Exception as e:
            print(f"[TICK {tick+1} ERROR] {e}")
            import traceback
            traceback.print_exc()

    print("\n=== Тест завершен ===")
    if server_proc:
        server_proc.terminate()