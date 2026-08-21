# ADR-O-211 — CALIBRATION ENGINE & IDENTITY STABILITY KERNEL Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-211 — CALIBRATION ENGINE & IDENTITY STABILITY KERNEL` [STANDARD] **IMPACT**

﻿# ADR-O-211 — CALIBRATION ENGINE & IDENTITY STABILITY KERNEL Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-211 — CALIBRATION ENGINE & IDENTITY STABILITY KERNEL` [STANDARD] ****
# АРХИТЕКТУРНЫЙ КОНТРАКТ: ADR-O-211 — CALIBRATION ENGINE & IDENTITY STABILITY KERNEL
# ADR-O-211

<!-- ADR-O-211 -->
> **СТАТУС:** Phase 0 (pass-through) 🔴
>
> **Реальное состояние:** CalibrationEngine существует, но все методы возвращают заглушки. `strain_memory` всегда `{}`. `compute_drives_updates` возвращает `{}`.
>
> **План ремонта:** ТЗ-2 §2.8 (после применения — обновить статус на ✅ Implemented).
>
> **Аудит:** 2026-06-19 (см. ADR_STATUS_MATRIX.md)

## 1. ПАРАДИГМА: НАУЧНЫЙ ПРИБОР, А НЕ ТЕСТ

Директория `calibration/` содержит код, который не тестирует ENIGMA, а **измеряет законы физики, на которых ENIGMA должна строиться**. Результаты его работы — это не `PASS/FAIL`, а константы и фазовые карты, которые затем вручную или скриптом переносятся в `architecture/identity.yaml`.

**Инвариант изоляции:** Код в `calibration/` запрещено импортировать из `backend/app/`. Он импортирует только `numpy`, базовые `dataclasses` и абстракции из собственного `contracts.py`.

---

## 2. IDENTITY STABILITY KERNEL (ISK)

Мы определяем регим через **чувствительность к микро-возмущениям**.

Вместо прямой классификации состояния, мы подаём на систему стандартный тестовый импульс ($\delta P$) и измеряем распределение ответов ($\Delta g$) по множеству прогонов (Monte Carlo над шумом дисперсии).

### Алгоритм ISK:

1.  Зафиксировать текущий базис $CSV_k$ и накопленное напряжение $S$.
2.  Инжектировать серию микро-импульсов $\delta P$ (одинаковой амплитуды).
3.  Измерить вектор смещения метрики $\Delta g_i$ для каждого импульса.
4.  Вычислить статистику ответа: $\mu(\Delta g)$ и $\sigma(\Delta g)$.

### Классификация через ISK:

*   **Кристалл:** $\mu(\Delta g) \approx 0$, $\sigma(\Delta g) \approx 0$. Удар гасится, аттрактор глубокий.
*   **Пластик:** $\mu(\Delta g) > 0$, $\sigma(\Delta g) < \epsilon$. Плавная, предсказуемая деформация.
*   **Хрупкий:** $\mu(\Delta g)$ скачет от $0$ до $A_{max}$ при незначительном изменении фазы. Высокая дисперсия в окрестности сепаратрисы.
*   **Хаос:** $\mu(\Delta g) \approx 0$, но $\sigma(\Delta g)$ огромна. Система блуждает, аттрактора нет.

---

## 3. СКЕЛЕТ CALIBRATION ENGINE

### Файл: `backend/tests/sandbox/calibration/contracts.py`
(Общие структуры данных, независимые от рантайма)

```python
import numpy as np
from dataclasses import dataclass

@dataclass(frozen=True)
class CausalPressureVector:
    fear: float = 0.0
    control: float = 0.0
    significance: float = 0.0
    desire: float = 0.0
    volatility: float = 0.0

@dataclass(frozen=True)
class CausalStateVector:
    g_basis: np.ndarray
    last_commit_tick: int = 0
    version: int = 0
```

### Файл: `backend/tests/sandbox/calibration/isk.py`
(Ядро измерения устойчивости)

```python
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
```

### Файл: `backend/tests/sandbox/calibration/run_sweep.py`
(Сканирование фазового пространства)

```python
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
```

---

## 4. СВЯЗЬ С DECISIONHUB (ПУТЬ B ИЗ ПРЕДЫДУЩЕГО ШАГА)

Теперь, когда регим — это аттракторная характеристика, а не ярлык, мы можем ответить на твой вопрос: **как режим изменяет геометрию выбора?**

Регим не меняет политику напрямую. Он меняет **чувствительность метрики к внешнему давлению**.

*   **Кристалл:** `ElasticWarp` сильно демпфируется. Высокий порог $\theta_{yield}$. DecisionHub работает почти на чистом $g_0$.
*   **Пластик:** `ElasticWarp` линейно отзывчив. Давление среды плавно искривляет пространство.
*   **Хрупкий:** `ElasticWarp` имеет зону нечувствительности, за которой следует срыв. Накопленное $S$ держит систему на краю.
*   **Хаос:** `ElasticWarp` усиливает флуктуации. Геометрия "дышит".
