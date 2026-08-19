# PSY-ARCH-01 — Unified Psychological Dynamics

**Документ:** Техническое задание (ТЗ) для архитектора-программиста
**Код документа:** PSY-ARCH-01
**Статус:** Draft for implementation
**Владелец:** Архитектор ENIGMA Psychology
**Зависимости:** ADR-031 (WillpowerGate), ADR-049 (Active Inference Affect), ADR-O-208 (DRP Phase II), ADR-O-211 (Phase Lock Gate), ADR-O-304 (Trait Stabilization), ADR-O-307 (Asymmetric Trauma)

---

## 0. Как читать этот документ

Документ описывает архитектурный переход от **сценарно-таблицевого** подхода к психике NPC (где каждый тип события жёстко прописан как «если X → fear += 0.1») к **единой динамической модели**, в которой эмоции, мотивация, воля и реакция на травму являются различными вычислительными проекциями одного внутреннего состояния.

**Архитектор** должен воспринимать документ как строгий контракт:

1. Главы 1–4 — контекст и мотивация (читается один раз, формирует картину).
2. Главы 5–9 — целевая спецификация (контракт, который нельзя нарушать).
3. Главы 10–11 — карта маппинга и фазовый план (используется как чек-лист при работе).
4. Главы 12–14 — запреты, критерии приёмки, открытые вопросы.

Любое отклонение от контракта глав 5–9 требует явного ADR (Architecture Decision Record), который архивируется в `backend/docs/adr/`.

---

## 1. Контекст и мотивация

### 1.1 Что сейчас не так

Текущий бэкенд ENIGMA (`backend/app/services/will.py`, `affect.py`, `reaction/reaction_rules.py`, `social/reputation_engine.py`, `events/reaction_subscriber.py`, `npc/break_progress_engine.py`) устроен как **сценаристская таблица**: для каждого типа события (player_attacks, player_threatens, player_insults, …) прописаны жёсткие коэффициенты дельт по нескольким осям (fear, trust, stress, humiliation).

Примеры текущих правил:

- `will.py:resolve_intent_pressure` → если `action == "attack"` → `IntentPressureProfile(violence=0.8, self_risk=0.4, moral_violation=0.5, identity_deviation=0.6)`.
- `reaction_subscriber._REACTION_RULES["player_attacks"] = (15.0, 10.0, -8.0)` — stress, fear, trust_loss.
- `social_deltas._BASE_DELTAS["player_attacks"] = (-10.0, +8.0, "aggression")`.
- `break_progress_engine.TRAUMA_TOPOLOGY` — четыре жёстко зашитых типа травмы (`will_broken`, `humiliated`, `betrayed`, `near_death`).

Архитектурный дефект не в том, что эти числа «неправильные», а в том, что:

- **Не масштабируется.** Добавление N новых категорий действий (романтика, сексуальное насилие, газлайтинг, утешение, похищение, …) потребует N новых записей в каждом из этих справочников. Через год получится «психологический Pokédex».
- **Нет эмерджентности.** Одно и то же событие «Орм обнял Люсю» даёт одинаковый эффект для всех NPC, хотя NPC A (любовник Орма), NPC B (враг Орма) и NPC C (незнакомец) должны воспринять его совершенно по-разному.
- **Эмоция как скаляр.** Текущие модели хранят `fear=0.7` как фундаментальную величину, хотя в современной когнитивной науке эмоция понимается как контекстная интерпретация низкоразмерного состояния (valence × arousal × dominance) через призму appraisal и self-model.
- **Воля как правило.** `if fear > 0.7 → NPC ломается` — это эвристика, а не механика выбора. Воля должна быть вычислена как разность субъективных полезностей конкурирующих действий, а не как порог по скаляру.

### 1.2 Цель PSY-ARCH-01

Заменить event-specific delta-rules общей динамической моделью, в которой:

1. Любое событие сначала превращается в **AppraisalVector** (каково значение события лично для этого агента).
2. Appraisal обновляет **AffectVector** (низкоразмерное состояние) и **NeedVector** (мотивационные переменные).
3. Состояние транслируется в **MotivationVector** (что агент пытается делать).
4. WillEngine вычисляет **полезность каждой candidate policy** и выбирает действие.
5. Травма становится **обновлением параметров модели агента** (priors, precisions, action policies), а не установкой булевого флага.

При этом **большинство существующих подсистем ENIGMA сохраняются** — они занимают ровно то место, которое им предписано в новой архитектуре (см. главу 4).

---

## 2. Архитектурный диагноз

### 2.1 Текущая диаграмма (упрощённо)

```
Event (raw_text)
   │
   ├── DMRouter (regex + pymorphy3) → 6 жёстких категорий
   │
   ├── LLMCompressor (qwen_7b) → богатый JSON: action, target_zone,
   │   speech_act, social_intent, semantic {aggression, fear, shame, ...}
   │   ⚠ Не полностью потребляется Python-слоем
   │
   ├── phase_1_input._IC_PRIORITY_MAP (5 записей) — маппит LLM action → event_type
   │
   └── EventBus.publish(...)
         │
         ├── WillEngine.resolve_intent_pressure — 6 веток
         │
         ├── ReactionSubscriber — _REACTION_RULES (11 записей)
         ├── SocialEngine.propagate — NEGATIVE_EVENTS (6 записей)
         ├── ReputationEngine — EVENT_REPUTATION_IMPACT (5 записей)
         │
         ├── CombatSubscriber → ImpactEngine — каскад Force→Tissue→Pain→Shock
         │
         ├── BeliefCrystallizationEngine — 2 трейта (fear, trust)
         │
         └── StateApplicator (single writer) → NPCState
```

### 2.2 Точки разрыва

| Точка разрыва | Симптом | Причина |
|---|---|---|
| LLM-компрессор → phase_1 | `action=FLIRT` не маппится в event_type | `_IC_PRIORITY_MAP` содержит только ATTACK/THREATEN/STEAL/MOVE/FLEE |
| WillEngine → давление | Нет ветки для FLIRT/PERSUADE/COMFORT/INTIMATE | `resolve_intent_pressure` ветвится по 6 action-строкам |
| Event → психика | Одинаковая реакция свидетелей на событие независимо от их отношения | `_REACTION_RULES` глобальны, не модулированы персональным RelationshipProfile |
| AffectiveImprint → будущее | Травма «сексуальное насилие» неотличима от «обычного нападения» | `humiliation_signature` вычисляется из `WillState`, а не из appraisal |
| BeliefCrystallization | Только 2 трейта (fear, trust) | `target_trait ∈ {"fear", "trust"}` хардкод в `belief_crystallization_engine.py:77` |
| TRAUMA_TOPOLOGY | 4 типа острой травмы, нет сексуальной/интимной/хартфрейк | `break_progress_engine.py:196-212` |

### 2.3 Архитектурный вердикт

Текущий код **концептуально готов** к接纳 новой модели: есть single-writer (`StateApplicator`), есть epistemic boundary, есть L3-projection gate (`CalibrationEngine`), есть причинная трассировка (`L1Chronicle` + `PatternDetector` + `ResonanceEngine`). Не хватает **только AppraisalEngine** — среднего слоя, который превращает событие в персонально-окрашенный вектор оценки. Без него всё сыпется в event-specific таблицы.

---

## 3. Научный фундамент

Четыре теоретические традиции являются основой архитектуры. Архитектор должен понимать их концептуально (не обязательно как математические формулы), потому что они задают форму данных и интерфейсам движков.

### 3.1 Appraisal Theory — Component Process Model (Scherer, 2001)

Событие не вызывает эмоцию напрямую. Эмоция возникает из последовательной оценки события агентом по множеству критериев (SECE): **N**ovelty, **I**ntrinsic pleasantness, **G**oal significance, **C**oping potential, **N**orm compatibility/self-concept.

Для ENIGMA это означает: любой event передаётся в `AppraisalEngine`, который на основе текущего состояния агента возвращает `AppraisalVector` (см. §6.1). Один и тот же event даёт разный вектор для разных агентов.

### 3.2 Active Inference / Predictive Processing (Friston, 2010)

Агент имеет generative model мира и поддерживает beliefs о его латентных причинах. Разница между prediction и observation (prediction error) обновляет модель. **Precision** определяет, насколько сильно конкретная ошибка должна повлиять на систему в целом.

Уже частично реализовано в ENIGMA:
- `PerceptualKernel.uncertainty` → prediction error.
- `PerceptualKernel.anomaly_score` → сильное расхождение.
- `affective_integrator.integrate_affective_pressure` — Hysteresis-интеграл threat_gradient × _w_threat + uncertainty × _w_uncertainty + anomaly × _w_anomaly + somatic × _w_somatic.

В новой архитектуре:
- EpistemicStore (`backend/app/services/npc/epistemic_store.py`) → **Beliefs** (что агент считает истиной).
- BeliefRevisionEngine (`backend/app/services/npc/belief_revision_engine.py`) → **Belief Update** loop.
- PerceptualKernel → **Prediction Error** интеграл.

### 3.3 Homeostatic Motivation (Drive theory / RL на внутренних переменных)

Внутренние переменные (голод, усталость, безопасность, социальная связь, автономия) рассматриваются как **многомерное пространство состояний**. Мотивационный drive определяется как расстояние от текущего состояния к желаемому (setpoint):

$$
D(H_t) = \| H_t - H^* \|_W
$$

где $H^*$ — preferred state, $W$ — весовая матрица значимости.

Это уже частично заложено в ENIGMA как `NPCPersonality.drives_base` (control, significance, fear, desire — должны быть переинтерпретированы как **гомеостатические переменные**, а не как «типы эмоций»). `DriveResolver.resolve_drives` (`backend/app/services/npc/drive_resolver.py:24`) уже делает то, что нужно — проекцию L0+L1+L2.5+body → L3.

### 3.4 Self-Determination Theory (Deci & Ryan, 2000)

Три универсальные психологические потребности:
- **AUTONOMY** — свобода выбора и согласованность с истинным Я.
- **COMPETENCE** — ощущение эффективности и мастерства.
- **RELATEDNESS** — близость, привязанность, принадлежность.

В ENIGMA:
- AUTONOMY ↔ `NPCState.identity_integrity` + `WillState` + (новое) `consent_state`.
- COMPETENCE ↔ (новое) `self_model.competence` (можно вывести из истории успешных/провальных действий через `PatternDetector.query_evidence`).
- RELATEDNESS ↔ `SocialFabricTracker` + `AffectiveImprint.bond_signature` (новое).

---

## 4. Существующая карта кода ENIGMA → роль в новой архитектуре

Эта таблица — единственный источник правды для миграции. Каждая существующая сущность получает чёткое место в новой модели.

| Научный конструкт | Существующий файл/класс в ENIGMA | Роль в новой архитектуре | Действие |
|---|---|---|---|
| **Prediction** (что агент ожидает) | `PerceptualKernel` (`backend/app/models/npc_state.py:538`) | Субъективный прогноз угрозы/неопределённости | Расширить полями `expected_valence`, `expected_agency` |
| **Prediction error** | `PerceptualKernel.uncertainty`, `anomaly_score` | Расхождение prediction vs observation | Без изменений |
| **Belief (что агент считает истиной)** | `EpistemicStore` (`backend/app/services/npc/epistemic_store.py:14`) + `EpistemicRecord` (`app/domain/epistemology.py`) | Семантические убеждения о фактах мира | Без изменений |
| **Belief update** | `BeliefRevisionEngine.revise` (`backend/app/services/npc/belief_revision_engine.py:30`) | Ревизия убеждений на основе ClaimEvent | Без изменений |
| **Appraisal** (что событие значит лично) | ⚠ ЧАСТИЧНО: `WillEngine.resolve_intent_pressure`, `affect.scan_affective_resonance` | Главный новый слой — `AppraisalEngine` | **СОЗДАТЬ** (см. §7.1) |
| **Body state** (физиология) | `NPCState.body_state`, `combat/impact_engine.py`, `combat/injury_processor.py`, `combat/physiology_decay_handler.py` | HP, pain, fatigue, blood_loss, injuries | Без изменений |
| **Affect (низкоразмерное состояние)** | `affective_integrator`, `AffectiveImprint`, `affective_load`, `affective_memory` | V/A/D-вектор (см. §6.2) | **Расширить** до 3D |
| **Affective memory** (прошлые травмы) | `AffectiveImprint` (`app/models/affect.py:19`) | Импринты с сигнатурами | **Расширить** сигнатурами |
| **Motivation (needs)** | `NPCPersonality.drives_base`, `DriveResolver.resolve_drives` | Гомеостатические переменные + distance-to-setpoint | **Реинтерпретировать** semantics |
| **Self-model** | `NPCState.identity_integrity`, `NPCIdentityL1.active_traits`, `life_project` | Целостный контейнер self | **Расширить** в `SelfModel` (см. §6.5) |
| **Social model** | `SocialFabricTracker`, `CrystallizedBelief`, `RelationshipStore` | Матрица связей + модель других агентов | **Расширить** до `SocialModel` (см. §6.6) |
| **Policy selection** | `DecisionHub.compute` (`app/services/npc/decision_hub.py`) | Скоринг candidate intents | **Изменить интерфейс** (см. §7.5) |
| **Will (выбор при конфликте)** | `WillEngine.compute_willpower` (`app/services/will.py`) | Вычисление ΔU между alternative policies | **Переписать** как policy-comparator (см. §7.4) |
| **Action** | `Intent`, `IntentDTO` (`app/domain/intent.py`) | Каноническое действие агента | Без изменений |
| **Consequence** (физическое) | `EventCompiler` (`app/services/event_compiler.py:40`) | Геометрический резолвер для движения/коллизий | Без изменений |
| **Learning / Crystallization** | `BeliefCrystallizationEngine` + `PatternDetector` + `ResonanceEngine` | L1.5 → L2.5 transition (статистика → убеждение) | **Расширить** словарь трейтов (см. §9) |
| **Temporal evolution** | `TickOrchestrator.execute` (`app/services/tick_orchestrator.py:61`) | Каузальная очерёдность фаз | **Дополнить** вызовом `AppraisalEngine` в Фазе 3 |
| **Trauma (острая)** | `break_progress_engine.TRAUMA_TOPOLOGY` (4 типа) | Acute parameter updates of self/social model | **Расширить** топологию (см. §8) |
| **Stable traits** | `L1Chronicle` + `CalibrationEngine` | Гистерезис между L3_raw и L3_stable | Без изменений |
| **State writer** | `StateApplicator` (single-writer invariant) | Единый мутатор NPCState | **Расширить** payload-типами (AppraisalPayload, AffectPayload, etc.) |

**Главное наблюдение:** архитектору не нужно создавать новую психику с нуля. Нужно:

1. **Добавить недостающий слой** — `AppraisalEngine` (главный маппер event → персональный appraisal vector).
2. **Реинтерпретировать** существующие поля (`fear` в drives_base — это не «эмоция страха», а «гомеостатическая переменная потребности в безопасности»).
3. **Расширить** словарь в нескольких местах (трейты, сигнатуры, типы травм).
4. **Переписать** `WillEngine` как policy-comparator вместо threshold-классификатора.

---

## 5. Целевая архитектура — формальная

### 5.1 Главный цикл агента

```
┌──────────────────────────────────────────────────────────────┐
│                     WORLD (simulation)                       │
└──────────────────────────┬───────────────────────────────────┘
                           ↓
                    ┌──────────────┐
                    │  PERCEPTION  │  (PerceptualKernel, EpistemicStore)
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │   BELIEFS    │  (BeliefRevisionEngine)
                    └──────┬───────┘
                           ↓
                    ┌──────────────┐
                    │   APPRAISAL  │  (AppraisalEngine)  ← НОВОЕ
                    └──────┬───────┘
                           ↓
              ┌────────────┴────────────┐
              ↓                         ↓
       ┌──────────┐              ┌──────────────┐
       │  AFFECT  │              │  MOTIVATION  │
       │ (V,A,D)  │              │  (NeedVector)│
       └────┬─────┘              └──────┬───────┘
            └────────────┬─────────────┘
                         ↓
                  ┌──────────────┐
                  │  SELF MODEL  │  (identity, agency, competence, commitments)
                  └──────┬───────┘
                         ↓
                  ┌──────────────┐
                  │ POLICY VALUE │  (WillEngine — comparator)
                  └──────┬───────┘
                         ↓
                  ┌──────────────┐
                  │   DECISION   │  (DecisionHub — selector)
                  └──────┬───────┘
                         ↓
                  ┌──────────────┐
                  │    ACTION    │  (IntentDTO)
                  └──────┬───────┘
                         ↓
                      WORLD
```

### 5.2 Три дополнительные подпетли

Каждая запускается параллельно основному циклу, но с разной частотой:

#### 5.2.1 Петля обучения (perception → belief update)

```
Prediction → Observation → Prediction Error → Belief/Policy Update
```

В ENIGMA:
- `PerceptualKernel.uncertainty` → `BeliefRevisionEngine.revise(ClaimEvent)` → обновление `EpistemicRecord.confidence`.
- Запускается каждый раз, когда наблюдается расхождение между ожиданием и фактом.
- Не требует LLM — детерминированный.

#### 5.2.2 Петля идентичности (action → self-appraisal → identity update)

```
Action → Outcome → Self Appraisal → Identity Update
```

В ENIGMA:
- После исполнения действия `ActionConsequenceCompiler` фиксирует outcome.
- `ResonanceEngine.detect` находит паттерн (betrayal_chain, chronic_help, gaslighting — см. `app/services/memory/resonance_engine.py:143-207`).
- `BeliefCrystallizationEngine.crystallize` переносит статистику в `CrystallizedBelief`.
- `L1Chronicle` записывает `TraitDriftEvent`.
- `CalibrationEngine.stabilize` решает, стало ли поведение стабильной чертой (гистерезис).

#### 5.2.3 Социальная петля (моя модель тебя ↔ твоя модель меня)

```
MyModelOfYou ↔ YourModelOfMe
```

В ENIGMA:
- `SocialFabricTracker` — направленная связь source → target с trust/fear/affection/debt/respect.
- `EpistemicStore` хранит second-order beliefs: «A верит, что B утверждает P» (см. `belief_revision_engine.py:51`).
- Распространение слухов — `SocialEngine.propagate` (BFS по графу).

### 5.3 Концептуальная иерархия слоёв (L0–L3)

| Слой | Что хранит | Кто пишет | Персистентность | Существующий код |
|---|---|---|---|---|
| **L0** — Архетип | Базовые драйвы, voice_profile, backstory | Автор JSON | Статический | `NPCPersonality` |
| **L1** — Идентичность | Кристаллизованные черты (активные traits) | `ResonanceEngine` через `BeliefCrystallizationEngine` | Стабильная, обновляется редко | `NPCIdentityL1`, `CrystallizedBelief` |
| **L2** — Убеждения | EpistemicStore (что агент считает истиной) + AffectiveImprints (что агент чувствует по поводу прошлых событий) | `BeliefRevisionEngine` + `apply_conditioning` | Накопительная | `EpistemicStore`, `AffectiveImprint` |
| **L3** — Состояние | Текущее эфемерное состояние: drives, affect, perceptual_kernel | `StateApplicator` (single writer) | Тик-уровневая, пересчитывается | `NPCState` |
| **L3-stable** | Кристаллизованные дрейфы L3 | `CalibrationEngine` (phase lock gate) | Долгоживущая проекция L3 | `drives_runtime`, `strain_memory` |

---

## 6. Контракты данных (формальные пространства)

Все контракты — frozen dataclasses (immutable). Любая мутация только через `StateApplicator` с типизированным payload.

### 6.1 AppraisalVector

```python
# backend/app/models/psychology/appraisal.py  (НОВОЕ)

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class AppraisalVector:
    """
    Персональная оценка события агентом.
    Вычисляется AppraisalEngine на основе:
        Event + AgentState + EpistemicStore + SocialModel + SelfModel + BodyState
    Не хранится в NPCState — эфемерен, как и L3-проекция.
    """

    # ── Scherer CPM-inspired dimensions ──────────────────────────────────

    # Novelty / Prediction error: насколько событие неожиданно
    novelty: float                # 0.0..1.0

    # Intrinsic pleasantness / valence-anticipation
    pleasantness: float           # -1.0..+1.0 (negative = aversive)

    # Goal relevance & conduciveness
    goal_relevance: float         # 0.0..1.0
    goal_conduciveness: float     # -1.0..+1.0 (negative = obstructive)

    # Coping potential (Scherer's three subcomponents)
    control: float                # 0.0..1.0 (can agent influence?)
    power: float                  # 0.0..1.0 (can agent cope with consequences?)
    adjustment: float             # 0.0..1.0 (can agent adjust to outcome?)

    # Self-relevance / norm compatibility
    self_relevance: float         # 0.0..1.0
    norm_violation: float         # 0.0..1.0 (against agent's values/norms)
    identity_significance: float  # 0.0..1.0 (touches agent's core identity)

    # ── ENIGMA-specific extensions (Romance/SDT-relevant) ────────────────

    # SDT axes (Self-Determination Theory)
    autonomy_threat: float        # 0.0..1.0 (event reduces agent's agency)
    competence_threat: float      # 0.0..1.0 (event reduces agent's sense of effectiveness)
    relatedness_threat: float     # 0.0..1.0 (event threatens belonging/bond)
    relatedness_satisfaction: float  # 0.0..1.0 (event strengthens bond)

    # ── Derived helpers (read-only properties) ────────────────────────────

    @property
    def valence_prediction(self) -> float:
        """Sign-bucket of expected emotional valence. -1..+1."""
        return self.pleasantness + self.goal_conduciveness * 0.5 - self.norm_violation * 0.3

    @property
    def arousal_prediction(self) -> float:
        """Expected activation. 0..1."""
        return max(self.novelty, self.self_relevance, self.autonomy_threat, self.norm_violation)

    @property
    def dominance_prediction(self) -> float:
        """Expected sense of agency. -1..+1."""
        return self.control * 0.5 + self.power * 0.3 - self.autonomy_threat * 0.5

    @property
    def trauma_load(self) -> float:
        """
        Предиктор острой травмы. Если > 0.8 → AppraisalEngine сигнализирует
        BreakProgressEngine.apply_acute_trauma.
        """
        return (
            self.novelty * 0.2
            + (1.0 - self.power) * 0.3
            + self.self_relevance * 0.2
            + self.norm_violation * 0.15
            + self.autonomy_threat * 0.15
        )
```

### 6.2 AffectVector

```python
# backend/app/models/psychology/affect.py  (НОВОЕ, замещает ad-hoc affective_load)

from dataclasses import dataclass

@dataclass(frozen=True)
class AffectVector:
    """
    Низкоразмерное аффективное состояние по Russell's Circumplex + dominance axis.
    НЕ эмоция. Эмоция = интерпретация (см. §9).
    """

    valence: float     # -1.0..+1.0 (negative=averse, positive=approach)
    arousal: float     #  0.0..1.0 (low=calm, high=activated)
    dominance: float   # -1.0..+1.0 (negative=submissive, high=dominant)

    # ── Differential signatures (для резонанса с прошлыми травмами) ───────
    # Эти оси НЕ фундаментальные эмоции, а измерения, по которым
    # прошлые импринты резонируют с текущим состоянием.
    humiliation_load: float = 0.0   # 0.0..1.0
    intimacy_load: float = 0.0      # 0.0..1.0 (positive=intimacy-seeking, negative=aversion)
    abandonment_load: float = 0.0  # 0.0..1.0
```

### 6.3 NeedVector (гомеостатические переменные)

```python
# backend/app/models/psychology/needs.py  (НОВОЕ)

from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class NeedVector:
    """
    Многомерное пространство гомеостатических переменных.
    Каждое измерение имеет setpoint (preferred) и current value.
    Drive = weighted distance to setpoint.
    """

    # ── Физиологические (body-derived) ───────────────────────────────────
    safety: float           # 0.0..1.0 (1.0 = полностью безопасно)
    integrity: float        # 0.0..1.0 (1.0 = тело цело)
    energy: float           # 0.0..1.0 (1.0 = full energy, без fatigue)
    satiation: float        # 0.0..1.0 (food/water)

    # ── SDT (psychological) ─────────────────────────────────────────────
    autonomy: float         # 0.0..1.0 (1.0 = full agency)
    competence: float       # 0.0..1.0 (1.0 = effective)
    relatedness: float      # 0.0..1.0 (1.0 = connected)

    # ── ENIGMA-specific (semantic, derived from SocialModel + SelfModel) ─
    meaning: float          # 0.0..1.0 (alignment with life_project)
    identity_coherence: float  # 0.0..1.0 (consistency with self-model)

    # ── Setpoints (per-NPC, loaded from personality profile) ─────────────
    # Задаётся через NPCPersonality.setpoints или вычисляется из L0+L1.
    # Не входит в state, передаётся отдельно в MotivationEngine.

    @staticmethod
    def from_body_and_state(body_state: Dict, npc_state) -> "NeedVector":
        """Конвертация существующих NPCState полей в NeedVector."""
        # safety: 1 - threat_gradient
        # integrity: identity_integrity * body_integrity
        # energy: 1 - fatigue/100
        # satiation: from economy layer (если есть)
        # autonomy: derived from WillState (FREE=1.0, COERCED=0.3, BROKEN=0.0, ...)
        # competence: from PatternDetector success-rate
        # relatedness: from SocialFabricTracker (max affection across bonds)
        # meaning: from life_project FSM state
        # identity_coherence: identity_integrity
        ...

    @staticmethod
    def default_setpoints() -> "NeedVector":
        """Setpoints для среднего NPC. Переопределяются через NPCPersonality."""
        return NeedVector(
            safety=0.7, integrity=1.0, energy=0.8, satiation=0.7,
            autonomy=0.8, competence=0.6, relatedness=0.5,
            meaning=0.6, identity_coherence=0.9,
        )
```

### 6.4 MotivationVector

```python
# backend/app/models/psychology/motivation.py  (НОВОЕ)

from dataclasses import dataclass

@dataclass(frozen=True)
class MotivationVector:
    """
    Тяга к действию по категориям.
    Вычисляется MotivationDynamics из NeedVector (distance to setpoint) + AffectVector.
    НЕ является действием — это лишь вектор давления на DecisionHub.
    """

    approach_seeking: float      # 0..1 (go toward reward)
    avoidance_seeking: float     # 0..1 (go away from threat)
    affiliation_seeking: float   # 0..1 (go toward social bond)
    autonomy_seeking: float      # 0..1 (resist control, restore agency)
    meaning_seeking: float       # 0..1 (act in alignment with life_project)
    intimacy_seeking: float      # 0..1 (positive: approach intimate contact)
    intimacy_aversion: float    # 0..1 (negative: avoid intimate contact — trauma response)
    aggression_seeking: float   # 0..1 (hostile action toward source of pressure)
    submission_seeking: float   # 0..1 (comply to reduce pressure)
    freeze_seeking: float       # 0..1 (do nothing, dissociate)
```

### 6.5 SelfModel

```python
# backend/app/models/psychology/self_model.py  (НОВОЕ, композитный)

from dataclasses import dataclass, field
from typing import Dict, Tuple
from app.models.npc_state import NPCIdentityL1, BehaviorMaskState

@dataclass(frozen=True)
class SelfModel:
    """
    Динамическая модель агентом самого себя.
    Часть PsychState, обновляется через петлю идентичности.
    """

    # ── Stable identity (from L0 + L1) ───────────────────────────────────
    base_drives: Dict[str, float]            # from NPCPersonality.drives_base (L0)
    crystallized_traits: Dict[str, float]    # from NPCIdentityL1.active_traits (L1)

    # ── Self-appraisal state (volatile, updated by identity loop) ────────
    identity_integrity: float                # 0.0..1.0 (существующее поле)
    intimacy_integrity: float                # 0.0..1.0 (НОВОЕ — способность к интимной близости)
    sexual_autonomy: float                   # 0.0..1.0 (НОВОЕ — агентность в сексуальной сфере)
    trust_in_own_perception: float           # 0.0..1.0 (НОВОЕ — для газлайтинга)

    # ── Commitments / life project (FSM) ─────────────────────────────────
    life_project: str                        # current FSM state: ACTIVE/COLLAPSING/LOST/SEARCHING/COMMITTED
    active_commitments: Tuple[str, ...]       # IDs of active commitments (promises, obligations)

    # ── Consent state (для романтики/насилия) ────────────────────────────
    consent_state: str                       # UNDEFINED/GIVEN/WITHDRAWN/COERCED/INCAPABLE
    last_consent_target: str                 # npc_id
    last_consent_tick: int

    # ── Self-efficacy (derived from PatternDetector) ─────────────────────
    competence_recent: float                 # 0..1, rolling avg of recent success rate

    # ── Behavior mask (current persona overlay) ──────────────────────────
    behavior_mask: BehaviorMaskState         # существующий

    @staticmethod
    def from_npc_state(state) -> "SelfModel":
        """Проекция NPCState → SelfModel (для передачи в AppraisalEngine)."""
        return SelfModel(
            base_drives=dict(state.personality.drives_base) if state.personality else {},
            crystallized_traits=dict(state.identity_l1.active_traits) if state.identity_l1 else {},
            identity_integrity=state.identity_integrity,
            intimacy_integrity=getattr(state, "intimacy_integrity", 1.0),
            sexual_autonomy=getattr(state, "sexual_autonomy", 1.0),
            trust_in_own_perception=getattr(state, "trust_in_own_perception", 1.0),
            life_project=state.life_project,
            active_commitments=tuple(),
            consent_state=getattr(state, "consent_state", "UNDEFINED"),
            last_consent_target=getattr(state, "last_consent_target", ""),
            last_consent_tick=getattr(state, "last_consent_tick", 0),
            competence_recent=getattr(state, "competence_recent", 0.5),
            behavior_mask=state.behavior_mask,
        )
```

### 6.6 SocialModel

```python
# backend/app/models/psychology/social_model.py  (НОВОЕ, композитный)

from dataclasses import dataclass, field
from typing import Dict, Optional
from app.models.social_fabric import RelationshipSnapshot

@dataclass(frozen=True)
class SocialModel:
    """
    Модель социальных отношений агента.
    Композитный объект — НЕ мутатор. Читает данные из SocialFabricTracker
    и EpistemicStore при каждом вызове AppraisalEngine.
    """

    # ── Direct relationships (от SocialFabricTracker) ────────────────────
    # source_id = self, target_id = X
    outgoing: Dict[str, RelationshipSnapshot]  # {target_id: snapshot}

    # ── Inferred relationships (от EpistemicStore, second-order) ─────────
    # "Я верю, что Y думает обо мне Z"
    perceived_incoming: Dict[str, Dict]  # {source_id: {trust, fear, ...}}

    # ── Reputation in factions ───────────────────────────────────────────
    faction_reputation: Dict[str, float]   # {faction_id: reputation}

    # ── Group belonging (SDT relatedness) ───────────────────────────────
    primary_group: Optional[str]            # faction_id
    group_role: Optional[str]               # "leader", "member", "outcast"

    # ── Recent social events (window of last N events involving self) ────
    recent_betrayals: int
    recent_kindnesses: int
    recent_public_humiliations: int
    recent_intimate_violations: int        # НОВОЕ — separate from humiliations
```

### 6.7 PsychologicalState (композитный)

```python
# backend/app/models/psychology/psych_state.py  (НОВОЕ)

from dataclasses import dataclass

@dataclass(frozen=True)
class PsychologicalState:
    """
    Полный снимок психики агента для передачи в движки.
    НЕ persistent storage — эфемерный объект, собираемый каждый тик.
    Persistent storage остаётся NPCState (single source of truth через StateApplicator).
    """

    body_snapshot: dict          # from NPCState.body_state
    needs: NeedVector            # computed from body + state
    affect: AffectVector         # current affective state
    self_model: SelfModel        # identity projection
    social_model: SocialModel    # relationships snapshot
    beliefs: list                # from EpistemicStore.get_all_for_agent
    imprints: tuple              # from NPCState.affective_imprints
    perceptual_kernel: object    # NPCState.perceptual_kernel
    tick: int

    @staticmethod
    def build(npc_state, fabric_tracker, epistemic_store, faction_tracker, tick: int) -> "PsychologicalState":
        """Собирает снимок из всех источников. Pure function."""
        ...
```

---

## 7. Движки — контракты вычислений

### 7.1 AppraisalEngine

```python
# backend/app/services/psychology/appraisal_engine.py  (НОВОЕ)

from app.models.psychology.appraisal import AppraisalVector
from app.models.psychology.psych_state import PsychologicalState

class AppraisalEngine:
    """
    Главный новый слой. Превращает событие + состояние агента в персональный
    AppraisalVector. НЕ мутирует состояние. Pure function.

    Принцип: одно событие → N разных appraisal vectors для N разных агентов.

    Вызывается из TickOrchestrator._phase_3_appraisal (новая фаза, см. §11).
    """

    def appraise(
        self,
        event: "EventDTO",
        agent_state: PsychologicalState,
        setpoints: "NeedVector",
    ) -> AppraisalVector:
        """
        Вход: EventDTO (что произошло) + PsychState агента + NeedVector setpoints.
        Выход: AppraisalVector (каково значение события лично для этого агента).

        Реализация:
        1. Novelty: расхождение event vs EpistemicStore beliefs агента об источнике.
        2. Pleasantness: sign(goal_conduciveness_prediction) — базовая эвристика.
        3. Goal_relevance: пересечение event.target_id с active_commitments/self_model.
        4. Goal_conduciveness: polarity(event, life_project alignment).
        5. Control/Power/Adjustment: derive from self_model.competence_recent + WillState.
        6. Self_relevance: 1.0 если event.target_id == self или event.source == important_other.
        7. Norm_violation: lookup в norms_table (можно вынести в PersonalityProfile).
        8. Identity_significance: если event затрагивает self_model.life_project или commitments.
        9. SDT axes: autonomy_threat = 1.0 если event — приказ/принуждение/force.
                     relatedness_*  = lookup в SocialModel (есть ли связь с source).
        """
        ...
```

**Инварианты AppraisalEngine:**

- **Pure function.** Никаких side effects, никакого мутатора.
- **Personal.** Каждый вызов — для одного агента. Никаких глобальных таблиц «событие → эмоция».
- **LLM-free.** Полностью детерминированный Python. LLM используется только для интерпретации нарратива (DM agent), не для appraisal.

### 7.2 AffectDynamics

```python
# backend/app/services/psychology/affect_dynamics.py  (НОВОЕ, замещает affective_integrator частично)

from app.models.psychology.affect import AffectVector
from app.models.psychology.appraisal import AppraisalVector

class AffectDynamics:
    """
    Динамика аффективного состояния во времени.

    A_{t+1} = A_t + α · f(Appraisal) − λ · A_t

    где α — learning rate, λ — decay rate.
    Параметры модулируются self_model (например, identity_rigidity снижает α).
    """

    def update(
        self,
        current: AffectVector,
        appraisal: AppraisalVector,
        self_model: "SelfModel",
        dt: float = 1.0,
    ) -> AffectVector:
        """
        Pure function: текущий affect + appraisal + self-model → новый affect.
        """
        # α modulated by identity_rigidity: rigid agents resist affect shifts
        alpha = 0.3 * (1.0 - self_model.identity_integrity * 0.5)
        # λ decay rate — universal, can be tuned per-personality
        lambda_decay = 0.05

        # Target affect from appraisal
        target_valence = appraisal.valence_prediction
        target_arousal = appraisal.arousal_prediction
        target_dominance = appraisal.dominance_prediction

        # Discrete-time update with decay
        new_valence = current.valence + alpha * (target_valence - current.valence) - lambda_decay * current.valence * dt
        new_arousal = current.arousal + alpha * (target_arousal - current.arousal) - lambda_decay * current.arousal * dt
        new_dominance = current.dominance + alpha * (target_dominance - current.dominance) - lambda_decay * current.dominance * dt

        # Differential signatures (for imprint resonance)
        new_humiliation = max(0.0, current.humiliation_load + alpha * appraisal.norm_violation * (1.0 - appraisal.control) - lambda_decay)
        new_intimacy = current.intimacy_load + alpha * (appraisal.relatedness_satisfaction - appraisal.relatedness_threat) - lambda_decay * current.intimacy_load
        new_abandonment = max(0.0, current.abandonment_load + alpha * appraisal.relatedness_threat * 0.5 - lambda_decay)

        return AffectVector(
            valence=clamp(new_valence, -1.0, 1.0),
            arousal=clamp(new_arousal, 0.0, 1.0),
            dominance=clamp(new_dominance, -1.0, 1.0),
            humiliation_load=clamp(new_humiliation, 0.0, 1.0),
            intimacy_load=clamp(new_intimacy, -1.0, 1.0),
            abandonment_load=clamp(new_abandonment, 0.0, 1.0),
        )
```

### 7.3 MotivationDynamics

```python
# backend/app/services/psychology/motivation_dynamics.py  (НОВОЕ)

from app.models.psychology.needs import NeedVector
from app.models.psychology.affect import AffectVector
from app.models.psychology.motivation import MotivationVector

class MotivationDynamics:
    """
    Преобразует NeedVector + AffectVector → MotivationVector.

    Каждое мотивационное измерение вычисляется как функция от distance-to-setpoint
    по соответствующей потребности, модулированной текущим affect.

    D(H_t) = ||H_t - H*||_W  →  motivation_axis = w · D · affect_modulation
    """

    def compute(
        self,
        needs: NeedVector,
        setpoints: NeedVector,
        affect: AffectVector,
    ) -> MotivationVector:
        """
        Pure function. Возвращает эфемерный MotivationVector.
        """
        # Approach seeking: low pleasantness deficit → seek reward
        # If valence < 0 and arousal > 0.5 → avoidance_seeking rises
        # If relatedness deficit > threshold → affiliation_seeking
        # If autonomy deficit > threshold → autonomy_seeking
        # If intimacy_load > 0 → intimacy_seeking
        # If intimacy_load < 0 OR trauma imprints resonate → intimacy_aversion
        # ...
```

### 7.4 WillEngine (переписанный)

```python
# backend/app/services/psychology/will_engine.py  (ЗАМЕЩАЕТ app/services/will.py)

from app.models.psychology.motivation import MotivationVector
from app.models.psychology.psych_state import PsychologicalState

class WillEngine:
    """
    Переписанный WillEngine. Больше не threshold-классификатор.

    Принимает candidate policies (action alternatives) и возвращает
    для каждой expected utility. DecisionHub выбирает max (или softmax
    при стохастическом выборе).

    U(a) = E[goal_gain(a)]
         + E[need_reduction(a)]
         + E[identity_coherence(a)]
         + E[social_value(a)]
         − E[risk(a)]
         − E[effort(a)]

    Will(a) = U_chosen(a) − U_alternative(a) − C_control(a)

    где C_control(a) — стоимость волевого усилия (растёт при конфликте с affect/intimacy_aversion).
    """

    def evaluate(
        self,
        candidates: list,  # List[IntentDTO]
        agent_state: PsychologicalState,
        motivation: MotivationVector,
        affect: AffectVector,
        appraisal: AppraisalVector,
    ) -> "WillEvaluation":
        """
        Возвращает WillEvaluation — dict {intent: utility, will_strength, expected_state_delta}.
        """
        utilities = {}
        for action in candidates:
            u = (
                self._expected_goal_gain(action, agent_state)
                + self._expected_need_reduction(action, agent_state, motivation)
                + self._expected_identity_coherence(action, agent_state)
                + self._expected_social_value(action, agent_state)
                - self._expected_risk(action, agent_state, appraisal)
                - self._expected_effort(action, agent_state)
            )
            utilities[action] = u

        # Will strength = difference between top-2 candidates
        sorted_u = sorted(utilities.values(), reverse=True)
        will_strength = (sorted_u[0] - sorted_u[1]) if len(sorted_u) >= 2 else sorted_u[0]

        # Softmax probability for stochastic choice
        beta = self._precision(self_model=agent_state.self_model)
        probs = self._softmax(utilities, beta)

        return WillEvaluation(
            utilities=utilities,
            probabilities=probs,
            will_strength=will_strength,
            top_action=max(utilities, key=utilities.get),
        )

    def _precision(self, self_model) -> float:
        """
        β = precision / decisiveness.
        Низкая β → стохастический выбор (колебание).
        Высокая β → детерминированный (уверенность).
        Вычисляется из self_model.competence_recent и identity_integrity.
        """
        return 1.0 + self_model.competence_recent * 2.0 + self_model.identity_integrity
```

**Главное отличие от текущего `compute_willpower`:** новый WillEngine **не классифицирует** события и не выдаёт `WillState` как состояние-результат. Он оценивает конкретные candidate actions и возвращает распределение полезностей. `WillState` сохраняется как производная характеристика (см. §9.3), но больше не является центральной сущностью воли.

### 7.5 DecisionHub (изменённый интерфейс)

```python
# backend/app/services/npc/decision_hub.py  (ИЗМЕНЁННЫЙ интерфейс)

class DecisionHub:
    """
    Существующий DecisionHub получает:
        candidate_actions: List[IntentDTO]
        will_evaluation: WillEvaluation
        agent_state: PsychologicalState

    И больше не получает:
        fear=0.7, trust=0.3, ... (старые скалярные входы)

    DecisionHub по-прежнему комбинирует контексты (proximity, time, role,
    life_project) и возвращает финальный IntentDTO для исполнения.
    Но скоринг теперь принимается от WillEngine, а не вычисляется заново.
    """

    def compute(
        self,
        state: NPCState,
        event: EventContext,
        candidate_actions: list,
        will_evaluation: "WillEvaluation",
        psych_state: PsychologicalState,
    ) -> DecisionResult:
        """
        Изменение: вместо self._score(...) используется will_evaluation.utilities.
        Остальная логика (constraint checking, role gating) без изменений.
        """
        ...
```

---

## 8. Травма как обновление параметров модели

### 8.1 Принцип

Травма — **не** булев флаг `trauma_markers.add("sexual_assault")`. Травма — обновление параметров модели агента: priors, precisions, action policies. Конкретно:

| Параметр модели | Что обновляется при травме | Как выглядит в ENIGMA |
|---|---|---|
| Threat priors | `PerceptualKernel.threat_gradient` baseline растёт | `affective_memory` (SEL trace state) |
| Trust priors | `CrystallizedBelief(source=X, trait="fear")` weight растёт | `BeliefCrystallizationEngine.crystallize` |
| Self-model parameters | `identity_integrity` падает + `intimacy_integrity` падает (для сексуальной травмы) | `StateApplicator._apply_trauma_and_traits` |
| Action policies | Избегание действий в контексте, похожем на травматический | `AffectiveImprint.trigger_tags` + `scan_affective_resonance` |
| Precision weights | Снижение `trust_in_own_perception` (для газлайтинга) | НОВОЕ поле NPCState |
| Need setpoints | `NeedVector.intimacy` setpoint падает (для сексуальной травмы) | Расширение NPCPersonality.setpoints |

### 8.2 Acute trauma path

Текущий `BreakProgressEngine.calculate` — это **непрерывный дрейф** (стадии resistance → cracks → rationalization → adaptation → deformation). Этот путь сохраняется для хронического давления.

Для **острой травмы** (единомоментной) добавляется новый метод:

```python
# backend/app/services/npc/break_progress_engine.py  (РАСШИРЕНИЕ)

class BreakProgressEngine:
    # ... существующий calculate() для хроники ...

    ACUTE_TRAUMA_DELTAS: dict = {
        "near_death":              {"identity_integrity": -0.20, "intimacy_integrity": 0.0,  "trust_in_own_perception": 0.0},
        "sexual_assault":           {"identity_integrity": -0.25, "intimacy_integrity": -0.40, "trust_in_own_perception": -0.10},
        "torture":                  {"identity_integrity": -0.30, "intimacy_integrity": 0.0,  "trust_in_own_perception": -0.15},
        "gaslit_chronic":           {"identity_integrity": -0.15, "intimacy_integrity": 0.0,  "trust_in_own_perception": -0.30},
        "witnessing_atrocity":      {"identity_integrity": -0.10, "intimacy_integrity": 0.0,  "trust_in_own_perception": 0.0},
        "heartbreak":               {"identity_integrity": -0.05, "intimacy_integrity": -0.15, "trust_in_own_perception": 0.0},
        "intimate_betrayal":        {"identity_integrity": -0.10, "intimacy_integrity": -0.20, "trust_in_own_perception": -0.05},
        "humiliated_public":        {"identity_integrity": -0.05, "intimacy_integrity": 0.0,  "trust_in_own_perception": 0.0},
    }

    def apply_acute_trauma(
        self,
        state: NPCState,
        trauma_type: str,
        appraisal: AppraisalVector,
    ) -> "AcuteTraumaDelta":
        """
        Единомоментное обновление при острой травме. Перепрыгивает стадии слома.

        Критерий вызова: appraisal.trauma_load > 0.8.
        Тип травмы определяется AppraisalEngine (см. ниже).

        Возвращает дельту для StateApplicator.
        """
        deltas = self.ACUTE_TRAUMA_DELTAS.get(trauma_type, {})
        # Дельта умножается на magnitude appraisal (от 0.8 до 1.0)
        magnitude = (appraisal.trauma_load - 0.8) / 0.2  # 0..1
        scaled = {k: v * (0.5 + 0.5 * magnitude) for k, v in deltas.items()}
        return AcuteTraumaDelta(trauma_type=trauma_type, deltas=scaled)
```

### 8.3 Тип травмы выводится из Appraisal, а не из event_type

Это критичный момент. Тип травмы должен **не** определяться строкой `if event_type == "player_assaults_intimate"`, а выводиться из **комбинации компонент AppraisalVector**:

| Комбинация appraisal-компонент | Тип травмы |
|---|---|
| `novelty > 0.8 ∧ norm_violation > 0.7 ∧ self_relevance > 0.8 ∧ control < 0.3 ∧ intimacy_load < 0` | `sexual_assault` |
| `novelty > 0.9 ∧ self_relevance > 0.9 ∧ power < 0.2 ∧ (1 - integrity) > 0.5` | `near_death` |
| `self_relevance > 0.7 ∧ norm_violation > 0.7 ∧ trust_in_own_perception < 0.5` (хронически) | `gaslit_chronic` |
| `relatedness_threat > 0.7 ∧ intimacy_load > 0.3 ∧ identity_significance > 0.6` (от значимого другого) | `intimate_betrayal` |
| `norm_violation > 0.6 ∧ social_exposure > 0.7 ∧ self_relevance > 0.6` | `humiliated_public` |

Эта таблица — **не** ещё один сценаристский справочник. Это формальная функция от appraisal-вектора. Архитектор может реализовать её как простой `if/elif` или как классификатор над компонентами. Принципиально: вход — это appraisal, а не event_type.

---

## 9. Спецификация эмоций как интерпретаций

### 9.1 Эмоция — не фундаментальная переменная

Эмоции (`fear`, `anger`, `shame`, `love`, `lust`, `disgust`) **не хранятся** как фундаментальные величины в PsychState. Они — **контекстные интерпретации** (V/A/D + appraisal + action tendency), используемые:

1. Для нарратива (DM-агент получает метку эмоции для словесного описания).
2. Для VerbalizationContext (чтобы LLM знал, какого тона реплика ждать).
3. Для тестов/отладки (чтобы человек-разработчик видел «NPC зол»).

### 9.2 Таблица интерпретаций (reference, не exhaustive)

| Emotion label | Valence | Arousal | Dominance | Appraisal signatures |
|---|---|---|---|---|
| Fear | − | + | − | novelty+, power−, autonomy_threat+, control− |
| Anger | − | + | + | goal_conduciveness−, control+, norm_violation+ (other-blame) |
| Sadness | − | − | − | goal_conduciveness−, control−, adjustment− |
| Shame | − | −/+) | − | norm_violation+, self_relevance+, social_exposure+, control− |
| Guilt | − | − | − | norm_violation+, self_relevance+, control+ (self-blame) |
| Joy | + | + | + | goal_conduciveness+, pleasantness+, competence+ |
| Affection | + | − | + | relatedness_satisfaction+, intimacy_load+ |
| Lust | + | + | +/−) | intimacy_load+, arousal+, (special channel, см. §9.4) |
| Disgust | − | −/+) | + | norm_violation+, intimacy_aversion+, relatedness_threat+ |

### 9.3 WillState сохраняется, но как производная

```python
def derive_will_state(affect: AffectVector, motivation: MotivationVector, self_model: SelfModel) -> WillState:
    """
    Derives WillState from current psych state. Used for:
    - VerbalizationContext (LLM cue)
    - DMContract (for narration hooks)
    - Backward compat с существующим кодом (break_progress_engine).

    Не является primary truth — primary truth = utilities from WillEngine.
    """
    # BROKEN: identity_integrity < 0.2 + dominance < -0.5
    # DISSOCIATING: trust_in_own_perception < 0.3 + arousal < 0.3
    # PANICKED: arousal > 0.9 + dominance < -0.5
    # DISTRESSED: arousal > 0.6 + valence < -0.4
    # RELUCTANT: motivation conflict (approach_avoidance)
    # COMPLY: motivation.submission_seeking > 0.7 + autonomy_seeking < 0.3
    # FREE: default
    ...
```

### 9.4 Lust как специальный мотивационный канал

Lust **не** сводится к (valence, arousal, dominance). Это отдельный мотивационный канал в `MotivationVector.intimacy_seeking` + `intimacy_aversion`. Внутри него свои переменные:

- `sexual_salience` — реактивность на сексуальные стимулы (модулируется гормонами, fatigue, imprint resonance).
- `approach_motivation` — целевая тяга.
- `reward_expectation` — прогноз удовольствия от контакта (обучается через `BeliefCrystallizationEngine`).
- `inhibition` — торможение (нормы, страх, тревога).
- `social_norm_cost` — социальная цена действия.

Эти переменные живут в `MotivationVector` и `AffectVector.intimacy_load`. `lust` как эмоция выводится как `intimacy_seeking > 0.6 ∧ intimacy_aversion < 0.2 ∧ arousal > 0.5` для нарратива.

---

## 10. Маппинг на существующий код (миграционная карта)

### 10.1 Что остаётся без изменений

- `StateApplicator` (single-writer invariant).
- `CalibrationEngine.stabilize` (phase lock gate).
- `L1Chronicle` (causal trace).
- `PatternDetector`, `ResonanceEngine` (pattern → trait).
- `BeliefRevisionEngine`, `EpistemicStore` (epistemic layer).
- `EventCompiler` (geometric resolver).
- `TickOrchestrator.execute` (causal ordering).
- `NPCPersonality`, `NPCIdentityL1` (static identity).
- `PerceptualKernel` (subjective prediction).

### 10.2 Что расширяется

| Сущность | Что добавляется |
|---|---|
| `NPCState` | + `intimacy_integrity: float = 1.0` |
|  | + `sexual_autonomy: float = 1.0` |
|  | + `trust_in_own_perception: float = 1.0` |
|  | + `consent_state: ConsentState = UNDEFINED` |
|  | + `last_consent_target: str = ""` |
|  | + `last_consent_tick: int = 0` |
|  | + `attachment_bonds: Dict[str, AttachmentBond]` |
| `AffectiveImprint` | + `intimacy_violation_signature: float = 0.0` |
|  | + `bond_signature: float = 0.0` |
|  | + `lust_signature: float = 0.0` |
|  | + `disgust_signature: float = 0.0` |
| `ResonanceProfile` | + `intimacy_resonance`, `bond_resonance`, `lust_resonance`, `disgust_resonance` |
| `CrystallizedBelief.trait` | расширение словаря трейтов: `love`, `disgust`, `lust`, `awe`, `loyalty`, `infatuation` (в дополнение к `fear`, `trust`) |
| `BeliefCrystallizationEngine` | расширение `_TRAIT_TO_DRIVE_SENSITIVITY` mapping |
| `TRAUMA_TOPOLOGY` | + `sexual_assault`, `intimate_betrayal`, `heartbreak`, `gaslit`, `molested`, `comforted` |
| `BreakProgressEngine` | + `apply_acute_trauma()` метод |
| `_REACTION_RULES` (ReactionSubscriber) | замена на appraisal-modulated правила (см. §10.4) |
| `EVENT_REPUTATION_IMPACT` (ReputationEngine) | + новые записи для `SEXUAL_ASSAULT`, `INTIMATE_VIOLATION`, `EMOTIONAL_ABUSE` |
| `SocialEngine.NEGATIVE_EVENTS` | + `player_assaults_intimate`, `player_molests`, `player_gaslights` |
| `_BASE_DELTAS` (social_deltas) | замена на appraisal-modulated deltas |
| `IntentPressureProfile` | сохраняется как **адаптер** к старому интерфейсу `compute_willpower`; фактически вычисляется из Appraisal |

### 10.3 Что переписывается

| Сущность | Действие |
|---|---|
| `app/services/will.py` `resolve_intent_pressure` | **DEPRECATE**. Заменяется на `AppraisalEngine.appraise` → `IntentPressureProfile.from_appraisal()` адаптер. |
| `app/services/will.py` `compute_willpower` | **ПЕРЕПИСАТЬ** на policy-comparator (см. §7.4). |
| `app/services/affect.py` `scan_affective_resonance` | **РАСШИРИТЬ** до 4 сигнатур (добавить intimacy/bond/lust/disgust). |
| `app/services/affect.py` `distort_pressure` | Без изменений в логике, расширить ResonanceProfile consumption. |
| `app/services/reaction/reaction_rules.py` `_REACTION_RULES` | **ЗАМЕНИТЬ** на appraisal-modulated rules. |

### 10.4 Как замена event-specific правил на appraisal-modulated

Старый код:
```python
_REACTION_RULES["player_attacks"] = (15.0, 10.0, -8.0)  # stress, fear, trust_loss
```

Новый код:
```python
def compute_reaction_delta(
    appraisal: AppraisalVector,
    self_model: SelfModel,
    social_model: SocialModel,
) -> ReactionDelta:
    """
    Персонифицированная реакция свидетеля.
    Один и тот же event даёт разные дельты для разных свидетелей.
    """
    # Stress: arousal × novelty × self_relevance
    stress_delta = appraisal.arousal_prediction * 20.0 * appraisal.self_relevance

    # Fear: low dominance × high novelty × high relatedness_threat (если target — знакомый)
    relatedness_factor = 1.0 if social_model.has_relationship_with(appraisal.target_id) else 0.3
    fear_delta = (1.0 - appraisal.dominance_prediction) * 0.5 * appraisal.novelty * relatedness_factor * 10.0

    # Trust loss toward source: norm_violation × self_relevance
    trust_delta = -appraisal.norm_violation * appraisal.self_relevance * 8.0

    return ReactionDelta(stress=stress_delta, fear=fear_delta, trust=trust_delta)
```

**Суть миграции:** справочник `_REACTION_RULES` (11 записей) и `_BASE_DELTAS` (12 записей) **не** расширяются до 50+ записей для новых категорий. Они **заменяются** на одну функцию `compute_reaction_delta(appraisal, self_model, social_model)`.

### 10.5 Существующие движки становятся специализированными потребителями

```
AppraisalEngine.appraise(event, agent_state)
       │
       ├─→ AffectDynamics.update(...)         → обновляет AffectVector
       │
       ├─→ MotivationDynamics.compute(...)     → обновляет MotivationVector
       │
       ├─→ WillEngine.evaluate(candidates,...) → возвращает utilities
       │      │
       │      └─→ DecisionHub.compute(..., will_evaluation, ...) → IntentDTO
       │
       ├─→ ReactionSubscriber.handle(...) — теперь appraisal-modulated
       │
       ├─→ BreakProgressEngine.apply_acute_trauma(...) — если trauma_load > 0.8
       │
       └─→ BeliefCrystallizationEngine.crystallize(...) — на основе EventMemory,
                                                          не appraisal (он отдельно)
```

---

## 11. Фазовый план развёртывания

### 11.1 Общие принципы миграции

1. **Параллельная разработка, не big-bang.** Каждый Phase (A–F) — отдельный PR с backward-compat адаптерами.
2. **Все новые модели в `app/models/psychology/` и `app/services/psychology/`.** Старый код не ломается.
3. **Тесты на каждом Phase.** Базовый набор: 10 синтетических сценариев (см. §13.3) должен проходить до перехода к следующему Phase.
4. **Feature flag `psy_arch_01_enabled`** для переключения между старым и новым путем. На время миграции обе версии живут параллельно.

### 11.2 Фазовая разбивка

#### Phase A — Формальные пространства (1 неделя)

**Цель:** создать все контрактные dataclasses в `app/models/psychology/`.

**Задачи:**
- A1. Создать `app/models/psychology/appraisal.py` с `AppraisalVector` (см. §6.1).
- A2. Создать `app/models/psychology/affect.py` с `AffectVector` (см. §6.2).
- A3. Создать `app/models/psychology/needs.py` с `NeedVector` (см. §6.3).
- A4. Создать `app/models/psychology/motivation.py` с `MotivationVector` (см. §6.4).
- A5. Создать `app/models/psychology/self_model.py` с `SelfModel` (см. §6.5).
- A6. Создать `app/models/psychology/social_model.py` с `SocialModel` (см. §6.6).
- A7. Создать `app/models/psychology/psych_state.py` с `PsychologicalState` (см. §6.7).
- A8. Создать `app/models/psychology/consent.py` с `ConsentState` enum + `AttachmentBond` dataclass.
- A9. Расширить `NPCState` (в `app/models/npc_state.py`) новыми полями (intimacy_integrity, sexual_autonomy, trust_in_own_perception, consent_state, attachment_bonds).
- A10. Расширить `AffectiveImprint` (в `app/models/affect.py`) новыми сигнатурами.
- A11. Расширить `ResonanceProfile` (в `app/models/affect.py`) новыми осями резонанса.

**Критерии приёмки Phase A:**
- Все новые dataclasses проходят `mypy --strict`.
- Существующие тесты NPCState не падают (поля добавлены с дефолтами).
- Базовый test_psych_state_build проходит (создание снимка из NPCState).

#### Phase B — AppraisalEngine (2 недели)

**Цель:** реализовать центральный новый слой.

**Задачи:**
- B1. Создать `app/services/psychology/appraisal_engine.py` с `AppraisalEngine.appraise(event, agent_state, setpoints) -> AppraisalVector`.
- B2. Реализовать все 11 компонент appraisal-вектора (novelty, pleasantness, goal_relevance, goal_conduciveness, control, power, adjustment, self_relevance, norm_violation, identity_significance, SDT axes).
- B3. Тесты: 10 эталонных сценариев (см. §13.3). Для каждого — фиксированный event + agent_state → ожидаемый appraisal vector (±0.05 tolerance).
- B4. Интегрировать вызов `AppraisalEngine.appraise` в `TickOrchestrator._run_core_phases` (новая Фаза 3.5).
- B5. Feature flag: appraisal векторы логируются, но пока не потребляются.

**Критерии приёмки Phase B:**
- AppraisalEngine покрывается unit-тестами на 11 компонент.
- TickOrchestrator успешно вызывает AppraisalEngine на каждом тике (логи видны).
- Перформанс: один appraisal < 0.5 ms (pure Python, no LLM).

#### Phase C — AffectDynamics (1 неделя)

**Цель:** переписать affect update как динамику 3D-вектора.

**Задачи:**
- C1. Создать `app/services/psychology/affect_dynamics.py` с `AffectDynamics.update(current, appraisal, self_model)`.
- C2. Реализовать обновление valence/arousal/dominance по формуле `A_{t+1} = A_t + α·f(Appraisal) − λ·A_t`.
- C3. Реализовать обновление дифференциальных сигнатур (humiliation/intimacy/abandonment).
- C4. Создать адаптер `AffectVector → NPCState.affective_load` для backward compat (legacy потребители продолжают работать).
- C5. Расширить `affect.scan_affective_resonance` до 4 сигнатур (intimacy_violation, bond, lust, disgust).
- C6. Тесты: 5 сценариев "событие X → ожидаемое смещение affect".

**Критерии приёмки Phase C:**
- AffectDynamics не нарушает существующий affective_integrator pipeline.
- NPCState.affective_load корректно обновляется из AffectVector.valence и .arousal.
- affect.scan_affective_resonance корректно реагирует на расширенные сигнатуры.

#### Phase D — MotivationDynamics (1 неделя)

**Цель:** переинтерпретировать drives как гомеостатические переменные.

**Задачи:**
- D1. Создать `app/services/psychology/motivation_dynamics.py`.
- D2. Реализовать `NeedVector.from_body_and_state(body_state, npc_state)`.
- D3. Реализовать `MotivationDynamics.compute(needs, setpoints, affect) -> MotivationVector`.
- D4. Реализовать гомеостатическую формулу: `motivation_axis = w · distance(need, setpoint) · affect_modulation`.
- D5. Создать конфигурацию `setpoints` для стандартного NPC (можно вынести в `app/core/constants.py`).
- D6. Тесты: для каждого motivation axis — 2 сценария (need deficit + нет deficit → ожидаемое значение motivation).

**Критерии приёмки Phase D:**
- Все 9 motivation axes вычисляются и логируются.
- NeedVector корректно выводится из существующих полей NPCState (без миграции данных).
- DriveResolver продолжает работать параллельно (он использует `drives_base`, а MotivationDynamics — `NeedVector` — это две проекции одного и того же).

#### Phase E — WillEngine переписка (2 недели)

**Цель:** заменить threshold-классификатор на policy-comparator.

**Задачи:**
- E1. Создать `app/services/psychology/will_engine.py` (новый, рядом со старым will.py).
- E2. Реализовать `WillEngine.evaluate(candidates, agent_state, motivation, affect, appraisal) -> WillEvaluation`.
- E3. Реализовать 5 компонент utility: `_expected_goal_gain`, `_expected_need_reduction`, `_expected_identity_coherence`, `_expected_social_value`, `_expected_risk`, `_expected_effort`.
- E4. Реализовать `_precision` (β для softmax).
- E5. Реализовать `derive_will_state(affect, motivation, self_model) -> WillState` — для backward compat с `BreakProgressEngine` и `VerbalizationContext`.
- E6. Создать адаптер `IntentPressureProfile.from_appraisal(appraisal) -> IntentPressureProfile` — для backward compat с reaction_subscriber, social_engine (они пока потребляют старый формат).
- E7. Тесты: для каждого из 10 эталонных сценариев — сравнение utilities топ-3 candidate actions.
- E8. Feature flag: переключение между старым `compute_willpower` и новым `WillEngine.evaluate`.

**Критерии приёмки Phase E:**
- WillEngine корректно выбирает между "resist" и "comply" для конфликтной ситуации (player угрожает NPC, который может либо сдаться, либо сопротивляться).
- Воля = ΔU между топ-2 candidates ≥ 0.2 для случая уверенного отказа, ≤ 0.05 для случая колебания.
- Все существующие consumers `WillState` (VerbalizationContext, BreakProgressEngine, DMContractBuilder) продолжают работать через `derive_will_state`.

#### Phase F — DecisionHub интеграция (1 неделя)

**Цель:** научить DecisionHub принимать `WillEvaluation` вместо скалярных fear/trust.

**Задачи:**
- F1. Расширить `DecisionHub.compute` сигнатурой: добавить параметр `will_evaluation: WillEvaluation`.
- F2. Заменить внутренний scoring на `will_evaluation.utilities` для ranking candidates.
- F3. Сохранить constraint checking (proximity, role gating, can_move, can_speak) — без изменений.
- F4. Расширить `ReactionSubscriber.handle` для использования appraisal-modulated `compute_reaction_delta`.
- F5. Расширить `BreakProgressEngine.apply_acute_trauma` и интегрировать вызов при `appraisal.trauma_load > 0.8`.
- F6. Удалить feature flag — новый путь становится единственным.

**Критерии приёмки Phase F:**
- DecisionHub успешно выбирает action на основе utility ranking.
- ReactionSubscriber генерирует разные дельты для разных свидетелей одного события (эмерджентность).
- Тест 10 эталонных сценариев проходит end-to-end.

### 11.3 Общая длительность

~8 недель разработки + 2 недели стабилизации/калибровки = **~10 недель**.

---

## 12. Запреты и анти-паттерны

### 12.1 Категорически запрещено

1. **Не создавать отдельные файлы для каждой эмоции или социального конструкта.**
   - ❌ `app/services/emotions/love.py`
   - ❌ `app/services/emotions/lust.py`
   - ❌ `app/services/emotions/shame.py`
   - ❌ `app/services/psychology/trauma_types/sexual_assault.py`
   - ✅ Все эмоции — конфигурация модели, не код.

2. **Не расширять event-specific справочники.**
   - ❌ Добавление новых записей в `_REACTION_RULES`, `_BASE_DELTAS`, `EVENT_REPUTATION_IMPACT`, `TRAUMA_TOPOLOGY` для каждой новой категории действий (romance, molestation, etc.).
   - ✅ Заменять эти справочники на appraisal-modulated функции.

3. **Не хранить эмоции как скалярные фундаментальные переменные.**
   - ❌ `NPCState.fear = 0.7`
   - ❌ `NPCState.love = 0.4`
   - ✅ Хранить `AffectVector` (valence/arousal/dominance + signatures). Эмоция — производная.

4. **Не использовать LLM для appraisal.**
   - AppraisalEngine — pure Python, deterministic, < 0.5 ms.
   - LLM используется только для нарратива (DM agent) и интерпретации ввода (LLMCompressor), не для оценки события.

5. **Не нарушать single-writer invariant.**
   - Любая мутация NPCState — только через `StateApplicator._apply_deltas`.
   - Любой new payload (AppraisalPayload, AffectPayload, etc.) — extends `StateDeltas` с domain tag.

6. **Не мутация L0 (NPCPersonality).** Только L1/L2/L3 могут меняться.

### 12.2 Категорически требуется

1. **Pure functions в движках.** `AppraisalEngine.appraise`, `AffectDynamics.update`, `MotivationDynamics.compute`, `WillEngine.evaluate` — без side effects, без сохранения состояния. Эфемерность.

2. **Determinism.** При том же (event, agent_state) → тот же appraisal. Никакого RNG в appraisal.

3. **Backward-compat адаптеры** на каждом Phase для сохранения работоспособности существующих consumers.

4. **Trace causality.** Каждый шаг аппаратного обновления должен логироваться через `jsonl_log` с уникальным `event_id`, чтобы L1Chronicle мог восстановить цепочку.

5. **Feature flag** `psy_arch_01_enabled` (default: false) до полного завершения Phase F.

---

## 13. Критерии приёмки

### 13.1 Общие критерии (после Phase F)

1. **Эмерджентность.** Один и тот же event «Орм обнял Люсю» даёт разные дельты для трёх свидетелей: NPC A (любовник Орма — relatedness_satisfaction=0.8 → positive affect), NPC B (враг — goal_conduciveness=−0.7 → negative affect), NPC C (незнакомец — novelty low → near-zero affect). Доказать тестом.

2. **O(N) scaling.** Добавление нового типа события (например, `player_gifts_ring`) не требует написания нового кода в `will.py`, `reaction_rules.py`, `social_deltas.py`, `break_progress_engine.py`. Достаточно описать новый event как (proposition, appraisal signatures) в конфигурации.

3. **Determinism & Replay.** При одинаковом seed и идентичной последовательности событий результат полностью воспроизводим. L1Chronicle может быть проигран назад без расхождений.

4. **No Pókemon emotions.** Отсутствуют файлы `love.py`, `lust.py`, `shame.py`, `trauma_sexual.py`. Все эти феномены — конфигурация.

### 13.2 Проверка архитектурных инвариантов

| Инвариант | Как проверить |
|---|---|
| Single-writer для NPCState | `grep -r "NPCState\." backend/app/services/ \| grep -v state_applicator` должен быть пустым |
| Pure functions в движках | Все методы в `psychology/*.py` имеют `@staticmethod` или не имеют `self`-мутации. Проверить через mypy + ручной ревью. |
| Appraisal не использует LLM | `grep -r "router\|llm\|provider" backend/app/services/psychology/appraisal_engine.py` должен быть пустым |
| Epistemic Boundary | `grep -r "state.beliefs\|state.affective_imprints" backend/app/services/psychology/appraisal_engine.py` должен быть пустым (AppraisalEngine не читает скрытые слои напрямую, только через PsychState) |

### 13.3 Эталонные тестовые сценарии

10 сценариев, каждый — JSON-файл в `backend/tests/sandbox/psy_arch_scenarios/`. Для каждого задано:

- `event.json` — EventDTO.
- `agent_state.json` — снимок NPCState + EpistemicStore + SocialFabricTracker.
- `expected_appraisal.json` — ожидаемый AppraisalVector (±0.05 tolerance per component).
- `expected_affect_delta.json` — ожидаемое смещение AffectVector.
- `expected_motivation.json` — ожидаемый MotivationVector.
- `expected_will_evaluation.json` — для 2-3 candidate actions, ожидаемые utilities.

Сценарии:

1. **Свидетель объятия знакомым.** Event: hug. Agent: NPC_A (lover). Expect: positive affect.
2. **Свидетель объятия врагом.** Event: hug. Agent: NPC_B (enemy of hugger). Expect: negative affect, autonomy_threat moderate.
3. **Свидетель объятия незнакомцем.** Event: hug. Agent: NPC_C (stranger). Expect: low everything.
4. **Игрок угрожает NPC средним страхом.** Event: threat. Agent: NPC_D (fear_drive=0.6). Expect: high arousal, low dominance, autonomy_threat high.
5. **Игрок угрожает NPC с высокой храбростью.** Event: threat. Agent: NPC_E (fear_drive=0.1, aggression=0.7). Expect: aggression_response — anger-interpretation, high dominance.
6. **Sexual assault на NPC с прошлой травмой.** Event: intimate assault. Agent: NPC_F (has trauma imprint with intimacy_violation_signature=0.8). Expect: trauma_load > 0.9, acute trauma triggered.
7. **Sexual assault на NPC без прошлой травмы.** Event: same. Agent: NPC_G (no imprints). Expect: trauma_load > 0.8, acute trauma triggered, but recovery rate higher.
8. **Gaslighting repeated.** Series of 5 events that contradict agent's perception. Agent: NPC_H. Expect: trust_in_own_perception drops over time, eventually < 0.3.
9. **Heartbreak (romantic betrayal).** Event: discovered infidelity of bond partner. Agent: NPC_I (has bond with target). Expect: intimacy_integrity drop, relatedness_threat high.
10. **Comforting action.** Event: comfort by trusted friend. Agent: NPC_J (in distress). Expect: positive valence shift, intimacy_integrity recovery.

### 13.4 Перформанс-критерии

- AppraisalEngine.appraise: ≤ 0.5 ms per call (pure Python, no I/O).
- AffectDynamics.update: ≤ 0.2 ms.
- MotivationDynamics.compute: ≤ 0.2 ms.
- WillEngine.evaluate (5 candidates): ≤ 1 ms.
- Tick with 10 NPCs, all getting appraised: ≤ 50 ms total for psychology phase.

---

## 14. Открытые вопросы для архитектора

Эти вопросы требуют отдельного ADR-документа каждый. Архитектор должен либо принять решение (с указанием rationale), либо эскалировать владельцу продукта.

### Q1. Хранилище AttachmentBond

`SelfModel.attachment_bonds: Dict[str, AttachmentBond]` — где персистится?

- Опция A: внутри `NPCState` (новое поле). Миграция NPCState.
- Опция B: отдельный store (как `SocialFabricTracker`).
- Опция C: через `EpistemicStore` как особый тип proposition.

**Рекомендация:** B (отдельный store), потому что attachment bonds — это directed graph, а не скалярное поле NPCState. По аналогии с `SocialFabricTracker`.

### Q2. Источник candidate actions для WillEngine

Кто генерирует `candidate_actions: List[IntentDTO]`, которые передаются в `WillEngine.evaluate`?

- Опция A: `DecisionHub` сам генерирует (по существующей схеме `Intent` enum).
- Опция B: Отдельный `CandidateGenerator` движок (новый).
- Опция C: LLM генерирует 3-5 вариантов, WillEngine их оценивает.

**Рекомендация:** A (DecisionHub), потому что текущий DecisionHub уже умеет генерировать intents на основе context. LLM-генерация кандидатов — отдельная будущая фаза.

### Q3. Граница между LLM и Python для нарратива эмоций

Эмоция как интерпретация (см. §9.2) — это таблица внутри Python (fast, deterministic), или LLM-генерация на основе (valence, arousal, dominance, appraisal)?

- Опция A: Таблица в Python (текущий VerbalizationContext._WILL_STATE_NUANCE approach).
- Опция B: LLM генерирует эмоцию на основе V/A/D + appraisal context.
- Опция C: Гибрид — Python даёт 2-3 candidate labels, LLM выбирает подходящий с учётом контекста.

**Рекомендация:** C. Python даёт label candidates быстро, LLM финализирует с учётом нюансов.

### Q4. Параметр β (precision) в softmax

Как β (precision) вычисляется и насколько он должен быть динамическим?

- Опция A: Константа per-NPC (из NPCPersonality).
- Опция B: Динамическая, из self_model.competence_recent + identity_integrity (как в §7.4).
- Опция C: Bayesian update на основе прошлых верных/неверных выборов.

**Рекомендация:** B. Это даёт персонологичную вариативность без сложности Bayesian inference.

### Q5. Семейная/интимная фракция

В `EVENT_REPUTATION_IMPACT` мы упоминали «women» фракцию. Как обрабатывать динамические фракции (семья цели, близкий круг)?

- Опция A: Статические фракции, описанные в `factions.json`.
- Опция B: Динамические группировки — выводятся из `SocialFabricTracker` (kin, bond-partner, etc.).
- Опция C: Гибрид — статические фракции + временное членство через `attachment_bonds`.

**Рекомендация:** C. Статика + overlay.

### Q6. Совместимость со старым `fear`/`trust` скалярами в RelationshipStore

`RelationshipStore.update(campaign_id, source, target, delta={"fear": 30.0, "trust": -30.0})` — текущий интерфейс. Как мигрировать?

- Опция A: Сохранить скаляры, добавить `affect_state` field в RelationshipSnapshot.
- Опция B: Полностью заменить скаляры на V/A/D-вектор.
- Опция C: Оставить `trust`/`fear` как высокоуровневые aggregate над V/A/D (для верификации извне).

**Рекомендация:** C. Aggregate-проекция из V/A/D. Сохраняет back-compat.

### Q7. Migration path для существующих сейвов

Старые сейвы (campaign_state.json) не имеют `intimacy_integrity`, `consent_state`, etc. Как загружать?

- Опция A: Default- значения при загрузке (1.0 для всех integrity, UNDEFINED для consent).
- Опция B: Выводить из существующих полей (если trauma_markers contains "sexual_assault" → intimacy_integrity = 0.5).
- Опция C: Принудительный reset для всех существующих кампаний.

**Рекомендация:** A (defaults). B (inference) как nice-to-have.

### Q8. Логирование appraisal для дебага

AppraisalVector имеет 13+ компонент. Как логировать, чтобы не залить диск?

- Опция A: Полный лог только при `settings.dm_debug=True`.
- Опция B: Только короткая сигнатура (`{novelty, valence, arousal, trauma_load}`).
- Опция C: Семплирование (каждый N-ый тик).

**Рекомендация:** B + A. Короткая сигнатура всегда, полный вектор при dm_debug.

---

## 15. Ссылки и литература

### 15.1 Научные источники

1. **Scherer, K. R. (2001).** Appraisal Processes in Emotion: Theory, Methods, Research. Component Process Model. — Canonical reference for appraisal theory.
2. **Friston, K. (2010).** The free-energy principle: a unified brain theory? Nature Reviews Neuroscience. — Active Inference framework.
3. **Deci, E. L., & Ryan, R. M. (2000).** The "what" and "why" of goal pursuits: Human needs and the self-determination of behavior. Psychological Inquiry. — SDT.
4. **Russell, J. A. (1980).** A circumplex model of affect. Journal of Personality and Social Psychology. — V/A circumplex.
5. **Mehrabian, A. (1996).** Pleasure-arousal-dominance: A general framework for describing and measuring individual differences in temperament. — VAD model.
6. **Pezzulo, G., Rigoli, F., & Friston, K. (2018).** Hierarchical Active Inference: A Theory of Motivated Control. Trends in Cognitive Sciences. — Motivation through active inference.

### 15.2 Внутренние ADR

- **ADR-031** — WillpowerGate (Cumulative Strain Model)
- **ADR-035** — Semantic Action priority
- **ADR-037** — Embodied Vector
- **ADR-049** — Active Inference Affect
- **ADR-055** — Attention Capture
- **ADR-083** — Invariant of Violence
- **ADR-086** — Personality modulation of suppression
- **ADR-O-146** — Perception-derived pressure
- **ADR-O-147** — CJK retry
- **ADR-O-201** — EventCompiler as geometric resolver
- **ADR-O-208** — DRP Phase II (no direct mutation by TIFL)
- **ADR-O-211** — Phase Lock Gate (CalibrationEngine)
- **ADR-O-304** — Trait Stabilization Hysteresis
- **ADR-O-305** — BeliefCrystallizationEngine input
- **ADR-O-306** — EvidenceOfPersistence as statistics
- **ADR-O-307** — Asymmetric Trauma (×6)
- **ADR-O-308** — Error propagation (no silent failures)
- **ADR-O-313** — DM agent doesn't generate NPC speech
- **ADR-O-322** — Markdown wrapper stripping
- **ADR-O-330** — MacroMovementGoal

### 15.3 Существующие файлы, на которые опирается контракт

| Файл | Что взять за основу |
|---|---|
| `backend/app/models/npc_state.py` | NPCState, NPCPersonality, NPCIdentityL1, PerceptualKernel, WillState, EmotionTag |
| `backend/app/models/will.py` | IntentPressureProfile, WillResponseDTO, EmbodiedVector, WillState |
| `backend/app/models/affect.py` | AffectiveImprint, ResonanceProfile, ResponseBias |
| `backend/app/models/delta_payloads.py` | EmotionPayload, SocialPayload, PhysiologyPayload, IdentityPayload, PerceptionPayload, ReputationPayload |
| `backend/app/models/state_delta.py` | StateDeltas, DeltaDomain |
| `backend/app/models/epistemology.py` | Proposition, ClaimEvent, EpistemicRecord, Predicate, SpeechAct, SocialIntent |
| `backend/app/models/identity_events.py` | CrystallizedBelief, EvidenceOfPersistence, TraitDriftEvent, L1EventStream |
| `backend/app/models/social_fabric.py` | RelationshipSnapshot, RelationshipDelta |
| `backend/app/services/npc/state_applicator.py` | Single-writer for NPCState |
| `backend/app/services/npc/calibration_engine.py` | Phase Lock Gate (Hysteresis) |
| `backend/app/services/npc/break_progress_engine.py` | Break stages, Trauma topology |
| `backend/app/services/npc/drive_resolver.py` | L3 projection pattern |
| `backend/app/services/npc/belief_crystallization_engine.py` | Pattern → belief projection |
| `backend/app/services/npc/belief_revision_engine.py` | Bayesian belief update |
| `backend/app/services/npc/epistemic_store.py` | Belief storage |
| `backend/app/services/npc/l1_chronicle.py` | Causal trace (append-only) |
| `backend/app/services/npc/pattern_detector.py` | L1.5 statistics |
| `backend/app/services/memory/resonance_engine.py` | Pattern → trait deltas |
| `backend/app/services/affective/affective_integrator.py` | Hysteresis integration of pressure |
| `backend/app/services/affective/affective_decay_handler.py` | Imprint decay |
| `backend/app/services/affect.py` | Resonance scan + pressure distortion |
| `backend/app/services/will.py` | Current WillEngine (to be replaced) |
| `backend/app/services/social/social_fabric_tracker.py` | Outgoing relationship matrix |
| `backend/app/services/social/social_engine.py` | BFS rumor propagation |
| `backend/app/services/social/reputation_engine.py` | Faction reputation |
| `backend/app/services/events/reaction_subscriber.py` | Direct observer reaction |
| `backend/app/services/reaction/reaction_rules.py` | MicroEvent generation |
| `backend/app/services/combat/impact_engine.py` | Force → Pain → Shock cascade |
| `backend/app/services/event_compiler.py` | Geometric event resolver |
| `backend/app/services/tick_orchestrator.py` | Causal phase ordering |
| `backend/app/services/npc/decision_hub.py` | Decision scoring (to be adapted) |
| `backend/app/services/npc/interpretation_engine.py` | Bias computation (to be subsumed by AppraisalEngine) |

---

## 16. Финальная директива архитектору

**Ваш мандат:** реализовать переход от сценарно-таблицевого подхода к единой динамической модели психики NPC, сохранив все инварианты ENIGMA (single-writer, epistemic boundary, phase lock gate, causal trace, deterministic replay).

**Что вы НЕ должны делать:**
- Не создавать новых файлов для каждой эмоции, социальной категории или типа травмы.
- Не расширять справочники `_REACTION_RULES`, `_BASE_DELTAS`, `EVENT_REPUTATION_IMPACT`, `TRAUMA_TOPOLOGY` новыми строками. Заменять их на appraisal-modulated функции.
- Не использовать LLM в AppraisalEngine.
- Не нарушать single-writer для NPCState.
- Не менять NPCPersonality (L0) в рантайме.

**Что вы ДОЛЖНЫ сделать:**
- Создать слой `AppraisalEngine` как центральный новый компонент.
- Расширить словарь трейтов/сигнатур в нескольких местах (CrystallizedBelief, AffectiveImprint, TRAUMA_TOPOLOGY).
- Переписать WillEngine как policy-comparator.
- Сохранить все существующие интерфейсы через адаптеры на время миграции.
- Покрыть тестами 10 эталонных сценариев (см. §13.3).
- Дойти до Phase F и убрать feature flag.

**Критерий успеха:** когда новый тип социального действия (например, «player_gifts_ring») добавляется в игру изменением конфигурации события + одной записи в LLM-компрессоре (а не добавлением кода в 5 разных справочников) — вы достигли цели.

---

**Документ подготовлен для архитектора ENIGMA Psychology.**
**Формат: Markdown.**
**Расположение: `/home/z/my-project/download/PSY-ARCH-01_Unified_Psychological_Dynamics.md`**.
