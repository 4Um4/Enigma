# backend/tests/sandbox/system/test_homeostatic_stability.py
"""
Запуск: cd backend; python -c "from tests.sandbox.system.test_homeostatic_stability import run_stability_test; run_stability_test()"; cd ..
"""

import math
import logging

_SOCIAL_EMA_DECAY_RATE = math.log(2) / 50.0 
_SOCIAL_PRESSURE_SCALE = 1.5
_SOCIAL_RELAXATION_RATE = 0.05

_INPUT_SPEAK = 0.10
_INPUT_LISTEN = 0.15

logging.basicConfig(level=logging.WARNING, format='%(message)s')

def run_stability_test():
    npc_state = {
        "npc_id": "extrovert",
        "gregariousness": 0.8,
        "social_satiation": 50.0,
        "social_input_ema": 0.0
    }
    
    setpoint = 0.2 + (0.6 * npc_state["gregariousness"])
    print(f"=== STABILITY TEST: NPC={npc_state['npc_id']} Setpoint={setpoint:.2f} ===")
    
    history = []
    
    for tick in range(200):
        # 1. Field Layer (True Homeostasis)
        current_sat = npc_state["social_satiation"]
        relaxation = (50.0 - current_sat) * _SOCIAL_RELAXATION_RATE
        
        actual = npc_state["social_input_ema"]
        # Transient Force: исчезает при actual -> 0
        input_force = (actual - setpoint) * _SOCIAL_PRESSURE_SCALE * actual
        
        satiation_delta = relaxation + input_force
        ema_decay = -actual * _SOCIAL_EMA_DECAY_RATE
        
        npc_state["social_satiation"] = max(0.0, min(100.0, current_sat + satiation_delta))
        npc_state["social_input_ema"] = max(0.0, min(1.0, actual + ema_decay))
        
        # 2. Event Layer: ОДИН разговор на 10-м тике, затем тишина
        if tick == 10:
            npc_state["social_input_ema"] = min(1.0, npc_state["social_input_ema"] + _INPUT_SPEAK + _INPUT_LISTEN)
            
        history.append(npc_state["social_satiation"])
        
    max_val = max(history)
    min_val = min(history)
    last_val = history[-1]
    
    print(f"Start: {history[0]:.1f}")
    print(f"Min:   {min_val:.1f}")
    print(f"Max:   {max_val:.1f}")
    print(f"End:   {last_val:.1f}")
    
    # Система стабильна, если после всплеска она возвращается к 50.0
    if abs(last_val - 50.0) < 2.0:
        print("[OK] Истинный гомеостаз. Система вернулась в равновесие (~50.0).")
    else:
        print(f"[WARN] Система не вернулась в равновесие. End={last_val:.1f}")

if __name__ == "__main__":
    run_stability_test()