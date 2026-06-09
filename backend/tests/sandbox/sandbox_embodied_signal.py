"""
Запуск: cd backend; python -m pytest tests/sandbox/sandbox_embodied_signal.py -v -s; cd ..
"""

import logging
import sys
import os

# Локальное включение DEBUG для этого теста
logging.basicConfig(level=logging.DEBUG, format='[%(name)s] %(message)s', stream=sys.stdout)

# Добавляем корень бэкенда в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.services.perception.behavior_manifestation_service import BehaviorManifestationService
from app.services.perception.phenomenology_projection_service import PhenomenologyProjectionService
from app.domain.embodied_trace import EmbodiedTraceDTO, PlayerPerceptionDTO

def test_embodied_signal_flow():
    """
    Тест: Инъекция pain=80 в body_state NPC должна пройти до cue_key=WINCING 
    и попасть в DM-контракт.
    """
    print("\n--- [SANDBOX] EMBODIED SIGNAL FLOW TEST ---")
    
    # 1. Подготовка реальных данных (Археология: all_npcs_raw = list[dict])
    npc_id = "test_npc_wounded"
    all_npcs_raw = [{
        "npc_id": npc_id,
        "id": npc_id,
        "body_state": {
            "pain": 80.0,        # 0-100 шкала (ADR-094)
            "fatigue": 10.0,
            "blood_loss": 0.1,   # 0-1 шкала
            "shock_impulse": 0.2, # 0-1 шкала
            "life_status": "ALIVE",
            "injuries": []
        },
        "psyche": {"willpower": 0.5, "fear": 0.0, "state": "free", "stress": 0.0},
        "location": "tavern:main_hall"
    }]
    
    scene_state = {
        "npc_positions": {npc_id: {"local_position": [10, 10]}},
        "active_traversals": {}
    }

    # 2. Генерация моторных следов (BehaviorManifestationService)
    manifest_svc = BehaviorManifestationService()
    traces = manifest_svc.produce_traces(scene_state, all_npcs_raw=all_npcs_raw)
    
    print(f"[TRACE_STEP] Traces generated: {len(traces)}")
    assert len(traces) == 1, "Ожидается 1 trace для раненого NPC"
    
    trace = traces[0]
    print(f"[TRACE_STEP] Trace for {trace.npc_id}: instability={trace.locomotion_instability:.2f}, rigidity={trace.posture_rigidity:.2f}, is_shaking={trace.is_shaking}, is_frozen={trace.is_frozen}")
    
    # При pain=80: instability = min(1.0, 80/50) = 1.0. is_shaking = (1.0 > 0.3) = True
    assert trace.is_shaking is True, f"NPC с pain=80 должен дрожать! (instability={trace.locomotion_instability})"
    print("[TRACE_STEP] ✔ is_shaking=True (Труба BehaviorManifestation работает)")

    # 3. Проекция в наблюдения (PhenomenologyProjectionService)
    project_svc = PhenomenologyProjectionService()
    perception = project_svc.project(traces, scene_state, tick=1)
    
    print(f"[PERCEPTION_STEP] Cues generated: {len(perception.active_perceptions)}")
    
    cue_keys = [c.get("cue_key") for c in perception.active_perceptions if isinstance(c, dict)]
    print(f"[PERCEPTION_STEP] Cue keys: {cue_keys}")
    
    # При pain=80 и instability > 0.3 должны быть SWAYING/UNEVEN_STANCE. 
    # При pain > 20 и blood_loss > 0.05 должны быть WINCING/HOLDING_SIDE
    assert "WINCING" in cue_keys or "HOLDING_SIDE" in cue_keys, f"Должны быть болевые cue, но есть только {cue_keys}"
    print("[PERCEPTION_STEP] ✔ Болевые cue_key сгенерированы (Труба Phenomenology работает)")

    # 4. Проверка проброса в DM (симуляция чтения dm_agent)
    # В реальном коде dm_agent делает: _traces = _perception.embodied_traces
    dm_traces = perception.embodied_traces
    
    obs_lines = []
    for t_dict in dm_traces:
        _symptoms = []
        if t_dict.get('is_shaking'): _symptoms.append("дрожит")
        if t_dict.get('is_frozen'): _symptoms.append("окаменел")
        if t_dict.get('locomotion_instability', 0) > 0.3: _symptoms.append("покачивается")
        if t_dict.get('posture_rigidity', 0) > 0.5: _symptoms.append("напряжённая поза")
        
        if _symptoms:
            obs_lines.append(f"- {t_dict.get('npc_id', '???')}: {', '.join(_symptoms)}")
            
    print(f"[DM_STEP] DM obs_lines: {obs_lines}")
    
    assert len(obs_lines) > 0, "DM должен увидеть хотя бы 1 симптом!"
    print("[DM_STEP] ✔ DM получит блок с симптомами (Труба до DM работает)")
    
    print("\n--- [SANDBOX] ALL PIPELINES VERIFIED ---")

if __name__ == "__main__":
    test_embodied_signal_flow()