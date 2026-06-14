"""

"""

import numpy as np
from typing import List
from .contracts import CausalPressureVector, CausalStateVector

# Абстрактный интерфейс физики, которую мы калибруем
class PhasePhysicsEngine:
    def elastic_warp(self, csv: CausalStateVector, pressure: CausalPressureVector) -> CausalStateVector:
        raise NotImplementedError
        
    def phi_stable_check(self, tick: int, csv: CausalStateVector, pressure: CausalPressureVector) -> bool:
        raise NotImplementedError

def run_perturbation_test(
    engine: PhasePhysicsEngine,
    base_csv: CausalStateVector,
    perturbation_amplitude: float = 0.1,
    num_samples: int = 100
) -> dict:
    """
    Измеряет устойчивость аттрактора через микро-возмущения.
    Возвращает статистику реакции системы на одинаковые удары.
    """
    delta_g_norms = []
    
    for i in range(num_samples):
        # Добавляем микро-шум к амплитуде для стохастичности
        noise = np.random.normal(0, perturbation_amplitude * 0.1)
        p = CausalPressureVector(fear=perturbation_amplitude + noise)
        
        # Измеряем упругую деформацию (Elastic Warp)
        warped_csv = engine.elastic_warp(base_csv, p)
        
        # Фиксируем магнитуду смещения базиса
        if base_csv.g_basis is not None and warped_csv.g_basis is not None:
            delta_g = np.linalg.norm(warped_csv.g_basis - base_csv.g_basis)
            delta_g_norms.append(delta_g)
            
    return {
        "mu_delta_g": np.mean(delta_g_norms),
        "sigma_delta_g": np.std(delta_g_norms)
    }

def classify_regime_by_isk(isk_results: dict) -> str:
    """Классифицирует регим на основе статистики устойчивости."""
    mu = isk_results["mu_delta_g"]
    sigma = isk_results["sigma_delta_g"]
    
    if mu < 0.01 and sigma < 0.01:
        return "CRYSTAL"
    elif mu > 0.01 and sigma < mu * 0.5:
        return "PLASTIC"
    elif sigma > mu * 1.5: # Высокая дисперсия относительно смещения
        return "BRITTLE" 
    else:
        return "CHAOTIC"