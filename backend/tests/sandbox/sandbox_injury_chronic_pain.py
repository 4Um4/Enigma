"""
Запуск: cd backend; python -m pytest tests/sandbox/sandbox_injury_chronic_pain.py -v -s; cd ..
"""

import logging
import math
import sys
import os

logging.basicConfig(level=logging.DEBUG, format='[%(name)s] %(message)s', stream=sys.stdout)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.services.combat.physiology_decay_handler import PhysiologyDecayHandler, PAIN_DECAY_LAMBDA
from app.services.combat.injury_processor import InjuryProcessor

def test_chronic_pain_equilibrium():
    """
    ADR-141: InjuryProcessor генерирует pain_delta, компенсирующий Decay.
    Pipeline симулирует TickOrchestrator: all_npcs_raw (вложенный) -> projection (плоский) -> handlers.
    """
    print("\n--- [SANDBOX] CHRONIC PAIN EQUILIBRIUM TEST (ADR-141) ---")
    
    decay_handler = PhysiologyDecayHandler()
    injury_proc = InjuryProcessor()
    
    # 1. Источник истины (all_npcs_raw формат)
    npc_raw = {
        "npc_id": "wounded_npc",
        "id": "wounded_npc",
        "body_state": {
            "pain": 40.0, "fatigue": 0.0, "blood_loss": 0.1, "shock_impulse": 0.6,
            "consciousness": 1.0, "life_status": "ALIVE",
            "injuries": [{"target_zone": "torso_chest", "damage_type": "slash", "structural_damage": 0.5}]
        },
        "statuses": []
    }
    
    print(f"[T+0] После удара: pain={npc_raw['body_state']['pain']:.2f}")
    
    for tick in range(1, 15):
        # 2. Проекция TickOrchestrator → плоский NPCStateSnapshot (как в строках 1693-1699)
        bs = npc_raw["body_state"]
        injuries_by_zone = {}
        for inj in bs.get("injuries", []):
            zone = inj.get("target_zone", "unknown")
            injuries_by_zone.setdefault(zone, []).append(inj)
            
        flat_snapshot = {
            "npc_id": npc_raw["npc_id"],
            "pain": float(bs.get("pain", 0.0)),
            "fatigue": float(bs.get("fatigue", 0.0)),
            "blood_loss": float(bs.get("blood_loss", 0.0)),
            "shock_impulse": float(bs.get("shock_impulse", 0.0)),
            "consciousness": float(bs.get("consciousness", 1.0)),
            "life_status": str(bs.get("life_status", "ALIVE")),
            "injuries_by_zone": injuries_by_zone,
            "statuses": npc_raw.get("statuses", [])
        }
        
        # 3. Decay (PhysiologyDecayHandler)
        decay_deltas = decay_handler.handle([flat_snapshot], campaign_id="test", current_tick=tick)
        pain_decay = decay_deltas[0].payload.pain_delta if decay_deltas else 0.0
        
        # 4. Injury Processor (InjuryProcessor)
        injury_deltas = injury_proc.handle([flat_snapshot], campaign_id="test", current_tick=tick)
        injury_pain = injury_deltas[0].payload.pain_delta if injury_deltas else 0.0
        
        # 5. Apply Deltas (StateApplicator simulation)
        npc_raw['body_state']['pain'] = max(0.0, npc_raw['body_state']['pain'] + pain_decay + injury_pain)
        
        pain = npc_raw['body_state']['pain']
        is_shaking = (pain > 10 and min(1.0, pain / 50.0) > 0.3) 
        is_wincing = pain > 20.0 
        
        print(f"[T+{tick}] pain={pain:.2f} (decay={pain_decay:.2f}, injury={injury_pain:.2f}) | Дрожит={is_shaking}, Морщится={is_wincing}")

    # Ожидаемое равновесие: pain_rate (2.25) / PAIN_DECAY_LAMBDA (0.05) = 45.0
    final_pain = npc_raw['body_state']['pain']
    assert final_pain > 20.0, f"Боль упала ниже порога проявления ({final_pain:.2f}), труба сухая!"
    assert abs(final_pain - 45.0) < 5.0, f"Боль не достигла равновесия около 45 (сейчас {final_pain:.2f})"
    print(f"\n--- [SANDBOX] ADR-141 VERIFIED: Хроническая боль стабилизировалась на {final_pain:.2f}. Труба не высыхает ---")

if __name__ == "__main__":
    test_chronic_pain_equilibrium()