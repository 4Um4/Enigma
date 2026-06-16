### ADR-O-304: L3 & DecisionContext Pipeline Unification & Projection-Native Transition

**Статус:** VERIFIED (Smoke Tests Passed) | **Этап:** 7.1 Complete → Переход к Этапу 8
**Домен:** DOM-02 (Will, Pressure & Decision)

---

#### ДО (Split-Brain & L0-Centric Architecture)
```text
[Player Path]
PerceptualKernel → Manual DecisionContext (from_kernel + post-hoc affective_load)
ProfileL0 + Local DriveResolver → EffectiveDrives (если повезёт)
    ↓
DecisionHub (L0 fallbacks active: _score_components, _context_relevance, _switching_cost)

[Idle Path]
PerceptualKernel → PressureTranslator → DecisionContext (Somatic Veto)
TickOrchestrator → EffectiveDrivesMap
    ↓
LifeEngine → DecisionHub (L0 fallbacks active)
```

#### ПОСЛЕ (Unified Causal Pipeline & Projection-Native Core)
```text
[Both Paths]
PerceptualKernel + BodyState → PressureTranslator → DecisionContext (Somatic Veto + Viability)
ProfileL0 + L1Chronicle → TickOrchestrator._compute_effective_drives() → EffectiveDrivesMap (SSOT)
    ↓
DecisionHub (Projection-Native: L3 пронизывает всё ядро скоринга)
    ├─ _score_components (drives = L3)
    ├─ _context_relevance (lens = L3)
    └─ _switching_cost / dominant_drive (identity = L3)
```

---

#### УСТРАНЕНО (Полная ликвидация L0 в принятии решений)

1. **Split-Brain DecisionContext:** Путь Игрока лишился ручной пересборки. `PressureTranslator` — единственный легитимный вход, возвращающий Somatic Veto и Viability Gate.
2. **Split-Brain DriveResolver:** Локальный `DriveResolver` и `L1Chronicle` в `npc_tick_pipeline` уничтожены. SSOT = `TickOrchestrator._compute_effective_drives()`.
3. **L3→L0 fallback в транспортном слое:** Уничтожен в `LifeEngine` и `_is_intent_available`. Отсутствие L3 = skip тика с диагностикой `[L3_MISSING]`.
4. **L3→L0 fallback в ядре скоринга (`_score_components`):** `personality.drives_base` заменён на `dict(effective_drives.values)`. Риск и релевантность вычисляются на основе текущей деформации.
5. **L3→L0 fallback в линзе реальности (`_context_relevance`):** Извлечение весов (fear, control) переведено с архетипа на L3-проекцию.
6. **L3→L0 fallback в инерции личности (`_switching_cost`):** Определение `dominant_drive` (ось соответствия identity) переведено с L0 на L3. NPC теперь упорствует в соответствии с *текущим* состоянием личности, а не врождённым архетипом.

---

#### АРХИТЕКТУРНЫЙ СДВИГ (Следствие ADR-O-304)

DecisionHub стал **projection-native system**. `personality.drives_base` (L0) более не является активной переменной в скоринге. L0 сводится к роли *initial condition seed* (затравка при создании NPC).

**Новый архитектурный риск: Сверхадаптивность (Слишком жидкий мир)**
Ликвидация L0 и опора на строго эфемерную L3-проекцию (Инвариант L3-P1) лишила систему демпфирующего слоя. Любой всплеск `PerceptualKernel` теперь мгновенно перекрашивает `EffectiveDrives`, лишая NPC "кристаллизованной памяти".

#### СЛЕДУЮЩИЙ ЭТАП (8.0: Trait Stabilization Hysteresis Layer)

Для предотвращения осцилляции личности (мульти-личности) требуется ввести гистерезис:
*   **Momentum (L3 drift)** — текущее смещение под давлением.
*   **Memory Inertia (L1 history trace)** — сопротивление резкому выходу из устойчивого состояния.

L0 навсегда останется затравкой, но L3 должен обрастись порогами кристаллизации ($\theta_{up}$, $\theta_{down}$) и `dwell_time`.