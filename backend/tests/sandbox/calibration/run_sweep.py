"""

"""

import numpy as np
from .contracts import CausalStateVector
from .isk import PhasePhysicsEngine, run_perturbation_test, classify_regime_by_isk

# Здесь будет реализация PhasePhysicsEngine на основе наших формул Φ_stable
class EnigmaPhaseEngine(PhasePhysicsEngine):
    # ... реализация интегратора и детектора ...
    pass

def build_phase_stability_map():
    """
    Строит Карту Фазовой Устойчивости.
    Варьирует внутреннее напряжение (S_internal) и амплитуду удара (A).
    """
    engine = EnigmaPhaseEngine()
    stability_map = []
    
    for s_fear in np.arange(0.0, 1.5, 0.1): # Уровень накопленного стресса
        for a_amplitude in np.arange(0.1, 1.5, 0.1): # Сила удара
            
            # Формируем CSV с базисом, уже деформированным страхом
            base_csv = CausalStateVector(g_basis=np.array([0.5 - s_fear*0.2, 0.5 + s_fear*0.2]))
            
            # Измеряем устойчивость
            isk_results = run_perturbation_test(engine, base_csv, perturbation_amplitude=a_amplitude)
            regime = classify_regime_by_isk(isk_results)
            
            stability_map.append({
                "s_fear": round(s_fear, 2),
                "amplitude": round(a_amplitude, 2),
                "regime": regime,
                "mu": isk_results["mu_delta_g"],
                "sigma": isk_results["sigma_delta_g"]
            })
            
    return stability_map