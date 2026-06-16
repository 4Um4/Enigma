# backend/tests/sandbox/test_7_3_threat_scenario.py
"""
Sandbox 7.3: Целевой сценарий угрозы.
Игрок атакует стража. Проверяем:
1. SURVIVAL доминирует (FLEE или ATTACK).
2. WHY-лог показывает декомпозицию скоринга.
3. L3 (effective_drives) реально влияет на решение.

cd backend; python -m tests.sandbox.test_7_3_threat_scenario; cd ..
"""
import sys
import os
import logging

# Перенаправляем путь для импорта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from app.models.npc_state import NPCState, NPCPersonality, NPCTier, Intent
from app.services.npc.decision_hub import DecisionHub, EventContext
from app.domain.identity_events import EffectiveDrives

# Включаем DEBUG логирование для WHY-лога
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

def run_threat_scenario():
    print("--- Сценарий 7.3: Игрок атакует стража ---")
    
    # 1. NPC: Страж (контроль + воля)
    state = NPCState(npc_id="guard_borko")
    state.hp = 100
    state.max_hp = 100
    
    personality = NPCPersonality(
        npc_id="guard_borko",
        tier=NPCTier.MAJOR,
        drives_base={"control": 0.45, "significance": 0.35, "fear": 0.10, "desire": 0.10},
        willpower=70.0,
        breakpoint=85.0,
        loyalty_base=60.0
    )
    
    # 2. Событие: Прямая атака игрока
    event = EventContext(
        event_type="player_attacks",
        actor_id="player",
        target_id="guard_borko",
        success=True,
        intensity=0.9,          # Сильная атака
        distance=1.5,           # Близкий бой
        witness_count=2,
        visible_threat_markers=["weapon_melee"]
    )
    
    # 3. L3 Проекция: Страх взлетает, контроль тоже (инстинкт самосохранения сменяется боем)
    # ADR-O-304: DecisionHub читает ТОЛЬКО L3, не L0
    l3_drives = EffectiveDrives(values={
        "fear": 0.75, 
        "control": 0.60, 
        "significance": 0.20, 
        "desire": 0.10
    })
    
    # 4. Выполнение
    hub = DecisionHub(seed=42)
    
    print("\n[ОЖИДАНИЕ] SURVIVAL домен должен победить (ATTACK или FLEE). ROUTINE (IDLE/TALK) должен быть подавлен.\n")
    
    result = hub.compute(
        state=state,
        personality=personality,
        event=event,
        effective_drives=l3_drives
    )
    
    print("\n--- РЕЗУЛЬТАТ ---")
    print(f"Выбранный интент: {result.intent}")
    
    if result.intent in (Intent.FLEE, Intent.ATTACK, Intent.INTIMIDATE, Intent.CALL_FOR_HELP):
        print("✅ УСПЕХ: Выбран интент выживания/реакции на угрозу.")
    else:
        print("❌ ПРОВАЛ: Страж проигнорировал угрозу (ROUTINE/SOCIAL).")

if __name__ == "__main__":
    run_threat_scenario()