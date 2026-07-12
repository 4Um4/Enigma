# backend/tests/sandbox/system/test_homeostatic_dialogue_stability.py
"""
Sandbox Test: Homeostatic Stability & LLM Dialogue Extraction.
Прогоняет 200 тиков, извлекает чистый текст диалогов LLM и трекает social_satiation.

Запуск:
cd backend
python -c "from tests.sandbox.system.test_homeostatic_dialogue_stability import run_homeostatic_sandbox; run_homeostatic_sandbox()"
"""

import asyncio
import logging
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger("HomeostasisSandbox")
logging.basicConfig(level=logging.WARNING, format="%(message)s")


def _start_llama_server(settings) -> subprocess.Popen:
    """Запускает llama-server используя пути из settings."""
    print("[SETUP] Запуск llama-server...")

    try:
        urllib.request.urlopen(f"{settings.llama_cpp_server_url}/health", timeout=2)
        print("[SETUP] llama-server уже запущен (внешний инстанс).")
        return None
    except Exception:
        pass

    cmd = [
        settings.llama_cpp_server_executable,
        "-m",
        settings.llama_cpp_model_path,
        "--port",
        settings.llama_cpp_server_url.split(":")[-1],
        "--host",
        "localhost",
        "-ngl",
        str(settings.gpu_layers),
        "-c",
        str(settings.ctx_size),
        "-t",
        str(settings.threads),
    ]

    logs_dir = Path("backend/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    stderr_path = logs_dir / "llama_server_stderr.log"

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=open(stderr_path, "a", encoding="utf-8"),
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
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


def run_homeostatic_sandbox():
    try:
        from app.core.config import settings
        from app.models.schemas import ChatTurnRequest, PlayerAction
        from app.services.game_loop.scene_init import ensure_scene_initialized
        from app.services.game_loop_builder import build_game_loop
        from app.services.npc.life_engine import get_life_engine
    except ImportError as e:
        print(f"[ERROR] Импорт не удался. {e}")
        return

    # 1. Запуск LLM сервера
    server_proc = _start_llama_server(settings)

    print("=== ИНИЦИАЛИЗАЦИЯ ПЕСОЧНИЦЫ ===")

    # 2. Инициализация GameLoop
    data_dir = Path(settings.data_dir)
    game_loop = build_game_loop(data_dir)
    engine = get_life_engine()

    campaign_id = "Open_road"
    world_id = "Open_road"
    location = "tavern"
    player_name = "Tester"

    # 3. Загрузка кампании и инициализация сцены (загрузка NPC в кэш)
    print(f"[SETUP] Загрузка кампании {campaign_id}...")
    game_loop.load_campaign(campaign_id, world_id)
    ensure_scene_initialized(game_loop, campaign_id)

    # 4. Подготовка NPC
    all_npcs = engine._npc_cache.get(campaign_id, {})
    npc_ids = []
    for npc_dict in all_npcs.values():
        if npc_dict.get("npc_id") != "player":
            npc_dict["social_satiation"] = 10.0
            npc_dict["social_input_ema"] = 0.0
            npc_ids.append(npc_dict["npc_id"])
            print(f"[SETUP] NPC {npc_dict.get('name', npc_dict['npc_id'])} forced to social_satiation=10.0")

    if len(npc_ids) < 2:
        print("[WARN] Нужно минимум 2 NPC для диалога.")

    satiation_history: Dict[str, List[float]] = {nid: [] for nid in npc_ids}
    llm_dialogues: List[str] = []

    print("\n=== ЗАПУСК 200 ТИКОВ ===")

    # 5. Цикл тиков
    for tick in range(200):
        player_action = PlayerAction(player_name=player_name, action="осмотреться")
        req = ChatTurnRequest(world_id=world_id, campaign_id=campaign_id, location=location, actions=[player_action])

        try:
            result = asyncio.run(game_loop.run_turn(req))

            if result and hasattr(result, "dm_response") and result.dm_response:
                clean_text = result.dm_response.strip()
                if clean_text:
                    llm_dialogues.append(f"--- Tick {tick + 1} ---\n{clean_text}")

            current_npcs = engine._npc_cache.get(campaign_id, {})
            for nid in npc_ids:
                sat = current_npcs.get(nid, {}).get("social_satiation", 50.0)
                satiation_history[nid].append(sat)

        except Exception as e:
            print(f"[TICK {tick + 1} ERROR] {e}")

    print("\n=== РЕЗУЛЬТАТЫ: DIALOGUES (LLM OUTPUT) ===")
    for d in llm_dialogues[-5:]:  # Выводим последние 5 диалогов
        print(d)
        print()

    if not llm_dialogues:
        print("LLM не сгенерировала ни одного диалога. Проверь логи backend/logs/llama_server_stderr.log")

    print("\n=== РЕЗУЛЬТАТЫ: STABILITY (SOCIAL SATIATION) ===")
    for nid, history in satiation_history.items():
        if not history:
            continue
        max_val = max(history)
        min_val = min(history)
        last_val = history[-1]
        print(f"NPC {nid}: Start={history[0]:.1f} | Min={min_val:.1f} | Max={max_val:.1f} | End={last_val:.1f}")

        amplitude = max_val - min_val
        if amplitude > 40.0 and abs(last_val - 50.0) > 20.0:
            print(f"  [WARN] Высокая амплитуда ({amplitude:.1f}). Возможна осцилляция (голод <-> перегруз).")
        else:
            print(f"  [OK] Амплитуда {amplitude:.1f}. Система стремится к равновесию.")

    # 6. Завершение работы сервера
    print("\n=== ЗАВЕРШЕНИЕ ===")
    if server_proc is not None:
        server_proc.terminate()
        server_proc.wait(timeout=5)
        print("[SETUP] llama-server остановлен.")
    else:
        print("[SETUP] llama-server был запущен извне, не останавливаем.")


if __name__ == "__main__":
    run_homeostatic_sandbox()
