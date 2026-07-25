"""
Автономный Мир-Контракт (AWC) — автотест для pre-launch проверки.

Запускать при работающем game_launcher.py:
    python backend/scripts/verify_autonomous_world.py

Создаёт сессию, ждёт 5 минут (ничего не отправляя), проверяет AWC.
Если все 8 пунктов (A-H) проходят — мир автономен.

ВНИМАНИЕ: Требует запущенный backend на http://localhost:8000.
Запускать ТОЛЬКО после применения шагов 1-4 этого ТЗ.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

BACKEND = "http://localhost:8000"
CAMPAIGN = "Open_road"
WAIT_SECONDS = 300  # 5 минут

# Путь к логам — адаптировать под реальную структуру
PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_PATH = PROJECT_ROOT / "backend" / "logs" / "cds_backend.log"


def test_autonomous_world():
    """Главная функция проверки AWC."""
    print("=" * 60)
    print(f"AWC test: starting session for campaign '{CAMPAIGN}'...")
    print("=" * 60)

    # 0. Проверить что backend жив
    try:
        r = requests.get(f"{BACKEND}/api/system/status", timeout=5)
        if r.status_code != 200:
            print(f"❌ BACKEND NOT ALIVE: /api/system/status returned {r.status_code}")
            sys.exit(1)
        print(f"✅ Backend alive: {r.json()}")
    except Exception as e:
        print(f"❌ BACKEND NOT ALIVE: {e}")
        print("   Запусти game_launcher.py и дождись backend startup")
        sys.exit(1)

    # 1. Создать сессию
    try:
        r = requests.post(f"{BACKEND}/api/game/{CAMPAIGN}/start", json={}, timeout=10)
        if r.status_code != 200:
            # Возможно сессия уже есть — попробовать без start
            print(f"⚠️ /start returned {r.status_code}, trying to use existing session...")
        else:
            print(f"✅ Session started for {CAMPAIGN}")
    except Exception as e:
        print(f"❌ Cannot start session: {e}")
        sys.exit(1)

    # 2. Начальное состояние
    try:
        initial = requests.get(f"{BACKEND}/api/game/{CAMPAIGN}/state", timeout=10).json()
    except Exception as e:
        print(f"❌ Cannot get initial state: {e}")
        sys.exit(1)

    initial_time = initial.get("game_time_seconds", 0)
    initial_positions = {}
    for n in initial.get("npcs", []):
        npc_id = n.get("npc_id", n.get("id", ""))
        pos = n.get("position", n.get("local_position", {}))
        initial_positions[npc_id] = pos

    print(f"Initial game_time_seconds: {initial_time}")
    print(f"Initial NPC positions: {len(initial_positions)} NPCs")

    # 3. Ждать 5 минут
    print(f"\nWaiting {WAIT_SECONDS} seconds (autonomous observation)...")
    print("Не вводи ничего в игру. Просто наблюдай.")
    for i in range(WAIT_SECONDS, 0, -30):
        print(f"  ...{i} seconds remaining")
        time.sleep(30)

    # 4. Финальное состояние
    try:
        final = requests.get(f"{BACKEND}/api/game/{CAMPAIGN}/state", timeout=10).json()
    except Exception as e:
        print(f"❌ Cannot get final state: {e}")
        sys.exit(1)

    final_time = final.get("game_time_seconds", 0)
    final_positions = {}
    for n in final.get("npcs", []):
        npc_id = n.get("npc_id", n.get("id", ""))
        pos = n.get("position", n.get("local_position", {}))
        final_positions[npc_id] = pos

    # 5. Чтение логов
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            log_content = f.read()
    except Exception as e:
        print(f"⚠️ Cannot read {LOG_PATH}: {e}")
        log_content = ""

    tick_crash_count = log_content.count("[TICK_CRASH]")
    dialogue_sub_count = log_content.count("[NPC_DIALOGUE_SUB]")
    dialogue_exec_count = log_content.count("[TASK_SCHED] dialogue executed")
    decision_hub_return_count = log_content.count("[DECISION_HUB_RETURN]")
    motion_router_count = log_content.count("[MOTION_ROUTER]")
    build_comm_failed_count = log_content.count("[BUILD_COMM_FAILED]")

    # 6. Проверки AWC
    failures = []

    print(f"\n{'=' * 60}")
    print("AWC RESULTS")
    print(f"{'=' * 60}")

    # A. Время идёт
    time_delta = final_time - initial_time
    if time_delta < 3000:  # минимум 50 минут игрового времени
        failures.append(f"A: time only advanced {time_delta}s (expected >3000)")
        print(f"❌ A FAILED: time advanced {time_delta}s (expected >3000)")
    else:
        print(f"✅ A PASSED: time advanced {time_delta}s ({time_delta/60:.1f} minutes)")

    # B. NPC двигаются
    moved = 0
    for npc_id, initial_pos in initial_positions.items():
        final_pos = final_positions.get(npc_id, {})
        ix = initial_pos.get("x", 0) if isinstance(initial_pos, dict) else 0
        iy = initial_pos.get("y", 0) if isinstance(initial_pos, dict) else 0
        fx = final_pos.get("x", 0) if isinstance(final_pos, dict) else 0
        fy = final_pos.get("y", 0) if isinstance(final_pos, dict) else 0
        if fx != ix or fy != iy:
            moved += 1
    if moved < 5:
        failures.append(f"B: only {moved}/{len(initial_positions)} NPCs moved (expected ≥5)")
        print(f"❌ B FAILED: only {moved}/{len(initial_positions)} NPCs moved")
    else:
        print(f"✅ B PASSED: {moved}/{len(initial_positions)} NPCs moved")

    # C. DecisionHub возвращает решения
    if decision_hub_return_count < 10:
        failures.append(f"C: only {decision_hub_return_count} DECISION_HUB_RETURN logs (expected ≥10)")
        print(f"❌ C FAILED: only {decision_hub_return_count} DECISION_HUB_RETURN")
    else:
        print(f"✅ C PASSED: {decision_hub_return_count} DECISION_HUB_RETURN logs")

    # D. Communication intents → dialogues
    if dialogue_exec_count < 1:
        failures.append("D: 0 dialogues executed (expected ≥1)")
        print("❌ D FAILED: 0 dialogues executed")
    else:
        print(f"✅ D PASSED: {dialogue_exec_count} dialogues executed")

    # E. NpcDialogueSubscriber ловит события
    if dialogue_sub_count < 1:
        failures.append("E: 0 NPC_DIALOGUE_SUB events (expected ≥1)")
        print("❌ E FAILED: 0 NPC_DIALOGUE_SUB events")
    else:
        print(f"✅ E PASSED: {dialogue_sub_count} NPC_DIALOGUE_SUB events")

    # F. Persistence не падает
    if tick_crash_count > 0:
        failures.append(f"F: {tick_crash_count} TICK_CRASH events (expected 0)")
        print(f"❌ F FAILED: {tick_crash_count} TICK_CRASH events")
    else:
        print("✅ F PASSED: 0 TICK_CRASH events")

    # G. _build_communication не падает
    if build_comm_failed_count > 5:
        failures.append(f"G: {build_comm_failed_count} BUILD_COMM_FAILED (expected ≤5)")
        print(f"❌ G FAILED: {build_comm_failed_count} BUILD_COMM_FAILED")
    else:
        print(f"✅ G PASSED: {build_comm_failed_count} BUILD_COMM_FAILED (acceptable)")

    # H. Proactive movement
    if motion_router_count < 1:
        failures.append("H: 0 MOTION_ROUTER logs (expected ≥1)")
        print("❌ H FAILED: 0 MOTION_ROUTER logs")
    else:
        print(f"✅ H PASSED: {motion_router_count} MOTION_ROUTER logs")

    # 7. Итог
    print(f"\n{'=' * 60}")
    if failures:
        print(f"❌ AWC FAILED — {len(failures)} issues:")
        for f in failures:
            print(f"  - {f}")
        print("\nОтладка:")
        print(f"  1. Проверь логи: {LOG_PATH}")
        print("  2. grep 'TICK_CRASH\\|BUILD_COMM_FAILED' backend/logs/cds_backend.log")
        print("  3. grep 'DECISION_HUB_RETURN' backend/logs/cds_backend.log | tail -5")
        sys.exit(1)
    else:
        print("✅ AWC PASSED — мир автономен!")
        print("\nЧто это значит:")
        print("  - Симуляция работает без ввода игрока")
        print("  - NPC двигаются, принимают решения, говорят")
        print("  - Цикл эмерджентности замыкается")
        print("  - Можно переходить к мини-игре «Секреты Люси»")
        sys.exit(0)


if __name__ == "__main__":
    test_autonomous_world()
