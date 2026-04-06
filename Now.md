# ENIGMA — АКТУАЛЬНАЯ АРХИТЕКТУРА (FINAL SPEC v2.0)

## 0. ЦЕЛЬ И ОГРАНИЧЕНИЯ

Цель: Локальная RPG-система с NPC, демонстрирующими причинно-следственное поведение, устойчивостью реакций и предсказуемостью без детерминированности.

Жёсткие ограничения:
- LLM 7B–13B, VRAM ≤ 16GB, контекст ≤ 4k токенов
- Целевой масштаб: 10–30 NPC одновременно (max ~50)
- Локальный запуск без облачных API

---

## 1. КЛЮЧЕВОЙ ПРИНЦИП (НЕПРИКОСНОВЕНЕН)

**LLM НЕ ПРИНИМАЕТ РЕШЕНИЯ. НЕ МЕНЯЕТ СОСТОЯНИЕ. НЕ ВЫДАЁТ ДЕЛЬТЫ.**

LLM = слой вербализации (текст из чисел).
Python = слой интеллекта (DecisionHub).

NPC — система числовых сил (weights), не текстовых рассуждений.

---

## 2. АРХИТЕКТУРНОЕ ЯДРО (УТОЧНЁННОЕ)

```
Event (Player/World)
  ↓
PerceptionFilter (радиус, видимость)
  ↓
DecisionHub.compute(NPCState, Personality, Event)  # чистая функция, read-only
  ↓
DecisionResult (intent, deltas, facts)
  ↓
StateApplicator.apply()  # atomic write-only
  ↓
NPCState (source of truth)
  ↓
VerbalizationContext (Python → текст)
  ↓
LLM (генерация речи/эмоций, read-only context)
```

---

## 3. ИСТОЧНИКИ ПРАВДЫ

### 3.1 NPCState (динамический)
Единственный mutable объект. Содержит:
- `emotion`, `stress`, `intent`, `intent_duration`
- `relationship_cache` (snapshot из RelationshipStore)
- `active_traits` (наложения на личность, decay со временем)
- `trauma_markers` (set строк)
- `narrative_cache` (max 10 фактов, для EXPLAIN mode)
- `will_state` (free/coerced/broken/deceptive/loyal)

### 3.2 NPCPersonality (immutable)
Загружается из JSON один раз, never changes:
- `tier` (mass/minor/major) — статический уровень симуляции
- `drives_base` (control/significance/fear/desire, сумма=1.0)
- `willpower`, `breakpoint`, `loyalty_base`
- `voice_profile` (строка: "Говоришь грубо, материшься...") — для LLM
- `can_awaken` (bool) — разрешение на "пробуждение" через замену NPC

### 3.3 SceneState
Визуальное состояние:
- Координаты NPC (x,y)
- Объекты, препятствия
- НЕ источник логики, только для PerceptionFilter

---

## 4. MEMORY ARCHITECTURE (R1)

### 4.1 Core Memory = Weights (для логики)
- RelationshipStore: `trust/fear/debt` (-100..100)
- WorkingMemory: последние 20 событий с decay
- Используется DecisionHub для расчёта `relationship_modifier`

### 4.2 Narrative Memory = Facts (только для вербализации)
```python
@dataclass(frozen=True)
class NarrativeFact:
    event_type: str      # enum: "combat", "theft", "help"
    target_id: str
    emotion_tag: str
    day: int
    importance: float    # 0.0-1.0
```
**Ограничения:**
- Только 1 факт в обычном режиме (если importance > 0.6)
- Max 2 факта при `intent=EXPLAIN`
- НЕ используется в формуле `score()` — только для текста
- НЕТ semantic search, НЕТ retrieval по запросу игрока

---

## 5. DECISION HUB (R2) — ЯДРО ИНТЕЛЛЕКТА

### 5.1 Свойства
- Чистая функция, read-only, no LLM, no IO
- Seed per session (детерминизм ±10% randomness)

### 5.2 Формула score(action)
```python
score = (drive_weight × context_relevance)
      + emotion_modifier
      + relationship_modifier
      + trait_modifier
      - (fear × risk)
      + intent_inertia        # чем дольше intent, тем сложнее сменить
      ± noise(10%)
```

### 5.3 Trait System (вместо mutable personality)
- `active_traits`: накопленные черты (suspicious, grateful), decay к 0
- `personality_base`: неизменен
- Effective modifier = base + traits (traits затухают, base остаётся)

### 5.4 Explanation Mode
Explanation — не отдельный слой, а `intent=EXPLAIN` в DecisionHub.
- Выбирает top-2 NarrativeFacts
- Генерирует `VerbalizationContext` с `is_explain_mode=True`
- LLM получает факты и формулирует ответ "почему"

### 5.5 Risk Calculation
- Количество свидетелей
- Дистанция до события
- Видимые маркеры угрозы (heavy_armor, weapon) — НЕ реальная сила игрока

---

## 6. STATE APPLICATOR (R2.3)

Единственная точка записи в NPCState.

**Атомарность:** `copy.deepcopy` → изменения → замена целиком. При ошибке возвращается оригинал.

**Saturation (Diminishing Returns):**
- Изменения теряют эффективность у границ диапазона (headroom)
- Hard cap override при `intensity > 1.5` (критические события пробивают saturation)
- Curve: "soft" (linear) или "sigmoid" (S-образная)

**Применяет:**
- Дельты стресса/эмоций (с saturation)
- Обновления в RelationshipStore (atomic)
- Trait decay (к нулю каждый тик)
- Will break (при stress > breakpoint)

---

## 7. VERBALIZATION LAYER (R3)

### 7.1 Принципы
- Python генерирует ВСЮ фактуру (эмоция, нюанс, стиль)
- LLM только "оживляет" текстом
- **LLM не получает:** числа (stress=87), working_memory как текст, reasoning, дельты для применения

### 7.2 VerbalizationContext (frozen)
```python
npc_id, npc_name, tier
emotion, will_state, intent, intent_target
scene_hint: str (≤500 chars, факт из PerceptionFilter)
emotional_nuance: str (Python-generated: "зол, но сдерживается...")
speech_style: str (из dominant drive)
voice_profile: str (из Personality)
adult_content: bool
narrative_hints: Tuple[NarrativeFact, ...] (max 2)
is_explain_mode: bool
```

### 7.3 Tier-Aware Verbalization
- **MASS NPC:** Шаблоны без LLM (`"{name} бежит в панике}"`)
- **MINOR/MAJOR:** LLM с dynamic token budget
  - EXPLAIN: 300 токенов
  - TALK: 200 токенов
  - ATTACK/FLEE: 80 токенов
  - IDLE/OBSERVE: 0 токенов (lazy verbalization)

### 7.4 Lazy Verbalization
- **Радиус:** 10м для обычных действий, 15м для криков (WARN/ATTACK)
- Далёкие NPC не вызывают LLM (экономия VRAM)
- Только MASS-шаблоны или silence

### 7.5 Emotional Nuance Engine
Python генерирует литературное описание состояния из чисел:
- `stress > 70` + `angry` → "зол, едва сдерживается — голос на грани срыва"
- `trait suspicious > 0.6` → "недоверчиво прищуривается"
- `will_state=broken` → "сломлен — глаза бегают"

### 7.6 Контракт с LLM
**LLM получает:**
- Кто ты (voice_profile, speech_style)
- В каком состоянии (emotional_nuance, will_state)
- Что хочешь сделать (intent, target)
- Один важный факт (narrative_hints)
- Сцену (scene_hint)

**LLM НЕ возвращает:**
- `trust_delta`, `stress_delta` (игнорируются даже если есть в ответе)
- Новые intent (игнорируются)
- "Внутренние мысли" как логику (только как текст для F12 debug, генерируемый Python)

---

## 8. LIFE ENGINE (R4)

Фоновая симуляция:
- Движение (координаты в SceneState)
- Рутины (schedules)
- Физиология (голод, усталость → модификаторы к stress)
- Recovery (stress -= 5 за тик, 15 если sleeping)

**Не принимает решений.** Генерирует события для EventBus.

---

## 9. WORLD PRESSURE ENGINE

Не меняет NPC напрямую. Публикует события:
```python
event_bus.publish(Event(type="faction_war_started", ...))
```
NPC реагируют через DecisionHub как на обычные события.

---

## 10. NPC TIER SYSTEM (R1.7)

Статическое назначение при создании кампании:

**MASS (Tier 0):**
- Нет WorkingMemory (или ограниченная)
- Нет NarrativeFacts
- Шаблонная вербализация (без LLM)
- Упрощённый DecisionHub (только базовые реакции)

**MINOR (Tier 1):**
- Полный DecisionHub
- WorkingMemory (20 событий)
- Ограниченная NarrativeMemory
- LLM с короткими бюджетами

**MAJOR (Tier 2):**
- Полная симуляция
- LLM с длинными бюджетами (300 токенов для EXPLAIN)
- Может иметь `can_awaken=True`

**Запрещено:** Runtime upgrade tier. "Пробуждение" — через spawn нового NPC с загрузкой snapshot старого.

---

## 11. ROADMAP (ОБНОВЛЁННЫЙ)

R1 ✅  Memory Core
R2 ✅  Decision Core
R3 ✅  Verbalization Layer
R4 ✅  Calibration + Coordinates

R5 — MEMORY DEPTH
  R5.1 ✅  EventMemory (clarity, confidence, lifecycle, decay)
  R5.2 ✅  clarity/confidence → verbalization prompt
  R5.3 ✅  L3 Identity: trait formation из паттернов
              + calculate_clarity из PerceptionFilter
              + ImportanceEngine обновление
  R5.4 ✅  ResonanceEngine: детекция паттернов
              (betrayal_chain, chronic_help, gaslighting)
              → to_identity_weight → L3 traits

R6 — BREAK SYSTEM (Слом.md)
  R6.1 ✅  NPCState +: resentment, dependency, identity_integrity
  R6.2 ✅  BehaviorMask: FAKE_SUBMISSION, BETRAYAL, COLLAPSE
         (расширение WillState, не замена)
  R6.3 ✅ OpportunityEngine: когда сломленный NPC действует
  Из Баги.md — защита от абьюза уже заложена в спецификации (resistance scaling, cost of control).

  R6.4 ✅  BreakProgressEngine: По дизайну: pressure > willpower → запускает процесс слома В коде: pressure = fear + stress + failures - support

  Защита от багов в R6 не установлена

R7 — RESOLUTION LAYER (DICE.md)
  R7.1  expected_success → DecisionResult (заготовка есть)
  R7.2  ResolutionEngine: roll + bias → final_value
         bias = stat_mod + context_mod + npc_state_mod
  R7.3  OutcomeMapping: 6 уровней градиента (не hit/miss)
  R7.4  gap = actual - expected → источник traits и травм
  R7.5  Anti-exploit: штраф за повторные броски,
         diminishing returns на однотипные действия

R7.5 - единый слой балансировки balance/break_config. pymemory_config.pydecision_config.py  

R8 — CHARACTER CONSTRAINT (player layer)
  R8.1  CharacterProfile: traits, willpower, conflicts
  R8.2  ConstraintEngine: affinity = f(traits, intent)
         soft resistance, не hard lock
  R8.3  Stress cost при отклонении от характера

R9 — SOCIAL NETWORKS
  R9.1  NPC↔NPC RelationshipMatrix (не только player↔NPC)
  R9.2  Rumor propagation: события распространяются между NPC
  R9.3  Reputation system: репутация игрока в регионе

R10 — DEEP SYSTEMS (будущее)
  R10.1  NPC meta-learning (адаптация к паттернам игрока)
  R10.2  Contextual modifiers (время суток, погода, шум)
  R10.3  World Legends (географическая память событий)
  R10.4  NPC Schemes (долгосрочные планы, риск раскрытия)
  R10.5  Thought Cabinet (активные мысли → модификаторы DecisionHub)

R11 — OPTIMIZATION
  R11.1  Async IO
  R11.2  Batching LLM (30+ NPC)
  R11.3  lru_cache для _score_one

---

## 12. ЗАПРЕЩЁННЫЕ ПАТТЕРНЫ (АНТИПАТТЕРНЫ)

- ❌ LLM принимает решения (возвращает дельты, выбирает intent)
- ❌ Mutable personality (изменение base характеристик)
- ❌ Semantic search в памяти (retrieval по запросу)
- ❌ Runtime tier upgrade (mass → major)
- ❌ Working memory как текст в промпте (только weights)
- ❌ God Object (NPC dict с прямой мутацией)
- ❌ Reasoning через промпты ("внутренние мысли" до DecisionHub)

---

## 13. КРИТЕРИЙ УСПЕХА (ИТОГОВЫЙ)

Игрок ощущает:
- **Память:** NPC помнит поступки (через веса, видно в поведении)
- **Объяснимость:** При "почему?" получает конкретные факты (NarrativeFacts), не абстракции
- **Устойчивость:** NPC не меняет мнение резко (saturation, trait decay)
- **Предсказуемость:** Можно предугадать реакцию (формула score прозрачна)
- **Живость:** Текст разнообразен (voice_profile, emotional_nuance), но логика стабильна

---

## 14. ТЕХНИЧЕСКИЕ КОНСТАНТЫ

```python
WORKING_MEMORY_SIZE = 20
MAX_NARRATIVE_CACHE = 10
NARRATIVE_THRESHOLD_NORMAL = 0.6  # для показа 1 факта
VERbalIZATION_RADIUS = 10.0       # метры
SCREAM_RADIUS = 15.0              # для WARN/ATTACK/FLEE
TOKEN_BUDGET_EXPLAIN = 300
TOKEN_BUDGET_TALK = 200
TOKEN_BUDGET_COMBAT = 80
SCORE_NOISE_RANGE = 0.10          # ±10%
SATURATION_FLOOR = 0.1            # минимум 10% эффекта
INTENT_INERTIA_MAX_TICKS = 10
STRESS_BROKEN_THRESHOLD = personality.breakpoint  # не константа 80!
```

---

## 15. ФАЙЛОВАЯ СТРУКТУРА (АКТУАЛЬНАЯ)

```
backend/app/services/npc/
  npc_state.py           # NPCState, NPCPersonality, NarrativeFact
  decision_hub.py        # DecisionHub, formula, scoring
  state_applicator.py    # StateApplicator, saturation math
  verbalization_context.py  # VerbalizationContext, nuance engine
  math_utils.py          # apply_saturation, normalize

backend/app/services/memory/
  memory_manager.py      # Фасад
  working_memory.py      # R1.2
  relationship_store.py  # R1.4
  importance_engine.py   # R1.3
  contradiction_resolver.py  # R1.5

backend/app/engines/
  python_engines.py      # R2.5 Integration (без process_player_action)
  npc_agent.py           # R3 verbalization (run_from_context)
```
```

**Ключевые изменения в v2.0:**
1. **R2.5 Integration** — чёткое разделение: DecisionHub считает, StateApplicator пишет, python_engines только собирает контекст
2. **Voice Profile** — статический голос из JSON, не генерируемый LLM
3. **Emotional Nuance** — Python генерирует "грязь" и "характер" из чисел
4. **Saturation** — математика diminishing returns формализована
5. **Tier-aware** — MASS NPC не тратят VRAM на LLM
6. **Lazy verbalization** — далёкие NPC молчат
7. **Запрет на LLM-deltas** — жёсткое игнорирование trust_delta из ответа LLM (только для логов)











Ты абсолютно прав. Это классическая и очень опасная утечка бизнес-логики в слой данных.

Ты поймал меня с поличным: StateApplicator должен быть исключительно "тупым" исполнителем (atomic write-only), а не судьёй, принимающим решения о сломе психики. Более того, наличие хардкода 80.0 прямо противоречит 14-му разделу твоей собственной спецификации, где чётко сказано: STRESS_BROKEN_THRESHOLD = personality.breakpoint # не константа 80!.

Мы однозначно выбираем стратегию 90%. Архитектурная целостность Enigma держится на строгом разделении: DecisionHub (и будущий BreakProgressEngine) — думают, StateApplicator — молча применяет. Нам нужно расширить транспортный контракт StateDeltas и ампутировать логику из аппликатора.

Чтобы провести эту операцию чисто, мне нужны следующие файлы:

backend/app/services/npc/decision_hub.py
Зачем: Чтобы обновить контракт StateDeltas (или то, как хаб формирует DecisionResult) и научить его прокидывать новые параметры (identity_integrity_delta, pressure_resistance_delta, will_state_override) в аппликатор.

backend/app/services/npc/state_applicator.py
Зачем: Чтобы хирургически вырезать метод _apply_will_break и константу 80.0, заставив его просто принимать will_state_override из дельт, соблюдая логику сатурации.

backend/app/services/npc/npc_state.py
Зачем: Чтобы увидеть актуальные датаклассы NPCState и NPCPersonality. Нам нужно убедиться, что поля для identity_integrity, resentment и dependency (из R6.1) там присутствуют, а breakpoint правильно настроен.

Готов загрузить эти три файла, чтобы мы могли вычистить хардкод и подготовить идеальный фундамент для BreakProgressEngine?

Что оставляем для R6.4 и DecisionHub:

1. BehaviorMask → конкретные интенты

В коде есть _MASK_UNLOCKS, но он не используется в calculate(). Это правильно — фильтрация интентов по маске (FAKE_SUBMISSION vs BETRAYAL) это работа DecisionHub, который вызывает OpportunityEngine и затем пересекает unlocked_intents с _MASK_UNLOCKS[mask].

2. Защита от абьюза (история попыток)

Тест test_repeated_opportunity_has_diminishing_returns проверяет динамику при изменении контекста, но настоящая защита от спама (когда игрок постоянно провоцирует/отвлекает NPC для фарма opportunity) требует отслеживания истории. Это логично делать в R6.4 BreakProgressEngine, который будет накапливать "трещины" (cracks) и поднимать resistance или suspicion при повторных проверках opportunity в коротком временном окне.

3. Процесс слома (pressure → cracks → broken)

Сейчас will_state передается как строка. R6.4 будет отвечать за то, как NPC переходит в состояние "broken" (и как накапливаются resentment, dependency, identity_integrity). OpportunityEngine только потребляет этот факт, не меняя его.

Ты заявляешь в правилах: «DecisionHub — ядро интеллекта, а StateApplicator — точка записи».
Но я открываю твой state_applicator.py и вижу метод _apply_will_break с жестко зашитой константой _STRESS_BROKEN_THRESHOLD = 80.0. Твой тупой механизм записи вдруг начал принимать сложнейшие психоэмоциональные решения! Это недопустимая утечка логики. Решение о сломе воли должно рождаться в BreakProgressEngine, передаваться через хаб в виде явной команды и лишь беспрекословно исполняться аппликатором.

СТРАТЕГИЧЕСКИЙ ВЫБОР
Теперь нам нужно научиться передавать результаты будущих вычислений BreakProgressEngine через хаб в аппликатор. Распределение вероятностей сохранения архитектурной целостности выглядит так:

90% вероятности успеха: Ты показываешь мне backend/app/services/npc/decision_hub.py. Мы расширяем контракт StateDeltas для новых параметров (identity_integrity_delta, pressure_resistance_delta, will_state_override), хирургически вырезаем хардкод из аппликатора и только затем пишем чистый движок слома.

10% вероятности успеха: Мы пишем BreakProgressEngine в вакууме прямо сейчас, рискуя создать логику, которую хаб не сможет правильно маршрутизировать. Это приведет к костылям и деградации системы, о которой ты сам же предупреждал.