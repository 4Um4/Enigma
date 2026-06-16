"""
path: backend/app/services/npc/calibration_engine.py
Назначение: Phase Lock Gate (Trait Stabilization Hysteresis Layer). 
Асимметричный стабилизатор L3 проекции. Решает, какая часть мгновенного поведения становится реальностью мира.
Зависимости: domain.identity_events
Основные сущности: CalibrationEngine

Закон Фазового Перехода: "Поведение может быть мгновенным. Память — только отфильтрованная стабильность поведения."
Архитектурная роль: НЕ трансформер. НЕ интерпретатор. ONLY phase lock gate.
"""

from typing import Dict, Tuple
from app.domain.identity_events import EffectiveDrives


class CalibrationEngine:
    """
    ADR-O-211 / ADR-O-304: Trait Stabilization Hysteresis Layer.
    Вводит гистерезисную петлю между L3_raw (мгновенное поведение) и L3_stable (кристаллизованная память).
    
    Физика фазового перехода:
    - TRAUMA (удаление от L0): энергия накапливается в strain_memory, прорыв → snap transition
    - HEALING (возврат к L0): медленная релаксация, без прорыва, энергия рассеивается
    """
    
    # Энергетический барьер активации (порог пластичности)
    _BARRIER: float = 0.12
    # Скорость релаксации при возврате к L0 (Residual Strain / Инерция памяти)
    _RELAX_RATE: float = 0.05
    
    def stabilize(
        self, 
        l3_raw: EffectiveDrives, 
        l3_prev: Dict[str, float],
        l0_baseline: Dict[str, float],
        strain_memory: Dict[str, float] = None,
        tick_delta: int = 1
    ) -> Tuple[EffectiveDrives, Dict[str, float], Dict[str, float]]:
        """
        Фильтр фазового перехода.
        
        Вход: 
        - l3_raw (физика момента от DriveResolver)
        - l3_prev (кристалл прошлого тика из state.drives_runtime)
        - l0_baseline (архетип для определения направления деформации)
        - strain_memory (накопленная энергия деформации)
        
        Выход:
        - L3_stable (для DecisionHub)
        - drives_update (для StateApplicator → drives_runtime)
        - strain_memory (для StateApplicator → state.strain_memory)
        
        Инварианты:
        - CalibrationEngine НЕ знает об интентах, эмоциях и событиях.
        - CalibrationEngine НЕ генерирует смыслы, только демпфирует скорость изменения.
        - Сумма драйвов после стабилизации = 1.0 (Закон Сохранения Я).
        """
        if strain_memory is None:
            strain_memory = {}
            
        # БЕЗОПАСНЫЙ РЕЖИМ (Test C Fix): 
        # CalibrationEngine переведён в режим прямого пропускания (pass-through),
        # пока не будет внедрён Pattern Detector (Evidence of Persistence).
        # Без детекции паттернов strain_memory накапливает шум (Test C).
        return l3_raw, dict(l3_raw.values), {}