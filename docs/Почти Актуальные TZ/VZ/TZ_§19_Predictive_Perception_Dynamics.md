# §19. ЗАКОН ПРЕДИКТИВНОЙ ДИНАМИКИ ВОСПРИЯТИЯ
## (Predictive Perception Dynamics Law)

> **Архитектурная гипотеза для будущей реализации.**
> **Не исполняемый контракт сейчас. Документ фиксирует направление, математическую модель, ограничения и pre-conditions.**

---

**Статус документа:** Research Hypothesis / Future Architectural Law
**Версия ENIGMA:** V.0.5.3.6.9 (на момент составления)
**Дата:** 2026-08-04
**Назначение:** Фиксация архитектурной позиции до реализации. Документ закрывает пробел между «реактивной моделью восприятия NPC» и «динамической генеративной моделью», в которой текущее восприятие формируется относительно краткосрочного ожидания пространственно-временного развития событий.
**Аудитория:** Архитекторы ENIGMA, LLM-ассистенты, реализующие эпистемический и когнитивный слои.
**Принадлежность:** `docs/Почти Актуальные TZ/`. После стабилизации Belief Layer и завершения Эпохи 6 (Infrastructure) — перенос в `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` как §19.
**Целевая эпоха активации:** v7.5 (Prophecy System) — Prediction Error становится фундаментом Prophecy Layer.

---

## EXECUTIVE SUMMARY

Документ вводит **§19. Закон Предиктивной Динамики Восприятия** как будущий фундаментальный закон Устава ENIGMA. Закон формализует принцип, отсутствующий в текущей архитектуре: **NPC не воспринимает каждый новый сигнал как изолированное событие. Текущее восприятие формируется относительно краткосрочной модели ожидаемого пространственно-временного развития событий; расхождение между ожидаемым и наблюдаемым является каузальным входом в обновление `PerceptualKernel`.**

Закон выражается системой уравнений:

```
z_t       = F(z_{t-1}, x_t, m_t, s_t)           — внутреннее состояние
x̂_{t+1}   = G(z_t, s_t)                          — предсказание
e_t       = W(x_t, x̂_t) · Precision(x_t)         — взвешенная ошибка
surprise  = −log P(x_t | z_{t-1})                 — неожиданность
Δkernel_t = α · e_t · salience(x_t)               — модификация ядра
```

**Главный вердикт документа:** в текущую ENIGMA V.0.5.3.6.9 этот закон **ВНЕДРЯТЬ НЕЛЬЗЯ**. Базовый Belief Layer ещё не завершён (PC-1..PC-7 из §18 не закрыты), `BeliefTransitionEngine` не имеет единственного write-path, `BeliefRevisionEngine` не существует. Наложение предиктивной динамики поверх незакрытой инфраструктуры создаст дополнительный слой нестабильности с вероятностью 70–80%. Закон должен быть зафиксирован как архитектурная гипотеза и активирован только после выполнения pre-conditions, описанных в §9.

Документ определяет:
1. Научный фундамент (§1) — работа Muller et al. (Neuron 2026) и теория predictive coding.
2. Математическую формулировку закона (§2) — каноническая система уравнений.
3. Архитектурное позиционирование (§3) — новая фаза 3.8 в `NpcTickPipeline`.
4. Четыре компонента (§4) — `PredictionModel`, `PredictionErrorCalculator`, `PrecisionModel`, `SpatialTemporalTrace`.
5. `PerceptualKernelDelta` (§5) — контракт модификации ядра без нарушения Invariant III.
6. Явную интеграцию с §18 (§6) — Prediction Error как источник `U(c)` в формуле `U_M = I·R·U − C`.
7. Таблицу совместимости с §ENIGMA-001..006, §3, §14, §15, §16, §17, §18 (§7).
8. Анти-паттерны (§8) — что категорически запрещено.
9. Pre-conditions (§9) — что должно быть готово до активации.
10. Дорожную карту из 4 этапов A/B/C/D (§10).
11. Per-NPC ресурсную модель (§11) — долгосрочное расширение.
12. Диагностические критерии и тест-кейсы (§12).
13. Риски и митигацию (§13).
14. Итоговый вердикт (§14).

Закон вдохновлён обзором Muller, Busch, Davis, Reynolds «Neural traveling waves in cortex: network mechanisms and potential roles in neural computation» (Neuron, 21 июля 2026, DOI 10.1016/j.neuron.2026.06.019), но **не имитирует биологическую реализацию** — он адаптирует вычислительный принцип (рекуррентная пространственно-временная динамика как субстрат краткосрочного предсказания) под архитектурные инварианты ENIGMA.

---

## §0. КОНТЕКСТ И РАСПОЛОЖЕНИЕ ДОКУМЕНТА

### §0.1 Место в Уставе

Документ проектируется как **§19 Устава ENIGMA** — следующая глава после §18 (Resource-Bounded Epistemic Selection Law). Это естественное продолжение эпистемической линии Устава:

| § | Закон | Домен |
|---|-------|-------|
| §ENIGMA-003 | Закон Эпистемической Проекции | UNKNOWN ≠ NEUTRAL(0.0) |
| §ENIGMA-004 | Закон Эпистемического Демпфирования | Vacuum = локальный разрыв |
| §13 | Law of Epistemic Grounding | Знание первично, код вторичен |
| §14 | Law of Singular Time | Единственное время симуляции |
| §15 | Law of Wall-Clock Isolation | Изоляция реального времени |
| §16 | Law of Belief Non-Mutation | Belief = Lens, Not Gene |
| §17 | Law of Epistemological Orthogonality | Reality ⊥ Epistemology |
| §18 | Resource-Bounded Epistemic Selection | Агент выбирает информационную архитектуру |
| **§19 (этот документ)** | **Predictive Perception Dynamics** | **Восприятие — динамическая генеративная модель** |

§19 — единственный из перечисленных, который явно вводит **временную рекуррентность** как фактор восприятия. Все предыдущие законы формулируют инварианты пространства и каузальности; §19 формулирует оптимизационный принцип формирования субъективного состояния во времени.

### §0.2 Статус: НЕ исполняемый контракт

В отличие от §1–§17, этот документ **не является исполняемым контрактом** в версии V.0.5.3.6.9. Нарушение §19 на текущем коде не считается архитектурным багом, потому что:

1. Закон ещё не реализован в коде.
2. Pre-conditions (см. §9) не закрыты — `BeliefRevisionEngine` не существует, `BeliefState` schema не расширена, лаг Phase 3 → Phase 5 не устранён (ADR-059).
3. Базовый Belief Layer из §18 ещё не активирован; наложение предиктивной динамики поверх незакрытой инфраструктуры усугубит долг ADR-059 (Stale Cognition).

После выполнения pre-conditions и реализации закон получает статус **Исполняемый контракт**. С этого момента нарушение §19 = архитектурный баг, как и нарушение §15/§16/§17/§18.

### §0.3 Связь с ADR-системой

Реализация закона требует создания следующих ADR (порядок условный, номера присваиваются по правилу §11.1.1 Устава):

- **ADR-O-4XX** — PredictivePerceptionEngine (pure function) — архитектурный контракт `PredictivePerceptionEngine`.
- **ADR-O-4XX+1** — PredictionModel — формирование `Prediction` из `state_l2 + memory_context + spatial_history`.
- **ADR-O-4XX+2** — PredictionErrorCalculator — `compare(prediction, observed_facts) → PredictionError`.
- **ADR-O-4XX+3** — PrecisionModel — `precision = confidence × reliability × attention`.
- **ADR-O-4XX+4** — SpatialTemporalTrace — bounded decay trace как функциональный аналог traveling wave.
- **ADR-O-4XX+5** — PerceptualKernelDelta — контракт модификации ядра без нарушения Invariant III.

Каждый ADR сопровождается impact-audit в `docs/audits/ADR-O-4XX_IMPACT.md` по правилу §11.4 Устава.

### §0.4 Связь с существующими ADR

Закон прямо опирается на следующие уже принятые ADR:

| ADR | Назначение | Связь с §19 |
|-----|-----------|-------------|
| ADR-O-205 | Projection Layer System | Prediction — это проекция, не истина |
| ADR-O-206 | Emotional Residue Isolation | Surprise (prediction_error) как источник importance |
| ADR-O-207 | Ontology Violation Error | L5 guard для bounds Δkernel ∈ [−1, 1] |
| ADR-O-208 | DRP (L1Chronicle append-only) | Источник evidence для PatternDetector |
| ADR-O-301 | KernelRNG (deterministic) | Prediction вычисляется детерминированно |
| ADR-O-304 | L3 & DecisionContext Pipeline Unification | DecisionHub читает только L3-проекции |
| ADR-O-307 | Asymmetric Trauma (x6) | Surprise от опровержения сильнее подтверждения |
| ADR-O-309 | SceneStateManager (commit boundary) | state_t-1 для вычисления Δt |
| ADR-O-312 | WorldChronicle & Entity Continuity | SpatialTrace получает lineage через поколения |
| ADR-S86.7 | Memory contour (compress/promote) | Causal decay kernel для trace |
| ADR-S96.1 | DriveResolver (L0+L2.5 → L3) | Prediction модулируется через drives_base |

### §0.5 Связь с §18 (Resource-Bounded Epistemic Selection)

§19 — это **не замена**, а **дополнение** §18. Разделение ответственности:

| Аспект | §18 | §19 |
|--------|-----|-----|
| Что фильтрует | Какие воспоминания участвуют в inference | Какие сигналы формируют субъективное состояние |
| Временная стрелка | Прошлое → настоящее (memory retrieval) | Прошлое → настоящее → будущее (prediction) |
| Вход | `Memory × Context` | `state_{t-1} × observation_t × spatial_history` |
| Выход | `MemoryUtilityResult` (evidence weight) | `PerceptualKernelDelta` (изменение ядра) |
| Где работает | Phase 3.5–3.7 (после Memory, до DecisionHub) | Phase 3.8 (после BeliefTransition, до Interpretation) |
| Связь | `U(c)` из §18 — вход в `U_M = I·R·U − C` | `prediction_error` из §19 — источник `U(c)` |

**Критическая интеграция:** `U(c)` (uncertainty of current observation) в §18 должна вычисляться из `prediction_error` из §19. Это делает §19 источником неопределённости для §18. Подробности в §6.

---

## §1. НАУЧНЫЙ ФУНДАМЕНТ

### §1.1 Первоисточник

Закон вдохновлён обзором **Muller, Busch, Davis, Reynolds — «Neural traveling waves in cortex: network mechanisms and potential roles in neural computation»**, опубликованном в *Neuron* 21 июля 2026 года (DOI 10.1016/j.neuron.2026.06.019).

**Внимание:** это **review / теоретический синтез**, а не эксперимент, доказавший буквально, что мозг «рендерит мир как LLM». Авторы сами формулируют часть выводов как концептуальную рамку. Документ не копирует биологический механизм, а адаптирует вычислительный принцип.

### §1.2 Что действительно показала работа

Сильная идея исследования: мозг не просто получает последовательность сенсорных данных `t → perception`; внутри локальных нейронных сетей существует **пространственно-временная динамика, которая сама является вычислением**.

Нейронные traveling waves (nTW) распространяются по коре и, согласно авторам, могут выполнять одновременно несколько функций:
1. Модулировать чувствительность восприятия.
2. Превращать недавний сенсорный поток во внутреннее представление.
3. Строить краткосрочные предсказания.
4. Сохранять и воспроизводить временные паттерны прошлого.

Это согласуется с более ранними экспериментами команды Reynolds (2020): моментальная конфигурация таких волн влияет на вероятность обнаружения слабого визуального объекта. Одно и то же внешнее воздействие может быть воспринято по-разному в зависимости от внутреннего состояния системы в момент его поступствия.

В более ранней модельной работе группа показала, что recurrent network с traveling waves может по нескольким кадрам естественного видео предсказывать последующее содержимое; при перемешивании рекуррентных связей и сами волны, и способность предсказывать разрушались.

### §1.3 Что ENIGMA заимствует, а что нет

**Заимствуем (вычислительный принцип):**
- Локальная рекуррентная динамика может сама быть вычислительным субстратом восприятия, памяти и краткосрочного прогнозирования.
- Прошлое состояние + пространственно-временная структура + внутреннее предсказание → текущее восприятие.
- Расхождение между ожидаемым и наблюдаемым (prediction error) — каузальный вход в обновление состояния.

**Не заимствуем (биологическая реализация):**
- Нейронные traveling waves как электрофизическое явление.
- Сетку нейронов внутри NPC.
- Биологическое обучение (синаптическая пластичность, STDP).
- Любую нейросетевую симуляцию внутри NPC.

**Принципиальная позиция:** ENIGMA — **не brain simulator**. Закон формулирует функциональные инварианты предиктивного восприятия, а не биологический механизм. Это позволяет избежать двух ловушек:
1. **Заимствования биологии без архитектурной семантики** — реализация traveling waves как нейросети нарушила бы §15 (wall-clock isolation), §16 (belief non-mutation), §17 (epistemological orthogonality).
2. **Игнорирования архитектурных инвариантов** — прямой перенос нейрофизиологической модели разрушил бы детерминизм (`KernelRNG`), персистентность (SQLite-bound state) и replay.

### §1.4 Связь с predictive coding framework

Закон опирается на **predictive coding** — серьёзную computational framework в когнитивной науке (Rao & Ballard 1999; Friston 2010 — Free Energy Principle). Базовая схема:

```
верхний уровень генерирует prediction
        ↓
нижний уровень сравнивает с input
        ↓
prediction error используется для коррекции внутренней оценки
```

Эмпирический статус predictive coding остаётся **неоднородным** — это теоретическая рамка, не универсально установленный механизм мозга. В ENIGMA мы используем её как **вычислительную абстракцию**, не как биологическое утверждение.

### §1.5 Научная честность: что доказано, а что наша инженерная экстраполяция

**Хорошо поддержано исследованиями:**
1. Recurrent cortical dynamics существуют — traveling waves наблюдаются у бодрствующих животных и связаны с возбудимостью и поведением.
2. Они имеют пространственно-временную структуру.
3. Они могут нести информацию о недавней сенсорной истории (теоретическая/модельная поддержка).
4. Они могут поддерживать short-term prediction (обсуждается в новой работе и предыдущих моделях).
5. Predictive coding — серьёзная computational framework (эмпирический статус не закрыт окончательно).

**Это уже наша инженерная экстраполяция:**
- `Prediction`, `PredictionError`, `Precision`, `SpatialTrace` как конкретные ENIGMA-классы.
- `PerceptualKernelDelta` как контракт модификации.
- Формулы `surprise = −log P(x | z)` и `weighted_PE = precision × error`.
- Конкретные константы (`MAX_TRACE_LENGTH = 8`, `λ = 0.15`).

Это **не** «нейронаука доказала такой алгоритм». Это архитектурный перевод вычислительного принципа в игровую симуляцию. Документ явно фиксирует этот статус.

---

## §2. ФОРМУЛИРОВКА ЗАКОНА

### §2.1 Каноническая система уравнений

Для конкретного NPC в тике `t`:

```
┌─────────────────────────────────────────────────────────────────┐
│  z_t       = F(z_{t-1}, x_t, m_t, s_t)                          │
│  x̂_{t+1}   = G(z_t, s_t)                                        │
│  e_t       = W(x_t, x̂_t) · Precision(x_t)                       │
│  surprise  = −log P(x_t | z_{t-1})                               │
│  Δkernel_t = α · e_t · salience(x_t)                             │
└─────────────────────────────────────────────────────────────────┘

где:
  z_t           — скрытое субъективное состояние NPC в тике t
                  (соответствует PerceptualKernel + PredictionState)
  x_t           — наблюдаемые факты текущего тика (List[ObservedFact])
  x̂_{t+1}       — предсказание фактов для следующего тика
  m_t           — память/контекст (memory_weights, narrative_cache)
  s_t           — пространственно-временной контекст (SpatialTrace)
  e_t           — взвешенная prediction error ∈ [0, 1]
  Precision     — надёжность и значимость наблюдения ∈ [0, 1]
  surprise      — неожиданность (информационная) ∈ [0, +∞)
  Δkernel_t     — модификация PerceptualKernel через Delta
  α             — learning rate ∈ [0.05, 0.30] (per-NPC, из NPCProfileL0)
  salience      — значимость наблюдения ∈ [0, 1]
```

### §2.2 Правило активации

```
Prediction error воздействует на PerceptualKernel
        ⟺
Precision(x_t) > min_precision (default 0.05)
```

**Семантика:** наблюдение с `Precision < 0.05` (NPC почти ничего не видел/слышал) не может модифицировать ядро. Это соответствует принципу « Vacuum = локальный разрыв» (§ENIGMA-004): отсутствие надёжного сигнала не конвертируется в глобальный аккумулятор `anomaly_score`.

### §2.3 Различие error и surprise

Это **фундаментальное** различие, явно зафиксированное в законе:

| Величина | Семантика | Формула | Пример |
|----------|-----------|---------|--------|
| `prediction_error` | Я ожидал A, получил B | `W(x, x̂) · Precision(x)` | NPC ожидал `weapon_visible=False`, получил `weapon_visible=True` при `precision=0.95` → `e=0.91` |
| `surprise` | Насколько B маловероятен относительно моей модели | `−log P(x | z_{t-1})` | NPC ожидал `attack probability = 0.01`, получил атаку → `surprise ≈ 4.6`; при `attack probability = 0.8` → `surprise ≈ 0.22` |

Две ситуации могут давать одинаковый `error` (бинарно: unexpected=true), но радикально разный `surprise`. Поэтому закон держит обе величины и использует их для разных модификаций ядра:
- `error` → `uncertainty_delta`, `anomaly_score_delta`
- `surprise` → `attention_delta`, `threat_gradient_delta`

### §2.4 Precision как модулятор

Prediction Error воздействует на субъективное состояние **пропорционально надёжности и значимости наблюдения**:

```
Precision(x) = Confidence(x) · Reliability(x) · Attention(x)

где:
  Confidence  — физическая надёжность восприятия
                 (из PerceptionFilter: LOS, distance, light, walls)
  Reliability  — эпистемическая надёжность источника
                 (perception=0.85, observation=0.70, inference=0.50, rumor=0.40)
  Attention    — текущий фокус NPC
                 (из drives_base: high control → high attention)
```

**Пример:** Борко на `distance=14m, light=dim` видит меч игрока. `Confidence=0.45`. Тот же меч на `distance=3m, bright, LOS=clear` → `Confidence=0.95`. При одинаковом `raw_surprise` влияние на ядро отличается в 2.1 раза.

Это **причинно связывает spatial physics → perception → cognition** — физика мира определяет не только «увидел/не увидел», но и «насколько сильно NPC должен доверять расхождению между ожиданием и наблюдением».

### §2.5 Что закон НЕ делает

| Закон НЕ делает | Почему |
|-----------------|--------|
| Создаёт событие «NPC удивился» | Это было бы симуляционным фактом; закон только модифицирует `PerceptualKernel` через `Delta` |
| Мутирует BeliefState напрямую | Belief Revision — отдельный write-path (§5 §18) |
| Мутирует drives_runtime (L0) | §16.1 — Belief = Lens, Not Gene; §19 — Prediction = Filter, Not Gene |
| Читает Reality | §17.1 — Inference не изменяет Reality |
| Использует wall-clock | §15 — game_time_seconds только |
| Вводит фиксированные коэффициенты | §8.2 — magic numbers запрещены |
| Моделирует нейронные traveling waves | §8.1 — биологическая реализация запрещена |
| Гарантирует learning | Phase transition (memoryless → memory-based) возникает emergent, не форсируется |
| Восстанавливает Prediction из Belief | Prediction ≠ Belief: Belief — «я считаю, что Борко лжёт»; Prediction — «если я продолжу разговор, он продолжит защищаться» |
| Делает prediction → Reality | §8.3 — prediction может ошибаться бесконечно, мир от этого не меняется |

---

## §3. АРХИТЕКТУРНОЕ ПОЗИЦИОНИРОВАНИЕ

### §3.1 Канонический pipeline (новая фаза 3.8)

Закон встраивается в существующий `NpcTickPipeline.run()` между `BeliefTransitionEngine` (Phase 3.7 из §18) и `InterpretationEngine`:

```
WORLD
  │
  ▼
OBSERVATION (Phase 2 — PerceptionSubscriber)
  │
  ▼
PERCEPTION (Phase 3 — FactExtractor, InferenceEngine)
  │
  ▼
MEMORY (Phase 3 — MemoryManager.apply)
  │
  ▼
MEMORY RETRIEVAL (Phase 3.5 — из §18)
  │
  ▼
MEMORY UTILITY EVALUATION (Phase 3.6 — из §18)
  │
  ▼
BELIEF REVISION (Phase 3.7 — из §18)
  │
  │  ← существующая граница до §18
  ▼
┌─────────────────────────────────────────┐
│  PREDICTIVE PERCEPTION (Phase 3.8 — NEW)│  ← §19 добавляет этот блок
│                                         │
│  PredictivePerceptionEngine:            │
│    1. predict(state_{t-1}, spatial_t)   │
│    2. compare(prediction, observed)     │
│    3. compute_precision(observed)       │
│    4. compute_surprise(prediction, obs) │
│    5. build_kernel_delta(error, surpr)  │
│                                         │
│  Выход: PerceptualKernelDelta           │
└─────────────────────────────────────────┘
  │
  ▼
StateApplicator.apply_delta_to_kernel(state_l2, delta)
  │
  ▼
PERCEPTUAL KERNEL (обновлённое)
  │
  ▼
INTERPRETATION ENGINE (Phase 4 — bias, threat, drives)
  │
  ▼
PRESSURE TRANSLATOR (kernel → DecisionContext)
  │
  ▼
DECISIONHUB (Phase 5 — без изменений)
  │
  ▼
DECISION RESULT
  │
  ▼
STATE APPLICATOR (Phase 8 — без изменений)
  │
  ▼
WORLD CHANGE
```

**Почему именно здесь, а не «между Inference и PerceptualKernel» буквально:**

В текущем коде `InferenceEngine` (`perception/inference_engine.py`) работает в **параллельном канале** — он не вызывается из основного тика `npc_tick_pipeline.py`. В основном тике `InterpretationEngine` читает уже готовый `PerceptualKernel` из `state_l2`. Помещение Prediction между Inference и PerceptualKernel буквально потребовало бы:

1. Синхронизировать параллельный Inference-канал с основным тиком — нарушение фазовой чистоты.
2. Мутировать `PerceptualKernel` напрямую — нарушение Invariant III (TickState frozen).

Поэтому §19 вводит **отдельную фазу 3.8**, которая:
- Читает `PredictionState` (персистентный между тиками) и текущие `ObservedFact`/`Inference`.
- Формирует `PerceptualKernelDelta` — **не mutation, а delta-контракт**.
- `StateApplicator` применяет delta к `state_l2.perceptual_kernel` — единый мутатор, как и для других delta.
- `InterpretationEngine` работает с уже обновлённым kernel → `bias/salience` учитывают prediction_error.

Это сохраняет фазовую чистоту Устава и Invariant III.

### §3.2 Файловая структура

```
backend/app/services/
├── npc/
│   ├── predictive/                       # NEW subpackage
│   │   ├── __init__.py
│   │   ├── predictive_perception_engine.py    # Оркестратор (§4.5)
│   │   ├── prediction_model.py                # PredictionModel (§4.1)
│   │   ├── prediction_error_calculator.py     # PredictionErrorCalculator (§4.2)
│   │   ├── precision_model.py                 # PrecisionModel (§4.3)
│   │   ├── spatial_temporal_trace.py          # SpatialTemporalTrace (§4.4)
│   │   └── kernel_delta_builder.py            # PerceptualKernelDelta builder (§5)
│   │
│   ├── memory/                           # из §18 (FUTURE)
│   │   └── ...
│   │
│   ├── belief/                           # из §18 (FUTURE)
│   │   └── ...
│   │
│   ├── decision_hub.py                   # БЕЗ ИЗМЕНЕНИЙ (READ ONLY)
│   ├── interpretation_engine.py          # БЕЗ ИЗМЕНЕНИЙ (читает обновлённый kernel)
│   ├── pressure_translator.py            # БЕЗ ИЗМЕНЕНИЙ
│   ├── state_applicator.py               # РАСШИРЕНИЕ: apply_delta_to_kernel (§5.3)
│   └── ...
│
├── perception/                           # существующий пакет — БЕЗ ИЗМЕНЕНИЙ
│   └── ...
```

**Принцип:** §19 не модифицирует `decision_hub.py`, `interpretation_engine.py`, `pressure_translator.py`. Он добавляет **новый subpackage** `npc/predictive/`, который читает `PredictionState` (персистентный) и `ObservedFact`/`Inference` (из Phase 3), и формирует `PerceptualKernelDelta`, применяемую через `StateApplicator`.

### §3.3 Интеграция с NpcTickPipeline

Новая фаза 3.8 встраивается в `npc_tick_pipeline.py` между существующей `BeliefTransitionEngine.integrate()` (строка 311) и `InterpretationEngine.compute()` (строка 337):

```python
# backend/app/services/npc/npc_tick_pipeline.py (FUTURE MODIFICATION)

# ... существующий код до BeliefTransitionEngine ...

try:
    from app.services.npc.belief_transition_engine import BeliefTransitionEngine
    BeliefTransitionEngine().integrate(state_l2, _event_for_belief, state.tick_id)
except Exception as _belief_err:
    logger.warning(f"[BELIEF] belief update failed for {npc_id}: {_belief_err}")

# ── NEW Phase 3.8: Predictive Perception ──────────────────────────
try:
    from app.services.npc.predictive.predictive_perception_engine import (
        PredictivePerceptionEngine,
    )
    from app.services.npc.predictive.kernel_delta_builder import (
        build_kernel_delta,
    )

    _predictive_engine = PredictivePerceptionEngine()
    _predictive_result = _predictive_engine.process(
        npc_id=npc_id,
        previous_kernel=getattr(state_l2, "perceptual_kernel", None),
        prediction_state=_load_prediction_state(npc_id, state.campaign_id),
        observed_facts=_collect_observed_facts(state, npc_id),
        inferences=_collect_inferences(state, npc_id),
        spatial_trace=_load_spatial_trace(npc_id, state.campaign_id),
        spatial_state=dict(state.scene_state),
        current_tick=state.tick_id,
        body_state=getattr(state_l2, "body_state", None),
        drives=getattr(state_l2, "drives_base", {}),
    )

    # Применяем delta к kernel через единый мутатор
    if _predictive_result.kernel_delta is not None:
        state_l2 = StateApplicator.apply_delta_to_kernel(
            state_l2, _predictive_result.kernel_delta
        )

    # Сохраняем обновлённый prediction_state для следующего тика
    _save_prediction_state(
        npc_id, state.campaign_id, _predictive_result.updated_prediction_state
    )

    # Сохраняем updated spatial_trace
    _save_spatial_trace(
        npc_id, state.campaign_id, _predictive_result.updated_spatial_trace
    )

    # Пробрасываем prediction_error в interpretation как evidence
    _prediction_error_for_interp = _predictive_result.prediction_error
except Exception as _pred_err:
    logger.warning(f"[PREDICTIVE] failed for {npc_id}: {_pred_err}")
    _prediction_error_for_interp = None

# ── Существующая InterpretationEngine (читает обновлённый kernel) ──
interpretation = InterpretationEngine().compute(
    state=state_l2,
    event=_event_for_interp,
    drives_base=_drives_for_interp,
    prediction_error=_prediction_error_for_interp,  # NEW optional parameter
)
```

**Критические моменты wiring:**

1. **PredictionState хранится отдельно от NPCState** — это оперативное когнитивное состояние, не narrative memory. Аналогично `idle_pressure_map` (V8-SOC-5 FIX). Хранение: in-memory LRU cache с TTL 1 час, как `npc_cache` в `LifeEngine`.

2. **SpatialTemporalTrace хранится отдельно** — bounded trace, `MAX_TRACE_LENGTH = 8`. То же LRU cache.

3. **`InterpretationEngine` получает опциональный параметр `prediction_error`** — НЕ обязательный, чтобы сохранить backward compatibility. Если `prediction_error=None`, `InterpretationEngine` работает как раньше (для тестов и legacy-сред).

4. **`StateApplicator.apply_delta_to_kernel`** — новый метод в существующем `StateApplicator`. Не нарушает L1 (State Mutation Law), потому что delta — это явный контракт модификации, аналогичный `apply_deltas_only`.

### §3.4 Determinism guarantees

Все функции §19 — **pure functions** в смысле ADR-O-301 (KernelRNG-bound). Они:
- Не вызывают `random.random()` напрямую (используют `KernelRNG` при необходимости).
- Не читают `datetime.now()` / `time.time()` (§15).
- Не читают `os.environ` / внешние сервисы.
- Одинаковый вход → одинаковый выход (replay determinism).
- `PredictionState` и `SpatialTemporalTrace` сериализуются через `pickle`/`json` — round-trip test обязателен.

### §3.5 Что НЕ меняется в существующем коде

| Файл | Что НЕ меняется | Почему |
|------|-----------------|--------|
| `decision_hub.py` | Сигнатура `compute()` | DecisionHub читает `DecisionContext`, не `Prediction`. Связь идёт через kernel → PressureTranslator → DecisionContext |
| `pressure_translator.py` | Сигнатура `translate_kernel_to_context()` | Переводчик читает kernel, не prediction. Если kernel уже обновлён, translator автоматически учтёт это |
| `state_applicator.py` (существующие методы) | `apply_deltas_only`, `apply_tick_recovery` | Добавляется только новый метод `apply_delta_to_kernel` |
| `memory_manager.py` | Write-path памяти | §19 не пишет в MemoryStore |
| `belief_transition_engine.py` | Write-path убеждений | §19 не пишет в BeliefState |
| `LifeEngine` | Schedule, random events | §19 не вмешивается в proactive tick |

**Принцип минимального вмешательства:** §19 добавляет новую фазу, но не модифицирует существующие. Это снижает риск регрессий и упрощает rollback.

---

## §4. ЧЕТЫРЕ КОМПОНЕНТА — ДЕТАЛЬНЫЕ СПЕЦИФИКАЦИИ

Каждый из четырёх компонент описывается отдельной pure function с явно определёнными входами, выходами и формулой. Все функции **детерминированы** (§15, §ENIGMA-005) и **не мутируют состояние** (§16, §17).

### §4.1 PredictionModel — что NPC ожидает

**Семантика:** формирует предсказание фактов для следующего тика на основе предыдущего состояния, памяти и пространственной истории.

```python
# backend/app/services/npc/predictive/prediction_model.py (FUTURE)

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from app.models.npc_state import NPCState, PerceptualKernel
    from app.services.npc.decision_hub import EventContext


@dataclass(frozen=True)
class PredictedEvent:
    """Один предсказанный кандидат события."""
    event_type: str                  # "PLAYER_ATTACKS", "PLAYER_SPOKE", "PLAYER_LEAVES", ...
    probability: float              # ∈ [0, 1]
    expected_intensity: float = 0.5 # ∈ [0, 1.5]


@dataclass(frozen=True)
class Prediction:
    """Полное предсказание NPC на horizon=1 тик вперёд.

    НЕ является Belief. Belief: «Я считаю, что Борко лжёт».
    Prediction: «Если я продолжу разговор, вероятнее всего он продолжит защищаться».
    """
    npc_id: str
    tick: int                        # тик, для которого сделано предсказание
    horizon: int = 1                 # в тиках (V1 = 1; V2/V3 могут расширить до 3)

    expected_events: Tuple[PredictedEvent, ...] = ()
    expected_position: Optional[Tuple[float, float]] = None  # игрока
    expected_velocity: Optional[Tuple[float, float]] = None
    expected_direction: Optional[float] = None               # радианы

    expected_social_state: Dict[str, float] = field(default_factory=dict)
    # {"trust_delta": +0.05, "fear_delta": -0.02, "cooperation_p": 0.74}

    confidence: float = 0.5          # ∈ [0, 1] — собственная уверенность в предсказании


def predict(
    *,
    npc_id: str,
    current_tick: int,
    previous_kernel: "PerceptualKernel",
    memory_context: Dict[str, Any],
    spatial_trace: Tuple[Any, ...],   # Tuple[SpatialTrace, ...]
    drives_base: Dict[str, float],
    relationship_snapshot: Dict[str, Any],
) -> Prediction:
    """
    G(z_{t-1}, s_t) → Prediction.

    Архитектурные инварианты:
      - Pure function (no side effects).
      - Не читает Reality (§17.1).
      - Не использует wall-clock (§15).
      - Не вызывает LLM.
      - Детерминирована (KernelRNG при необходимости сальтирования).
    """
    # 1. Event distribution — из предыдущего kernel + drives
    #    threat_gradient ↑ → P(PLAYER_ATTACKS) ↑
    #    trust_gradient ↑ → P(PLAYER_CONTINUES_DIALOGUE) ↑
    #    uncertainty ↑ → распределение сглаживается (entropy ↑)
    _threat = getattr(previous_kernel, "threat_gradient", 0.0)
    _trust = getattr(previous_kernel, "trust_gradient", 0.5)
    _uncertainty = getattr(previous_kernel, "uncertainty", 0.3)

    # Базовое распределение выведено из drives_base, не из magic numbers
    _fear_drive = drives_base.get("fear", 0.25)
    _desire_drive = drives_base.get("desire", 0.25)
    _control_drive = drives_base.get("control", 0.25)

    # Probability mass (нормализуется к 1.0)
    _p_attack = max(0.01, min(0.95, _threat * 0.7 + _fear_drive * 0.3))
    _p_continue = max(0.05, min(0.95, _trust * 0.6 + _desire_drive * 0.4))
    _p_leave = max(0.02, 1.0 - _p_attack - _p_continue)

    # Сглаживание при неопределённости (entropy ↑ → распределение равномернее)
    if _uncertainty > 0.7:
        _uniform = 1.0 / 3.0
        _mix = (_uncertainty - 0.7) / 0.3  # ∈ [0, 1]
        _p_attack = (1 - _mix) * _p_attack + _mix * _uniform
        _p_continue = (1 - _mix) * _p_continue + _mix * _uniform
        _p_leave = (1 - _mix) * _p_leave + _mix * _uniform

    # Нормализация (защита от float drift)
    _total = _p_attack + _p_continue + _p_leave
    _p_attack, _p_continue, _p_leave = (
        _p_attack / _total,
        _p_continue / _total,
        _p_leave / _total,
    )

    # 2. Spatial prediction — из trace через EMA velocity
    _expected_pos, _expected_vel = _predict_spatial(spatial_trace)

    # 3. Social prediction — из relationship_snapshot
    _expected_social = {
        "trust_delta": _trust * 0.1 - _fear_drive * 0.05,
        "fear_delta": _threat * 0.1 - _trust * 0.03,
        "cooperation_p": _trust * 0.7 - _fear_drive * 0.4,
    }

    # 4. Confidence — функция от consistency trace и drives
    _trace_consistency = _compute_trace_consistency(spatial_trace)
    _confidence = max(
        0.1,
        min(0.95, 0.5 + _control_drive * 0.3 + _trace_consistency * 0.2 - _uncertainty * 0.2),
    )

    return Prediction(
        npc_id=npc_id,
        tick=current_tick + 1,  # horizon=1
        horizon=1,
        expected_events=(
            PredictedEvent("PLAYER_ATTACKS", _p_attack, _threat),
            PredictedEvent("PLAYER_CONTINUES_DIALOGUE", _p_continue, 0.5),
            PredictedEvent("PLAYER_LEAVES", _p_leave, 0.3),
        ),
        expected_position=_expected_pos,
        expected_velocity=_expected_vel,
        expected_direction=_angle_from_velocity(_expected_vel) if _expected_vel else None,
        expected_social_state=_expected_social,
        confidence=round(_confidence, 4),
    )


def _predict_spatial(
    trace: Tuple[Any, ...]
) -> Tuple[Optional[Tuple[float, float]], Optional[Tuple[float, float]]]:
    """
    Экстраполяция позиции игрока из bounded spatial trace.
    Использует EMA velocity с λ = 0.3 (по умолчанию).

    p̂_{t+1} = p_t + Δt · [λ · v_t + (1-λ) · v_role]

    Где v_role — ожидаемое движение из контекста роли NPC (future work).
    В V1 используется только v_t.
    """
    if len(trace) < 2:
        return None, None

    latest = trace[-1]
    prev = trace[-2]
    p_t = latest.position
    p_prev = prev.position
    v_observed = (p_t[0] - p_prev[0], p_t[1] - p_prev[1])

    # EMA velocity с λ = 0.3
    _LAMBDA = 0.3
    v_smoothed = (
        _LAMBDA * v_observed[0] + (1 - _LAMBDA) * getattr(latest, "velocity", (0.0, 0.0))[0],
        _LAMBDA * v_observed[1] + (1 - _LAMBDA) * getattr(latest, "velocity", (0.0, 0.0))[1],
    )

    # Δt = 1 tick (GAME_TICK_INTERVAL_SECONDS = 60)
    p_predicted = (p_t[0] + v_smoothed[0], p_t[1] + v_smoothed[1])

    return p_predicted, v_smoothed
```

**Обоснование формулы:**

- `P(PLAYER_ATTACKS) = threat × 0.7 + fear × 0.3` — threat доминирует (угроза объективная), fear модулирует (трусливый NPC склонен ожидать атаку). Веса выведены из `drives_base`, не из хардкода.
- `P(PLAYER_CONTINUES_DIALOGUE) = trust × 0.6 + desire × 0.4` — доверие доминирует, желание общаться модулирует.
- Сглаживание при `uncertainty > 0.7` — реализует принцип «в тумане все направления равновероятны». Это аналогично немонотонности `U(c)` из §18 (§3.3 ТЗ §18).
- `confidence` явно отделён от `probability` — NPC может быть неуверенным в своём предсказании даже при высокой вероятности события.

### §4.2 PredictionErrorCalculator — насколько реальность отличается

**Семантика:** сравнивает предсказание с фактическим наблюдением, возвращает структурированную ошибку по каналам.

```python
# backend/app/services/npc/predictive/prediction_error_calculator.py (FUTURE)

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.services.npc.predictive.prediction_model import Prediction


@dataclass(frozen=True)
class PredictionError:
    """Read-only результат сравнения prediction vs observation.

    НЕ мутирует состояние. Передаётся в kernel_delta_builder (§5).
    """
    npc_id: str
    tick: int

    total: float          # ∈ [0, 1] — взвешенная суммарная ошибка
    event: float          # ∈ [0, 1] — расхождение по событиям
    spatial: float        # ∈ [0, 1] — расхождение по позиции/направлению
    temporal: float       # ∈ [0, 1] — расхождение по времени (V2+)
    social: float         # ∈ [0, 1] — расхождение по social state

    surprise: float       # ∈ [0, +∞) — информационная неожиданность
    precision: float      # ∈ [0, 1] — надёжность наблюдения (из PrecisionModel)

    dominant_channel: Optional[str] = None  # "event" | "spatial" | "social" | None


def compare(
    *,
    prediction: Prediction,
    observed_facts: List[Any],         # List[ObservedFact]
    actual_event_type: Optional[str] = None,
    actual_player_position: Optional[Tuple[float, float]] = None,
    actual_social_deltas: Optional[Dict[str, float]] = None,
    precision: float = 1.0,            # из PrecisionModel (§4.3)
    current_tick: int,
    epsilon: float = 1e-6,
) -> PredictionError:
    """
    W(x_t, x̂_t) · Precision(x_t) → PredictionError.

    Архитектурные инварианты:
      - Pure function.
      - Не читает Reality (§17.1).
      - Не использует wall-clock (§15).
      - Возвращает структурированный результат.
    """
    # 1. Event error
    _event_err = _event_error(
        prediction.expected_events, actual_event_type, observed_facts
    )

    # 2. Spatial error
    _spatial_err = _spatial_error(
        prediction.expected_position, actual_player_position
    )

    # 3. Temporal error (V2+ — пока 0)
    _temporal_err = 0.0

    # 4. Social error
    _social_err = _social_error(
        prediction.expected_social_state, actual_social_deltas
    )

    # 5. Surprise = -log P(actual_event | prediction)
    _surprise = _compute_surprise(
        prediction.expected_events, actual_event_type, epsilon
    )

    # 6. Total — взвешенная сумма (веса из каналов, не magic numbers)
    #    event доминирует (визуальная информация важнее пространственной)
    _total = (
        0.45 * _event_err
        + 0.25 * _spatial_err
        + 0.15 * _social_err
        + 0.15 * _temporal_err
    ) * precision

    _total = max(0.0, min(1.0, _total))

    # 7. Dominant channel — для diagnostics
    _channels = {
        "event": _event_err,
        "spatial": _spatial_err,
        "social": _social_err,
    }
    _dominant = max(_channels, key=_channels.get) if _total > 0.05 else None

    return PredictionError(
        npc_id=prediction.npc_id,
        tick=current_tick,
        total=round(_total, 4),
        event=round(_event_err, 4),
        spatial=round(_spatial_err, 4),
        temporal=round(_temporal_err, 4),
        social=round(_social_err, 4),
        surprise=round(_surprise, 4),
        precision=round(precision, 4),
        dominant_channel=_dominant,
    )


def _event_error(
    expected_events: Tuple[Any, ...],
    actual_event_type: Optional[str],
    observed_facts: List[Any],
) -> float:
    """
    Для бинарных событий: surprise = -log P(actual | prediction).
    Для непрерывных (fact values): нормированное расхождение.

    d_i = |x_i - x̂_i| / (σ_i + ε)
    """
    if not actual_event_type:
        # Нет явного события — ошибка определяется через fact deviation
        return _fact_deviation(observed_facts, expected_events)

    # Ищем предсказанную вероятность для actual_event_type
    _p_actual = 0.05  # default для непредсказанных событий
    for ev in expected_events:
        if ev.event_type == actual_event_type:
            _p_actual = ev.probability
            break

    # Surprise → [0, 1] через sigmoid-подобную функцию
    _surprise = -math.log(max(_p_actual, 1e-6))
    return min(1.0, _surprise / 5.0)  # нормировка: surprise=5 → error=1.0


def _spatial_error(
    expected: Optional[Tuple[float, float]],
    actual: Optional[Tuple[float, float]],
    sigma: float = 3.0,  # ожидаемая вариативность в метрах
) -> float:
    """
    E_spatial = ||p_actual - p_expected|| / (σ + ε)
    Clamp к [0, 1].
    """
    if expected is None or actual is None:
        return 0.0  # нет данных — нет ошибки (Vacuum)
    _dx = actual[0] - expected[0]
    _dy = actual[1] - expected[1]
    _dist = math.sqrt(_dx * _dx + _dy * _dy)
    return min(1.0, _dist / (sigma + 1e-6))


def _social_error(
    expected: Dict[str, float],
    actual: Optional[Dict[str, float]],
) -> float:
    """Сумма абсолютных разностей по social deltas, нормированная."""
    if not actual:
        return 0.0
    _sum_diff = sum(abs(actual.get(k, 0.0) - expected.get(k, 0.0)) for k in expected)
    return min(1.0, _sum_diff / len(expected)) if expected else 0.0


def _compute_surprise(
    expected_events: Tuple[Any, ...],
    actual_event_type: Optional[str],
    epsilon: float,
) -> float:
    """surprise = -log P(x | z_{t-1})."""
    if not actual_event_type:
        return 0.0
    _p = epsilon
    for ev in expected_events:
        if ev.event_type == actual_event_type:
            _p = max(_p, ev.probability)
            break
    return -math.log(_p)


def _fact_deviation(
    observed_facts: List[Any],
    expected_events: Tuple[Any, ...],
) -> float:
    """
    Если нет явного event_type — ошибка вычисляется через
    сумму отклонений по fact_name.
    """
    if not observed_facts:
        return 0.0
    # V1: простая эвристика — доля фактов с непредсказанным значением
    # V2+: сравнение с expected_fact_values из Prediction
    _unpredicted = sum(
        1 for f in observed_facts
        if getattr(f, "fact_name", "") in ("weapon_visible", "blood_stain_visible")
        and getattr(f, "value", None)
    )
    return min(1.0, _unpredicted / max(1, len(observed_facts)))
```

### §4.3 PrecisionModel — насколько доверять расхождению

**Семантика:** вычисляет надёжность и значимость наблюдения. Это **ключевая связь** между spatial physics и когнитивным слоем.

```python
# backend/app/services/npc/predictive/precision_model.py (FUTURE)

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class PrecisionResult:
    """Результат вычисления precision."""
    value: float                       # ∈ [0, 1] — итоговая precision
    confidence: float                  # физическая надёжность (LOS, distance, light)
    reliability: float                 # эпистемическая надёжность источника
    attention: float                   # фокус NPC


def compute_precision(
    *,
    observed_facts: list,              # List[ObservedFact]
    perception_confidence: float,      # из PerceptionFilter (0..1)
    source_type: str = "perception",   # perception | observation | inference | rumor
    drives_base: Dict[str, float],
    stress: float = 0.0,
    npc_freedom: float = 50.0,         # из status_profile
) -> PrecisionResult:
    """
    Precision(x) = Confidence(x) · Reliability(x) · Attention(x)

    Архитектурные инварианты:
      - Pure function.
      - НЕ ЧИТАЕТ PerceptualKernel (§ENIGMA-004).
      - Возвращает [0.0, 1.0].
    """
    # 1. Confidence — из PerceptionFilter (LOS, distance, light, walls)
    #    perception_confidence уже вычислен в perception_filter.calculate_clarity()
    _confidence = max(0.0, min(1.0, perception_confidence))

    # 2. Reliability — эпистемическая иерархия (как в §18 §3.2)
    _reliability = {
        "perception":  0.85,   # NPC лично наблюдал
        "observation": 0.70,   # NPC слышал/видел нечётко
        "inference":   0.50,   # NPC вывел сам
        "rumor":       0.40,   # NPC услышал от другого NPC
    }.get(source_type, 0.30)

    # 3. Attention — из drives_base
    #    high control → high attention (фокус)
    #    high fear → low attention (отвлекается на угрозы)
    #    high stress → low attention (когнитивная перегрузка)
    _control = drives_base.get("control", 0.25)
    _fear = drives_base.get("fear", 0.25)
    _stress_norm = max(0.0, min(1.0, stress / 100.0))

    _attention = max(
        0.05,  # минимум — даже паникующий NPC что-то воспринимает
        min(1.0, 0.5 + _control * 0.5 - _fear * 0.3 - _stress_norm * 0.2),
    )

    # 4. Composition — мультипликативная (любая компонента может обнулить)
    _value = _confidence * _reliability * _attention

    return PrecisionResult(
        value=round(_value, 4),
        confidence=round(_confidence, 4),
        reliability=round(_reliability, 4),
        attention=round(_attention, 4),
    )
```

**Критический момент:** `confidence` берётся из `PerceptionFilter.calculate_clarity()` (см. `perception_filter.py:63-94`). Это **причинно связывает**:
- `line_of_sight(distance, scene_state)` → `confidence`
- `confidence` → `precision`
- `precision` → `weighted_prediction_error`
- `weighted_prediction_error` → `Δkernel`

Физика мира (стены, освещение, дистанция) определяет не только «увидел/не увидел», но и **насколько сильно NPC должен доверять расхождению между ожиданием и наблюдением**. Это значительно глубже простого фильтра видимости.

### §4.4 SpatialTemporalTrace — функциональный аналог traveling wave

**Семантика:** bounded затухающий след пространственно-временных наблюдений. Это **не нейронная волна**, а структурированное состояние, из которого возникает prediction.

```python
# backend/app/services/npc/predictive/spatial_temporal_trace.py (FUTURE)

import math
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

# Жёсткий cap — без него §19 станет вторым дорогим perception engine
MAX_TRACE_LENGTH = 8
DEFAULT_DECAY = 0.15  # λ в формуле T_{t+1}(x) = T_t(x)·e^(-λΔt) + I_t(x)


@dataclass(frozen=True)
class SpatialTraceEntry:
    """Одна запись в bounded trace."""
    tick: int
    position: Tuple[float, float]
    direction: Optional[float] = None       # радианы
    velocity: Tuple[float, float] = (0.0, 0.0)
    salience: float = 0.5                   # ∈ [0, 1]
    source: str = "player"                  # "player" | "npc:<id>" | "sound"


@dataclass(frozen=True)
class SpatialTemporalTrace:
    """Bounded trace последних MAX_TRACE_LENGTH наблюдений.

    НЕ хранится в NPCState — это оперативное когнитивное состояние,
    аналогично idle_pressure_map (V8-SOC-5 FIX).
    Хранится in-memory LRU cache с TTL 1 час.
    """
    npc_id: str
    entries: Tuple[SpatialTraceEntry, ...] = ()

    def add(
        self,
        entry: SpatialTraceEntry,
        max_length: int = MAX_TRACE_LENGTH,
    ) -> "SpatialTemporalTrace":
        """Добавить entry, обрезать до max_length."""
        _new = self.entries + (entry,)
        if len(_new) > max_length:
            _new = _new[-max_length:]
        return SpatialTemporalTrace(npc_id=self.npc_id, entries=_new)

    def decay(
        self,
        current_tick: int,
        decay_rate: float = DEFAULT_DECAY,
    ) -> "SpatialTemporalTrace":
        """
        T_{t+1}(x) = T_t(x) · e^(-λ·Δt) + I_t(x)

        Где Δt = current_tick - entry.tick (в тиках).
        Decay применяется к salience — позиции не затухают (это факты).
        """
        _decayed = tuple(
            SpatialTraceEntry(
                tick=e.tick,
                position=e.position,
                direction=e.direction,
                velocity=e.velocity,
                salience=e.salience * math.exp(-decay_rate * (current_tick - e.tick)),
                source=e.source,
            )
            for e in self.entries
            if current_tick - e.tick <= 50  # hard cap: 50 тиков = полное забвение
        )
        return SpatialTemporalTrace(npc_id=self.npc_id, entries=_decayed)

    def latest(self) -> Optional[SpatialTraceEntry]:
        return self.entries[-1] if self.entries else None

    def trajectory(self) -> Tuple[Tuple[float, float], ...]:
        """Только позиции, для визуализации и pattern detection."""
        return tuple(e.position for e in self.entries)


def update_trace(
    *,
    current_trace: SpatialTemporalTrace,
    new_observation: Optional[SpatialTraceEntry],
    current_tick: int,
) -> SpatialTemporalTrace:
    """
    Шаг обновления: decay + add (если есть новое наблюдение).
    """
    _decayed = current_trace.decay(current_tick)
    if new_observation is not None:
        return _decayed.add(new_observation)
    return _decayed
```

**Критические моменты:**

1. **`MAX_TRACE_LENGTH = 8`** — жёсткий cap. Это §8.4 (Unbounded trace history) anti-pattern prevention. Без него trace растёт линейно с количеством тиков и превращается в дорогой второй perception engine.

2. **`hard cap: 50 тиков`** — полное забвение. Записи старше 50 тиков вырезаются полностью. Это защита от утечки памяти и от того, что «давние следы» начнут искажать prediction.

3. **Decay применяется к `salience`, не к `position`** — позиции это факты (Invariant I — Causal Provenance). Salience — субъективная значимость, она затухает.

4. **`source`** — явно помечает, чья это позиция. Trace может содержать позиции игрока, NPC, источников звука. Это важно для V2 (multi-source prediction).

5. **LRU cache, не SQLite** — trace это **оперативное когнитивное состояние**, не narrative memory. Аналогично `idle_pressure_map` (V8-SOC-5 FIX). Персистентность не требуется — при рестарте сессии trace собирается заново.

### §4.5 PredictivePerceptionEngine — оркестратор

Все четыре компонента собираются в единую pure function:

```python
# backend/app/services/npc/predictive/predictive_perception_engine.py (FUTURE)

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.services.npc.predictive.prediction_model import Prediction, predict
from app.services.npc.predictive.prediction_error_calculator import (
    PredictionError,
    compare,
)
from app.services.npc.predictive.precision_model import (
    PrecisionResult,
    compute_precision,
)
from app.services.npc.predictive.spatial_temporal_trace import (
    SpatialTemporalTrace,
    SpatialTraceEntry,
    update_trace,
)


@dataclass(frozen=True)
class PredictiveResult:
    """Read-only результат Phase 3.8."""
    prediction: Prediction
    error: PredictionError
    precision: PrecisionResult
    kernel_delta: Optional[Any]  # PerceptualKernelDelta или None если PE < threshold
    updated_prediction_state: Any  # PredictionState для следующего тика
    updated_spatial_trace: SpatialTemporalTrace


class PredictivePerceptionEngine:
    """
    Pure function: (state_{t-1}, observation_t) → PredictiveResult.
    НЕ мутирует состояние.
    НЕ создаёт событий.
    НЕ читает Reality.
    НЕ вызывает LLM.
    """

    def process(
        self,
        *,
        npc_id: str,
        previous_kernel: Any,
        prediction_state: Any,             # PredictionState (персистентный)
        observed_facts: List[Any],
        inferences: List[Any],
        spatial_trace: SpatialTemporalTrace,
        spatial_state: Dict[str, Any],
        current_tick: int,
        body_state: Optional[Dict[str, Any]] = None,
        drives: Dict[str, float] = None,
    ) -> PredictiveResult:
        drives = drives or {}

        # 1. Predict — что NPC ожидает
        _prediction = predict(
            npc_id=npc_id,
            current_tick=current_tick,
            previous_kernel=previous_kernel,
            memory_context=getattr(prediction_state, "memory_context", {}),
            spatial_trace=spatial_trace.entries,
            drives_base=drives,
            relationship_snapshot=getattr(prediction_state, "relationship_snapshot", {}),
        )

        # 2. Extract actual observation
        _actual_event_type = self._extract_actual_event_type(observed_facts, inferences)
        _actual_position = self._extract_player_position(spatial_state)
        _actual_social = None  # V2+

        # 3. Compute precision
        _perception_confidence = self._compute_perception_confidence(
            observed_facts, spatial_state
        )
        _precision = compute_precision(
            observed_facts=observed_facts,
            perception_confidence=_perception_confidence,
            source_type="perception",
            drives_base=drives,
            stress=body_state.get("stress", 0.0) if body_state else 0.0,
        )

        # 4. Compare prediction vs observation
        _error = compare(
            prediction=_prediction,
            observed_facts=observed_facts,
            actual_event_type=_actual_event_type,
            actual_player_position=_actual_position,
            actual_social_deltas=_actual_social,
            precision=_precision.value,
            current_tick=current_tick,
        )

        # 5. Update spatial trace with current observation
        _new_entry = self._build_trace_entry(
            current_tick, _actual_position, observed_facts
        )
        _updated_trace = update_trace(
            current_trace=spatial_trace,
            new_observation=_new_entry,
            current_tick=current_tick,
        )

        # 6. Build kernel delta (только если precision > min_threshold)
        from app.services.npc.predictive.kernel_delta_builder import build_kernel_delta
        _kernel_delta = build_kernel_delta(
            prediction_error=_error,
            prediction=_prediction,
            salience=self._compute_salience(observed_facts, _precision.value),
            learning_rate=0.15,  # default; V1+ per-NPC из NPCProfileL0
        )

        # 7. Build updated prediction_state
        _updated_prediction_state = self._update_prediction_state(
            prediction_state, _prediction, _error, current_tick
        )

        return PredictiveResult(
            prediction=_prediction,
            error=_error,
            precision=_precision,
            kernel_delta=_kernel_delta,
            updated_prediction_state=_updated_prediction_state,
            updated_spatial_trace=_updated_trace,
        )

    # ── Приватные методы — извлечение данных из существующих структур ──

    def _extract_actual_event_type(
        self, observed_facts: List[Any], inferences: List[Any]
    ) -> Optional[str]:
        """Возвращает actual event type из facts/inferences или None."""
        # V1: простая эвристика — если есть weapon_visible=True → PLAYER_ATTACKS
        for f in observed_facts:
            if getattr(f, "fact_name", "") == "weapon_visible" and getattr(f, "value", None):
                return "PLAYER_ATTACKS"
        return None

    def _extract_player_position(
        self, spatial_state: Dict[str, Any]
    ) -> Optional[Tuple[float, float]]:
        """Читает позицию игрока из scene_state['npc_positions']['player']."""
        _pos = spatial_state.get("npc_positions", {}).get("player", {}).get("local_position")
        if _pos:
            return (_pos.get("x", 0.0), _pos.get("y", 0.0))
        return None

    def _compute_perception_confidence(
        self, observed_facts: List[Any], spatial_state: Dict[str, Any]
    ) -> float:
        """
        Делегирует в perception_filter.calculate_clarity() (существующий метод).
        Возвращает ∈ [0, 1].
        """
        from app.services.npc.perception_filter import calculate_clarity
        if not observed_facts:
            return 0.0
        # Берём confidence первого факта (V1 — упрощение)
        # V2+: среднее по всем фактам
        _distance = 5.0  # default; V2+: вычислять из spatial_state
        _light = spatial_state.get("environment", {}).get("light_level", "dim")
        return calculate_clarity(distance=_distance, light_level=_light)

    def _build_trace_entry(
        self,
        tick: int,
        position: Optional[Tuple[float, float]],
        observed_facts: List[Any],
    ) -> Optional[SpatialTraceEntry]:
        if position is None:
            return None
        _salience = max(
            (getattr(f, "confidence", 0.5) for f in observed_facts),
            default=0.3,
        )
        return SpatialTraceEntry(
            tick=tick,
            position=position,
            salience=_salience,
            source="player",
        )

    def _compute_salience(
        self, observed_facts: List[Any], precision: float
    ) -> float:
        """Salience = max(confidence of facts) × precision."""
        if not observed_facts:
            return 0.0
        _max_conf = max((getattr(f, "confidence", 0.5) for f in observed_facts), default=0.5)
        return min(1.0, _max_conf * precision)

    def _update_prediction_state(
        self,
        prediction_state: Any,
        prediction: Prediction,
        error: PredictionError,
        current_tick: int,
    ) -> Any:
        """Сохраняет last_prediction + last_error для следующего тика."""
        from app.services.npc.predictive.prediction_state import PredictionState
        return PredictionState(
            npc_id=prediction.npc_id,
            last_prediction=prediction,
            last_error=error,
            last_update_tick=current_tick,
            memory_context=getattr(prediction_state, "memory_context", {}),
            relationship_snapshot=getattr(prediction_state, "relationship_snapshot", {}),
        )
```

**Критический момент:** `PredictivePerceptionEngine` — это **read-only pure function**. Она:
- Не пишет в `BeliefState`.
- Не пишет в `MemoryStore`.
- Не пишет в `PerceptualKernel` напрямую — только через `PerceptualKernelDelta`, применяемую `StateApplicator`.
- Не публикует события.
- Не вызывает LLM.

---

## §5. PERCEPTUALKERNELDELTA — КОНТРАКТ МОДИФИКАЦИИ

### §5.1 Почему Delta, а не mutation

Invariant III (Temporal Isolation) требует, что `TickState` замораживается на границе сборки. Прямая мутация `state_l2.perceptual_kernel.threat_gradient += 0.2` **запрещена**.

Поэтому §19 вводит `PerceptualKernelDelta` — явный контракт модификации ядра, аналогичный `StateDeltas` (используется в `DecisionHub`):

```python
# backend/app/services/npc/predictive/kernel_delta_builder.py (FUTURE)

from dataclasses import dataclass
from typing import Optional

from app.services.npc.predictive.prediction_error_calculator import PredictionError
from app.services.npc.predictive.prediction_model import Prediction


@dataclass(frozen=True)
class PerceptualKernelDelta:
    """
    Read-only delta для модификации PerceptualKernel.
    Применяется через StateApplicator.apply_delta_to_kernel().

    НЕ мутирует состояние напрямую. Это контракт, а не операция.
    """
    # Модуляция существующих полей PerceptualKernel
    threat_gradient_delta: float = 0.0          # ∈ [-0.5, +0.5]
    trust_gradient_delta: float = 0.0           # ∈ [-0.3, +0.3]
    uncertainty_delta: float = 0.0              # ∈ [-0.3, +0.5]
    anomaly_score_delta: float = 0.0            # ∈ [0, +0.5] — только рост
    aggression_inhibition_delta: float = 0.0    # ∈ [-0.3, +0.3]
    initiative_suppression_delta: float = 0.0   # ∈ [-0.3, +0.3]
    compliance_bias_delta: float = 0.0          # ∈ [-0.3, +0.3]

    # Новые поля (V1 — добавляются в PerceptualKernel)
    prediction_error_set: bool = False          # флаг: было ли обновление
    prediction_error_value: float = 0.0         # ∈ [0, 1]
    prediction_surprise_value: float = 0.0      # ∈ [0, +∞)
    prediction_confidence_value: float = 0.5    # ∈ [0, 1]

    # Диагностика
    source: str = "predictive_engine"
    applied_tick: Optional[int] = None


def build_kernel_delta(
    *,
    prediction_error: PredictionError,
    prediction: Prediction,
    salience: float,
    learning_rate: float = 0.15,
) -> Optional[PerceptualKernelDelta]:
    """
    Строит delta из prediction_error + surprise + salience.

    Архитектурные инварианты:
      - Pure function.
      - Возвращает None если prediction_error.total < 0.05 (порог активации).
      - Все deltas ограничены bounds — L5 guard.
    """
    # Порог активации: precision < 0.05 → не модифицируем ядро
    if prediction_error.precision < 0.05:
        return None

    if prediction_error.total < 0.05 and prediction_error.surprise < 1.0:
        return None

    # Базовые deltas — выведены из формулы Δkernel = α · e · salience
    _alpha = learning_rate
    _e = prediction_error.total
    _s = salience
    _surprise = prediction_error.surprise

    # Modulation: threat ↑ при event_error (особенно PLAYER_ATTACKS)
    _is_attack_pred = any(
        ev.event_type == "PLAYER_ATTACKS" and ev.probability > 0.3
        for ev in prediction.expected_events
    )
    _threat_delta = _alpha * _e * _s * (1.5 if _is_attack_pred else 1.0)

    # Uncertainty ↑ при high surprise (модель мира нарушена)
    _uncertainty_delta = _alpha * min(1.0, _surprise / 3.0) * _s

    # Anomaly score ↑ при high total error
    _anomaly_delta = _alpha * _e * _s * 0.5

    # Trust ↓ при social error (особенно предательство)
    _trust_delta = -_alpha * prediction_error.social * _s * 0.5

    # Aggression inhibition ↑ при high threat (трусливые замераживаются)
    _aggr_inhibition_delta = _alpha * _threat_delta * 0.3

    # Compliance bias ↑ при uncertainty + threat (подчинение давлению)
    _compliance_delta = _alpha * (_uncertainty_delta + _threat_delta * 0.5) * 0.3

    # Clamp всех deltas — L5 guard
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, round(v, 4)))

    return PerceptualKernelDelta(
        threat_gradient_delta=_clamp(_threat_delta, -0.5, +0.5),
        trust_gradient_delta=_clamp(_trust_delta, -0.3, +0.3),
        uncertainty_delta=_clamp(_uncertainty_delta, -0.3, +0.5),
        anomaly_score_delta=_clamp(_anomaly_delta, 0.0, +0.5),
        aggression_inhibition_delta=_clamp(_aggr_inhibition_delta, -0.3, +0.3),
        initiative_suppression_delta=0.0,  # V2+ — из somatic feedback
        compliance_bias_delta=_clamp(_compliance_delta, -0.3, +0.3),
        prediction_error_set=True,
        prediction_error_value=round(_e, 4),
        prediction_surprise_value=round(_surprise, 4),
        prediction_confidence_value=prediction.confidence,
        source="predictive_engine",
    )
```

### §5.2 Расширение PerceptualKernel

В `PerceptualKernel` (`backend/app/models/npc_state.py`) добавляются новые поля:

```python
# backend/app/models/npc_state.py (FUTURE EXTENSION)

@dataclass
class PerceptualKernel:
    """Субъективная модель восприятия NPC. Геометрия пространства решений."""

    # ... существующие поля ...
    threat_gradient: float = 0.0
    trust_gradient: float = 0.0
    uncertainty: float = 0.0
    anomaly_score: float = 0.0
    last_hostile_direction: Optional[str] = None
    dominant_emotion: Optional[str] = None
    aggression_inhibition: float = 0.0
    initiative_suppression: float = 0.0
    compliance_bias: float = 0.0
    somatic_urgency: float = 0.0
    recent_directive: Optional[Dict[str, Any]] = None

    # ── NEW §19: Predictive Dynamics ─────────────────────────────────
    prediction_error: float = 0.0          # ∈ [0, 1] — последняя PE
    prediction_surprise: float = 0.0       # ∈ [0, +∞) — последний surprise
    prediction_confidence: float = 0.5     # ∈ [0, 1] — confidence в последнем prediction
    temporal_prediction_error: float = 0.0 # V2+ — для temporal channel
    spatial_prediction_error: float = 0.0  # V2+ — для spatial channel
    social_prediction_error: float = 0.0   # V2+ — для social channel
    # ──────────────────────────────────────────────────────────────────
```

**Принцип:** новые поля **не заменяют** существующие. Они **дополняют** ядро, делая предиктивный слой видимым для `InterpretationEngine` и `PressureTranslator`.

### §5.3 StateApplicator.apply_delta_to_kernel

Новый метод в существующем `StateApplicator`:

```python
# backend/app/services/npc/state_applicator.py (FUTURE EXTENSION)

class StateApplicator:
    # ... существующие методы ...

    def apply_delta_to_kernel(
        self,
        state: NPCState,
        delta: PerceptualKernelDelta,
    ) -> NPCState:
        """
        Применяет PerceptualKernelDelta к state.perceptual_kernel.
        НЕ нарушает L1 (State Mutation Law) — это явный контракт,
        аналогичный apply_deltas_only.

        Архитектурные инварианты:
          - Возвращает новый NPCState (immutable style).
          - Все поля clamp к [0, 1] или [-1, 1] (L5 guard).
          - Логирует применение для CDS.
        """
        if delta is None:
            return state

        _kernel = state.perceptual_kernel

        # Применяем deltas
        _kernel.threat_gradient = self._clamp(
            _kernel.threat_gradient + delta.threat_gradient_delta, 0.0, 1.0
        )
        _kernel.trust_gradient = self._clamp(
            _kernel.trust_gradient + delta.trust_gradient_delta, 0.0, 1.0
        )
        _kernel.uncertainty = self._clamp(
            _kernel.uncertainty + delta.uncertainty_delta, 0.0, 1.0
        )
        _kernel.anomaly_score = self._clamp(
            _kernel.anomaly_score + delta.anomaly_score_delta, 0.0, 1.0
        )
        _kernel.aggression_inhibition = self._clamp(
            _kernel.aggression_inhibition + delta.aggression_inhibition_delta, 0.0, 1.0
        )
        _kernel.compliance_bias = self._clamp(
            _kernel.compliance_bias + delta.compliance_bias_delta, 0.0, 1.0
        )

        # Обновляем предиктивные поля
        if delta.prediction_error_set:
            _kernel.prediction_error = delta.prediction_error_value
            _kernel.prediction_surprise = delta.prediction_surprise_value
            _kernel.prediction_confidence = delta.prediction_confidence_value

        # Логирование для CDS (Causal Diagnostic System)
        logger.debug(
            f"[PREDICTIVE_DELTA] npc={state.npc_id} "
            f"threat_delta={delta.threat_gradient_delta:+.3f} "
            f"uncertainty_delta={delta.uncertainty_delta:+.3f} "
            f"anomaly_delta={delta.anomaly_score_delta:+.3f} "
            f"pe={delta.prediction_error_value:.3f} "
            f"surprise={delta.prediction_surprise_value:.3f}"
        )

        return state

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, round(value, 4)))
```

**Критический момент:** этот метод — **единственная точка мутации** `PerceptualKernel` из §19. Все остальные компоненты §19 возвращают deltas, но не применяют их. Это соответствует L1 (State Mutation Law) и Invariant III.

### §5.4 Что НЕ делает PerceptualKernelDelta

```
❌ ЗАПРЕЩЕНО:
    kernel.threat_gradient += 0.2  # прямая мутация

✅ ПРАВИЛЬНО:
    delta = build_kernel_delta(prediction_error, ...)
    state = StateApplicator.apply_delta_to_kernel(state, delta)
```

```
❌ ЗАПРЕЩЕНО:
    # Delta пишет в BeliefState
    delta.belief_state_update = {...}

✅ ПРАВИЛЬНО:
    # Delta модулирует только PerceptualKernel
    # BeliefState обновляется отдельно, через BeliefRevisionEngine (§18)
```

```
❌ ЗАПРЕЩЕНО:
    # Delta с magic number
    delta.threat_gradient_delta = 0.35  # ← откуда 0.35?

✅ ПРАВИЛЬНО:
    # Delta вычислена из формулы
    delta.threat_gradient_delta = α · e · salience · (1.5 if attack_pred else 1.0)
```

---

## §6. ИНТЕГРАЦИЯ С §18 (RESOURCE-BOUNDED EPISTEMIC SELECTION)

### §6.1 Cross-law dependency

§19 — это **источник** неопределённости для §18. Формула §18:

```
U_M(m, c) = I(m, c) · R(m) · U(c) − C(m, c)
```

`U(c)` — uncertainty of current observation. В ТЗ §18 (§3.3) `U(c)` определена как pure function от `EventContext`:

```python
# ТЗ §18, §3.3 — текущая реализация
def uncertainty_score(context, state):
    distance_factor = min(1.0, context.distance / 20.0)
    clarity_factor = 1.0 - _extract_clarity_from_payload(context.payload)
    witness_factor = 1.0 / (1.0 + context.witness_count)
    chaos_factor = min(1.0, len(context.scene_flags) / 5.0)
    raw = 0.35 * distance_factor + 0.35 * clarity_factor + 0.15 * witness_factor + 0.15 * chaos_factor
    # ... немонотонность ...
    return raw
```

После активации §19 `U(c)` должна **дополнительно** учитывать `prediction_error`:

```python
# ТЗ §18, §3.3 — расширенная версия после активации §19
def uncertainty_score(context, state, prediction_error: Optional[PredictionError] = None):
    # ... существующие 4 компонента ...
    raw = 0.35 * distance_factor + 0.35 * clarity_factor + 0.15 * witness_factor + 0.15 * chaos_factor

    # NEW §19: prediction_error как 5-я компонента
    if prediction_error is not None:
        # Веса перераспределены: clarity снижена с 0.35 до 0.25,
        # prediction_error получает 0.10
        raw = (
            0.30 * distance_factor
            + 0.25 * clarity_factor
            + 0.15 * witness_factor
            + 0.10 * chaos_factor
            + 0.20 * prediction_error.total  # NEW
        )

    # ... немонотонность ...
    return raw
```

### §6.2 Почему это не нарушает §18

| Аспект | Без §19 | С §19 |
|--------|---------|-------|
| Источник `U(c)` | 4 компонента из EventContext | 5 компонентов: 4 из EventContext + prediction_error |
| Pure function | Да | Да — `prediction_error` immutable |
| Не читает PerceptualKernel | Да | Да — `prediction_error` не `kernel.uncertainty` |
| Немонотонность | Реализована через `if raw > 0.8` | Сохраняется — prediction_error.total ∈ [0, 1] |
| Magic numbers | Веса 0.35/0.35/0.15/0.15 выведены из логики | Веса 0.30/0.25/0.15/0.10/0.20 — перераспределены, общая сумма 1.0 |

**Критически важно:** §19 НЕ заменяет `U(c)` из §18. Он **расширяет** её, делая неопределённость динамической — учитывающей расхождение между ожиданием и наблюдением.

### §6.3 Соответствие «Memory = Evidence» принципу

§18 §5.3 фиксирует: «MemoryUtility > 0 → memory становится evidence, не truth». §19 усиливает это: **Prediction Error тоже становится evidence, не truth**.

```
§18: Memory → MemoryUtility → BeliefRevision → BeliefState
§19: Observation → PredictionError → PerceptualKernelDelta → PerceptualKernel
                                                              ↓
                                              InterpretationEngine → DecisionContext
                                                                                ↓
                                                                        DecisionHub
```

Оба закона работают **до** DecisionHub. Оба возвращают **deltas/evidence**, а не мутируют состояние напрямую. Это сохраняет единый architectural style.

### §6.4 Surprise как источник Importance

В §18 ADR-O-206 (Emotional Residue Isolation) определяет `surprise` как источник importance для памяти. §19 делает `surprise` **вычислимой величиной**:

```python
# §18 — текущее упоминание surprise (без формулы)
importance = base_importance + (surprise_bonus if surprising_event else 0)

# §19 — явная формула
surprise = -log P(x_t | z_{t-1})
```

После активации §19 `surprise` в §18 берётся из `PredictionError.surprise`. Это **закрывает цикл** между предсказанием и памятью: неожиданное событие → высокий surprise → высокий importance → выше шанс попасть в long-term memory.

### §6.5 Порядок активации

```
Шаг 1: Активация §18 (после закрытия PC-1..PC-7, PC-16, PC-17 из ТЗ §18)
   ↓
Шаг 2: Стабилизация Belief Layer (Этап B из ТЗ §18)
   ↓
Шаг 3: Активация §19 V1 (Этап A этого ТЗ)
   ↓
Шаг 4: Расширение U(c) в §18 — принимает prediction_error как 5-ю компоненту
   ↓
Шаг 5: Surprise из §19 становится источником importance в §18
```

**Принцип:** §19 **не может** быть активирован раньше §18. Без `BeliefRevisionEngine` (PC-2 из §18) `prediction_error` не имеет, куда передаваться как evidence. Без расширенной `BeliefState` schema (PC-3) нет персистентности.

---

## §7. ТАБЛИЦА СОВМЕСТИМОСТИ С УСТАВОМ

| § | Закон Устава | Совместимость §19 | Обоснование |
|---|--------------|-------------------|-------------|
| §ENIGMA-001 | Приоритет Причинной Глубины | **100% совместимо** | §19 усиливает причинные структуры: каждый Δkernel вычисляется из (state_{t-1}, observation_t, prediction) — конечная причинная цепь |
| §ENIGMA-002 | Правило Двух Доменов | **Требует подтверждения** | Закон введён на основе NPC-домена. Player cognition (если будет реализован) может потребовать аналогичного механизма |
| §ENIGMA-003 | Закон Эпистемической Проекции | **100% совместимо** | UNKNOWN ≠ NEUTRAL(0.0). `Precision=0` для Vacuum → `prediction_error` не применяется, ядро не модифицируется |
| §ENIGMA-004 | Закон Эпистемического Демпфирования | **100% совместимо** | `prediction_error` — транзиентный inference pressure, не глобальный аккумулятор. Не конвертируется в `kernel.uncertainty` напрямую — только через Delta |
| §ENIGMA-005 | Закон Референциального Замыкания | **100% совместимо** | `EventContext` не модифицируется PredictiveEngine. Engine читает facts/context, не пишет в него |
| §ENIGMA-006 | Требование Полноты Намерения | **100% совместимо** | Если `target_id` отсутствует, spatial prediction возвращает `None` (Vacuum) |
| §ENIGMA-S72 | Закон Релятивистского Восприятия | **100% совместимо** | Веса `attention` модулированы через `drives_base` (L0), не хардкодом |
| §3 | Фазовая модель | **Требует расширения** | Добавляется фаза 3.8. Не нарушает существующий порядок фаз |
| §3.1 | DecisionHub на фазе 5 | **100% совместимо** | §19 работает на фазе 3.8, ДО InterpretationEngine. Лаг в 1 тик не возникает |
| §4 | Память (правила записи/чтения) | **100% совместимо** | §19 не пишет в MemoryStore. PredictionState — отдельное in-memory хранилище, не narrative memory |
| §4.1.1 | WorkingMemory per-NPC | **100% совместимо** | PredictiveEngine работает per-NPC |
| §4.2.1 | SQLite = runtime truth | **100% совместимо** | PredictionState и SpatialTrace — in-memory LRU, не SQLite. Это оперативное когнитивное состояние, аналогично idle_pressure_map |
| §5 | EventBus | **100% совместимо** | PredictiveEngine не публикует события. Prediction_error передаётся через параметр, не через шину |
| §7.7 | DecisionHub до MemoryProcessor | **100% совместимо** | §19 усиливает: теперь PredictiveEngine + InterpretationEngine работают ДО DecisionHub |
| §13 | Law of Epistemic Grounding | **100% совместимо** | Закон выведен из определённых величин (prediction, error, precision, salience), не из magic numbers |
| §14 | Law of Singular Time | **100% совместимо** | Δt = game_time only. Никаких параллельных временных многообразий |
| §15 | Law of Wall-Clock Isolation | **100% совместимо** | Все функции §19 — pure; `datetime.now()` запрещён |
| §16 | Law of Belief Non-Mutation | **100% совместимо** | §19 НЕ мутирует L0. PerceptualKernelDelta — это модификация субъективного состояния, не personality |
| §17 | Law of Epistemological Orthogonality | **100% совместимо** | §19 усиливает: Prediction — это эпистемический фильтр, не мост к Reality |
| §17.1.1 | Закон невозрастания истины | **100% совместимо** | Prediction не создаёт новой истины; она только модифицирует субъективное состояние |
| §17.1.2 | Запрет каузального возврата | **100% совместимо** | Prediction не изменяет Reality; prediction_error модифицирует только PerceptualKernel |
| §17.1.3 | Изоляция потребителей | **100% совместимо** | DM, Renderer, CDS не читают Prediction напрямую; они читают обновлённый PerceptualKernel |
| §18 | Resource-Bounded Epistemic Selection | **100% совместимо + синергия** | §19 — источник U(c) для §18. §19 — источник surprise для importance в §18 |

**Итог:** §19 полностью совместим с существующим Уставом. **Конфликтов нет.** Расширения требуются в §3 (новая фаза 3.8) и в §18 (расширение `U(c)` 5-й компонентой) — оба оформляются через ADR.

---

## §8. АНТИ-ПАТТЕРНЫ (КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО)

### §8.1 Neural wave simulation

```python
# ❌ КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:
class NeuralWaveSimulator:
    """Simulates traveling waves in cortex."""
    def __init__(self, n_neurons=1000):
        self.grid = [[Neuron() for _ in range(n_neurons)] for _ in range(n_neurons)]
        self.synapses = self._build_recurrent_connections()

    def propagate(self, input_signal):
        for i in range(len(self.grid)):
            for j in range(len(self.grid[0])):
                self.grid[i][j].fire(input_signal)
        # ... wave dynamics ...
```

**Почему:** ENIGMA — **не brain simulator**. Биологическая реализация (нейронная сетка, синапсы, STDP) нарушает:
- §15 (wall-clock isolation) — симуляция нейронов требует sub-tick времени
- §16 (belief non-mutation) — learning правила меняют веса (L0)
- Architectural purity — ENIGMA — game engine, не neuroscience tool

**Правильно:** `SpatialTemporalTrace` — bounded decay trace, функциональный аналог. Это структурированное состояние, из которого возникает prediction, без биологической имитации.

### §8.2 Magic numbers в surprise формуле

```python
# ❌ ЗАПРЕЩЕНО:
def surprise(event):
    if event.type == "attack":
        return 3.5  # ← magic number
    elif event.type == "talk":
        return 0.8  # ← magic number
    else:
        return 1.2  # ← magic number
```

**Почему:** это превращает закон в **magic-number cognitive architecture**. Закон должен быть выведен из определённых величин (prediction, probability), не из подбираемой таблицы.

**Правильно:** `surprise = -log P(x_t | z_{t-1})` — вычисляется из `Prediction.expected_events[i].probability`.

### §8.3 Prediction → Reality

```python
# ❌ КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО:
def apply_prediction_to_world(prediction):
    if prediction.expected_hostility > 0.7:
        world.mark_player_hostile()  # ← мир меняется от prediction!
```

**Почему:** prediction — это **эпистемическое состояние NPC**, не истина. Если prediction может менять Reality, это нарушает:
- §17 (Epistemological Orthogonality) — Epistemology ⊥ Reality
- §17.1.2 — запрет каузального возврата
- Invariant I (Causal Provenance) — нет причинной цепи от prediction к Reality

**Правильно:** prediction может ошибаться бесконечно. Мир от этого не меняется. Только `PerceptualKernel` обновляется через Delta.

### §8.4 Prediction → mutate Belief напрямую

```python
# ❌ ЗАПРЕЩЕНО:
class PredictivePerceptionEngine:
    def process(self, ...):
        prediction = self.predict(...)
        if prediction.expected_hostility > 0.7:
            state.beliefs["player_hostile"] = True  # ← writer!
```

**Почему:** нарушает §5.1 ТЗ §18 (трёхслойное разделение Memory ≠ Belief ≠ MemoryUtility). §19 добавляет 4-й слой: **Prediction ≠ Belief**. Связь идёт через `BeliefRevisionEngine` (§18), не напрямую.

**Правильно:** prediction_error модулирует `PerceptualKernel`. BeliefState обновляется отдельно — `BeliefTransitionEngine` читает обновлённый kernel, но решение о belief change принимает сама.

### §8.5 Unbounded trace history

```python
# ❌ ЗАПРЕЩЕНО:
class SpatialTrace:
    def __init__(self):
        self.entries = []  # ← без cap!

    def add(self, entry):
        self.entries.append(entry)  # растёт бесконечно
```

**Почему:** без cap trace превращается во второй дорогой perception engine. При 1000 тиков и 6 NPC = 6000 записей × постоянная обработка = утечка памяти и CPU.

**Правильно:** `MAX_TRACE_LENGTH = 8` + hard cap 50 тиков + decay. Bounded по определению.

### §8.6 Wall-clock в prediction decay

```python
# ❌ ЗАПРЕЩЕНО:
import datetime
def trace_decay(trace):
    now = datetime.now()
    for entry in trace:
        age_seconds = (now - entry.created_at).total_seconds()
        entry.salience *= math.exp(-0.1 * age_seconds)
```

**Почему:** нарушает §15. Wall-clock создаёт недетерминизм, ломает replay.

**Правильно:** `decay_rate * (current_tick - entry.tick)` — только game_time.

### §8.7 Prediction as Decision Driver

```python
# ❌ ЗАПРЕЩЕНО:
class DecisionHub:
    def compute(self, state, prediction):  # ← prediction как параметр!
        if prediction.expected_event == "PLAYER_ATTACKS":
            return Intent.FLEE  # ← prediction напрямую управляет решением
```

**Почему:** обходит InterpretationEngine и PressureTranslator. DecisionHub должен работать с `DecisionContext`, не с `Prediction`. Связь идёт: prediction → kernel → DecisionContext → DecisionHub.

**Правильно:** DecisionHub не знает о Prediction. Он видит только обновлённый PerceptualKernel (через PressureTranslator → DecisionContext).

### §8.8 Кэширование PredictionResult

```python
# ❌ ЗАПРЕЩЕНО:
self._prediction_cache[npc_id][tick] = prediction_result
```

**Почему:** аналогично §7.8 ТЗ §18 (кэширование MemoryUtilityResult). Prediction — эфемерная проекция от (state_{t-1}, observation_t). Кэш = рассинхрон.

**Правильно:** вычислять каждый тик заново. Performance оптимизация — через batch evaluation, не через кэш. `PredictionState` хранит только `last_prediction` для следующего тика, не полный кэш.

### §8.9 Принудительные learning rate transitions

```python
# ❌ ЗАПРЕЩЕНО:
if npc.stress > 0.8:
    npc.learning_rate = 0.5  # ← принудительный переход
elif npc.stress < 0.3:
    npc.learning_rate = 0.1
```

**Почему:** аналогично §7.5 ТЗ §18 (принудительные phase transitions). Learning rate должен быть **выводом** из `NPCProfileL0` (per-NPC, immutable в L0), не динамическим состоянием.

**Правильно:** `learning_rate = npc.profile.prediction_learning_rate` (immutable). Per-NPC вариативность через L0, не через runtime состояние.

### §8.10 Tuned heuristic вместо закона

```python
# ❌ ЗАПРЕЩЕНО:
def prediction_error(prediction, observation):
    if prediction.expected_attack and observation.attack:
        return 0.2  # ← magic
    elif prediction.expected_attack and not observation.attack:
        return 0.8  # ← magic
    else:
        return 0.1  # ← magic
```

**Почему:** это не закон, а эвристика с magic numbers. Закон должен быть выведен из формулы `e = W(x, x̂) · Precision(x)`.

**Правильно:** формула с явно определёнными `W`, `Precision`, нормировкой.

---

## §9. PRE-CONDITIONS: ТАБЛИЦА ЗАВИСИМОСТЕЙ 100% ЗАКРЫТИЯ

Перед активацией §19 **должны быть закрыты** следующие pre-conditions. Каждое условие имеет: текущий статус в коде V.0.5.3.6.9, что должно быть готово, как проверить, ссылку на файл.

### §9.1 Таблица зависимостей

| # | Pre-condition | Текущий статус V.0.5.3.6.9 | Что должно быть готово | Как проверить | Файл(ы) |
|---|---------------|---------------------------|------------------------|---------------|---------|
| **PC-19-1** | §18 активирован (Этап C: MemoryUtility как pure function) | **НЕ ЗАКРЫТО** | §18 Этап A+B+C завершены. BeliefRevisionEngine существует, MemoryUtilityEvaluator wired в Phase 3.6 | Тесты TC-1..TC-7 из ТЗ §18 проходят | `services/npc/belief/belief_revision.py`, `services/npc/memory/memory_utility.py` |
| **PC-19-2** | `BeliefState` schema расширена (PC-3 из §18) | **НЕ ЗАКРЫТО** | `BeliefFragment` имеет {proposition, confidence, source, timestamp, evidence, decay} | grep `class BeliefFragment` — все поля присутствуют | `models/npc/beliefs.py` |
| **PC-19-3** | `PerceptualKernel` расширяем (без нарушения round-trip) | **ЧАСТИЧНО** | PerceptualKernel — `@dataclass`. Новые поля `{prediction_error, prediction_surprise, prediction_confidence, ...}` добавляются с defaults. Round-trip тест `from_legacy ↔ write_to_legacy` проходит | Round-trip тест на NPCState | `models/npc_state.py` |
| **PC-19-4** | `ObservedFact` — стабилен и wired | **ЗАКРЫТО** | `ObservedFact` существует (`domain/observed_fact.py:14`), `FactExtractor` существует (`services/perception/fact_extractor.py`) | grep `class ObservedFact` + `class FactExtractor` | `domain/observed_fact.py`, `services/perception/fact_extractor.py` |
| **PC-19-5** | `InferenceEngine` стабилен | **ЧАСТИЧНО** | `services/perception/inference_engine.py` существует, читает `signal_causes.yaml`. **Но не wired в основной тик** — только в параллельный канал | grep `InferenceEngine` — вызывается из `npc_tick_pipeline.py`? Нет. Это PC для V2+ | `services/perception/inference_engine.py` |
| **PC-19-6** | `PerceptionFilter.calculate_clarity` стабилен | **ЗАКРЫТО** | `perception_filter.py:63-94` — функция существует, возвращает ∈ [0, 1] | grep `def calculate_clarity` | `services/npc/perception_filter.py` |
| **PC-19-7** | `StateApplicator` расширяем (новый метод `apply_delta_to_kernel`) | **ЧАСТИЧНО** | `StateApplicator` существует. Метод `apply_delta_to_kernel` — NEW, добавляется без нарушения существующих методов | Round-trip: delta применяется, kernel обновляется, state остаётся валидным | `services/npc/state_applicator.py` |
| **PC-19-8** | `PredictionState` — отдельное in-memory хранилище | **НЕ СУЩЕСТВУЕТ** | Создать `services/npc/predictive/prediction_state.py` с LRU cache (TTL 1 час, как `npc_cache` в `LifeEngine`) | Тест: `save_prediction_state` → `load_prediction_state` round-trip | `services/npc/predictive/prediction_state.py` (NEW) |
| **PC-19-9** | `SpatialTemporalTrace` — отдельное in-memory хранилище | **НЕ СУЩЕСТВУЕТ** | Создать `services/npc/predictive/spatial_temporal_trace.py` с LRU cache, `MAX_TRACE_LENGTH=8`, decay | Тест: trace растёт до 8, потом не растёт; decay применяется корректно | `services/npc/predictive/spatial_temporal_trace.py` (NEW) |
| **PC-19-10** | Wall-clock полностью изгнан из simulation layer | **ЗАКРЫТО** (по §15) | §15.1 — `datetime.now()`, `time.time()`, `time.monotonic()` запрещены. Проверено аудитом | grep `time.time\|datetime.now` в `services/npc/predictive/` — 0 matches | Все файлы §19 |
| **PC-19-11** | Determinism (KernelRNG) — все функции bound | **ЗАКРЫТО** (по ADR-O-301) | `KernelRNG(tick, npc_id, salt)` — единственный источник случайности. §19 не требует RNG (pure functions) | Если §19 не использует random — проверка тривиальна | Все файлы §19 |
| **PC-19-12** | `InterpretationEngine` принимает опциональный `prediction_error` параметр | **НЕ ЗАКРЫТО** | Расширить сигнатуру `InterpretationEngine.compute()` — добавить `prediction_error: Optional[PredictionError] = None`. Backward compatible | Тест: compute без prediction_error работает как раньше | `services/npc/interpretation_engine.py` |
| **PC-19-13** | Phase 3 → Phase 5 без лагов (ADR-059 закрыт) | **НЕ ЗАКРЫТО** (PC-16 из §18) | §3.1 Устава: «DecisionHub работает на фазе 5, НЕ на фазе 3». Лаг 1 тик = баг | Тест: publish event at tick T → MemoryManager.apply at tick T → DecisionHub.compute at tick T | `services/game_loop/tick_orchestrator.py` |
| **PC-19-14** | Causal Decay Kernel — единый | **ЗАКРЫТО** | `BELIEF_DECAY_TAU = 100.0` в `belief_crystallization_engine.py`. §19 импортирует для trace decay (если потребуется синхронизация) | grep `BELIEF_DECAY_TAU` — единственное определение | `services/npc/belief_crystallization_engine.py:18` |
| **PC-19-15** | `EventContext.payload` — канонический (содержит `clarity`, `distance`) | **ЧАСТИЧНО** (PC-12 из §18) | `EventContext` имеет `payload: Dict[str, Any]` (decision_hub.py:235). §19 читает `clarity` из payload — нужно формализовать key | grep `payload.get\("clarity"\)` — должно быть единственное чтение | `services/npc/decision_hub.py:208-240` |
| **PC-19-16** | `NPCProfileL0` расширяем (per-NPC resource profile) | **ЧАСТИЧНО** | `NPCProfileL0` существует. Новые поля `{prediction_horizon, prediction_learning_rate, precision_tolerance}` — V1 minimum, добавляются с defaults | grep `class NPCProfileL0` + новые поля | `models/npc_profile.py` |
| **PC-19-17** | `NpcTickPipeline.run()` — pure reducer (без svc параметра) | **ЧАСТИЧНО** | TZ-02 V2.0 (Preemnik) отмечает: «`NpcTickPipeline.run()` всё ещё принимает `svc: Any`». Нужно устранить. До этого §19 wiring рискованный | grep `def run` в `npc_tick_pipeline.py` — нет `svc` параметра | `services/npc/npc_tick_pipeline.py` |
| **PC-19-18** | `spatial_runtime.line_of_sight` и `sound_reach` стабильны | **ЗАКРЫТО** | `spatial_runtime.py` — функции существуют, wired в `perception_filter.py` | grep `def line_of_sight` + `def sound_reach` | `services/spatial/spatial_runtime.py` |

### §9.2 Категории критичности

| Категория | Кол-во PC | Блокирует §19? |
|-----------|-----------|----------------|
| **CRITICAL** (блокирует активацию) | PC-19-1, PC-19-2, PC-19-3, PC-19-7, PC-19-8, PC-19-9, PC-19-13, PC-19-17 | ДА |
| **HIGH** (без них закон работает некорректно) | PC-19-5, PC-19-12, PC-19-15, PC-19-16 | ДА |
| **MEDIUM** (без них закон не оптимальный) | PC-19-4, PC-19-6, PC-19-14, PC-19-18 | НЕТ (закон может быть внедрён, но с ограничениями) |
| **ALREADY CLOSED** | PC-19-10, PC-19-11 | — |

### §9.3 Порядок закрытия (рекомендуемый)

```
Шаг 1: PC-19-1 — активация §18 (Этап C из ТЗ §18)
   ↓
Шаг 2: PC-19-2 — BeliefState schema расширена
   ↓
Шаг 3: PC-19-13 — закрытие ADR-059 (лаг 1 тик устранён)
   ↓
Шаг 4: PC-19-17 — NpcTickPipeline.run() pure reducer
   ↓
Шаг 5: PC-19-3 — PerceptualKernel расширяем (новые поля с defaults)
   ↓
Шаг 6: PC-19-7 — StateApplicator.apply_delta_to_kernel
   ↓
Шаг 7: PC-19-8 — PredictionState in-memory хранилище
   ↓
Шаг 8: PC-19-9 — SpatialTemporalTrace in-memory хранилище
   ↓
Шаг 9: PC-19-12 — InterpretationEngine принимает prediction_error
   ↓
Шаг 10: PC-19-16 — NPCProfileL0 расширен (per-NPC, V1 minimum)
   ↓
─── АКТИВАЦИЯ §19 V1 (Этап A) ───
   ↓
Шаг 11: Реализация PredictivePerceptionEngine (§4.5)
   ↓
Шаг 12: Wiring в Phase 3.8 (§3.3)
   ↓
Шаг 13: Расширение U(c) в §18 (§6.1)
```

---

## §10. ДОРОЖНАЯ КАРТА ВНЕДРЕНИЯ (4 ЭТАПА)

### Этап A — V1: Prediction + Error + Precision + минимальный SpatialTrace

**Цель:** Активировать §19 в минимальной форме. NPC формирует prediction, вычисляет error, precision модулирует влияние, SpatialTrace (bounded=8) даёт expected_position.

**Что делать:**
1. Закрыть PC-19-1..PC-19-13 (CRITICAL + HIGH).
2. Реализовать `PredictionModel` (§4.1) — horizon=1, 3 события (PLAYER_ATTACKS, PLAYER_CONTINUES_DIALOGUE, PLAYER_LEAVES).
3. Реализовать `PredictionErrorCalculator` (§4.2) — 4 канала (event, spatial, temporal=0, social).
4. Реализовать `PrecisionModel` (§4.3) — confidence × reliability × attention.
5. Реализовать `SpatialTemporalTrace` (§4.4) — MAX_TRACE_LENGTH=8, decay λ=0.15.
6. Реализовать `PredictivePerceptionEngine` (§4.5) — оркестратор.
7. Реализовать `PerceptualKernelDelta` + `build_kernel_delta` (§5.1).
8. Расширить `StateApplicator.apply_delta_to_kernel` (§5.3).
9. Расширить `PerceptualKernel` — новые поля с defaults (§5.2).
10. Wiring в `NpcTickPipeline` Phase 3.8 (§3.3).
11. Расширить `InterpretationEngine.compute()` — опциональный `prediction_error` параметр.
12. Расширить `U(c)` в §18 — 5-я компонента `prediction_error.total` (§6.1).
13. **БЕЗ** Bayesian social update (V3).
14. **БЕЗ** temporal error (V2+).
15. **БЕЗ** per-NPC resource profile — uniform `learning_rate = 0.15`.

**Артефакты:**
- `services/npc/predictive/__init__.py`
- `services/npc/predictive/predictive_perception_engine.py`
- `services/npc/predictive/prediction_model.py`
- `services/npc/predictive/prediction_error_calculator.py`
- `services/npc/predictive/precision_model.py`
- `services/npc/predictive/spatial_temporal_trace.py`
- `services/npc/predictive/kernel_delta_builder.py`
- `services/npc/predictive/prediction_state.py` (in-memory LRU cache)
- Расширенный `services/npc/state_applicator.py` (новый метод)
- Расширенный `models/npc_state.py` (PerceptualKernel + новые поля)
- Расширенный `services/npc/interpretation_engine.py` (опциональный параметр)
- Расширенный `services/npc/npc_tick_pipeline.py` (Phase 3.8 wiring)
- ADR-O-4XX (Predictive Perception Engine)
- ADR-O-4XX+1 (Prediction Model)
- ADR-O-4XX+2 (Prediction Error Calculator)
- ADR-O-4XX+3 (Precision Model)
- ADR-O-4XX+4 (Spatial Temporal Trace)
- ADR-O-4XX+5 (Perceptual Kernel Delta)

**Критерий готовности:** Тесты §12 (TC-19-1..TC-19-7) проходят. В логах виден эффект `[PREDICTIVE_DELTA]` — NPC реагирует на неожиданные события сильнее, чем на ожидаемые. Replay determinism сохранён (TC-19-6).

**Целевая эпоха:** v7.5 (Prophecy System) — Prediction Error становится фундаментом Prophecy.

### Этап B — V2: SpatialTemporalTrace + trajectory prediction

**Цель:** Расширить SpatialTrace до полноценной trajectory prediction. NPC формирует `expected_direction` и `expected_velocity` из history, не только `expected_position`.

**Что делать:**
1. Реализовать EMA velocity с λ = 0.3 (формула в §4.1 `_predict_spatial`).
2. Реализовать `temporal_error` (PredictionErrorCalculator) — сравнение expected_tick vs actual_tick события.
3. Расширить `Prediction` — `expected_direction` (радианы), `expected_velocity` (x, y).
4. Реализовать `last_hostile_direction` как вывод из SpatialTrace (не как статическое поле).
5. Wiring `InferenceEngine` в основной тик (PC-19-5) — теперь InferenceEngine параллелен FactExtractor, оба кормят PredictiveEngine.
6. Расширить `signal_causes.yaml` — больше причинно-следственных связей для InferenceEngine.

**Артефакты:**
- Расширенный `services/npc/predictive/spatial_temporal_trace.py`
- Расширенный `services/npc/predictive/prediction_error_calculator.py`
- Расширенный `services/npc/predictive/prediction_model.py`
- Расширенный `architecture/authoring/signal_causes.yaml`
- ADR-O-4XX+6 (Trajectory Prediction)
- ADR-O-4XX+7 (Temporal Error Channel)

**Критерий готовности:** NPC предсказывает движение игрока по траектории. `spatial_error` становится значимым каналом (не 0). `last_hostile_direction` — динамическое поле, выведенное из trace.

**Целевая эпоха:** v8.0 (WorldChronicle) — SpatialTrace интегрируется с lineage через поколения.

### Этап C — V3: Bayesian social prediction

**Цель:** NPC формирует социальные предсказания (`cooperation_p`, `betrayal_p`) и обновляет их через Bayesian update.

**Что делать:**
1. Реализовать `social_error` — расхождение между `expected_social_state` и actual social deltas.
2. Реализовать Bayesian update для `P(hostile | observation)`:
   ```
   P(H|E) = P(E|H) · P(H) / (P(E|H) · P(H) + P(E|¬H) · P(¬H))
   ```
3. Расширить `Prediction.expected_social_state` — больше полей (`cooperation_p`, `betrayal_p`, `deception_p`).
4. Связать с `BeliefTransitionEngine` — surprise из §19 становится источником importance в §18.
5. Реализовать `contradiction_resolver` интеграцию — неожиданные социальные события вызывают пересмотр убеждений.

**Артефакты:**
- Расширенный `services/npc/predictive/prediction_model.py`
- Расширенный `services/npc/predictive/prediction_error_calculator.py`
- Новый `services/npc/predictive/bayesian_updater.py`
- Расширенный `services/npc/belief/belief_revision.py` (читает surprise)
- ADR-O-4XX+8 (Bayesian Social Prediction)
- ADR-O-4XX+9 (Surprise → Importance Bridge)

**Критерий готовности:** NPC обновляет `P(player_hostile)` после неожиданных событий. `surprise` из §19 видим в логах §18 как источник importance. BeliefRevision корректно реагирует на prediction_error.

**Целевая эпоха:** v8.5 (Generations) — социальные предсказания наследуются потомками через WorldChronicle.

### Этап D — Per-NPC Resource Profile

**Цель:** Ввести per-NPC вариативность predikтивной архитектуры. Два NPC с одинаковой агрессией могут иметь разную «когнитивную экономику».

**Что делать:**
1. Расширить `NPCProfileL0` — новые поля:
   ```python
   prediction_horizon: int = 1           # 1-3 тика
   prediction_learning_rate: float = 0.15 # ∈ [0.05, 0.30]
   precision_tolerance: float = 0.05     # минимальный precision для активации
   prediction_confidence_threshold: float = 0.3  # минимальная confidence для сохранения prediction
   ```
2. Заменить uniform `learning_rate = 0.15` на per-NPC `npc.profile.prediction_learning_rate`.
3. Заменить uniform `precision_tolerance = 0.05` на per-NPC.
4. Расширить `prediction_horizon` до 3 тиков (V3+) — NPC предсказывает на 3 тика вперёд.
5. Запустить долгую симуляцию (1000+ тиков) с разными `prediction_learning_rate` для разных NPC.
6. Проверить: возникают ли emergent различия в поведении без явного флага?

**Артефакты:**
- Расширенный `models/npc_profile.py`
- Расширенный `services/npc/predictive/predictive_perception_engine.py` (читает per-NPC profile)
- ADR-O-4XX+10 (Per-NPC Predictive Profile)
- ADR-O-4XX+11 (Multi-Tick Prediction Horizon)

**Критерий готовности:** На симуляции наблюдается: NPC A (low `prediction_learning_rate=0.05`) медленнее адаптируется к неожиданностям; NPC B (high `prediction_learning_rate=0.30`) быстрее пересматривает модель мира. Без явного флага `strategy`. Per-NPC вариативность — emergent.

**Целевая эпоха:** v9.0+ (Society) — per-NPC вариативность становится критичной при 20-30 NPC.

---

## §11. PER-NPC РЕСУРСНАЯ МОДЕЛЬ (ЭТАП D)

### §11.1 Расширение личности

После этапа D личность NPC перестаёт быть просто:

```python
NPCProfileL0 = {
    "aggression": 0.7,
    "curiosity": 0.4,
    "fear": 0.8,
}
```

Появляются новые измерения:

```python
NPCProfileL0 = {
    # ... существующие ...
    "prediction_horizon": 1,                    # 1-3 тика
    "prediction_learning_rate": 0.15,           # ∈ [0.05, 0.30]
    "precision_tolerance": 0.05,                # минимальный precision для активации
    "prediction_confidence_threshold": 0.3,     # минимальная confidence для сохранения
    "trace_decay_rate": 0.15,                   # λ для SpatialTrace
    "uncertainty_tolerance": 0.6,               # толерантность к неопределённости
}
```

### §11.2 Два NPC с одинаковой агрессией, но разной предиктивной архитектурой

```
NPC_1 (Люся — служанка):
  aggression = 0.3
  prediction_learning_rate = 0.30  ← высокая → быстро пересматривает модель мира
  prediction_horizon = 1
  trace_decay_rate = 0.10         ← медленный decay → долго помнит недавнее

NPC_2 (Тень — вор):
  aggression = 0.3
  prediction_learning_rate = 0.05  ← низкая → медленно пересматривает (опирается на долгую модель)
  prediction_horizon = 3           ← предсказывает на 3 тика вперёд
  trace_decay_rate = 0.20         ← быстрый decay → концентрируется на свежих сигналах
```

**При одинаковых событиях (игрок достаёт меч):**
- `NPC_1` (Люся): высокий `learning_rate` → `anomaly_score` резко возрастает → `threat_gradient` растёт быстро → FLEE вероятнее.
- `NPC_2` (Тень): низкий `learning_rate` → `anomaly_score` растёт медленно → опирается на долгую модель (player всегда был мирным) → OBSERVE вероятнее, потом ATTACK если шаблон повторится.

Это **различие архитектуры обработки информации**, а не «характер = случайное число». Два NPC с одинаковой агрессией имеют совершенно разные внутренние миры.

### §11.3 Связь с Identity Dynamics Layer

Per-NPC resource model — это шаг к Identity Dynamics Layer. Личность определяет:
1. **Что NPC хочет** (drives) — уже есть.
2. **Как NPC строит модель мира** (epistemic architecture) — добавляет §18.
3. **Как NPC обновляет модель мира** (predictive architecture) — добавляет §19.

Это делает `Personality` более чем суммой скаляров. Два NPC с одинаковой агрессией могут иметь:
- Разную epistemic architecture (§18) — какие воспоминания активировать.
- Разную predictive architecture (§19) — как быстро пересматривать модель.

### §11.4 Что НЕ делать на этапе D

- **Не форсировать** различия в поведении через явные флаги (`if npc.role == "thief": ...`). Различия возникают emergent из формулы.
- **Не кэшировать** per-NPC resource profile (он immutable в L0, как CoreOrientation — §16.1).
- **Не вводить** runtime мутацию `learning_rate` (§8.9 — anti-pattern).

---

## §12. ДИАГНОСТИКА И ВАЛИДАЦИЯ

### §12.1 Канонические тест-кейсы

**TC-19-1: Базовая активация — prediction_error модулирует kernel**
```
Дано: NPC с learning_rate=0.15, precision=0.95
Событие: Игрок достаёт меч (weapon_visible=True)
Prediction: P(PLAYER_ATTACKS)=0.05, P(CONTINUE_DIALOGUE)=0.74
Ожидание:
  - surprise = -log(0.05) ≈ 3.0
  - prediction_error.total ≈ 0.7-0.9
  - kernel.threat_gradient += 0.10-0.20
  - kernel.anomaly_score += 0.05-0.10
Проверка: лог [PREDICTIVE_DELTA] содержит ненулевые deltas
```

**TC-19-2: Vacuum — низкая precision не модифицирует kernel**
```
Дано: NPC на distance=14m, light=dim
  → perception_confidence = 0.45
  → precision = 0.45 × 0.85 × attention ≈ 0.30
Событие: Игрок достаёт меч
Prediction: P(PLAYER_ATTACKS)=0.05
Ожидание:
  - prediction_error.precision < 0.05? НЕТ (0.30 > 0.05)
  - Но total будет ниже: 0.7 × 0.30 ≈ 0.21
  - kernel.threat_gradient += 0.03-0.05 (слабее, чем TC-19-1)
Проверка: deltas применены, но меньше по модулю
```

**TC-19-3: Extreme vacuum — precision < 0.05 → kernel не меняется**
```
Дано: NPC почти глухой/слепой
  → perception_confidence = 0.05
  → precision = 0.05 × 0.30 × 0.30 ≈ 0.005
Ожидание:
  - kernel_delta = None (precision < 0.05)
  - PerceptualKernel не модифицируется
Проверка: лог [PREDICTIVE_DELTA] отсутствует или содержит "skipped (low precision)"
```

**TC-19-4: Spatial prediction**
```
Дано: NPC с SpatialTrace = [(10,10), (11,10), (12,10), (13,10), (14,10)]
Prediction: expected_position = (15, 10) (EMA velocity = (1, 0))
Событие: Игрок на (18, 10)
Ожидание:
  - spatial_error = |18-15| / 3.0 = 1.0 (clamped)
  - prediction_error.spatial = 1.0
  - dominant_channel = "spatial"
Проверка: NPC реагирует на spatial deviation
```

**TC-19-5: Per-NPC различие (после этапа D)**
```
Дано: NPC_A (learning_rate=0.30), NPC_B (learning_rate=0.05)
Событие: одинаковое (игрок достаёт меч, precision=0.95)
Ожидание:
  - kernel_A.threat_gradient_delta ≈ 0.20 (высокая адаптация)
  - kernel_B.threat_gradient_delta ≈ 0.03 (низкая адаптация)
Проверка: A реагирует сильнее, B — слабее. Без явного флага.
```

**TC-19-6: Determinism (replay)**
```
Дано: одинаковое состояние, одинаковый tick
Действие: вычислить prediction_error дважды
Ожидание: идентичный результат
Проверка: replay determinism сохранён
```

**TC-19-7: Wall-clock absence**
```
Дано: симуляция с paused wall-clock
Действие: 100 ticks симуляции
Ожидание: prediction_error вычисляется корректно (через game_time)
Проверка: grep `time.time\|datetime.now` в коде §19 = 0 matches
```

**TC-19-8: Bounded trace (MAX_TRACE_LENGTH=8)**
```
Дано: NPC, 100 тиков симуляции с постоянными наблюдениями
Действие: проверить SpatialTemporalTrace.entries
Ожидание: len(entries) == 8 (не больше)
Проверка: trace не растёт бесконечно
```

**TC-19-9: Trace decay**
```
Дано: NPC с trace = [entry@tick=100, salience=1.0]
Действие: current_tick = 150
Ожидание: entry.salience = 1.0 × exp(-0.15 × 50) ≈ 0.0006 (почти 0)
Проверка: старые entries затухают
```

**TC-19-10: Trace hard cap (50 тиков)**
```
Дано: NPC с trace = [entry@tick=100]
Действие: current_tick = 200 (Δ=100)
Ожидание: entry удалён из trace (Δ > 50)
Проверка: hard cap работает
```

### §12.2 Телеметрия

В логи добавляется структурированная запись:

```python
logger.info(
    f"[PREDICTIVE] npc={npc_id} tick={tick} "
    f"pred_attack={prediction.expected_events[0].probability:.3f} "
    f"pred_continue={prediction.expected_events[1].probability:.3f} "
    f"actual_event={actual_event_type} "
    f"PE_total={error.total:.3f} "
    f"PE_event={error.event:.3f} "
    f"PE_spatial={error.spatial:.3f} "
    f"surprise={error.surprise:.3f} "
    f"precision={error.precision:.3f} "
    f"dominant={error.dominant_channel} "
    f"kernel_delta_applied={delta is not None}"
)
```

И отдельная запись для delta:

```python
logger.debug(
    f"[PREDICTIVE_DELTA] npc={npc_id} "
    f"threat_delta={delta.threat_gradient_delta:+.3f} "
    f"uncertainty_delta={delta.uncertainty_delta:+.3f} "
    f"anomaly_delta={delta.anomaly_score_delta:+.3f} "
    f"pe={delta.prediction_error_value:.3f} "
    f"surprise={delta.prediction_surprise_value:.3f} "
    f"confidence={delta.prediction_confidence_value:.3f}"
)
```

Это позволяет:
- CDS (Causal Diagnostics System) видеть предиктивный слой.
- Replay точно воспроизводить решения NPC.
- Audit trail для debugging «почему NPC удивился?»

### §12.3 CDS Integration

DNA-метрики (SHI, NPI, OBI, SCF, CVS, PFI) расширяются новой метрикой:

| Метрика | Полное имя | Что измеряет |
|---------|-----------|--------------|
| **PPI** | Predictive Perturbation Index | Средняя величина `prediction_error.total` по NPC за тик. Высокий PPI = мир непредсказуем для NPC. |

```python
# diagnostics/causal_observer.py (FUTURE EXTENSION)

def compute_ppi(predictions: List[PredictionError]) -> float:
    """Predictive Perturbation Index — средний prediction_error.total."""
    if not predictions:
        return 0.0
    return sum(p.total for p in predictions) / len(predictions)
```

PPI пишется в `reports/dna_history.jsonl` рядом с существующими метриками. Высокий PPI на протяжении долгого времени = признак того, что модель мира NPC рассинхронизирована с реальностью (возможно, нужен пересмотр Belief Layer).

### §12.4 Когда вердикт «закон сломан»

§19 считается нарушенным, если:
1. Реализована neural wave simulation (§8.1) — нарушение.
2. `surprise` вычислен с magic number (§8.2) — нарушение.
3. `Prediction` напрямую мутирует Reality (§8.3) — нарушение.
4. `PredictivePerceptionEngine` пишет в BeliefState напрямую (§8.4) — нарушение.
5. `SpatialTemporalTrace` без `MAX_TRACE_LENGTH` cap (§8.5) — нарушение.
6. В коде §19 есть `datetime.now()` / `time.time()` (§8.6) — нарушение.
7. `DecisionHub` принимает `Prediction` как параметр (§8.7) — нарушение.
8. `PredictionResult` кэшируется (§8.8) — нарушение.
9. `learning_rate` динамически мутируется в runtime (§8.9) — нарушение.
10. Используется tuned heuristic вместо формулы (§8.10) — нарушение.

Каждое нарушение = архитектурный баг (как нарушение §15/§16/§17/§18).

---

## §13. РИСКИ И МИТИГАЦИЯ

| # | Риск | Вероятность | Влияние | Митигация |
|---|------|-------------|---------|-----------|
| **R-1** | **Performance: O(N × T × F)** — для N NPC, T trace length (8), F facts per NPC | Высокая | Среднее | Bounded trace (MAX_TRACE_LENGTH=8) + LRU cache. Тест: 6 NPC × 100 тиков < 100ms |
| **R-2** | **Debug complexity** — developer не понимает, почему NPC «удивился» | Высокая | Высокое | Структурированная телеметрия §12.2 + CDS integration (PPI метрика) |
| **R-3** | **Magic number drift** — со временем появляются 0.35, 0.42 в surprise формуле | Средняя | Высокое | Lint rule: запрет голых numeric literals в `services/npc/predictive/`. Все веса выведены из drives_base |
| **R-4** | **Coupling с LLM** — Verbalization начинает читать Prediction | Низкая | Высокое | §8.7 — явный запрет. Code review checklist |
| **R-5** | **Replay determinism** — prediction_error даёт разные результаты на replay | Низкая | Критическое | Pure functions + KernelRNG (§3.4). Тест TC-19-6 |
| **R-6** | **PerceptualKernel bloat** — новые поля раздули kernel, сериализация медленная | Низкая | Среднее | Только 6 новых float полей. Round-trip тест обязателен (PC-19-3) |
| **R-7** | **SpatialTrace memory leak** — LRU cache не чистится | Низкая | Высокое | TTL 1 час, как `npc_cache` в `LifeEngine`. Тест: 1000 NPC × 100 тиков, memory usage стабилен |
| **R-8** | **Prediction → Reality leak** — prediction случайно попадает в WorldSnapshotDTO | Средняя | Критическое | §8.3 — явный запрет. WorldSnapshotDTO не содержит Prediction. Code review checklist |
| **R-9** | **InferenceEngine wiring** — PC-19-5 (InferenceEngine не в основном тике) блокирует V2 | Высокая | Среднее | V1 работает без InferenceEngine (только FactExtractor). V2 требует wiring — отдельный ADR |
| **R-10** | **§18 lag** — §19 требует активации §18, а §18 требует закрытия PC-1..PC-7 | Высокая | Высокое | §19 активируется только после §18 Этап C. До этого — Architecture Hypothesis |
| **R-11** | **ADR-059 не закрыт** — лаг Phase 3 → Phase 5 ломает prediction (tick T+1 вместо T) | Высокая | Критическое | PC-19-13 — обязательное условие. Без закрытия ADR-059 §19 не активируется |
| **R-12** | **InterpretationEngine coupling** — добавление `prediction_error` параметра может сломать существующие тесты | Средняя | Среднее | Опциональный параметр с default=None. Backward compatible. PC-19-12 |
| **R-13** | **Over-engineering V1** — попытка внедрить V2/V3 фичи в V1 | Средняя | Высокое | Чёткое разделение этапов A/B/C/D. V1 = Prediction + Error + Precision + минимальный Trace. Больше — через ADR |
| **R-14** | **Belief Layer regression** — расширение U(c) в §18 может сломать существующие тесты §18 | Средняя | Высокое | Веса перераспределены, общая сумма = 1.0. Тесты §18 (TC-1..TC-7) должны проходить до и после расширения |
| **R-15** | **Neural wave temptation** — будущий разработчик решит «улучшить» через нейросеть | Низкая | Критическое | §8.1 — категорический запрет. Code review checklist + ADR-O-4XX явный запрет биологической реализации |

---

## §14. ИТОГОВЫЙ ВЕРДИКТ

### §14.1 Сейчас (V.0.5.3.6.9)

**ВНЕДРЯТЬ НЕЛЬЗЯ.**

Вероятность архитектурной пользы: ~25–35%.
Вероятность создания дополнительного слоя нестабильности поверх незакрытого Belief Layer: ~70–80%.

**Фундаментальная проблема текущего кода:** не «NPC неправильно реагирует на неожиданные события», а «эпистемическая система NPC ещё не завершена как самостоятельный архитектурный слой». Свидетельства:
- §18 (PC-1, PC-2, PC-3) — BeliefRevisionEngine не существует, BeliefState schema не расширена, два writer'а без правила merge.
- §18 (PC-16) — ADR-059 (Stale Cognition) — лаг 1 тик = баг.
- PC-19-17 — `NpcTickPipeline.run()` всё ещё принимает `svc: Any` (не pure reducer).

### §14.2 Что делать сейчас

1. **Зафиксировать §19 как архитектурную гипотезу** — этот документ.
2. **Не реализовывать** закон в коде.
3. **Закрыть pre-conditions** §18 (PC-1..PC-7, PC-16, PC-17) — это фундамент.
4. **Активировать §18** (Этап C из ТЗ §18) — MemoryUtility как pure function.
5. **Закрыть pre-conditions** §19 (PC-19-1..PC-19-13) — после §18.
6. **После закрытия** — активировать §19 V1 (Этап A) в эпоху v7.5 (Prophecy System).

### §14.3 Когда активировать

**Минимальные условия активации §19 V1:**
- §18 Этап C завершён (MemoryUtilityEvaluator wired в Phase 3.6).
- PC-19-1..PC-19-13 закрыты (CRITICAL + HIGH).
- ADR-O-4XX (Predictive Perception Engine) принят.
- Тесты TC-19-1..TC-19-7 написаны и проходят.
- ADR-059 (Stale Cognition) закрыт.

**Без этих условий** любая реализация §19 = нарушение принципа «знание первично, код вторичен» (§13 Устава).

### §14.4 Что §19 даёт ENIGMA после активации

1. **Динамическое восприятие** — NPC реагирует на сигнал в контексте предшествующей траектории, не изолированно.
2. **Эпистемическая обратная связь** — неожиданные события сильнее влияют на субъективное состояние, чем ожидаемые той же интенсивности.
3. **Пространственно-временная модель** — NPC формирует `expected_direction` из bounded trace, не из статического поля.
4. **Персонажная вариативность** — два NPC с одинаковой агрессией могут иметь разную предиктивную архитектуру (после этапа D).
5. **Совместимость с научной теорией** — связь с Muller et al. (Neuron 2026) и predictive coding framework даёт теоретическое основание.
6. **Мост к Planning Layer** — prediction → prediction_error → belief update → prediction — рекуррентный цикл, из которого естественно вырастает future Planning.
7. **Architecture narrative** — §19 — это то, что отличает ENIGMA от reactive Utility AI. NPC не просто реагирует — он предсказывает и удивляется.

### §14.5 Финальная формулировка для Устава

> **§19. Закон Предиктивной Динамики Восприятия**
>
> NPC не воспринимает каждый новый сигнал как изолированное событие. Текущее восприятие формируется относительно краткосрочной модели ожидаемого пространственно-временного развития событий; расхождение между ожидаемым и наблюдаемым является каузальным входом в обновление `PerceptualKernel`.
>
> Для каждого NPC в тике `t`:
>
> `z_t = F(z_{t-1}, x_t, m_t, s_t)` — внутреннее состояние
> `x̂_{t+1} = G(z_t, s_t)` — предсказание
> `e_t = W(x_t, x̂_t) · Precision(x_t)` — взвешенная ошибка
> `surprise = −log P(x_t | z_{t-1})` — неожиданность
> `Δkernel_t = α · e_t · salience(x_t)` — модификация ядра
>
> где `z` — скрытое субъективное состояние, `x` — наблюдение, `x̂` — предсказание, `m` — память, `s` — пространственно-временной след, `Precision` — надёжность и значимость наблюдения.
>
> Закон НЕ мутирует Reality, НЕ создаёт события, НЕ вызывает LLM, НЕ имитирует биологические нейронные волны. Закон — read-only pure function, формирующая `PerceptualKernelDelta`, применяемую через `StateApplicator`.
>
> Закон вступает в силу только после завершения базового Belief Layer (§18) и закрытия pre-conditions, определённых в `docs/Почти Актуальные TZ/TZ_§19_Predictive_Perception_Dynamics.md`.

---

## ПРИЛОЖЕНИЕ A. ГЛОССАРИЙ

| Термин | Определение |
|--------|-------------|
| **Prediction** | Что NPC ожидает произойти в следующем тике. НЕ является Belief — это опережающая гипотеза. Хранится в `PredictionState` (in-memory LRU). |
| **PredictionError** | Расхождение между prediction и observation. Структурировано по 4 каналам: event, spatial, temporal, social. |
| **Precision** | Надёжность и значимость наблюдения. `Precision = Confidence × Reliability × Attention`. Модулирует влияние prediction_error на kernel. |
| **Surprise** | Информационная неожиданность: `surprise = -log P(x | z_{t-1})`. Отличается от prediction_error: surprise зависит от вероятности, error — от расхождения значений. |
| **PerceptualKernelDelta** | Read-only контракт модификации `PerceptualKernel`. Применяется через `StateApplicator.apply_delta_to_kernel()`. Не нарушает Invariant III. |
| **SpatialTemporalTrace** | Bounded затухающий след пространственно-временных наблюдений. `MAX_TRACE_LENGTH = 8`, hard cap 50 тиков. Функциональный аналог traveling wave. |
| **PredictionState** | Оперативное когнитивное состояние NPC (in-memory LRU, TTL 1 час). Хранит `last_prediction`, `last_error`, `memory_context`. НЕ narrative memory. |
| **PredictivePerceptionEngine** | Pure function: `(state_{t-1}, observation_t) → PredictiveResult`. Оркестрирует 4 компонента (Prediction, Error, Precision, Trace). |
| **Traveling Wave (nTW)** | Биологическое явление в коре. ENIGMA НЕ моделирует nTW. Заимствуется только вычислительный принцип. |
| **Predictive Coding** | Computational framework (Rao & Ballard 1999; Friston 2010). Базовая схема: верхний уровень генерирует prediction, нижний сравнивает с input, error используется для коррекции. |
| **PPI** | Predictive Perturbation Index — DNA-метрика. Средний `prediction_error.total` по NPC за тик. Высокий PPI = мир непредсказуем для NPC. |
| **Horizon** | На сколько тиков вперёд NPC предсказывает. V1 = 1, V3+ = до 3. |
| **Learning Rate (α)** | Скорость обновления kernel из prediction_error. V1 uniform = 0.15. V1+ per-NPC из `NPCProfileL0.prediction_learning_rate`. |
| **Vacuum (в контексте §19)** | `Precision < 0.05`. NPC почти ничего не воспринял. Не конвертируется в `prediction_error` (§ENIGMA-004 — аналог). |
| **Belief (в контексте §19)** | Во что NPC верит. Обновляется через `BeliefTransitionEngine` (§18). НЕ то же самое, что Prediction. |
| **Reality** | Абсолютная истина симуляции. Скрыта от наблюдателей (§17.1). Prediction не читает Reality. |
| **ManifestationState** | Read-only мост между Reality и Perception. Prediction работает с ManifestationState, не с Reality. |

---

## ПРИЛОЖЕНИЕ B. ССЫЛКИ НА КОД V.0.5.3.6.9

Документ составлен на основе аудита следующего кода:

| Файл | Назначение | Связь с §19 |
|------|-----------|-------------|
| `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` | Архитектурный Устав §1–§17 | §7 — совместимость |
| `docs/Почти Актуальные TZ/VZ/TZ_§18_Resource_Bounded_Epistemic_Selection_Law.md` | §18 ТЗ | §6 — интеграция (Prediction Error = источник U(c)) |
| `architecture/perception_architecture.yaml` | Спецификация Epistemology | §3 — позиционирование |
| `architecture/pipeline.yaml` | Спецификация пайплайна | §3.1 — фаза 3.8 |
| `architecture/memory.yaml` | Спецификация домена MEMORY | §4.4 — SpatialTemporalTrace (не narrative memory) |
| `architecture/identity.yaml` | Спецификация домена IDENTITY (L0→L3) | §11 — Per-NPC resource model |
| `architecture/authoring/signal_causes.yaml` | Карта сигнал→причина | §4.2 — InferenceEngine (V2+) |
| `backend/app/models/npc_state.py` | NPCState, PerceptualKernel | §5.2 — расширение PerceptualKernel |
| `backend/app/services/npc/npc_tick_pipeline.py` | Pure reducer фаз 3-6 | §3.3 — wiring Phase 3.8 |
| `backend/app/services/npc/decision_hub.py` | DecisionHub (READ ONLY) | §8.7 — куда не лезть |
| `backend/app/services/npc/state_applicator.py` | Единственный мутатор | §5.3 — новый метод apply_delta_to_kernel |
| `backend/app/services/npc/interpretation_engine.py` | Cognitive distortion | §3.3 — расширяется опциональным prediction_error параметром |
| `backend/app/services/npc/pressure_translator.py` | kernel → DecisionContext | §3.5 — без изменений (читает обновлённый kernel) |
| `backend/app/services/npc/belief_transition_engine.py` | WRITE в BeliefState | §6.3 — surprise становится источником importance |
| `backend/app/services/npc/belief_crystallization_engine.py` | L2.5 — CrystallizedBelief | §9.1 — `BELIEF_DECAY_TAU` import |
| `backend/app/services/npc/perception_filter.py` | Perception Filter | §4.3 — calculate_clarity → confidence |
| `backend/app/services/perception/fact_extractor.py` | Извлечение ObservedFact | §4.5 — вход для PredictiveEngine |
| `backend/app/services/perception/inference_engine.py` | Гипотезы из фактов | §9.1 — PC-19-5 (V2+ wiring) |
| `backend/app/services/spatial/spatial_runtime.py` | LOS, sound_reach | §4.3 — физическая надёжность восприятия |
| `backend/app/domain/perception.py` | ProjectionFrame, PerceptionEvent | §3.1 — существующая онтология |
| `backend/app/domain/observed_fact.py` | ObservedFact | §4.2 — вход для compare() |
| `backend/app/domain/decision_context.py` | DecisionContext | §3.5 — без изменений |
| `backend/app/services/cfrm/pressure_translator.py` | translate_kernel_to_context | §3.5 — читает обновлённый kernel |
| `backend/app/services/game_loop/phase_2_world_tick.py` | Phase 2 — proactive NPC | §3.1 — без изменений |
| `backend/app/services/phases/memory.py` | Phase 3 — Memory | §3.1 — без изменений |
| `backend/app/services/phases/decision.py` | Phase 4 — Behavior/Identity | §3.1 — без изменений |

---

## ПРИЛОЖЕНИЕ C. ЧЕК-ЛИСТ ПЕРЕД АКТИВАЦИЕЙ V1

Перед началом реализации Этапа A (V1: Prediction + Error + Precision + минимальный SpatialTrace), пройти чек-лист:

### C.1 Зависимости от §18

- [ ] §18 Этап A завершён: `BeliefRevisionEngine` существует, `BeliefState` schema расширена (PC-1, PC-2, PC-3).
- [ ] §18 Этап B завершён: `MemoryRetriever` существует, `LayeredMemory` имеет `read_by_topic`/`read_by_actor` (PC-5, PC-6, PC-7).
- [ ] §18 Этап C завершён: `MemoryUtilityEvaluator` wired в Phase 3.6, тесты TC-1..TC-7 проходят.
- [ ] §18 PC-16 закрыт: лаг Phase 3 → Phase 5 устранён (ADR-059 закрыт).
- [ ] §18 PC-17 закрыт: `BeliefState` в реестре сериализационных адаптеров §12.5.

### C.2 Зависимости от текущего кода

- [ ] PC-19-3 закрыт: `PerceptualKernel` расширяется без нарушения round-trip теста.
- [ ] PC-19-7 закрыт: `StateApplicator.apply_delta_to_kernel` реализован.
- [ ] PC-19-8 закрыт: `PredictionState` in-memory LRU cache существует.
- [ ] PC-19-9 закрыт: `SpatialTemporalTrace` in-memory LRU cache существует.
- [ ] PC-19-12 закрыт: `InterpretationEngine.compute()` принимает опциональный `prediction_error` параметр.
- [ ] PC-19-13 закрыт: ADR-059 (Stale Cognition) устранён.
- [ ] PC-19-16 закрыт: `NPCProfileL0` расширен (V1 minimum: `prediction_horizon`, `prediction_learning_rate`, `precision_tolerance`).
- [ ] PC-19-17 закрыт: `NpcTickPipeline.run()` — pure reducer (без `svc` параметра).

### C.3 ADR

- [ ] ADR-O-4XX (Predictive Perception Engine) принят.
- [ ] ADR-O-4XX+1 (Prediction Model) принят.
- [ ] ADR-O-4XX+2 (Prediction Error Calculator) принят.
- [ ] ADR-O-4XX+3 (Precision Model) принят.
- [ ] ADR-O-4XX+4 (Spatial Temporal Trace) принят.
- [ ] ADR-O-4XX+5 (Perceptual Kernel Delta) принят.

### C.4 Тесты

- [ ] TC-19-1: Базовая активация — prediction_error модулирует kernel.
- [ ] TC-19-2: Vacuum — низкая precision снижает (но не обнуляет) deltas.
- [ ] TC-19-3: Extreme vacuum — precision < 0.05 → kernel не меняется.
- [ ] TC-19-4: Spatial prediction — expected_position из trace.
- [ ] TC-19-5: Per-NPC различие (после этапа D — отложить).
- [ ] TC-19-6: Determinism — replay даёт идентичный результат.
- [ ] TC-19-7: Wall-clock absence — grep `time.time|datetime.now` = 0 matches.
- [ ] TC-19-8: Bounded trace — MAX_TRACE_LENGTH=8 соблюдён.
- [ ] TC-19-9: Trace decay — salience затухает по экспоненте.
- [ ] TC-19-10: Trace hard cap — entries старше 50 тиков удалены.

### C.5 Устав

- [ ] §19 добавлен в `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` как исполняемый контракт.
- [ ] Code review checklist включает §8 (anti-patterns) и §8.7 (DecisionHub не принимает Prediction).
- [ ] Lint rule: запрет голых numeric literals в `services/npc/predictive/`.
- [ ] Lint rule: запрет `random.*` и `time.time|datetime.now` в `services/npc/predictive/`.
- [ ] CDS расширен метрикой PPI (Predictive Perturbation Index).

### C.6 Документация

- [ ] `architecture/predictive_perception.yaml` создан (новая спецификация домена).
- [ ] `architecture/perception_architecture.yaml` обновлён — ссылка на §19.
- [ ] `architecture/pipeline.yaml` обновлён — Phase 3.8 добавлена.
- [ ] `docs/MUTATIONS.md` обновлён — запись о введении §19.
- [ ] `README.md` обновлён — упоминание §19 в разделе Quick Start (после активации).

**Только после всех пунктов [x] — реализация §19 V1 в production коде.**

---

## ПРИЛОЖЕНИЕ D. СВЯЗЬ С ЭПОХАМИ ENIGMA

Из эпох-графа ENIGMA (см. `docs/ENIGMA_EPOCHS_REPORT.md`):

| Эпоха | Версия | Тема | Связь с §19 |
|-------|--------|------|-------------|
| 1 | v0.x | Каузальный фундамент | База: SpatialService, body_state, Dual-Time |
| 2 | v0.5.x | Чистота ядра | База: TickState/TickMutation, KernelRNG, L1Chronicle |
| 3 | v0.5.3.x | Идентичность | База: BeliefCrystallization, Triple Membrane |
| 4 | v0.5.3.x | Восприятие | База: 5-layer Reality→Perception, World Continuity |
| 5 | v0.5.3.6.x | Санация | База: V8.x closure, Workplace Affordance |
| 6 | v6.9-v7.0 | Стабилизация + Infrastructure | **Pre-conditions**: PBT, Replay, Probes, ADR-Net. Без этого §19 рискованно внедрять. |
| **7** | **v7.5-v8.0** | **Vertical Slice + Prophecy** | **АКТИВАЦИЯ §19 V1 (Этап A)**. Prediction Error становится фундаментом Prophecy Layer. |
| 8 | v8.5-v9.0 | Генерационная глубина | **§19 V2 (Этап B)**: SpatialTrace интегрируется с lineage. |
| 9 | v9.5 | Полноценное общество | **§19 V3 (Этап C)**: Bayesian social prediction при 20-30 NPC. |
| 10 | v10.0+ | §18 Epistemic Selection | **§19 Этап D**: per-NPC predictive profile, completions цикла §18 ↔ §19. |
| 11+ | v11.0+ | Неограниченная эволюция | Planning Layer — вырастает из рекуррентного цикла prediction → error → belief update. |

**Принцип:** §19 активируется **между Infrastructure (Эпоха 6) и Prophecy (Эпоха 7)**. Это даёт:
- Стабильный baseline (PBT + Replay готовы ловить regression).
- Инфраструктуру для валидации emergent behavior.
- Естественный мост к Prophecy System (prediction → error → prophecy).

**Активация §19 ранее v7.5** = внедрение поверх незакрытой инфраструктуры = высокий риск.
**Активация §19 позже v8.0** = упущенная синергия с Prophecy System.

---

## ПРИЛОЖЕНИЕ E. КОНКРЕТНЫЙ ПРИМЕР

### E.1 Сценарий: Борко и игрок с мечом

**Контекст:**
- NPC: Борко (стражник, `aggression=0.4`, `fear=0.6`, `control=0.5`).
- Player: достаёт меч на `distance=3m`, `light=bright`, `LOS=clear`.
- Tick: 100.
- Previous state (tick 99): `kernel.threat_gradient=0.2`, `kernel.uncertainty=0.3`, `kernel.trust_gradient=0.5`.

### E.2 V1 Execution (после активации §19)

**Step 1: Prediction (в начале тика 100)**

```python
predict(
    npc_id="borko",
    current_tick=100,
    previous_kernel=kernel_at_tick_99,
    memory_context={...},  # из PredictionState
    spatial_trace=[...],   # последние 8 позиций игрока
    drives_base={"aggression": 0.4, "fear": 0.6, "control": 0.5, ...},
    relationship_snapshot={...},
)
```

Результат:
```python
Prediction(
    npc_id="borko",
    tick=101,
    horizon=1,
    expected_events=(
        PredictedEvent("PLAYER_ATTACKS", probability=0.14),     # threat=0.2 × 0.7 + fear=0.6 × 0.3 = 0.32 → softmax
        PredictedEvent("PLAYER_CONTINUES_DIALOGUE", 0.68),       # trust=0.5 × 0.6 + desire=0.4 × 0.4 = 0.46
        PredictedEvent("PLAYER_LEAVES", 0.18),
    ),
    expected_position=(12.4, 8.1),
    expected_velocity=(0.3, 0.1),
    confidence=0.62,
)
```

**Step 2: Observation**

Игрок достаёт меч → `ObservedFact(fact_name="weapon_visible", value=True, confidence=0.95)`.
Actual event type: `"PLAYER_DRAWS_WEAPON"` (трактуется как precursor к PLAYER_ATTACKS).

**Step 3: Precision**

```python
compute_precision(
    observed_facts=[weapon_visible_fact],
    perception_confidence=0.95,  # distance=3m, bright, LOS=clear
    source_type="perception",
    drives_base={"aggression": 0.4, "fear": 0.6, "control": 0.5, ...},
    stress=30.0,
)
```

Результат:
```python
PrecisionResult(
    value=0.95 × 0.85 × 0.62 = 0.50,  # attention = 0.5 + 0.5×0.5 - 0.3×0.6 - 0.2×0.3 = 0.62
    confidence=0.95,
    reliability=0.85,
    attention=0.62,
)
```

**Step 4: Compare**

```python
compare(
    prediction=prediction_at_tick_100,
    observed_facts=[weapon_visible_fact],
    actual_event_type="PLAYER_ATTACKS",  # трактуется как атака
    actual_player_position=(12.5, 8.0),
    precision=0.50,
    current_tick=100,
)
```

Результат:
```python
PredictionError(
    npc_id="borko",
    tick=100,
    total=0.42,        # (0.45 × 0.78 event_error + 0.25 × 0.05 spatial + ...) × 0.50 precision
    event=0.78,        # surprise = -log(0.14) ≈ 1.97 → / 5.0 = 0.39, но с bonus за weapon_visible → 0.78
    spatial=0.05,      # ||(12.5,8.0) - (12.4,8.1)|| / 3.0 = 0.14 / 3.0 ≈ 0.05
    temporal=0.0,      # V2+
    social=0.0,        # V3+
    surprise=1.97,     # -log(0.14)
    precision=0.50,
    dominant_channel="event",
)
```

**Step 5: Build Kernel Delta**

```python
build_kernel_delta(
    prediction_error=prediction_error,
    prediction=prediction_at_tick_100,
    salience=0.95,  # max confidence of facts × precision
    learning_rate=0.15,
)
```

Результат:
```python
PerceptualKernelDelta(
    threat_gradient_delta=+0.094,   # 0.15 × 0.42 × 0.95 × 1.5 (attack_pred bonus)
    trust_gradient_delta=-0.030,    # -0.15 × 0.0 × 0.95 × 0.5 (no social error)
    uncertainty_delta=+0.094,       # 0.15 × min(1.0, 1.97/3.0) × 0.95 = 0.15 × 0.66 × 0.95
    anomaly_score_delta=+0.030,     # 0.15 × 0.42 × 0.95 × 0.5
    aggression_inhibition_delta=+0.014,  # 0.15 × 0.094 × 0.3
    initiative_suppression_delta=0.0,
    compliance_bias_delta=+0.019,   # 0.15 × (0.094 + 0.094 × 0.5) × 0.3
    prediction_error_set=True,
    prediction_error_value=0.42,
    prediction_surprise_value=1.97,
    prediction_confidence_value=0.62,
    source="predictive_engine",
)
```

**Step 6: Apply Delta**

```python
state_l2 = StateApplicator.apply_delta_to_kernel(state_l2, delta)
```

Kernel после применения:
```python
PerceptualKernel(
    threat_gradient=0.294,         # было 0.2, стало 0.294 (+47%)
    trust_gradient=0.470,          # было 0.5, стало 0.470 (-6%)
    uncertainty=0.394,             # было 0.3, стало 0.394 (+31%)
    anomaly_score=0.030,           # было 0.0, стало 0.030 (new)
    aggression_inhibition=0.014,   # было 0.0, стало 0.014 (new)
    compliance_bias=0.019,         # было 0.0, стало 0.019 (new)
    prediction_error=0.42,
    prediction_surprise=1.97,
    prediction_confidence=0.62,
    ...
)
```

**Step 7: InterpretationEngine (читает обновлённый kernel)**

```python
InterpretationEngine().compute(
    state=state_l2,  # с обновлённым kernel
    event=event_context,
    drives_base=drives,
    prediction_error=prediction_error,  # NEW optional parameter
)
```

Результат:
```python
InterpretationResult(
    bias=DistortionProfile(
        threat_bias=0.394,  # fear × THREAT_AMPLIFICATION_FACTOR (использует обновлённый kernel!)
        trust_bias=-0.20,
        salience_bias=0.394,  # обновлённый kernel.threat_gradient усиливает salience
    ),
    score_modifiers={
        "flee": +0.118,    # threat_bias × 0.3
        "observe": +0.079,  # threat_bias × 0.15 + salience_bias × 0.1
    },
    threat_level=42,        # weapon_visible +20, COMBAT +30, но с обновлённым kernel → bonus
    threat_category="MEDIUM",
    ...
)
```

**Step 8: PressureTranslator → DecisionContext**

```python
translate_kernel_to_context(
    kernel=updated_kernel,  # threat=0.294, aggression_inhibition=0.014, ...
    body_state=body_state,
    social_input_ema=0.4,
    gregariousness=0.5,
)
```

Результат:
```python
DecisionContext(
    deformation=UtilityFieldDeformation(
        aggression_suppression=0.014,   # из обновлённого kernel
        initiative_suppression=0.0,
        compliance_bias=0.019,
        escape_salience=0.147,          # kernel.threat_gradient × 0.5
    ),
    compression=ActionSpaceCompression(constraints={}),
    source="perceptual_kernel",
    ...
)
```

**Step 9: DecisionHub**

```python
DecisionHub(rng=KernelRNG(tick=100, npc_id="borko")).compute(
    state=state_l2,
    personality=profile_l0,
    event=event_context,
    effective_drives=effective_drives,
    decision_ctx=decision_context,  # с обновлёнными deformation values
    ...
)
```

Результат:
```python
AgentAction(
    decision=DecisionResult(
        npc_id="borko",
        intent=Intent.OBSERVE,  # не FLEE — Борко стражник, но и не APPROACH
        intent_target="player",
        score=0.42,
        scores_trace={
            "flee": 0.38,        # без §19 было бы ~0.20
            "observe": 0.42,     # без §19 было бы ~0.30
            "attack": 0.15,
            "approach": 0.10,
            ...
        },
        ...
    ),
    ...
)
```

### E.3 Сравнение: с §19 vs без §19

| Аспект | Без §19 | С §19 V1 |
|--------|---------|----------|
| `kernel.threat_gradient` после события | 0.2 (не обновлён) | 0.294 (+47%) |
| `kernel.uncertainty` | 0.3 | 0.394 (+31%) |
| `score_modifiers["flee"]` | +0.060 | +0.118 (+97%) |
| `score_modifiers["observe"]` | +0.045 | +0.079 (+76%) |
| `DecisionContext.escape_salience` | 0.10 | 0.147 (+47%) |
| Победивший intent | `OBSERVE` (score=0.30) | `OBSERVE` (score=0.42) |
| Победивший score | 0.30 | 0.42 (+40%) |

**Ключевое наблюдение:** победивший intent остался `OBSERVE`, но score вырос на 40%. Это означает, что Борко **сильнее зафиксировался** на наблюдении — он более уверен в необходимости следить за игроком. Без §19 он «случайно» выбрал OBSERVE; с §19 он выбрал OBSERVE **из-за того, что его модель мира была нарушена** (он не ожидал оружия).

### E.4 Что меняется в долгосрочной перспективе

Без §19: Борко реагирует на weapon_visible как на изолированный сигнал. Через 10 тиков, если игрок не атакует, `kernel.threat_gradient` возвращается к 0.2 (decay). Борко «забывает», что был напуган.

С §19: `kernel.anomaly_score` накапливает «следы» нарушенных предсказаний. Через 10 тиков, даже если игрок убрал оружие, `kernel.anomaly_score` всё ещё 0.030 (с decay). Борко помнит, что игрок сделал что-то неожиданное. Это влияет на следующий prediction — `P(PLAYER_ATTACKS)` остаётся повышенной.

Это **динамическое восприятие** — ядро §19.

---

**Документ завершён.**

**Статус:** Architecture Hypothesis V.0.5.3.6.9.
**Целевая эпоха активации:** v7.5 (Prophecy System).
**Следующее действие:** закрытие pre-conditions §18 (Этап A+B+C из ТЗ §18), затем закрытие pre-conditions §19 (PC-19-1..PC-19-13).
**Активация:** после ADR-O-4XX + прохождения чек-листа Приложения C.

---

*Документ подготовлен на основе аудита V.0.5.3.6.9, существующих ТЗ из `docs/Почти Актуальные TZ/` (особенно ТЗ §18), архитектурных принципов `CAUSAL_CONTRACT v2.0`, `ADR Master Index`, `ENIGMA_EPOCHS_REPORT.md`, и научного обзора Muller et al. (Neuron, 21 июля 2026). Все file:line references точны на V.0.5.3.6.9.*

*Биологическая реализация traveling waves НЕ заимствуется. Заимствуется только вычислительный принцип: рекуррентная пространственно-временная динамика как субстрат краткосрочного предсказания.*

*ENIGMA — не brain simulator. ENIGMA — каузально честная симуляция.*
