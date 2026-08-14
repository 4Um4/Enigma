"""
Назначение: Детерминированный тест полного цикла сна (Phase B, E, F) без зависимости от LLM и MovementEngine.
Зависимости: backend/app/services/npc/sleep_lifecycle_service.py, backend/app/services/events/event_bus.py
Основные сущности: SleepLifecycleService, DreamSignal

Запуск: cd backend; python -m pytest tests/system/test_sleep_routing.py -v; cd ..
"""
import sys
import os
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Any

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ROOT = _PROJECT_ROOT / "backend"
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.npc.sleep_lifecycle_service import SleepLifecycleService
from app.services.npc.sleep_states import is_sleeping

class MockEventBus:
    """Мок EventBus для перехвата событий сна."""
    def __init__(self):
        self.published_events = []
        
    def publish(self, event: Any) -> None:
        self.published_events.append(event)

def _make_sleeping_npc(npc_id: str) -> Dict[str, Any]:
    """Создает тестового NPC в состоянии сна."""
    return {
        "id": npc_id,
        "npc_id": npc_id,
        "routine": {
            "current": "sleeping",
            "_sleep_start_tick": 0
        },
        "body_state": {
            "sleep_pressure": 0.8,
            "arousal": 0.0,
            "fatigue": 50.0,
            "current_hp": 100,
            "pain": 0.0,
            "shock_impulse": 0.0,
            "blood_loss": 0.0
        },
        "perceptual_kernel": {
            "threat_gradient": 0.0,
            "uncertainty": 0.0,
            "anomaly_score": 0.0,
            "initiative_suppression": 0.0,
            "compliance_bias": 0.0,
            "aggression_inhibition": 0.0
        },
        "affective_load": 0.0,
        "affective_memory": 0.0
    }

def test_sleep_lifecycle_phases():
    """Тестирует CouplingProfile (B), DreamSignal (E) и DreamResidue (F)."""
    event_bus = MockEventBus()
    service = SleepLifecycleService(event_bus)
    
    # 1. Создаем NPC
    borko = _make_sleeping_npc("guard_borko")
    lusya = _make_sleeping_npc("maid_lusya")
    goran = _make_sleeping_npc("merchant_goran")
    
    npcs = [borko, lusya, goran]
    
    # 2. Эмуляция сна (5 тиков)
    for tick in range(1, 6):
        # Инъекция стимулов на 2-м тике
        if tick == 2:
            borko["perceptual_kernel"]["threat_gradient"] = 0.9
            lusya["perceptual_kernel"]["anomaly_score"] = 0.8
        elif tick > 2:
            # Очищаем стимулы, чтобы сны не генерировались каждый тик
            borko["perceptual_kernel"]["threat_gradient"] = 0.0
            lusya["perceptual_kernel"]["anomaly_score"] = 0.0
            
        for npc in npcs:
            service.process_sleep_lifecycle(npc, tick)
            
    # 3. Проверка Phase B (CouplingProfile)
    for npc in npcs:
        _cp = npc["body_state"].get("coupling_profile", {})
        assert _cp.get("coupling_mode") in ("SLEEP", "DEEP_SLEEP", "REM"), f"{npc['id']}: NPC не уснул"
        assert _cp.get("motor_output_mult", 1.0) < 0.2, f"{npc['id']}: Моторика не заблокирована"
        
    # 4. Проверка Phase E (DreamSignal & DreamResidue)
    _borko_residue = borko.get("dream_residue")
    _lusya_residue = lusya.get("dream_residue")
    _goran_residue = goran.get("dream_residue")
    
    assert _borko_residue is not None, "guard_borko не увидел сон"
    assert _borko_residue["perception"] in ("monster", "shadow"), f"guard_borko поймал неверный сон"
    
    assert _lusya_residue is not None, "maid_lusya не увидела сон"
    assert _lusya_residue["perception"] in ("falling", "strange_sound"), f"maid_lusya поймала неверный сон"
    
    assert _goran_residue is None, "merchant_goran не должен был видеть сны"
    
    # Проверка публикации событий (ровно 2 — по одному на NPC)
    _dream_events = [e for e in event_bus.published_events if e.type in ("dream", "nightmare")]
    assert len(_dream_events) == 2, f"Должно быть опубликовано 2 события сна, получено {len(_dream_events)}"
    
    # 5. Эмуляция пробуждения (Phase F)
    for npc in npcs:
        npc["perceptual_kernel"]["threat_gradient"] = 1.0  # Резкая угроза
        npc["body_state"]["arousal"] = 1.0  # Принудительное пробуждение
        
    for npc in npcs:
        service.process_sleep_lifecycle(npc, 10)
        
    # 6. Проверка Phase F (DreamResidue)
    for npc in npcs:
        _routine = npc.get("routine", {}).get("current", "sleeping")
        assert not is_sleeping(_routine), f"{npc['id']} не проснулся"
        
    _borko_load = float(borko.get("affective_load", 0.0))
    _lusya_load = float(lusya.get("affective_load", 0.0))
    _goran_load = float(goran.get("affective_load", 0.0))
    
    _borko_threat = float(borko.get("perceptual_kernel", {}).get("threat_gradient", 0.0))
    
    assert _borko_load > 0.2, f"guard_borko не получил аффективный остаток (load={_borko_load})"
    assert _borko_threat > 0.4, f"guard_borko не получил осадок паранойи (threat={_borko_threat})"
    assert _goran_load < _borko_load, "merchant_goran без снов не должен быть сильнее нагружен"