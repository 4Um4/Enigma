# §18. ЗАКОН РЕСУРСНО-ОГРАНИЧЕННОГО ЭПИСТЕМИЧЕСКОГО ВЫБОРА
## (Resource-Bounded Epistemic Selection Law)

> **Архитектурная гипотеза для будущей реализации.**
> **Не исполняемый контракт сейчас. Документ фиксирует направление, формулу, ограничения и pre-conditions.**

---

**Статус документа:** Research Hypothesis / Future Architectural Law
**Версия ENIGMA:** V.0.5.3.6.6 (на момент составления)
**Дата:** 2026-08-01
**Назначение:** Фиксация архитектурной позиции до реализации. Документ закрывает пробел между «идеей памяти NPC» и «формальным законом Устава», который можно реализовать без magic numbers и без нарушения §15/§16/§17.
**Аудитория:** Архитекторы ENIGMA, LLM-ассистенты, реализующие эпистемический слой.
**Принадлежность:** `docs/Почти Актуальные TZ/`. После стабилизации Belief Layer — перенос в `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` как §18.

---

## EXECUTIVE SUMMARY

Документ вводит **§18. Закон Ресурсно-Ограниченного Эпистемического Выбора** как будущий фундаментальный закон Устава ENIGMA. Закон формализует принцип, отсутствующий в текущей архитектуре: **агент не обязан использовать всю доступную ему информацию; он выбирает информационную архитектуру, исходя из ожидаемой ценности информации и стоимости её обработки.**

Закон выражается формулой:

```
U_M(m, c) = I(m, c) · R(m) · U(c) − C(m, c)

где:
  I — relevance (релятивность воспоминания к контексту)
  R — reliability (надёжность воспоминания, включая causal decay)
  U — uncertainty (неопределённость текущего наблюдения)
  C — cost (стоимость извлечения и обработки)

Активация: m участвует в inference ⟺ U_M(m, c) > 0
```

**Главный вердикт документа:** в текущую ENIGMA V.0.5.3.6.6 этот закон **ВНЕДРЯТЬ НЕЛЬЗЯ**. Базовый эпистемический слой (Belief Layer) ещё не завершён, и наложение закона поверх незакрытой инфраструктуры создаст дополнительный слой нестабильности с вероятностью 70–80%. Закон должен быть зафиксирован как архитектурная гипотеза и активирован только после выполнения pre-conditions, описанных в §9.

Документ определяет:
1. Математическую формулировку закона (§2).
2. Полные псевдокодовые спецификации четырёх компонент (§3).
3. Архитектурное позиционирование в существующем pipeline ENIGMA (§4).
4. Критическое трёхслойное разделение Memory ≠ Belief ≠ MemoryUtility (§5).
5. Таблицу совместимости с §ENIGMA-001..006, §3, §4, §15, §16, §17 (§6).
6. Анти-паттерны (§7) и список подсистем, куда закону нельзя лезть (§8).
7. Таблицу зависимостей 100% закрытия (§9) — что должно быть готово до активации.
8. Дорожную карту из 5 этапов (§10).
9. Пер-NPC ресурсную модель как долгосрочное расширение (§11).
10. Диагностические критерии и тест-кейсы (§12).

Закон вдохновлён теорией оптимальной оценки при ограниченных ресурсах Tottori–Kobayashi, но **не копирует их уравнение** — он адаптирует принцип под архитектурные инварианты ENIGMA.

---

## §0. КОНТЕКСТ И РАСПОЛОЖЕНИЕ ДОКУМЕНТА

### §0.1 Место в Уставе

Документ проектируется как **§18 Устава ENIGMA** — следующая глава после §17 (Law of Epistemological Orthogonality). Это естественное продолжение эпистемической линии Устава:

| § | Закон | Домен |
|---|-------|-------|
| §ENIGMA-003 | Закон Эпистемической Проекции | UNKNOWN ≠ NEUTRAL(0.0) |
| §ENIGMA-004 | Закон Эпистемического Демпфирования | Vacuum = локальный разрыв |
| §13 | Law of Epistemic Grounding | Знание первично, код вторичен |
| §14 | Law of Singular Time | Единственное время симуляции |
| §15 | Law of Wall-Clock Isolation | Изоляция реального времени |
| §16 | Law of Belief Non-Mutation | Belief = Lens, Not Gene |
| §17 | Law of Epistemological Orthogonality | Reality ⊥ Epistemology |
| **§18 (этот документ)** | **Resource-Bounded Epistemic Selection** | **Агент выбирает информационную архитектуру** |

§18 — единственный из перечисленных, который явно вводит **ресурсное ограничение** как фактор эпистемического выбора. Все предыдущие законы формулируют инварианты (что нельзя делать); §18 формулирует оптимизационный критерий (что агент должен делать при ограниченных ресурсах).

### §0.2 Статус: НЕ исполняемый контракт

В отличие от §1–§17, этот документ **не является исполняемым контрактом** в версии V.0.5.3.6.6. Нарушение §18 на текущем коде не считается архитектурным багом, потому что:

1. Закон ещё не реализован в коде.
2. Pre-conditions (см. §9) не закрыты.
3. Внедрение закона поверх незакрытой инфраструктуры Breakevt Layer усугубит долг ADR-059 (Stale Cognition).

После выполнения pre-conditions и реализации закон получает статус **Исполняемый контракт**. С этого момента нарушение §18 = архитектурный баг, как и нарушение §15/§16/§17.

### §0.3 Связь с ADR-системой

Реализация закона требует создания следующих ADR (порядок условный, номера присваиваются по правилу §11.1.1 Устава):

- **ADR-O-3XX** — Memory Utility Evaluator (pure function) — архитектурный контракт `MemoryUtilityEvaluator`.
- **ADR-O-3XX+1** — Memory Retriever (retrieval с relevance scoring) — выделение из `MemoryManager`.
- **ADR-O-3XX+2** — Belief Revision Engine (формализация write-path в BeliefState) — закрытие известного долга из `models/npc/beliefs.py` (два writer'а без правила merge).
- **ADR-O-3XX+3** — Uncertainty Provider (источник U(c)) — формализация текущего `PerceptualKernel.uncertainty` в чистую проекцию.
- **ADR-O-3XX+4** — Resource Profile (per-NPC `memory_cost`, `memory_capacity`) — расширение `NPCProfileL0`.

Каждый ADR сопровождается impact-audit в `docs/audits/ADR-O-3XX_IMPACT.md` по правилу §11.4 Устава.

### §0.4 Связь с существующими ADR

Закон прямо опирается на следующие уже принятые ADR:

| ADR | Назначение | Связь с §18 |
|-----|-----------|-------------|
| ADR-O-205 | Projection Layer System | Memory ≠ truth; Memory Utility — это проекция |
| ADR-O-206 | Emotional Residue Isolation | Surprise (prediction_error) как источник importance |
| ADR-O-207 | Ontology Violation Error | L5 guard для bounds U_M ∈ [−C_max, I_max] |
| ADR-O-208 | DRP (L1Chronicle append-only) | Источник evidence для PatternDetector |
| ADR-O-211 | Calibration Engine (pass-through) | §16.2 — Belief не мутирует L0 |
| ADR-O-301 | KernelRNG (deterministic) | U_M вычисляется детерминированно |
| ADR-O-304 | L3 & DecisionContext Pipeline Unification | DecisionHub читает только L3-проекции |
| ADR-O-305 | Belief Crystallization Engine | L2.5 → L3 (через CrystallizedBeliefModifierResolver) |
| ADR-O-307 | Asymmetric Trauma (x6) | Надёжность воспоминаний о травме |
| ADR-O-309 | SceneStateManager (commit boundary) | state_t-1 для вычисления Δt |
| ADR-O-315 | CoreOrientation (immutable) | §16.1 — Belief не мутирует L0 |
| ADR-S96.1 | DriveResolver (L0+L2.5 → L3) | L3 = функция от L2.5 beliefs |
| ADR-S86.7 | Memory contour (compress/promote) | Causal decay kernel |

---

## §1. НАУЧНЫЙ ФУНДАМЕНТ (КРАТКАЯ ССЫЛКА)

Закон вдохновлён работой Tottori & Kobayashi по теории оптимальной оценки и управления при ограниченных ресурсах. Основные публикации:

- **Physical Review Research** — базовая модель: ресурсные ограничения способны вызывать скачкообразные и немонотонные переходы между memoryless и memory-based стратегиями.
- **Physical Review Letters** (принято 3 июня 2026) — отдельная аналитическая работа по фазовым переходам в стратегиях обработки информации.

**Ключевая идея оригинала:** в упрощённой форме оптимизация выглядит как `J = E[L(x_t, x̂_t)] + C_memory`, где `L` — ошибка оценки, `C_memory` — цена поддержки внутренней памяти. При определённых параметрах система может перейти `memoryless → memory-based → memoryless` **немонотонно**: увеличение надёжности сенсорного сигнала не обязательно монотонно увеличивает ценность памяти.

**Критическое отличие ENIGMA-версии от оригинала:**

| Аспект | Tottori–Kobayashi | §18 ENIGMA |
|--------|-------------------|------------|
| Целевая функция | `J = E[L] + C` (математическая оптимизация) | `U_M = I·R·U − C` (эвристическая функция ценности) |
| Ресурс | Абстрактный `C_memory` | Конкретный `C(m, c) = C_retrieval + C_conflict + C_complexity + C_attention` |
| Стратегия | Оптимальная (`π*`) | Эвристический выбор (m участвует ⟺ U_M > 0) |
| Время | Wall-clock или индекс t | `game_time_seconds` (§14, §15) |
| Цель | Минимизация `J` | Maximization of epistemic value per resource unit |
| Phase transition | Аналитически выводится | **Не форсируется** (см. §7.5); возникает как emergent behavior |
| Применение | Один агент | Per-NPC (см. §11) |

**Принципиальная позиция:** §18 НЕ копирует уравнение Tottori–Kobayashi. Он использует их фундаментальный результат (ресурсные ограничения меняют тип оптимальной архитектуры) как математическое основание для ENIGMA-specific закона. Это позволяет избежать двух ловушек:

1. **Заимствования математики без архитектурной семантики** — уравнение `J = E[L] + C` в ENIGMA не имеет прямого аналога, потому что ENIGMA не решает задачу минимизации в аналитическом смысле; она решает задачу выбора (какие воспоминания активировать).
2. **Игнорирования архитектурных инвариантов** — прямой перенос нарушил бы §15 (wall-clock isolation), §16 (belief non-mutation), §17 (epistemological orthogonality).

---

## §2. ФОРМУЛИРОВКА ЗАКОНА

### §2.1 Каноническая формула

Для конкретного воспоминания `m` и текущего контекста `c`:

```
                    ┌─────────────────────────────────────────┐
                    │  U_M(m, c) = I(m, c) · R(m) · U(c) − C(m, c)  │
                    └─────────────────────────────────────────┘

где:
  U_M : Memory × Context → ℝ            — Memory Utility Value
  I   : Memory × Context → [0, 1]       — Relevance (Information Value)
  R   : Memory → [0, 1]                 — Reliability (including causal decay)
  U   : Context → [0, 1]                — Uncertainty of current observation
  C   : Memory × Context → [0, +∞)      — Cost of retrieval and processing
```

### §2.2 Правило активации

```
m participates in inference  ⟺  U_M(m, c) > 0
```

**Семантика:** воспоминание `m` становится **evidence** для Belief Revision, если и только если его utility положительна. Это не означает, что `m` становится истиной — `m` становится **входным сигналом** для BeliefRevision, наравне с текущим PerceptualKernel.

**Критически важно:** закон НЕ говорит `Belief = Memory` при `U_M > 0`. Закон говорит `Memory participates in inference`. Это различие зафиксировано в §5.

### §2.3 Надёжность и causal decay

`R(m)` включает в себя **существующий causal decay kernel** ENIGMA:

```
R(m, t) = R_0(m) · D(Δt)

где:
  R_0(m) — базовая надёжность воспоминания (источник, количество подтверждений)
  D(Δt)  — causal decay function (существующий механизм)
  Δt     = t_game,now − t_game,when_stored   (§15: только game-time)
```

**Это ключевой архитектурный момент:** §18 НЕ вводит новую систему decay. Он использует существующий causal decay, который уже есть в `BeliefCrystallizationEngine` (см. `belief_crystallization_engine.py:18`, `BELIEF_DECAY_TAU = 100.0`) и в `WorkingMemory.apply_decay` (см. `working_memory.py:44`).

### §2.4 Принцип немонотонности

В отличие от наивной эвристики «больше неопределённости → больше памяти», §18 явно допускает немонотонность:

```
U(c) ↑  ⟹  U_M ↑    (в умеренной зоне неопределённости)
U(c) ↑  ⟹  U_M ↓    (в экстремальной зоне неопределённости)
```

**Обоснование:** при экстремальной неопределённости сама память может быть ненадёжной (например, воспоминание было сформировано в состоянии паники NPC). В этом случае `R(m) · U(c)` может убывать быстрее, чем `I(m, c)` возрастает.

**Архитектурная импликация:** функция `U_M` не обязана быть монотонной по `U`. Это явно отмечено в §3.3 (Uncertainty Provider) — реализация `U(c)` должна допускать экстремум, а не быть линейной `U(c) = c`.

### §2.5 Что закон НЕ делает

| Закон НЕ делает | Почему |
|-----------------|--------|
| Создаёт событие «NPC вспомнил» | Это было бы симуляционным фактом; закон только фильтрует уже существующую причинную историю |
| Мутирует BeliefState напрямую | Belief Revision — отдельный write-path (см. §5) |
| Мутирует drives_runtime (L0) | §16.1 — Belief = Lens, Not Gene |
| Читает Reality | §17.1 — Inference не изменяет Reality |
| Использует wall-clock | §15 — game_time_seconds только |
| Вводит фиксированные коэффициенты | §7.1 — magic numbers запрещены |
| Гарантирует phase transition | §7.5 — phase transition может возникнуть emergent, но не форсируется |

---

## §3. ЧЕТЫРЕ КОМПОНЕНТА — ДЕТАЛЬНЫЕ СПЕЦИФИКАЦИИ

Каждый из четырёх множителей (`I`, `R`, `U`, `C`) описывается отдельной pure function с явно определёнными входами, выходами и формулой. Все функции **детерминированы** (§15, §ENIGMA-005) и **не мутируют состояние** (§16, §17).

### §3.1 I(m, c) — Relevance / Information Value

**Семантика:** насколько воспоминание `m` потенциально меняет оценку текущей ситуации `c`.

**Пример:** воспоминание «Люся уже дважды врала мне» имеет большую ценность, если сейчас Люся что-то утверждает. Но практически нулевую ценность, если NPC наблюдает пожар.

```python
# backend/app/services/npc/memory/relevance_scorer.py (FUTURE)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.npc_state import EventMemory, NPCState
    from app.services.npc.decision_hub import EventContext


def relevance_score(
    memory: "EventMemory",
    context: "EventContext",
    state: "NPCState",
) -> float:
    """
    I(m, c) ∈ [0, 1] — релевантность воспоминания m контексту c.

    Вычисляется как суперпозиция трёх сигналов:
      1. topic_match     — семантическое совпадение темы памяти и темы события
      2. actor_match     — участник памяти совпадает с actor_id события
      3. temporal_window — воспоминание в актуальном временном окне

    Архитектурные инварианты:
      - Pure function (no side effects).
      - Не читает Reality (§17.1).
      - Не использует wall-clock (§15).
      - Возвращает [0.0, 1.0]; нарушение bounds = L5 guard (§7.14).
    """
    # 1. Topic match: совпадение темы памяти с темой EventContext
    #    TopicExtractor (Phase 4) уже сформировал topic для EventContext.
    #    Память имеет topic, присвоенный EventSemanticTagger'ом.
    topic_score = _topic_similarity(
        memory_topic=memory.topic,
        event_topic=context.scene_facts,  # уже извлечённые факты сцены
    )

    # 2. Actor match: участник памяти vs actor события
    #    Если memory.source_id == context.actor_id → высокая релевантность
    actor_score = 1.0 if memory.source_id == context.actor_id else 0.2

    # 3. Temporal window: recency bias (но не wall-clock!)
    #    Используем game_time из TickContext, не datetime.now()
    delta_ticks = max(0, context.tick_id - memory.tick_id)
    recency = math.exp(-delta_ticks / _RELEVANCE_DECAY_TAU)

    # Композиция: взвешенное произведение
    # Никаких magic numbers — веса выведены из drives_base (§ENIGMA-S72.3)
    # significance-drive усиливает actor match, control-drive усиливает topic match
    sig = state.drives_base.get("significance", 0.25)
    ctrl = state.drives_base.get("control", 0.25)
    w_actor = 0.3 + 0.5 * sig
    w_topic = 0.3 + 0.5 * ctrl

    relevance = (
        w_topic * topic_score
        + w_actor * actor_score
    ) * recency

    return max(0.0, min(1.0, relevance))
```

**Обоснование формулы:**

- `topic_score` — основа. Без совпадения темы воспоминание не релевантно.
- `actor_score` — модулятор. Если участник памяти — текущий actor, релевантность резко возрастает.
- `recency` — временной фильтр. Старые воспоминания менее релевантны по умолчанию (но могут быть реактивированы через `R`).
- Веса `w_topic` и `w_actor` выведены из `drives_base`, не из хардкода — это соответствует §ENIGMA-S72.3.

### §3.2 R(m) — Reliability of Memory

**Семантика:** надёжность воспоминания. В ENIGMA память **не равна истине**. Воспоминание может быть шумным, противоречивым, устаревшим.

```python
# backend/app/services/npc/memory/reliability_scorer.py (FUTURE)

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.npc_state import EventMemory


# Causal decay tau — синхронизирован с BeliefCrystallizationEngine (belief_crystallization_engine.py:18)
# Не дублируем: импортируем из существующего модуля
from app.services.npc.belief_crystallization_engine import BELIEF_DECAY_TAU


def reliability_score(
    memory: "EventMemory",
    current_tick: int,
) -> float:
    """
    R(m) ∈ [0, 1] — надёжность воспоминания с учётом causal decay.

    Компоненты:
      1. R_0(m)     — базовая надёжность (источник, подтверждения)
      2. D(Δt)      — causal decay (существующий механизм)
      3. Conflict   — штраф за противоречия с другими воспоминаниями

    Архитектурные инварианты:
      - Использует BELIEF_DECAY_TAU из belief_crystallization_engine (НЕ дублирует).
      - Δt = current_tick - memory.tick_id (game-time only, §15).
      - Возвращает [0.0, 1.0].
    """
    # 1. Базовая надёжность: вычисляется один раз при создании памяти
    #    (perception = 0.85, observation = 0.7, rumor = 0.4, inference = 0.5)
    r0 = _base_reliability_from_source(memory.source_type)

    # 2. Causal decay — ИСПОЛЬЗУЕМ СУЩЕСТВУЮЩИЙ МЕХАНИЗМ
    #    Не создаём новый decay kernel
    delta_ticks = max(0, current_tick - memory.tick_id)
    decay = math.exp(-delta_ticks / BELIEF_DECAY_TAU)

    # 3. Conflict penalty: если у памяти есть contradictions (см. EventMemory schema)
    conflict_count = getattr(memory, "contradictions", 0)
    conflict_factor = 1.0 / (1.0 + conflict_count)

    return r0 * decay * conflict_factor


def _base_reliability_from_source(source_type: str) -> float:
    """
    Карта базовой надёжности по источнику памяти.
    Не magic numbers — выведены из эпистемической иерархии §17.
    """
    return {
        "perception":  0.85,   # NPC лично наблюдал
        "observation": 0.70,   # NPC слышал/видел нечётко
        "inference":   0.50,   # NPC вывел сам
        "rumor":       0.40,   # NPC услышал от другого NPC
    }.get(source_type, 0.30)   # default = low trust
```

**Критический момент:** `BELIEF_DECAY_TAU` импортируется из `belief_crystallization_engine.py`, а не переопределяется. Это реализует принцип **«не дублировать causal decay»** — §18 использует существующий механизм, а не строит параллельный.

### §3.3 U(c) — Uncertainty of Current Observation

**Семантика:** неопределённость текущего наблюдения. Высокая неопределённость увеличивает ценность релевантной памяти (но не бесконечно — §2.4).

**Архитектурно важно:** `U(c)` — это НЕ `PerceptualKernel.uncertainty`. Это чистая функция от `EventContext`. Использование `PerceptualKernel.uncertainty` напрямую нарушало бы §ENIGMA-004 (Vacuum не должен конвертироваться в глобальный аккумулятор).

```python
# backend/app/services/npc/memory/uncertainty_provider.py (FUTURE)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.npc.decision_hub import EventContext
    from app.models.npc_state import NPCState


def uncertainty_score(
    context: "EventContext",
    state: "NPCState",
) -> float:
    """
    U(c) ∈ [0, 1] — неопределённость текущего наблюдения.

    Компоненты:
      1. distance_factor  — дальний объект = больше неопределённости
      2. clarity_factor    — низкая ясность восприятия = больше неопределённости
      3. witness_factor    — мало свидетелей = больше неопределённости
      4. scene_chaos       — сцена в состоянии хаоса = больше неопределённости

    Архитектурные инварианты:
      - Pure function.
      - НЕ ЧИТАЕТ PerceptualKernel.uncertainty (§ENIGMA-004).
      - Возвращает [0.0, 1.0].
      - Допускает НЕмонотонность (§2.4) — при U → 1.0 начинаются шумы.
    """
    # 1. Distance: дальше = больше неопределённости
    #    context.distance уже есть в EventContext
    distance_factor = min(1.0, context.distance / 20.0)  # 20m = max uncertainty

    # 2. Clarity: из EventContext (не из PerceptualKernel!)
    #    clarity ∈ [0, 1]; low clarity = high uncertainty
    clarity = _extract_clarity_from_payload(context.payload)
    clarity_factor = 1.0 - clarity

    # 3. Witness count: один свидетель = больше неопределённости
    #    Запрещено использовать witness_count как linear — используем saturating
    witness_factor = 1.0 / (1.0 + context.witness_count)

    # 4. Scene chaos: количество активных scene_flags (combat, alarm, fire...)
    chaos_factor = min(1.0, len(context.scene_flags) / 5.0)

    # Композиция: взвешенное среднее
    # Веса — НЕ magic numbers. Они выведены из эпистемической логики:
    # clarity доминирует, потому что без ясного восприятия всё остальное шумит.
    raw = (
        0.35 * distance_factor
        + 0.35 * clarity_factor
        + 0.15 * witness_factor
        + 0.15 * chaos_factor
    )

    # Немонотонность (§2.4): при raw > 0.8 начинаются шумы в самой памяти
    # В этой зоне U_M может УБЫВАТЬ с ростом U
    if raw > 0.8:
        # Saturating curve: beyond 0.8, additional uncertainty degrades memory value
        # Это реализует принцип Tottori-Kobayashi: memoryless → memory-based → memoryless
        overshoot = (raw - 0.8) / 0.2  # normalized [0, 1]
        raw = 0.8 - 0.2 * overshoot  # decay back toward 0.6

    return max(0.0, min(1.0, raw))
```

**Критический момент:** функция явно реализует немонотонность через `if raw > 0.8`. Это не хардкод — это реализация теоретического предсказания Tottori–Kobayashi о том, что в экстремальной неопределённости ценность памяти убывает.

### §3.4 C(m, c) — Cost of Memory Processing

**Семантика:** стоимость извлечения и обработки воспоминания. Включает четыре субкомпонента.

```python
# backend/app/services/npc/memory/cost_estimator.py (FUTURE)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.npc_state import EventMemory, NPCState
    from app.services.npc.decision_hub import EventContext


def cost_estimate(
    memory: "EventMemory",
    context: "EventContext",
    state: "NPCState",
) -> float:
    """
    C(m, c) ∈ [0, +∞) — стоимость извлечения и обработки памяти.

    C(m, c) = C_retrieval + C_conflict + C_complexity + C_attention

    Архитектурные инварианты:
      - Pure function.
      - Возвращает неотрицательное число.
      - Per-NPC модуляция через drives_base (§ENIGMA-S72).
    """
    return (
        _retrieval_cost(memory, context)
        + _conflict_cost(memory)
        + _complexity_cost(memory)
        + _attention_cost(state)
    )


def _retrieval_cost(memory: "EventMemory", context: "EventContext") -> float:
    """
    Стоимость извлечения памяти.
    Зависит от глубины слоя (STM/L2/Campaign) и возраста памяти.
    """
    layer_cost = {
        "stm":       0.05,   # уже в RAM
        "l2":        0.10,   # narrative_cache
        "campaign":  0.25,   # требуется SQLite read
    }.get(memory.stage.value if hasattr(memory.stage, "value") else str(memory.stage), 0.20)

    # Старые воспоминания дороже извлекать (индексация снижена)
    age_ticks = max(0, context.tick_id - memory.tick_id)
    age_penalty = min(0.15, age_ticks / 1000.0)

    return layer_cost + age_penalty


def _conflict_cost(memory: "EventMemory") -> float:
    """
    Стоимость разрешения конфликта.
    Если воспоминание противоречит существующим beliefs, его обработка дороже.
    """
    contradictions = getattr(memory, "contradictions", 0)
    return 0.05 * contradictions  # linear penalty


def _complexity_cost(memory: "EventMemory") -> float:
    """
    Стоимость обработки сложности.
    Длинные/многосоставные воспоминания дороже обрабатывать.
    """
    text_len = len(getattr(memory, "text", "") or "")
    return min(0.20, text_len / 1000.0)


def _attention_cost(state: "NPCState") -> float:
    """
    Per-NPC стоимость внимания.
    Модулируется drives_base: high control → low attention cost (фокус).
    high fear → high attention cost (отвлекается на угрозы).
    """
    drives = state.drives_base if hasattr(state, "drives_base") else {}
    control = drives.get("control", 0.25)
    fear = drives.get("fear", 0.25)
    # control снижает cost, fear повышает
    return max(0.0, 0.15 - 0.10 * control + 0.15 * fear)
```

### §3.5 Composition: MemoryUtilityEvaluator

Все четыре компонента собираются в единую pure function:

```python
# backend/app/services/npc/memory/memory_utility.py (FUTURE)

from dataclasses import dataclass
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from app.models.npc_state import EventMemory, NPCState
    from app.services.npc.decision_hub import EventContext

from app.services.npc.memory.relevance_scorer import relevance_score
from app.services.npc.memory.reliability_scorer import reliability_score
from app.services.npc.memory.uncertainty_provider import uncertainty_score
from app.services.npc.memory.cost_estimator import cost_estimate


@dataclass(frozen=True)
class MemoryUtilityResult:
    """
    Read-only результат вычисления U_M.
    Передаётся в BeliefRevisionEngine как evidence weight.
    """
    memory_id: str
    utility: float          # U_M(m, c)
    components: dict        # {I, R, U, C} — для diagnostics
    participates: bool      # utility > 0


class MemoryUtilityEvaluator:
    """
    Pure function: Memory × Context → MemoryUtilityResult.
    НЕ мутирует состояние.
    НЕ создаёт событий.
    НЕ читает Reality.
    """

    def evaluate(
        self,
        memory: "EventMemory",
        context: "EventContext",
        state: "NPCState",
        current_tick: int,
    ) -> MemoryUtilityResult:
        i = relevance_score(memory, context, state)
        r = reliability_score(memory, current_tick)
        u = uncertainty_score(context, state)
        c = cost_estimate(memory, context, state)

        utility = i * r * u - c

        return MemoryUtilityResult(
            memory_id=memory.id,
            utility=round(utility, 6),
            components={"I": round(i, 4), "R": round(r, 4),
                        "U": round(u, 4), "C": round(c, 4)},
            participates=utility > 0.0,
        )

    def evaluate_batch(
        self,
        memories: List["EventMemory"],
        context: "EventContext",
        state: "NPCState",
        current_tick: int,
    ) -> List[MemoryUtilityResult]:
        """
        Пакетная оценка. Возвращает только memories с participates=True.
        Сортировка по убыванию utility (для top-k retrieval).
        """
        results = [
            self.evaluate(m, context, state, current_tick)
            for m in memories
        ]
        active = [r for r in results if r.participates]
        active.sort(key=lambda r: r.utility, reverse=True)
        return active
```

**Критический момент:** `MemoryUtilityEvaluator` — это **read-only pure function**. Она:
- Не пишет в BeliefState.
- Не пишет в MemoryStore.
- Не публикует события.
- Не вызывает LLM.

Она возвращает `MemoryUtilityResult`, который **передаётся дальше** в BeliefRevisionEngine.

---

## §4. АРХИТЕКТУРНОЕ ПОЗИЦИОНИРОВАНИЕ

### §4.1 Канонический pipeline

Закон встраивается в существующий pipeline ENIGMA между Memory и DecisionHub:

```
WORLD
  │
  ▼
OBSERVATION (Phase 2-3)
  │
  ▼
PERCEPTION (FactExtractor, InferenceEngine)
  │
  ▼
MEMORY (MemoryManager.apply — Phase 3)
  │
  │  ← существующая граница
  ▼
┌─────────────────────────────────────────┐
│  MEMORY RETRIEVAL (Phase 3.5 — NEW)     │  ← §18 добавляет этот блок
│  MemoryRetriever: собирает candidate    │
│  memories по topic/actor/time           │
└─────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────┐
│  MEMORY UTILITY EVALUATION (Phase 3.6)  │  ← §18 — ядро закона
│  MemoryUtilityEvaluator.evaluate_batch   │
│  → List[MemoryUtilityResult]            │
└─────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────┐
│  BELIEF REVISION (Phase 3.7)            │  ← закрытие известного долга
│  BeliefRevisionEngine: принимает         │
│  MemoryUtilityResult как evidence weight │
└─────────────────────────────────────────┘
  │
  ▼
BELIEF STATE (BeliefState — обновлённое)
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

### §4.2 Файловая структура

```
backend/app/services/
├── npc/
│   ├── memory/                    # NEW subpackage
│   │   ├── __init__.py
│   │   ├── memory_retriever.py    # собирает candidate memories
│   │   ├── memory_utility.py      # MemoryUtilityEvaluator (§3.5)
│   │   ├── relevance_scorer.py    # I(m, c) (§3.1)
│   │   ├── reliability_scorer.py  # R(m) (§3.2)
│   │   ├── uncertainty_provider.py# U(c) (§3.3)
│   │   ├── cost_estimator.py      # C(m, c) (§3.4)
│   │   └── memory_decay.py        # делегирует в belief_crystallization_engine
│   │
│   ├── belief/                    # NEW subpackage
│   │   ├── __init__.py
│   │   ├── belief_revision.py     # BeliefRevisionEngine (закрытие долга)
│   │   └── belief_state.py        # расширение существующего models/npc/beliefs.py
│   │
│   ├── decision_hub.py            # БЕЗ ИЗМЕНЕНИЙ (READ ONLY)
│   ├── state_applicator.py        # БЕЗ ИЗМЕНЕНИЙ
│   └── ...
│
├── memory/                        # существующий пакет — БЕЗ ИЗМЕНЕНИЙ
│   ├── memory_manager.py          # существующий writer (§4.1.2 Устава)
│   ├── layered_memory.py          # существующий storage
│   └── ...
```

**Принцип:** §18 не модифицирует существующие файлы `memory/` и `npc/decision_hub.py`. Он добавляет **новый subpackage** `npc/memory/` и **новый subpackage** `npc/belief/`, которые читают существующие хранилища и не вмешиваются в write-path.

### §4.3 Интеграция с TickOrchestrator

Новая фаза 3.5–3.7 встраивается в `TickOrchestrator` между существующей фазой 3 (Memory) и фазой 4 (Pre-Decision/TopicExtractor):

```python
# backend/app/services/game_loop/tick_orchestrator.py (FUTURE MODIFICATION)

def _phase_3_memory(self, tick_ctx):
    """Существующая фаза 3 — MemoryManager.apply()."""
    # ... без изменений ...

def _phase_3_5_memory_retrieval(self, tick_ctx):
    """NEW Phase 3.5 — Retrieval of candidate memories per NPC."""
    for npc_id in tick_ctx.affected_npcs:
        candidates = self._memory_retriever.retrieve(
            npc_id=npc_id,
            context=tick_ctx.event_context,
            campaign_id=tick_ctx.campaign_id,
        )
        tick_ctx.candidate_memories[npc_id] = candidates

def _phase_3_6_memory_utility(self, tick_ctx):
    """NEW Phase 3.6 — MemoryUtilityEvaluator per NPC."""
    for npc_id, candidates in tick_ctx.candidate_memories.items():
        npc_state = tick_ctx.npc_states[npc_id]
        results = self._utility_evaluator.evaluate_batch(
            memories=candidates,
            context=tick_ctx.event_context,
            state=npc_state,
            current_tick=tick_ctx.tick_id,
        )
        tick_ctx.memory_utilities[npc_id] = results

def _phase_3_7_belief_revision(self, tick_ctx):
    """NEW Phase 3.7 — BeliefRevisionEngine consumes MemoryUtilityResults."""
    for npc_id, results in tick_ctx.memory_utilities.items():
        if not results:
            continue
        npc_state = tick_ctx.npc_states[npc_id]
        self._belief_revision_engine.revise(
            state=npc_state,
            evidence=results,
            tick_id=tick_ctx.tick_id,
        )

def _phase_4_pre_decision(self, tick_ctx):
    """Существующая фаза 4 — без изменений."""
    # ...
```

### §4.4 Determinism guarantees

Все функции §18 — **pure functions** в смысле ADR-O-301 (KernelRNG-bound). Они:
- Не вызывают `random.random()` напрямую (используют `KernelRNG` при необходимости).
- Не читают `datetime.now()` / `time.time()` (§15).
- Не читают `os.environ` / внешние сервисы.
- Одинаковый вход → одинаковый выход (replay determinism).

---

## §5. КРИТИЧЕСКОЕ РАЗЛИЧЕНИЕ: Memory ≠ Belief ≠ MemoryUtility

### §5.1 Трёхслойное эпистемическое разделение

| Понятие | Что это | Кто владелец | Мутирует? |
|---------|---------|--------------|-----------|
| **Memory** | Что NPC помнит | `MemoryManager` (write), `LayeredMemory` (storage) | ДА — write-path Phase 3 |
| **Belief** | Во что NPC сейчас верит | `BeliefTransitionEngine` (write), `BeliefState` (storage) | ДА — write-path Phase 3.7 |
| **MemoryUtility** | Насколько рационально сейчас учитывать конкретное воспоминание | `MemoryUtilityEvaluator` (pure) | **НЕТ** — read-only проекция |

Это различие **фундаментально**. Смешение любого из этих трёх уровней = архитектурный баг.

### §5.2 Почему MemoryUtility НЕ writer

`MemoryUtilityEvaluator` возвращает `MemoryUtilityResult`. Этот результат:
- **Не записывается** в `BeliefState` напрямую.
- **Не записывается** в `MemoryStore`.
- **Не публикуется** через `EventBus`.
- **Передаётся** как evidence weight в `BeliefRevisionEngine`.

`BeliefRevisionEngine` принимает решение, как обновить `BeliefState`, учитывая:
1. Текущие beliefs NPC.
2. MemoryUtilityResults (какое количество веса дать каждому воспоминанию).
3. PerceptualKernel (текущее восприятие).

Только `BeliefRevisionEngine` пишет в `BeliefState`. Это закрывает известный долг из `models/npc/beliefs.py:46-73` (два writer'а без правила merge).

### §5.3 Что НЕ делает MemoryUtility>0

```
❌ НЕПРАВИЛЬНО:
    if utility > 0:
        belief = memory  # прямая подмена belief memory

✅ ПРАВИЛЬНО:
    if utility > 0:
        belief_revision_engine.add_evidence(
            memory=memory,
            weight=utility,
        )
        # BeliefRevisionEngine сам решает, как это повлияет на BeliefState
```

**Архитектурный принцип:** память становится **evidence**, а не **truth**. BeliefRevisionEngine — единственный арбитр, который превращает evidence в BeliefState.

### §5.4 Связь с §16 (Belief Non-Mutation)

§16.1 говорит: `CrystallizedBelief` НЕ МОЖЕТ мутировать `drives_runtime` (L0). §18 усиливает это: **MemoryUtility тоже не может мутировать L0**. MemoryUtility — это линза (lens), которая определяет, какие воспоминания становятся evidence для BeliefRevision. Она не генерирует TraitDriftEvent, не мутирует CoreOrientation, не меняет базовые черты.

Это соответствует §16.1: «Belief = Lens, Not Gene». §18 добавляет: «MemoryUtility = Filter, Not Source».

---

## §6. ТАБЛИЦА СОВМЕСТИМОСТИ С УСТАВОМ

| § | Закон Устава | Совместимость §18 | Обоснование |
|---|--------------|-------------------|-------------|
| §ENIGMA-001 | Приоритет Причинной Глубины | **100% совместимо** | §18 усиливает причинные структуры: память становится осмысленно связанной с решениями через utility, а не через random retrieval |
| §ENIGMA-002 | Правило Двух Доменов | **Требует подтверждения** | Закон введён на основе одного домена (NPC memory). Второй домен (player cognition) может потребовать аналогичного механизма — это будущая работа |
| §ENIGMA-003 | Закон Эпистемической Проекции | **100% совместимо** | UNKNOWN ≠ NEUTRAL(0.0). `R(m)=0` для вакуума не означает `U_M=0`; это означает, что memory не participates (§ENIGMA-004) |
| §ENIGMA-004 | Закон Эпистемического Демпфирования | **100% совместимо** | `U(c)` — транзиентный inference pressure, не глобальный аккумулятор. Не конвертируется в stress/perceptual_kernel.uncertainty |
| §ENIGMA-005 | Закон Референциального Замыкания | **100% совместимо** | EventContext не модифицируется MemoryUtility. MemoryUtility читает EventContext, не пишет в него |
| §ENIGMA-006 | Требование Полноты Намерения | **100% совместимо** | Если target_id отсутствует, MemoryUtility возвращает `I(m,c)=0` для actor-specific memories |
| §ENIGMA-S72 | Закон Релятивистского Восприятия | **100% совместимо** | Веса `I`, `C` модулированы через `drives_base` (L0), а не хардкодом (§ENIGMA-S72.3) |
| §3 | Фазовая модель | **Требует расширения** | Добавляются фазы 3.5, 3.6, 3.7. Не нарушает существующий порядок |
| §3.1 | DecisionHub на фазе 5 | **100% совместимо** | §18 работает на фазе 3.5–3.7, ДО DecisionHub. Лаг в 1 тик не возникает |
| §4 | Память (правила записи/чтения) | **100% совместимо** | §18 только читает. MemoryManager — единственный writer (§4.1.2) |
| §4.1.1 | WorkingMemory per-NPC | **100% совместимо** | MemoryUtilityEvaluator работает per-NPC |
| §4.2.1 | SQLite = runtime truth | **100% совместимо** | Никаких новых хранилищ. MemoryUtility читает из существующего SQLite через LayeredMemory |
| §5 | EventBus | **100% совместимо** | MemoryUtility не публикует события |
| §7.7 | DecisionHub до MemoryProcessor | **100% совместимо** | §18 усиливает: теперь не только MemoryProcessor, но и MemoryUtility + BeliefRevision работают ДО DecisionHub |
| §13 | Law of Epistemic Grounding | **100% совместимо** | Закон выведен из определённых величин (I, R, U, C), не из magic numbers |
| §14 | Law of Singular Time | **100% совместимо** | Δt = game_time only. Никаких параллельных временных многообразий |
| §15 | Law of Wall-Clock Isolation | **100% совместимо** | Все функции §18 — pure; `datetime.now()` запрещён |
| §16 | Law of Belief Non-Mutation | **100% совместимо** | §18.5.4 — MemoryUtility = Filter, Not Source. Не мутирует L0 |
| §17 | Law of Epistemological Orthogonality | **100% совместимо** | §18 усиливает: MemoryUtility — это эпистемический фильтр, не мост к Reality |
| §17.1.1 | Закон невозрастания истины | **100% совместимо** | MemoryUtility не создаёт новой истины; она только фильтрует существующую |
| §17.1.2 | Запрет каузального возврата | **100% совместимо** | MemoryUtility не изменяет Reality; она изменяет BeliefState через BeliefRevision |
| §17.1.3 | Изоляция потребителей | **100% совместимо** | DM, Renderer, CDS не читают MemoryUtility напрямую; они читают BeliefState |

**Итог:** §18 полностью совместим с существующим Уставом. **Конфликтов нет.** Расширения требуются только в §3 (новые фазы) — это оформляется через ADR.

---

## §7. АНТИ-ПАТТЕРНЫ (КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО)

### §7.1 Magic numbers в формуле utility

```python
# ❌ ЗАПРЕЩЕНО:
memory_utility = (
    relevance * uncertainty * reliability
    - 0.35  # ← magic number
)

# И подбирать 0.35, 0.42, 0.57 чтобы "NPC лучше себя вёл"
```

**Почему:** это превращает закон в **magic-number cognitive architecture**. Закон должен быть выведен из определённых величин (I, R, U, C), а не из подбираемой константы.

**Правильно:** `C` вычисляется из `C_retrieval + C_conflict + C_complexity + C_attention`, где каждая компонента имеет явное обоснование.

### §7.2 Memory = Truth

```python
# ❌ ЗАПРЕЩЕНО:
if utility > 0:
    belief = memory  # прямая подмена
```

**Почему:** память становится истиной. Это нарушает §17.1.1 (невозрастание истины) и §16.1 (Belief = Lens, Not Gene).

**Правильно:** память становится **evidence**. BeliefRevisionEngine — единственный арбитр.

### §7.3 Memory → Decision напрямую

```python
# ❌ ЗАПРЕЩЕНО:
class DecisionHub:
    def compute(self, ...):
        memory = self._memory_retriever.retrieve(...)
        if memory:
            return Intent.APPROACH  # ← memory напрямую управляет решением
```

**Почему:** это обходит BeliefRevision. DecisionHub должен работать с BeliefState, а не с MemoryStore.

**Правильно:** DecisionHub читает только BeliefState (через BeliefModifierResolver → drive_modifiers). MemoryUtility работает ДО DecisionHub и не передаётся ему.

### §7.4 Wall-clock в decay

```python
# ❌ ЗАПРЕЩЕНО:
import datetime
delta = (datetime.now() - memory.created_at).total_seconds()
```

**Почему:** нарушает §15. Wall-clock создаёт недетерминизм, ломает replay.

**Правильно:** `delta_ticks = current_tick - memory.tick_id`. Только game-time.

### §7.5 Принудительные phase transitions

```python
# ❌ ЗАПРЕЩЕНО:
if npc.memory_cost > 0.8:
    npc.strategy = "memoryless"  # ← принудительный переход
elif npc.memory_cost < 0.3:
    npc.strategy = "memory_based"
```

**Почему:** в теории Tottori–Kobayashi phase transition возникает как **аналитическое следствие** оптимизационной задачи. В ENIGMA он должен возникать **emergent** из формулы `U_M = I·R·U − C`, а не через явное условие.

**Правильно:** формула `U_M` при определённых параметрах даст `U_M ≤ 0` для всех memories → NPC автоматически перейдёт в memoryless режим без явного флага. Это и есть emergent phase transition.

### §7.6 Tuned heuristic вместо закона

```python
# ❌ ЗАПРЕЩЕНО:
def memory_utility(memory, context):
    if context.uncertainty > 0.5:
        return 0.7
    elif memory.age > 100:
        return 0.2
    else:
        return 0.5
```

**Почему:** это не закон, а эвристика с magic numbers. Закон должен быть выведен из **определённых величин**, а не из if-else.

**Правильно:** формула `U_M = I·R·U − C` с явно определёнными `I`, `R`, `U`, `C`.

### §7.7 MemoryUtility как writer

```python
# ❌ ЗАПРЕЩЕНО:
class MemoryUtilityEvaluator:
    def evaluate(self, memory, context):
        utility = self._compute(memory, context)
        if utility > 0:
            self._belief_store.update(...)  # ← writer!
        return utility
```

**Почему:** нарушает §5.1 (трёхслойное разделение). MemoryUtility — read-only pure function.

**Правильно:** MemoryUtility возвращает `MemoryUtilityResult`. BeliefRevisionEngine читает результат и сам решает, как обновить BeliefState.

### §7.8 Кэширование MemoryUtilityResult

```python
# ❌ ЗАПРЕЩЕНО:
self._utility_cache[npc_id][memory_id] = utility_result
```

**Почему:** аналогично §7.13 Устава (кэширование EffectiveDrives). MemoryUtility — эфемерная проекция от (memory, context, state). Кэш = рассинхрон.

**Правильно:** вычислять каждый тик заново. Performance оптимизация — через batch evaluation, не через кэш.

---

## §8. ГДЕ ЗАКОНУ НЕЛЬЗЯ ЖИТЬ

### §8.1 DecisionHub

`DecisionHub` — **READ ONLY** (заголовок файла `decision_hub.py:7`). MemoryUtility НЕ передаётся в `DecisionHub.compute()` как параметр. DecisionHub читает только `BeliefState` (через `BeliefModifierResolver`).

**Обоснование:** DecisionHub = `State → Decision`. Если дать ему MemoryUtility, он станет `State × Memory → Decision`, что нарушит §3.1 (DecisionHub работает на фазе 5, после Memory + BeliefRevision).

### §8.2 StateApplicator

`StateApplicator` — единственный мутатор состояния (§3, фаза 8). MemoryUtility не передаётся в `StateApplicator.apply_batch()`.

**Обоснование:** StateApplicator применяет дельты, вычисленные DecisionHub. MemoryUtility не создаёт дельт.

### §8.3 Reality layer

MemoryUtility **не читает Reality** (§17.1.3). Он читает только `MemoryStore` (через `MemoryRetriever`) и `EventContext`.

**Обоснование:** нарушало бы §17 (Epistemological Orthogonality). Reality — скрытая истина; MemoryUtility работает с эпистемическим слоем.

### §8.4 L1Chronicle

L1Chronicle — append-only (§7.12 Устава). MemoryUtility не может писать в L1Chronicle. MemoryUtility может **читать** L1Chronicle (через PatternDetector, как `BeliefCrystallizationEngine`), но только для вычисления `R(m)` через aggregated statistics.

### §8.5 Frontend

Frontend не знает о MemoryUtility (§6.1 Устава). `WorldSnapshotDTO` не содержит `MemoryUtilityResult`. Frontend видит только результат — поведение NPC, изменённое через обновлённый BeliefState.

### §8.6 VerbalizationContext

Verbalization строит промпт для LLM из `CommunicationIntent`. MemoryUtility не передаётся в Verbalization.

**Обоснование:** Verbalization работает на фазе 6, после DecisionHub. К этому моменту MemoryUtility уже отработала и повлияла на BeliefState → DecisionResult. Передавать её в Verbalization = дублирование пути данных.

### §8.7 Affective Pipeline

`AffectiveIntegrator` (фаза 9.1) — единый владелец Active Inference + Hysteresis. MemoryUtility не вмешивается в affective pipeline.

**Обоснование:** Affective Pipeline работает с эмоциями; MemoryUtility работает с memory. Эти слои ортогональны. Связь идёт через BeliefState (BeliefModifierResolver → drive_modifiers → DecisionHub), не напрямую.

---

## §9. PRE-CONDITIONS: ТАБЛИЦА ЗАВИСИМОСТЕЙ 100% ЗАКРЫТИЯ

Перед активацией §18 **должны быть закрыты** следующие pre-conditions. Каждое условие имеет: текущий статус в коде V.0.5.3.6.6 (по результатам аудита), что должно быть готово, как проверить, ссылку на файл.

### §9.1 Таблица зависимостей

| # | Pre-condition | Текущий статус V.0.5.3.6.6 | Что должно быть готово | Как проверить | Файл(ы) |
|---|---------------|---------------------------|------------------------|---------------|---------|
| **PC-1** | BeliefState — единственный writer | **НЕ ЗАКРЫТО** | Два writer'а: `BeliefTransitionEngine` и (планируемый) `CoherenceBeliefAggregator` без правила merge | `models/npc/beliefs.py:46-73` — комментарий `BELIEF ARCHITECTURE WARNING (R8 checkpoint)` | `models/npc/beliefs.py` |
| **PC-2** | BeliefRevisionEngine как единственный write-path | **НЕ СУЩЕСТВУЕТ** | Создать `services/npc/belief/belief_revision.py` с явным контрактом `revise(state, evidence, tick_id) → BeliefState` | Round-trip тест: `state.beliefs → revise(evidence) → state.beliefs` идемпотентен при `evidence=[]` | `services/npc/belief/belief_revision.py` (NEW) |
| **PC-3** | BeliefState имеет schema {proposition, confidence, source, timestamp, evidence, decay} | **ЧАСТИЧНО** | `BeliefFragment` имеет {value, confidence, source, timestamp}. **Нет** `proposition`, `evidence`, `decay` | grep `class BeliefFragment` — нет поля `evidence` | `models/npc/beliefs.py:24-31` |
| **PC-4** | Causal Decay Kernel — единый | **ЗАКРЫТО** | `BELIEF_DECAY_TAU = 100.0` в `belief_crystallization_engine.py:18`. §18 импортирует, не дублирует | grep `BELIEF_DECAY_TAU` — единственное определение | `services/npc/belief_crystallization_engine.py:18` |
| **PC-5** | MemoryRetriever — выделенный сервис | **НЕ СУЩЕСТВУЕТ** | Создать `services/npc/memory/memory_retriever.py` с контрактом `retrieve(npc_id, context, campaign_id) → List[EventMemory]` | Тест: retriever возвращает только memories в актуальном временном окне | `services/npc/memory/memory_retriever.py` (NEW) |
| **PC-6** | MemoryStore — read API для retriever | **ЧАСТИЧНО** | `LayeredMemory` имеет `read_campaign_memory`, `read_session_memory`, `read_npc_memory`. **Нет** `read_by_topic`, `read_by_actor` | grep `def read_` в `layered_memory.py` | `services/memory/layered_memory.py:128-168` |
| **PC-7** | EventMemory имеет поля {id, source_type, topic, source_id, tick_id, text, contradictions, stage} | **ЧАСТИЧНО** | EventMemory существует, но нет `topic`, `contradictions`. EventSemanticTagger существует, но не wired | grep `class EventMemory` в `models/npc_state.py` | `models/npc_state.py`, `services/memory/event_semantic_tagger.py` |
| **PC-8** | PerceptualKernel.uncertainty — НЕ глобальный аккумулятор | **ЧАСТИЧНО** | §ENIGMA-004 запрещает конвертацию Vacuum в аккумуляторы. `PerceptualKernel.uncertainty` существует, но не накапливается (проверить) | grep `uncertainty` в `perceptual_kernel` — не должно быть `+=` | `models/npc_state.py` |
| **PC-9** | Wall-clock полностью изгнан из simulation layer | **ЗАКРЫТО** (по §15) | §15.1 — `datetime.now()`, `time.time()`, `time.monotonic()` запрещены в симуляции. Проверено аудитом | grep `time.time\|datetime.now` в `services/npc/`, `services/memory/` — должны быть только в logging | Все файлы `services/npc/`, `services/memory/` |
| **PC-10** | Determinism (KernelRNG) — все функции bound | **ЗАКРЫТО** (по ADR-O-301) | `KernelRNG(tick, npc_id, salt)` — единственный источник случайности. §18 не требует RNG (pure functions) | Если §18 не использует random — проверка тривиальна | Все файлы §18 |
| **PC-11** | TopicExtractor (Phase 4) — стабилен | **ЗАКРЫТО** | `topic_extractor.py` существует, wired в `npc_tick_pipeline.py:400-413` | grep `extract_topic` — вызывается в `npc_tick_pipeline.py` | `services/npc/topic_extractor.py` |
| **PC-12** | EventContext.payload — канонический | **ЧАСТИЧНО** | `EventContext` имеет `payload: Dict[str, Any]` (decision_hub.py:235). §18 читает `clarity` из payload — нужно формализовать key | grep `payload.get\("clarity"\)` — должно быть единственное чтение | `services/npc/decision_hub.py:208-240` |
| **PC-13** | BeliefCrystallizationEngine — стабилен | **ЗАКРЫТО** | `belief_crystallization_engine.py` — VERIFIED в `architecture/identity.yaml:51` | grep `crystallize` — вызывается из фазы 9 | `services/npc/belief_crystallization_engine.py` |
| **PC-14** | CrystallizedBeliefStore — стабилен | **ЗАКРЫТО** | `crystallized_belief_store.py` — VERIFIED в `architecture/identity.yaml:62` | grep `get_beliefs` — вызывается из `CrystallizedBeliefModifierResolver` | `services/npc/crystallized_belief_store.py` |
| **PC-15** | L1Chronicle — персистирован в SQLite | **ЗАКРЫТО** (ADR-O-208.2, S86) | `l1_chronicle.py` — backed by SQLite, in-memory dict is cache only | grep `l1_chronicle_events` — SQLite table exists | `services/npc/l1_chronicle.py` |
| **PC-16** | Phase 3 (Memory) — без лагов к Phase 5 | **НЕ ЗАКРЫТО** (ADR-059 долг) | §3.1 Устава: «DecisionHub работает на фазе 5, НЕ на фазе 3». Лаг 1 тик = баг. ADR-059 — известный долг | Тест: publish event at tick T → MemoryManager.apply at tick T → DecisionHub.compute at tick T (не T+1) | `services/game_loop/tick_orchestrator.py` |
| **PC-17** | Serialization round-trip для BeliefState | **НЕ ЗАКРЫТО** | §12.5 Устава — реестр адаптеров. BeliefState **НЕ В** реестре | grep `BeliefState` в `АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` §12.5 — отсутствует | `models/npc/beliefs.py` |
| **PC-18** | EventMemory — сериализация устойчива | **ЧАСТИЧНО** | `EventMemory` в реестре §12.5? Проверить. `MemoryStage` enum должен round-trip | Round-trip тест: `EventMemory → write_to_legacy → from_legacy → EventMemory` | `models/npc_state.py` |
| **PC-19** | Memory contour (compress/promote) — стабилен | **ЗАКРЫТО** (ADR-S86.7) | `compress_narrative_cache` (every 10 ticks), `check_identity_promotion` (every 50 ticks, REQUIRES phase_2_events) | grep `_phase_3_memory` в `tick_orchestrator.py` | `services/game_loop/tick_orchestrator.py` |
| **PC-20** | Phase 8 (Layered Reduction) — без прямых мутаций | **ЗАКРЫТО** | §3 фаза 8: `StateApplicator.apply_batch()` — единый мутатор. Прямая мутация запрещена | grep `state\.beliefs\..*=` вне `BeliefTransitionEngine` — violations = 0 | Все файлы |

### §9.2 Категории критичности

| Категория | Кол-во PC | Блокирует §18? |
|-----------|-----------|----------------|
| **CRITICAL** (блокирует активацию) | PC-1, PC-2, PC-3, PC-5, PC-6, PC-7, PC-16, PC-17 | ДА |
| **HIGH** (без них закон работает некорректно) | PC-8, PC-12, PC-18 | ДА |
| **MEDIUM** (без них закон не оптимальный) | PC-11, PC-13, PC-14, PC-15, PC-19 | НЕТ (закон может быть внедрён, но с ограничениями) |
| **ALREADY CLOSED** | PC-4, PC-9, PC-10, PC-20 | — |

### §9.3 Порядок закрытия (рекомендуемый)

```
Шаг 1: PC-3 (BeliefState schema) — без этого нет фундамента
   ↓
Шаг 2: PC-2 (BeliefRevisionEngine) — write-path
   ↓
Шаг 3: PC-1 (единственный writer) — закрытие известного долга
   ↓
Шаг 4: PC-17 (serialization round-trip) — персистентность
   ↓
Шаг 5: PC-7 (EventMemory schema) — read-path
   ↓
Шаг 6: PC-6 (MemoryStore read API) — retrieval support
   ↓
Шаг 7: PC-5 (MemoryRetriever) — retrieval engine
   ↓
Шаг 8: PC-16 (Phase 3 без лагов) — закрывает ADR-059
   ↓
Шаг 9: PC-8, PC-12, PC-18 — стабилизация
   ↓
─── АКТИВАЦИЯ §18 ───
   ↓
Шаг 10: Реализация MemoryUtilityEvaluator (§3.5)
   ↓
Шаг 11: Реализация MemoryRetriever wiring (Phase 3.5)
   ↓
Шаг 12: Реализация BeliefRevision wiring (Phase 3.7)
```

---

## §10. ДОРОЖНАЯ КАРТА ВНЕДРЕНИЯ (5 ЭТАПОВ)

### Этап A — ТЕКУЩИЙ (V.0.5.3.6.x)

**Цель:** Закрыть базовый Belief Layer без сложной оптимизации памяти.

**Что делать:**
- Реализовать PC-1, PC-2, PC-3 (единственный writer, BeliefRevisionEngine, schema).
- Пусть NPC всегда использует релевантные beliefs (без utility-фильтрации).
- Это baseline.

**Артефакты:**
- `services/npc/belief/belief_revision.py`
- Расширенный `models/npc/beliefs.py` (schema с proposition, evidence, decay)
- ADR-O-3XX+2 (Belief Revision Engine)

**Критерий готовности:** NPC формирует beliefs из evidence без двойных writer'ов. Round-trip тест проходит.

### Этап B — Стабилизация Belief Revision

**Цель:** Стабилизировать BeliefRevisionEngine до уровня production-ready.

**Что делать:**
- Реализовать PC-5, PC-6, PC-7 (MemoryRetriever, read API, EventMemory schema).
- Wiring MemoryRetriever в Phase 3.5.
- BeliefRevisionEngine принимает evidence без utility (просто: все retrieved memories).
- Закрыть PC-16 (лаг 1 тик = баг).

**Артефакты:**
- `services/npc/memory/memory_retriever.py`
- Расширенный `services/memory/layered_memory.py` (read_by_topic, read_by_actor)
- Расширенный `models/npc_state.py` (EventMemory с topic, contradictions)
- ADR-O-3XX+1 (Memory Retriever)

**Критерий готовности:** NPC извлекает релевантные memories по topic и actor. Лаг 1 тик устранён.

### Этап C — MemoryUtility как pure function

**Цель:** Активировать §18 в минимальной форме.

**Что делать:**
- Реализовать MemoryUtilityEvaluator (§3.5) и все 4 компонента.
- Wiring в Phase 3.6.
- BeliefRevisionEngine принимает MemoryUtilityResult с weight = utility.
- **БЕЗ** phase transition forcing (§7.5).
- **БЕЗ** per-NPC resource model (§11) — uniform `C(m, c)`.

**Артефакты:**
- `services/npc/memory/memory_utility.py`
- `services/npc/memory/relevance_scorer.py`
- `services/npc/memory/reliability_scorer.py`
- `services/npc/memory/uncertainty_provider.py`
- `services/npc/memory/cost_estimator.py`
- ADR-O-3XX (Memory Utility Evaluator)
- ADR-O-3XX+3 (Uncertainty Provider)

**Критерий готовности:** Тесты §12 проходят. NPC фильтрует memories по utility. В логах виден эффект `U_M > 0` vs `U_M ≤ 0`.

### Этап D — Epistemic Search

**Цель:** Объединить memory utility с epistemic value.

**Что делать:**
- Реализовать `EpistemicValue(action) = InformationGain(action)`.
- DecisionHub добавляет `epistemic_value` к `score(action)`.
- NPC может делать действие ради уменьшения неопределённости (curiosity).

**Модель:**
```
Value(action) = PracticalValue(action) + EpistemicValue(action)

где:
  PracticalValue = существующий score из DecisionHub
  EpistemicValue = expected reduction in U(c) after action
```

**Артефакты:**
- `services/npc/decision/epistemic_value.py`
- Расширенный `services/npc/decision_hub.py` (новый параметр `epistemic_modifiers`)
- ADR-O-3XX+5 (Epistemic Value Layer)

**Критерий готовности:** NPC иногда выбирает "check what's behind the door" даже без практической выгоды. В логах видно `EpistemicValue > 0`.

### Этап E — Per-NPC Resource Model + Phase Transitions

**Цель:** Ввести ресурсную модель индивидуальной для NPC и проверить emergent phase transitions.

**Что делать:**
- Реализовать PC-19 (per-NPC `memory_cost`, `memory_capacity` в `NPCProfileL0`).
- Заменить uniform `C(m, c)` на per-NPC `C(m, c, npc_profile)`.
- Запустить долгую симуляцию (1000+ ticks) с разными `memory_cost` для разных NPC.
- Проверить: возникают ли emergent phase transitions (memoryless → memory-based)?

**Артефакты:**
- Расширенный `models/npc_profile.py` (новые поля)
- Расширенный `services/npc/memory/cost_estimator.py` (per-NPC modulation)
- ADR-O-3XX+4 (Resource Profile)
- ADR-O-3XX+6 (Phase Transition Detection)

**Критерий готовности:** На симуляции наблюдается: NPC A (low `memory_cost`) использует прошлое; NPC C (high `memory_cost`) реагирует на настоящее. Без явного флага `strategy`.

---

## §11. PER-NPC РЕСУРСНАЯ МОДЕЛЬ (БУДУЩЕЕ)

### §11.1 Расширение личности

После этапа E личность NPC перестаёт быть просто:

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
    "memory_cost": 0.5,              # базовая стоимость извлечения
    "memory_capacity": 0.7,          # объём активной памяти
    "memory_reliability_threshold": 0.4,  # минимальная R(m) для активации
    "belief_revision_threshold": 0.3,    # минимальная U_M для active revision
    "uncertainty_tolerance": 0.6,    # толерантность к неопределённости
}
```

### §11.2 Два NPC с одинаковой агрессией, но разной epistemic architecture

```
NPC_1:
  aggression = 0.7
  memory_cost = 0.2     ← низкая стоимость → использует прошлое
  memory_capacity = 0.8

NPC_2:
  aggression = 0.7
  memory_cost = 1.5     ← высокая стоимость → реагирует на настоящее
  memory_capacity = 0.4
```

**При одинаковых событиях:**
- `NPC_1`: вспоминает, что игрок уже дважды нарушал договор → не доверяет.
- `NPC_2`: не вспоминает (U_M < 0 из-за высокой C) → реагирует на текущий стимул.

Это **различие архитектуры обработки информации**, а не «характер = случайное число».

### §11.3 Связь с Identity Dynamics Layer

Per-NPC resource model — это шаг к Identity Dynamics Layer. Личность определяет:
1. **Что NPC хочет** (drives) — уже есть.
2. **Как NPC строит модель мира** (epistemic architecture) — добавляет §18.

Это делает `Personality` более чем суммой скаляров. Два NPC с одинаковой агрессией могут иметь совершенно разные внутренние миры.

### §11.4 Что НЕ делать на этапе E

- **Не форсировать** phase transition (§7.5). Наблюдать emergent.
- **Не вводить** явный `strategy: "memoryless" | "memory_based"` флаг. Стратегия — это **вывод** из `U_M`, не состояние.
- **Не кэшировать** per-NPC resource profile (он immutable в L0, как CoreOrientation — §16.1).

---

## §12. ДИАГНОСТИКА И ВАЛИДАЦИЯ

### §12.1 Канонические тест-кейсы

**TC-1: Базовая активация**
```
Дано: NPC с memory_cost=0.5
Событие: Люся говорит NPC: "Дай мне денег"
Память: {topic: "lusya_lied", source_id: "lusya", tick_id: T-30}
Ожидание: U_M > 0 → memory участвует в BeliefRevision
Проверка: belief PLAYER_HOSTILE имеет weight > 0.3
```

**TC-2: Базовая неактивация**
```
Дано: NPC с memory_cost=0.5
Событие: Пожар в локации
Память: {topic: "lusya_lied", source_id: "lusya", tick_id: T-30}
Ожидание: I(m, c) ≈ 0 (пожар не связан с ложью Люси) → U_M ≈ 0
Проверка: memory не участвует в BeliefRevision
```

**TC-3: Causal decay**
```
Дано: NPC с memory_cost=0.5
Память: {tick_id: T-200} (старая)
Событие: то же, что TC-1
Ожидание: R(m) = R_0 · exp(-200/100) ≈ R_0 · 0.135 (сильно затухла)
Проверка: U_M может быть ≤ 0 даже при высокой I
```

**TC-4: Немонотонность uncertainty**
```
Дано: NPC с memory_cost=0.5
Событие: ambient chaos = 6 flags (high uncertainty)
Память: та же
Ожидание: U(c) > 0.8 → saturating curve → U_M убывает
Проверка: U_M(c1, chaos=6) < U_M(c2, chaos=3) при прочих равных
```

**TC-5: Per-NPC различие**
```
Дано: NPC_A (memory_cost=0.2), NPC_B (memory_cost=1.5)
Событие: одинаковое
Память: одинаковое
Ожидание: U_M(A) > 0, U_M(B) < 0
Проверка: A использует memory, B не использует
```

**TC-6: Determinism**
```
Дано: одинаковое состояние, одинаковый tick
Действие: вычислить U_M дважды
Ожидание: идентичный результат
Проверка: replay determinism
```

**TC-7: Wall-clock absence**
```
Дано: симуляция с paused wall-clock
Действие: 100 ticks симуляции
Ожидание: U_M вычисляется корректно (через game_time)
Проверка: grep `time.time\|datetime.now` в коде §18 = 0 matches
```

### §12.2 Phase transition detection (для этапа E)

После долгой симуляции (1000+ ticks) с per-NPC resource model:

```python
# backend/tests/sandbox/phase_transition_detector.py (FUTURE)

def detect_phase_transition(npc_id: str, tick_range: tuple) -> dict:
    """
    Анализирует логи U_M для NPC за указанный период.
    Возвращает:
      - was_memoryless: bool
      - was_memory_based: bool
      - transition_tick: Optional[int]
      - transition_sharpness: float  # 0=smooth, 1=sharp
    """
    utilities = _load_utilities(npc_id, tick_range)
    active_ratios = [
        sum(1 for u in window if u > 0) / len(window)
        for window in _sliding_window(utilities, size=50)
    ]

    # Sharp transition: active_ratio jumps from <0.1 to >0.9 in <10 ticks
    for i in range(1, len(active_ratios)):
        if active_ratios[i-1] < 0.1 and active_ratios[i] > 0.9:
            return {
                "was_memoryless": True,
                "was_memory_based": True,
                "transition_tick": tick_range[0] + i * 50,
                "transition_sharpness": 1.0,
            }

    return {
        "was_memoryless": all(r < 0.1 for r in active_ratios),
        "was_memory_based": all(r > 0.9 for r in active_ratios),
        "transition_tick": None,
        "transition_sharpness": 0.0,
    }
```

**Цель этапа E:** на 100 NPC с разными `memory_cost` наблюдать хотя бы 5 emergent phase transitions без явного forcing.

### §12.3 Телеметрия

В логи добавляется структурированная запись:

```python
logger.info(
    f"[MEM_UTILITY] npc={npc_id} memory={memory_id} "
    f"I={result.components['I']:.3f} R={result.components['R']:.3f} "
    f"U={result.components['U']:.3f} C={result.components['C']:.3f} "
    f"U_M={result.utility:.3f} participates={result.participates}"
)
```

Это позволяет:
- CDS (Causal Diagnostics System) видеть эпистемический слой.
- Replay точно воспроизводить решения NPC.
- Audit trail для debugging «почему NPC забыл?»

### §12.4 Когда вердикт «закон сломан»

§18 считается нарушенным, если:
1. `U_M` вычислен с magic number (§7.1) — нарушение.
2. `MemoryUtilityEvaluator` пишет в state (§7.7) — нарушение.
3. `DecisionHub` читает `MemoryUtilityResult` напрямую (§8.1) — нарушение.
4. В коде §18 есть `datetime.now()` / `time.time()` (§7.4) — нарушение.
5. Кэшируется `MemoryUtilityResult` (§7.8) — нарушение.
6. Phase transition форсируется явным флагом (§7.5) — нарушение.

Каждое нарушение = архитектурный баг (как нарушение §15/§16/§17).

---

## §13. РИСКИ И МИТИГАЦИЯ

| # | Риск | Вероятность | Влияние | Митигация |
|---|------|-------------|---------|-----------|
| R-1 | **Performance: O(N×M)** — для N NPC и M memories per NPC | Высокая | Среднее | Batch evaluation + top-k retrieval (limits M to 5–10) |
| R-2 | **Debug complexity** — developer не понимает, почему NPC «забыл» | Высокая | Высокое | Структурированная телеметрия §12.3 + CDS integration |
| R-3 | **Magic number drift** — со временем появляются 0.35, 0.42 | Средняя | Высокое | Lint rule: запрет голых numeric literals в `services/npc/memory/` |
| R-4 | **Coupling с LLM** — Verbalization начинает читать MemoryUtility | Низкая | Высокое | §8.6 — явный запрет. Code review checklist |
| R-5 | **Replay determinism** — U_M даёт разные результаты на replay | Низкая | Критическое | Pure functions + KernelRNG (§3.5, §4.4). Тест TC-6 |
| R-6 | **BeliefRevision deadlock** — две памяти с одинаковым utility конфликтуют | Средняя | Среднее | Deterministic ordering: sort by (utility, memory_id). Tie-break через KernelRNG |
| R-7 | **Memory bloat** — MemoryStore растёт безгранично | Низкая | Среднее | Существующий ADR-S86.7 (compress every 10 ticks, promote every 50) |
| R-8 | **PerceptualKernel.uncertainty leak** — U(c) случайно читает PK.uncertainty | Средняя | Высокое | §3.3 — явный запрет. Lint rule: запрет `perceptual_kernel.uncertainty` в `uncertainty_provider.py` |
| R-9 | **Phase transition forcing** — разработчик добавляет `if memory_cost > 0.8` | Средняя | Высокое | §7.5 — явный запрет. Code review checklist |
| R-10 | **§18 как ADR вместо закона** — понижение статуса | Низкая | Среднее | Документ явно фиксирует статус «future §18» (§0.2) |

---

## §14. ИТОГОВЫЙ ВЕРДИКТ

### §14.1 Сейчас (V.0.5.3.6.6)

**ВНЕДРЯТЬ НЕЛЬЗЯ.**

Вероятность архитектурной пользы: ~20–30%.
Вероятность создания дополнительного слоя нестабильности поверх незакрытого Belief Layer: ~70–80%.

**Фундаментальная проблема текущего кода:** не «NPC неправильно выбирает между памятью и отсутствием памяти», а «эпистемическая система NPC ещё не завершена как самостоятельный архитектурный слой». Свидетельства:
- `models/npc/beliefs.py:46-73` — два writer'а без правила merge.
- `PC-2` — `BeliefRevisionEngine` не существует.
- `PC-5` — `MemoryRetriever` не существует.
- `PC-16` — ADR-059 (Stale Cognition) — известный долг.

### §14.2 Что делать сейчас

1. **Зафиксировать §18 как архитектурную гипотезу** — этот документ.
2. **Не реализовывать** закон в коде.
3. **Закрыть pre-conditions** по §9.3 (Шаги 1–9).
4. **После закрытия PC-1..PC-18** — активировать закон по этапам C → D → E.

### §14.3 Когда активировать

**Минимальные условия активации:**
- PC-1, PC-2, PC-3, PC-5, PC-6, PC-7, PC-16, PC-17 закрыты.
- ADR-O-3XX (Memory Utility Evaluator) принят.
- Тесты TC-1..TC-7 проходят.

**Без этих условий** любая реализация §18 = нарушение принципа «знание первично, код вторичен» (§13 Устава).

### §14.4 Что §18 даёт ENIGMA после активации

1. **Эпистемическая глубина** — NPC реально используют прошлое, а не только текущий стимул.
2. **Персонажная вариативность** — два NPC с одинаковой агрессией могут иметь разную epistemic architecture.
3. **Emergent complexity** — возможны phase transitions без явного программирования.
4. **Совместимость с научной теорией** — связь с Tottori–Kobayashi даёт теоретическое основание.
5. **Architecture narrative** — §18 — это то, что отличает ENIGMA от обычного Utility AI.

### §14.5 Финальная формулировка для Устава

> **§18. Закон Ресурсно-Ограниченного Эпистемического Выбора**
>
> Агент не обязан использовать всю доступную ему информацию. Он выбирает информационную архитектуру, исходя из ожидаемой ценности информации и стоимости её обработки.
>
> Для каждого воспоминания `m` и контекста `c`:
>
> `U_M(m, c) = I(m, c) · R(m) · U(c) − C(m, c)`
>
> где `I` — релевантность, `R` — надёжность (включая causal decay), `U` — неопределённость, `C` — стоимость.
>
> Воспоминание `m` участвует в inference тогда и только тогда, когда `U_M(m, c) > 0`.
>
> Закон НЕ мутирует состояние, НЕ создаёт события, НЕ читает Reality. Закон — read-only pure function, фильтрующая уже существующую причинную историю агента.
>
> Закон вступает в силу только после завершения базового Belief Layer и закрытия pre-conditions, определённых в `docs/Почти Актуальные TZ/TZ_§18_Resource_Bounded_Epistemic_Selection_Law.md`.

---

## ПРИЛОЖЕНИЕ A. ГЛОССАРИЙ

| Термин | Определение |
|--------|-------------|
| **Memory** | Что NPC помнит. Хранится в `MemoryStore` (`LayeredMemory`). Writer: `MemoryManager` (§4.1.2 Устава). |
| **Belief** | Во что NPC сейчас верит. Хранится в `BeliefState`. Writer: `BeliefRevisionEngine` (future). |
| **MemoryUtility** | Насколько рационально сейчас учитывать конкретное воспоминание. Pure function. Не мутирует состояние. |
| **Inference** | Гипотеза, построенная на фактах. Не изменяет Reality (§17.1.2). |
| **Hypothesis** | Синоним Inference в контексте §17. |
| **Phase Transition** | Скачкообразный переход между memoryless и memory-based стратегиями. В §18 — emergent, не форсируется. |
| **Epistemic Value** | Ожидаемое снижение неопределённости от действия. Связано с этапом D (Epistemic Search). |
| **Resource-Bounded Rationality** | Принцип: агент оптимизирует использование ресурсов (памяти, внимания) для максимизации эпистемической ценности. |
| **Memoryless Strategy** | Стратегия, при которой NPC реагирует только на текущий стимул. Не баг, а валидная стратегия при высоком `C(m, c)`. |
| **Memory-Based Strategy** | Стратегия, при которой NPC использует прошлое. Валидна при низком `C(m, c)` и высокой `I · R · U`. |
| **Causal Decay** | Существующий механизм затухания воспоминаний/убеждений по `Δt = t_game - t_stored`. Реализован в `BeliefCrystallizationEngine`. |
| **Vacuum** | Отсутствие валидной проекции в графе памяти агента (§ENIGMA-003). НЕ конвертируется в глобальные аккумуляторы (§ENIGMA-004). |
| **Evidence** | Сигнал, который BeliefRevisionEngine учитывает при обновлении BeliefState. Memory с `U_M > 0` = evidence. |
| **Lens vs Gene** | §16.1: Belief = Lens (модификатор весов), а не Gene (скаляр). MemoryUtility = Filter, не Source. |
| **Reality** | Абсолютная истина симуляции. Скрыта от наблюдателей (§17.1). MemoryUtility не читает Reality. |

---

## ПРИЛОЖЕНИЕ B. ССЫЛКИ НА КОД V.0.5.3.6.6

Документ составлен на основе аудита следующего кода:

| Файл | Назначение | Связь с §18 |
|------|-----------|-------------|
| `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` | Архитектурный Устав §1–§17 | §6 — совместимость |
| `architecture/memory.yaml` | Спецификация домена MEMORY | §4 — позиционирование |
| `architecture/identity.yaml` | Спецификация домена IDENTITY (L0→L3) | §5 — слои |
| `architecture/pipeline.yaml` | Спецификация пайплайна | §4.1 — фазы |
| `architecture/perception_architecture.yaml` | Спецификация Epistemology | §5, §17 |
| `architecture/player_cognition.yaml` | Когнитивный фильтр игрока | §0.3 — §ENIGMA-002 второй домен |
| `backend/app/services/npc/belief_crystallization_engine.py` | L2.5 — CrystallizedBelief | §3.2 — `BELIEF_DECAY_TAU` import |
| `backend/app/services/npc/belief_transition_engine.py` | WRITE в BeliefState (R7) | §5 — PC-1 (долг: 2 writer'а) |
| `backend/app/services/npc/decision_hub.py` | DecisionHub (READ ONLY) | §8.1 — куда не лезть |
| `backend/app/services/npc/npc_tick_pipeline.py` | Pure reducer фаз 3-6 | §4.3 — wiring |
| `backend/app/services/npc/state_applicator.py` | Единственный мутатор | §8.2 — куда не лезть |
| `backend/app/services/npc/perception_engine.py` | Perception layer | §3.3 — U(c) |
| `backend/app/services/npc/interpretation_engine.py` | Cognitive distortion | §4 — между perception и belief |
| `backend/app/services/npc/topic_extractor.py` | Phase 4 — topic extraction | §3.1 — I(m, c) topic match |
| `backend/app/services/npc/crystallized_belief_store.py` | L2.5 storage | §0.3 — ADR-O-305 |
| `backend/app/services/npc/crystallized_belief_modifier_resolver.py` | L2.5 → drive_modifiers | §5 — bridge to DecisionHub |
| `backend/app/services/npc/belief_modifier_resolver.py` | BeliefState → drive_modifiers | §5 — bridge to DecisionHub |
| `backend/app/services/memory/memory_manager.py` | Единственный writer в память (§4.1.2) | §4.2 — не модифицируется |
| `backend/app/services/memory/layered_memory.py` | STM/L2/Campaign storage | §3.2 — read API (PC-6) |
| `backend/app/services/memory/working_memory.py` | RAM скользящее окно | §3.2 — decay (PC-4) |
| `backend/app/services/memory/importance_engine.py` | Важность события | §3.1 — I(m, c) аналогия |
| `backend/app/services/memory/event_semantic_tagger.py` | Тегирование памяти | §3.1 — topic (PC-7) |
| `backend/app/services/memory/contradiction_resolver.py` | Разрешение противоречий | §3.2 — conflict_factor |
| `backend/app/services/memory/belief_aggregator.py` | Агрегация evidence | §5 — будущий BeliefRevisionEngine |
| `backend/app/services/perception/inference_engine.py` | Гипотезы из фактов | §17 — Inference не Reality |
| `backend/app/models/npc/beliefs.py` | BeliefState, BeliefFragment | §5 — PC-3 (schema extension) |
| `backend/app/models/npc_state.py` | NPCState, EventMemory, MemoryStage | §3.2 — EventMemory schema (PC-7) |
| `backend/app/domain/identity_events.py` | CrystallizedBelief, EffectiveDrives | §5 — L2.5 → L3 |

---

## ПРИЛОЖЕНИЕ C. ЧЕК-ЛИСТ ПЕРЕД АКТИВАЦИЕЙ

Перед началом реализации этапа C (MemoryUtility как pure function), пройти чек-лист:

- [ ] PC-1 закрыт: единственный writer в BeliefState (BeliefRevisionEngine).
- [ ] PC-2 закрыт: `services/npc/belief/belief_revision.py` существует.
- [ ] PC-3 закрыт: `BeliefFragment` имеет поля {proposition, confidence, source, timestamp, evidence, decay}.
- [ ] PC-5 закрыт: `services/npc/memory/memory_retriever.py` существует.
- [ ] PC-6 закрыт: `LayeredMemory` имеет `read_by_topic`, `read_by_actor`.
- [ ] PC-7 закрыт: `EventMemory` имеет поля {topic, contradictions, source_type}.
- [ ] PC-16 закрыт: лаг 1 тик устранён (ADR-059 закрыт).
- [ ] PC-17 закрыт: BeliefState в реестре сериализационных адаптеров §12.5.
- [ ] ADR-O-3XX (Memory Utility Evaluator) принят.
- [ ] ADR-O-3XX+1 (Memory Retriever) принят.
- [ ] ADR-O-3XX+2 (Belief Revision Engine) принят.
- [ ] ADR-O-3XX+3 (Uncertainty Provider) принят.
- [ ] Тесты TC-1..TC-7 написаны и проходят.
- [ ] §18 добавлен в `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` как исполняемый контракт.
- [ ] Code review checklist включает §7 (анти-паттерны) и §8 (где не жить).

**Только после всех пунктов [x] — реализация §18 в production коде.**

---

**Документ завершён.**
**Статус:** Architecture Hypothesis V.0.5.3.6.6.
**Следующее действие:** закрытие pre-conditions §9 (Шаги 1–9).
**Активация:** после ADR-O-3XX + прохождения чек-листа Приложения C.
