# ТЕХНИЧЕСКОЕ ЗАДАНИЕ: SNIO v3.0 — PRODUCTION-READY BOUNDED STOCHASTIC ACTORS

**Проект:** ENIGMA Engine
**Ветка:** V.0.5.4.0_SNIO_PRODUCTION
**Онтология:** `Интеллект = Orchestration + Entropy Suppression`. `LLM = Unified Stochastic Renderer`. Мы не контролируем нейроны, мы формируем вероятностные коридоры.
**Цель:** Создать Simulation-Native Inference Layer на базе единой 4B модели с адаптивной глубиной промпта, нелинейной виртуализацией памяти и жесткими фильтрами драматургии.

---

## 0. УНИЧТОЖЕНИЕ MICRO-MODEL ECOLOGY

Концепция пула моделей (1B + 3B + 9B) мертва. На GTX 1060 6GB она убьет игру своппингом и latency.
**Новая парадигма:** Единая 4B модель (Qwen3-4B или Gemma-3-4B, Q4_K_M, ~3.5 GB VRAM) + Python Brain.
Глубина мышления определяется не сменой моделей, а **глубиной препроцессинга Python и размером инжектированного состояния**.

---

## I. АППАРАТНАЯ СТРАТЕГИЯ И МОДЕЛЬ

**Цель:** Вписаться в 4-6 GB VRAM с запасом под KV-cache.

1.  **Primary Model:** `Qwen3-4B-Instruct-Abliterated Q4_K_M` (или Gemma-3-4B).
2.  **VRAM Budget:** 3.5 GB (веса) + 0.5 GB (KV Q8_0) + 1.0 GB (Буфер/CUDA) = 5.0 GB.
3.  **KV Cache:** Обязательно `--cache-type-k q8_0 --cache-type-v q8_0`.
4.  **Hardware Negotiator:** При старте измеряет VRAM. Если < 5.5 GB, переключает игру в Low-End Mode (только Fast/Medium paths, обрезанные промпты).

---

## II. COGNITIVE LOAD ESTIMATOR (АДАПТИВНЫЙ ПУТЬ)

**Цель:** Не гонять LLM вообще, если Python может справиться сам.

### Модуль: `backend/app/services/eil/cognitive_load_estimator.py`

Оценивает `IntentSemanticField` + `CFRM Pressure` перед пайплайном.

1.  **FAST PATH (0 ms LLM latency):** Рутина, отсутствие давления, бытовые фразы ("Привет", "Пиво").
    *   *Движок:* `FastPathResponder` (Python-only).
    *   *Логика:* Стохастические шаблоны. Выбор из бакета `(Intent, Emotion)` с весами от `relationship.trust`. ("Привет" + низкий траст = "*кивает*", "Чего?").
2.  **MEDIUM PATH (~1.5 sec):** Стандартный диалог, среднее давление.
    *   *Движок:* `State Compiler` (базовый промпт ~1024 токена) → `4B Renderer`.
3.  **DEEP PATH (~2.5 sec):** Травма, боевка, шантаж, вскрытие тайн.
    *   *Движок:* Python вычисляет гранулярные `BehaviorCorridors` + `ECMV` тянет травмы → `State Compiler` (расширенный промпт ~2048 токена) → `4B Renderer`.

---

## III. FAST PATH RESPONDER (СТОХАСТИЧЕСКИЕ ШАБЛОНЫ)

**Цель:** Избежать роботизации при отсутствии LLM.

### Модуль: `backend/app/services/eil/fast_path_responder.py`

```python
class FastPathResponder:
    def respond(self, intent: IntentSemanticField, emotion: EmotionVector, relationship: RelationshipDTO) -> str:
        bucket = self.response_bank.get_bucket(intent.domain, emotion.dominant)
        # Веса зависят от траста и страха
        weights = self._calculate_weights(bucket, relationship)
        return bucket.weighted_choice(weights)
```
*Банк ответов:* `data/fast_responses.json`. Для `(GREETING, NEUTRAL)`: `["Привет.", "Чего надо?", "*кивает*", "М?", "Да?"]`. Никакого LLM, нулевая задержка, иллюзия живости через рандом.

---

## IV. BEHAVIOR CORRIDORS (SOFT/HARD GUARD)

**Цель:** Не убивать latency повторными генерациями при выходе LLM за рамки, но и не пускать галлюцинации в симуляцию.

### Модуль: `backend/app/services/eil/behavior_corridor.py`

`DecisionHub` генерирует коридор. `BehaviorCorridorGuard` валидирует ответ.

1.  **SOFT CORRIDOR (Guidance):** LLM может нарушить, но Python перехватит *действие*.
    *   *Пример:* LLM сгенерировала `"хватает нож"`. Soft-правило запрещает атаку. Python принимает текст (рендер эмоции), но `ImpactEngine` не получает `ImpactIntent`. NPC машет ножом, но не бьет.
2.  **HARD CORRIDOR (Enforced):** Физическая невозможность генерации.
    *   *Стоп-токены:* `"убью"`, `"атакую"`.
    *   *Regex:* `\[attack\]`.
    *   *При нарушении:* Мгновенный обрез генерации (по стоп-токену) + fallback на `FastPathResponder` (молчание "..." или тяжелое дыхание).

---

## V. ECMV (EXTERNAL COGNITIVE MEMORY VIRTUALIZATION)

**Цель:** Нелинейное затухание памяти. Травмы бессмертны, рутина забывается мгновенно.

### Обновление: `backend/app/services/memory/importance_engine.py`

Внедрить экспоненциальные кривые затухания (Salience Decay Curves):

```python
def calculate_salience(event: EventMemory, current_tick: int) -> float:
    delta_t = current_tick - event.tick
    
    if event.domain == DeltaDomain.IDENTITY or "trauma" in event.tags:
        decay = math.exp(-0.05 * delta_t)  # IMMORTAL LAYER
    elif event.domain == DeltaDomain.PHYSIOLOGY and event.payload.pain > 50:
        decay = math.exp(-0.3 * delta_t)   # Боль держится
    elif event.type in ["routine", "fluff", "greeting"]:
        decay = math.exp(-1.5 * delta_t)   # Мусор сгорает
    else:
        decay = math.exp(-0.2 * delta_t)   # Стандарт
        
    return event.importance * decay
```
При сборке промпта `ECMV Manager` отсекает всё с `salience < 0.1`.

---

## VI. NARRATIVE PRESSURE TRACKER (БЕЗ FEEDBACK LOOP)

**Цель:** Подтягивать драматургию, но не схлопывать мир в одержимость одной темой.

### Обновление: `backend/app/services/memory/memory_manager.py`

Формула Score дополнена **Domain Lock** и **Saturation Cap**:

```python
def calculate_recall_score(event, current_topic, active_pressures):
    semantic = 0.15
    emotional = 0.2
    goal = 0.2
    causal = 0.15
    
    # Narrative Pressure с защитой от циклов
    pressure_boost = 0.0
    for pressure in active_pressures:
        if domain_compatible(event.domain, current_topic.domain, pressure.domain):
            pressure_boost += pressure.magnitude * 0.3
            
    # Saturation Cap (не более 0.3 общего веса)
    pressure_boost = min(pressure_boost, 0.3) 
    
    return (semantic + emotional + goal + causal + pressure_boost)
```
Если давление "Вакуум Власти" (POLITICAL), а разговор о пиве (COMMERCE) — `domain_compatible` вернет `False`. Бармен не будет вещать о троне. Но если разговор зайдет о ценах на зерно (COMMERCE + POLITICAL) — давление пробьет барьер.

---

## VII. ПОРЯДОК ДЕЙСТВИЙ ДЛЯ LLM-КОДЕРА

1.  **Скачать Qwen3-4B-Instruct Q4_K_M** (или Gemma-3-4B). Обновить `config.py`.
2.  **Создать `cognitive_load_estimator.py`**: Разветвление логики на Fast/Medium/Deep.
3.  **Создать `fast_path_responder.py`**: Загрузить `fast_responses.json`, логика взвешенного выбора.
4.  **Создать `behavior_corridor.py`**: Интегрировать генерацию Soft/Hard правил в `DecisionHub`.
5.  **Обновить `importance_engine.py`**: Внедрить `calculate_salience()` с экспоненциальными кривыми (Trauma vs Routine).
6.  **Обновить `memory_manager.py`**: Добавить `NarrativePressure` буст с `domain_compatible` и `saturation_cap`.
7.  **Интегрировать в `GameLoop`**: `CognitiveLoadEstimator` → `FastPath` или `ECMV` → `StateCompiler` → `4B Renderer` → `CorridorGuard`.

**КРИТЕРИЙ УСПЕХА:**
Игра работает на GTX 1060 (VRAM < 5.5 GB). Бытовой диалог "Привет" обрабатывается за 0ms (Fast Path, Python-only). Травматический конфликт генерируется за 2.5 сек (Deep Path) без вылета за VRAM. Бармен не вещает о политике, когда ему просто заказывают эль (Domain Lock работает). NPC может схватиться за нож от страха (Soft Corridor), но не ударит, если Python не разрешил (Hard Guard).




# ТЕХНИЧЕСКОЕ ЗАДАНИЕ: SNIO v3.0 — PRODUCTION-READY BOUNDED STOCHASTIC ACTORS

**Проект:** ENIGMA Engine
**Ветка:** V.0.5.4.0_SNIO_PRODUCTION
**Онтология:** `Интеллект = Orchestration + Entropy Suppression`. `LLM = Unified Stochastic Renderer`. Мы не контролируем нейроны, мы формируем вероятностные коридоры.
**Цель:** Создать Simulation-Native Inference Layer на базе единой 4B модели с адаптивной глубиной промпта, нелинейной виртуализацией памяти и жесткими фильтрами драматургии.

---

## 0. УНИЧТОЖЕНИЕ MICRO-MODEL ECOLOGY

Концепция пула моделей (1B + 3B + 9B) мертва. На GTX 1060 6GB она убьет игру своппингом и latency.
**Новая парадигма:** Единая 4B модель (Qwen3-4B или Gemma-3-4B, Q4_K_M, ~3.5 GB VRAM) + Python Brain.
Глубина мышления определяется не сменой моделей, а **глубиной препроцессинга Python и размером инжектированного состояния**.

---

## I. АППАРАТНАЯ СТРАТЕГИЯ И МОДЕЛЬ

**Цель:** Вписаться в 4-6 GB VRAM с запасом под KV-cache.

1.  **Primary Model:** `Qwen3-4B-Instruct-Abliterated Q4_K_M` (или Gemma-3-4B).
2.  **VRAM Budget:** 3.5 GB (веса) + 0.5 GB (KV Q8_0) + 1.0 GB (Буфер/CUDA) = 5.0 GB.
3.  **KV Cache:** Обязательно `--cache-type-k q8_0 --cache-type-v q8_0`.
4.  **Hardware Negotiator:** При старте измеряет VRAM. Если < 5.5 GB, переключает игру в Low-End Mode (только Fast/Medium paths, обрезанные промпты).

---

## II. COGNITIVE LOAD ESTIMATOR (АДАПТИВНЫЙ ПУТЬ)

**Цель:** Не гонять LLM вообще, если Python может справиться сам.

### Модуль: `backend/app/services/eil/cognitive_load_estimator.py`

Оценивает `IntentSemanticField` + `CFRM Pressure` перед пайплайном.

1.  **FAST PATH (0 ms LLM latency):** Рутина, отсутствие давления, бытовые фразы ("Привет", "Пиво").
    *   *Движок:* `FastPathResponder` (Python-only).
    *   *Логика:* Стохастические шаблоны. Выбор из бакета `(Intent, Emotion)` с весами от `relationship.trust`. ("Привет" + низкий траст = "*кивает*", "Чего?").
2.  **MEDIUM PATH (~1.5 sec):** Стандартный диалог, среднее давление.
    *   *Движок:* `State Compiler` (базовый промпт ~1024 токена) → `4B Renderer`.
3.  **DEEP PATH (~2.5 sec):** Травма, боевка, шантаж, вскрытие тайн.
    *   *Движок:* Python вычисляет гранулярные `BehaviorCorridors` + `ECMV` тянет травмы → `State Compiler` (расширенный промпт ~2048 токена) → `4B Renderer`.

---

## III. FAST PATH RESPONDER (СТОХАСТИЧЕСКИЕ ШАБЛОНЫ)

**Цель:** Избежать роботизации при отсутствии LLM.

### Модуль: `backend/app/services/eil/fast_path_responder.py`

```python
class FastPathResponder:
    def respond(self, intent: IntentSemanticField, emotion: EmotionVector, relationship: RelationshipDTO) -> str:
        bucket = self.response_bank.get_bucket(intent.domain, emotion.dominant)
        # Веса зависят от траста и страха
        weights = self._calculate_weights(bucket, relationship)
        return bucket.weighted_choice(weights)
```
*Банк ответов:* `data/fast_responses.json`. Для `(GREETING, NEUTRAL)`: `["Привет.", "Чего надо?", "*кивает*", "М?", "Да?"]`. Никакого LLM, нулевая задержка, иллюзия живости через рандом.

---

## IV. BEHAVIOR CORRIDORS (SOFT/HARD GUARD)

**Цель:** Не убивать latency повторными генерациями при выходе LLM за рамки, но и не пускать галлюцинации в симуляцию.

### Модуль: `backend/app/services/eil/behavior_corridor.py`

`DecisionHub` генерирует коридор. `BehaviorCorridorGuard` валидирует ответ.

1.  **SOFT CORRIDOR (Guidance):** LLM может нарушить, но Python перехватит *действие*.
    *   *Пример:* LLM сгенерировала `"хватает нож"`. Soft-правило запрещает атаку. Python принимает текст (рендер эмоции), но `ImpactEngine` не получает `ImpactIntent`. NPC машет ножом, но не бьет.
2.  **HARD CORRIDOR (Enforced):** Физическая невозможность генерации.
    *   *Стоп-токены:* `"убью"`, `"атакую"`.
    *   *Regex:* `\[attack\]`.
    *   *При нарушении:* Мгновенный обрез генерации (по стоп-токену) + fallback на `FastPathResponder` (молчание "..." или тяжелое дыхание).

---

## V. ECMV (EXTERNAL COGNITIVE MEMORY VIRTUALIZATION)

**Цель:** Нелинейное затухание памяти. Травмы бессмертны, рутина забывается мгновенно.

### Обновление: `backend/app/services/memory/importance_engine.py`

Внедрить экспоненциальные кривые затухания (Salience Decay Curves):

```python
def calculate_salience(event: EventMemory, current_tick: int) -> float:
    delta_t = current_tick - event.tick
    
    if event.domain == DeltaDomain.IDENTITY or "trauma" in event.tags:
        decay = math.exp(-0.05 * delta_t)  # IMMORTAL LAYER
    elif event.domain == DeltaDomain.PHYSIOLOGY and event.payload.pain > 50:
        decay = math.exp(-0.3 * delta_t)   # Боль держится
    elif event.type in ["routine", "fluff", "greeting"]:
        decay = math.exp(-1.5 * delta_t)   # Мусор сгорает
    else:
        decay = math.exp(-0.2 * delta_t)   # Стандарт
        
    return event.importance * decay
```
При сборке промпта `ECMV Manager` отсекает всё с `salience < 0.1`.

---

## VI. NARRATIVE PRESSURE TRACKER (БЕЗ FEEDBACK LOOP)

**Цель:** Подтягивать драматургию, но не схлопывать мир в одержимость одной темой.

### Обновление: `backend/app/services/memory/memory_manager.py`

Формула Score дополнена **Domain Lock** и **Saturation Cap**:

```python
def calculate_recall_score(event, current_topic, active_pressures):
    semantic = 0.15
    emotional = 0.2
    goal = 0.2
    causal = 0.15
    
    # Narrative Pressure с защитой от циклов
    pressure_boost = 0.0
    for pressure in active_pressures:
        if domain_compatible(event.domain, current_topic.domain, pressure.domain):
            pressure_boost += pressure.magnitude * 0.3
            
    # Saturation Cap (не более 0.3 общего веса)
    pressure_boost = min(pressure_boost, 0.3) 
    
    return (semantic + emotional + goal + causal + pressure_boost)
```
Если давление "Вакуум Власти" (POLITICAL), а разговор о пиве (COMMERCE) — `domain_compatible` вернет `False`. Бармен не будет вещать о троне. Но если разговор зайдет о ценах на зерно (COMMERCE + POLITICAL) — давление пробьет барьер.

---

## VII. ПОРЯДОК ДЕЙСТВИЙ ДЛЯ LLM-КОДЕРА

1.  **Скачать Qwen3-4B-Instruct Q4_K_M** (или Gemma-3-4B). Обновить `config.py`.
2.  **Создать `cognitive_load_estimator.py`**: Разветвление логики на Fast/Medium/Deep.
3.  **Создать `fast_path_responder.py`**: Загрузить `fast_responses.json`, логика взвешенного выбора.
4.  **Создать `behavior_corridor.py`**: Интегрировать генерацию Soft/Hard правил в `DecisionHub`.
5.  **Обновить `importance_engine.py`**: Внедрить `calculate_salience()` с экспоненциальными кривыми (Trauma vs Routine).
6.  **Обновить `memory_manager.py`**: Добавить `NarrativePressure` буст с `domain_compatible` и `saturation_cap`.
7.  **Интегрировать в `GameLoop`**: `CognitiveLoadEstimator` → `FastPath` или `ECMV` → `StateCompiler` → `4B Renderer` → `CorridorGuard`.

**КРИТЕРИЙ УСПЕХА:**
Игра работает на GTX 1060 (VRAM < 5.5 GB). Бытовой диалог "Привет" обрабатывается за 0ms (Fast Path, Python-only). Травматический конфликт генерируется за 2.5 сек (Deep Path) без вылета за VRAM. Бармен не вещает о политике, когда ему просто заказывают эль (Domain Lock работает). NPC может схватиться за нож от страха (Soft Corridor), но не ударит, если Python не разрешил (Hard Guard).