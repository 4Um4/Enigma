# ENIGMA — МАСТЕР-ПЛАН v1.0
## Единый архитектурный документ (синтез всех материалов)

---

## 0. ГЛАВНЫЙ ПРИНЦИП (НЕПРИКОСНОВЕНЕН)

```
LLM НЕ ПРИНИМАЕТ РЕШЕНИЯ.
LLM НЕ МЕНЯЕТ СОСТОЯНИЕ.
LLM НЕ ВЫДАЁТ ДЕЛЬТЫ.
LLM НЕ ПОЛУЧАЕТ ЧИСЛА.
```

**Python = интеллект.** DecisionHub считает score(action) по числовым весам. Только он решает.
**LLM = голос.** Получает intent + emotion_tag + projection_string. Возвращает текст. Всё.
**NPC — система числовых сил** (pride, trust, fear, stress). Из чисел рождается поведение. LLM озвучивает уже принятое решение.
**Хардкод отдельных NPC запрещён.** Система масштабируема: поведение вытекает из профиля, не из имени.

---

## 1. ЧТО ОТБРОШЕНО И ПОЧЕМУ

| Идея | Причина отбраковки | Судьба |
|------|-------------------|--------|
| **GOAP** (планировщик действий) | Нечему планировать: нет голода/крафта/карты. UX текстовой RPG не выдержит 5 тиков текста планирования. LifeEngine через JSON-расписание закрывает рутину без ИИ | Бэклог R10.5 — добавить при режиме "Выживание с картой" |
| **intent_queue.py** | Явно признан ненужным. Логика инерции уже внутри decision_hub.py через commitment + switching_cost | Не создавать |
| **npc_agent.py** как основной путь | Bypassed в R3_DIRECT_MODE. DM = единственный LLM на тик | Оставить как заглушку, не развивать |
| **InternalVoice / WorldLegend / NPCScheme** | ResonanceEngine — это R10+. Нет фундаментальных механик для работы схем | Бэклог R10+ |
| **BODY_TRAIT / ROLE_MARKER** | Определены, но нигде не используются — мёртвый код | Удалить при следующей чистке |
| **long_term_store.py (SQLite)** | Phase 2+. Сейчас JSON достаточен | Бэклог Phase 2 |
| **Runtime TierConfig upgrade** | Только controlled respawn (новый NPC). Upgrade в рантайме нарушает предсказуемость | Запрещено |
| **world_sim_agent.py в текущем виде** | Asyncio баг: semaphore bound to different event loop. Небезопасен | Изолировать до полного рефакторинга asyncio-слоя |
| **Точные числа (stress=85) в LLM-промпте** | Пробивает Fog of War. NPC начинает говорить "мой стресс 85, сдаюсь" | Запрещено навсегда. Только psychological_projection строкой |
| **Randomness в DecisionHub при использовании кубиков** | Двойной RNG. score() — детерминирован. Случайность только в ResolutionEngine | Убрать любой random из score() |

---

## 2. КЛЮЧЕВЫЕ КОНТРАКТЫ СИСТЕМЫ (НЕ ЛОМАТЬ)

```
1. DecisionHub    — ТОЛЬКО читает. НЕ пишет. НЕ вызывает LLM.
2. StateApplicator — ТОЛЬКО пишет через apply(). НЕ принимает решений.
3. NPCState       — иммутабелен в рантайме. apply() возвращает копию.
4. LLM            — ТОЛЬКО вербализация. Получает строки, не числа.
5. GameLoop       — живёт в app.state. НЕ в глобальном синглтоне.
6. npc_profile.py — ТОЛЬКО L0 типы (immutable, из JSON).
7. npc_state.py   — ВСЕ L1/L2 типы и адаптеры.
8. SceneStateManager.commit() — ЕДИНСТВЕННАЯ точка сохранения состояния мира.
9. NarrativeFacts — max 2 факта. frozen. НЕ участвуют в логике.
10. TierConfig    — статичен. Только controlled respawn (новый NPC).
```

---

## 3. АРХИТЕКТУРА (РЕАЛЬНЫЕ ФАЙЛЫ)

```
enigma/
├── start_enigma.bat                   # Единая точка входа
│
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI + startup → app.state.game_loop
│   │   │
│   │   ├── api/                       # ТРАНСПОРТНЫЙ СЛОЙ (только передача)
│   │   │   ├── routes.py              # REST (run_turn)
│   │   │   ├── routes_stream.py       # SSE (stream_turn)
│   │   │   └── routes_debug.py        # God Mode (~-консоль)
│   │   │
│   │   ├── models/                    # ЧИСТЫЕ ДАННЫЕ (Pydantic / Dataclasses)
│   │   │   ├── npc_state.py           # NPCState L2, NPCIdentityL1, Intent enum, WillState
│   │   │   ├── npc_profile.py         # ТОЛЬКО L0: NPCProfileL0, PsycheBase, InventoryProfile
│   │   │   ├── personality.py         # L0 Core & L1 Identity (Immutable)
│   │   │   ├── decision.py            # DecisionResult, StateDeltas, EventContext
│   │   │   ├── psychological.py       # DistortionProfile, CausalEntry [✅ ШАГ 2b]
│   │   │   ├── spatial.py             # LocationNode, LocationGraph, LocalSpace
│   │   │   └── schemas.py             # Pydantic DTO для API
│   │   │
│   │   ├── core/                      # БАЗОВЫЕ МЕХАНИЗМЫ (не знают об игре)
│   │   │   ├── event_bus.py           # Шина событий
│   │   │   ├── event_types.py         # Типизированные события
│   │   │   ├── constants.py           # Central Math Config (единые веса, капы)
│   │   │   └── security.py            # Анти-спам, rate limiting
│   │   │
│   │   └── services/                  # ЯДРО ЛОГИКИ
│   │       │
│   │       ├── game_loop.py           # ★ КООРДИНАТОР (вызывает DM, крутит тики)
│   │       ├── game_loop_builder.py   # Сборка GameLoop при startup
│   │       ├── game_loop_accessor.py  # get_game_loop(request) через Depends
│   │       │
│   │       ├── action/                # DM SYSTEM (реальный путь)
│   │       │   ├── dm_orchestrator.py    # Главный фасад пайплайна
│   │       │   ├── dm_router.py          # Этап 1: текст → Event + intensity
│   │       │   ├── dm_scene_builder.py   # Этап 2: R4 Spatial контекст
│   │       │   ├── object_resolver.py    # Разрешение объектов в сцене
│   │       │   ├── player_target_extractor.py
│   │       │   ├── python_engines.py     # _run_python_engines() пайплайн
│   │       │   └── [ДОЛГ] dm_validator.py  # Фильтр реальности (можно ли?)
│   │       │
│   │       ├── reaction/              # 🆕 ШАГ 0.5 — REACTION LAYER [НЕ РЕАЛИЗОВАН]
│   │       │   ├── reaction_resolver.py  # DecisionResult → MicroEvents
│   │       │   ├── micro_event.py        # Структура микрособытия
│   │       │   └── reaction_rules.py     # Правила: threat→drop, attack→disrupt
│   │       │
│   │       ├── character/             # 🆕 ФАЗА 2.0 — ПЕРСОНАЖ [НЕ РЕАЛИЗОВАН]
│   │       │   ├── character_filter.py   # PlayerIntent → FilteredAction
│   │       │   ├── character_profile.py  # self_integrity, values, constraints
│   │       │   └── resistance_scorer.py  # Формула сопротивления (чистый Python)
│   │       │
│   │       ├── npc/                   # R2 — ЯДРО ИНТЕЛЛЕКТА
│   │       │   ├── decision_hub.py       # [ЦЕНТР] score() — не трогать без аудита
│   │       │   ├── state_applicator.py   # [ТОЧКА ЗАПИСИ] CausalLedger ✅
│   │       │   ├── cognitive_distortion.py  # Governor, DistortionProfile ✅
│   │       │   ├── perception_filter.py  # Фильтр по distance/LOS [БАГ R4 ⚠️]
│   │       │   ├── npc_cognition.py      # Фасад когнитивного цикла
│   │       │   ├── npc_loader.py         # JSON → объекты
│   │       │   ├── life_engine.py        # Data-driven расписание ✅
│   │       │   ├── spatial_runtime.py    # R4 Runtime расстояний
│   │       │   ├── location_graph.py     # Граф локаций
│   │       │   ├── threat_assessor.py    # Оценка угрозы
│   │       │   ├── psyche_engine.py      # Психологические режимы
│   │       │   ├── break_progress_engine.py  # R8 Прогресс слома ✅
│   │       │   ├── behavior_mask.py      # R8 Маски [ДОЛГ C.2: override→constraint]
│   │       │   ├── reaction_priority.py  # Приоритеты реакций
│   │       │   ├── resolution_engine.py  # R5 Gap System
│   │       │   └── math_utils.py         # Утилиты
│   │       │
│   │       ├── resolution/            # R5 — МЕХАНИКА ИСХОДОВ
│   │       │   └── action_resolver.py    # Диспетчер → dnd_5e / sandbox
│   │       │
│   │       ├── state/                 # R4 — УПРАВЛЕНИЕ МИРОМ
│   │       │   ├── scene_state_manager.py   # Source of Truth + Unit of Work ✅
│   │       │   ├── context_builder.py       # shared_context для DM + NPC
│   │       │   ├── json_persistence_adapter.py
│   │       │   └── persistence_port.py
│   │       │
│   │       ├── memory/                # R1 — ПАМЯТЬ
│   │       │   ├── working_memory.py        # Краткосрочная (20 событий)
│   │       │   ├── relationship_store.py    # Матрица отношений NPC↔Player
│   │       │   ├── layered_memory.py        # L1/L2/L3
│   │       │   ├── memory_manager.py        # Фасад
│   │       │   ├── resonance_engine.py      # L3 Identity (черты из паттернов)
│   │       │   ├── importance_engine.py     # Вес событий
│   │       │   └── contradiction_resolver.py
│   │       │
│   │       ├── verbalization/         # R3 — СЛОЙ ГОЛОСА
│   │       │   ├── scene_outcome_builder.py # SceneOutcome → DMFrame ✅
│   │       │   ├── verbal_stance.py         # Intent → Stance/Tone/Urgency ✅
│   │       │   ├── scene_continuity.py      # flags, tension, emotional_vector ✅
│   │       │   ├── scene_to_dm_adapter.py   # Адаптер для DM
│   │       │   ├── verbalization_context.py # Контекст вербализации
│   │       │   └── prompt_loader.py         # Загрузка промптов
│   │       │
│   │       ├── scene/                 # Парсинг нарратива
│   │       │   └── narrative_extractor.py   # TEXT→ENTITY заблокирован ✅
│   │       │
│   │       ├── simulation/
│   │       │   └── world_state.py     # WorldTokenBudget
│   │       │
│   │       └── llm/                   # LLM провайдеры
│   │           ├── router.py
│   │           ├── provider_manager.py
│   │           ├── llama_cpp_provider.py
│   │           └── parser.py
│   │
│   └── data/
│       ├── insults_ru.json
│       └── sessions/
│
└── frontend/
    └── ui/index.html
```

---

## 4. ПОЛНЫЙ DATA FLOW ОДНОГО ХОДА

```
Игрок вводит текст
        ↓
[1] dm_router.py
    → классифицирует: action_type, intensity, target_id
    → выдаёт Event (typed, не свободный текст)
        ↓
[2] dm_scene_builder.py
    → строит R4 Spatial контекст (дистанции, видимость)
        ↓
[3] dm_validator.py  [⚠️ ДОЛГ — не реализован]
    → проверяет: is_possible, difficulty DC, social_risk
    → при is_possible=False → возвращает объяснение игроку (без LLM)
        ↓
[4] character_filter.py  [⚠️ ФАЗА 2.0 — не реализован]
    → PlayerIntent → FilteredAction
    → resistance = f(self_integrity, value_conflict, stress)
    → ACCEPT / MODIFY / RESIST / REFUSE
    → NPC видит filtered_action, не raw_intent
        ↓
[5] perception_filter.py
    → фильтрует NPC по дистанции и LOS
    → [БАГ R4]: fallback должен быть конечным числом, не 999.0
        ↓
[6] decision_hub.py  (для каждого NPC в радиусе)
    → score(action) = drive_weight * context_relevance
                    + emotion_weight
                    + relationship_modifier
                    + trait_modifier
                    + distortion_bias  [ДОЛГ C.1]
                    - fear * risk
                    + commitment_bonus  [✅]
                    - switching_cost    [✅]
    → expected_success ∈ [0..1]
    → DecisionResult { intent, expected_success, emotion_delta, stress_delta, ... }
        ↓
[7] resolution_engine.py  (R5 Gap System)
    → roll d20 → normalize [0..1]
    → final_value = clamp(roll * 0.65 + bias * 0.35, 0.05, 0.95)
    → gap = actual_success - expected_success
    → gap < 0 → стресс / trauma_marker
    → gap > 0 → уверенность / trait_boost
        ↓
[8] state_applicator.py  (единственная точка записи)
    → apply(npc_state, deltas) → новый NPCState
    → пишет CausalEntry в causal_ledger [✅]
    → _apply_progress() для commitment [✅]
        ↓
[9] scene_state_manager.commit()  (Unit of Work)
    → атомарная запись изменений
        ↓
[10] scene_outcome_builder.py
    → SceneOutcome { NpcOutcome[] }
    → _build_psychological_projection(scores_trace) → строка [✅]
    → stance_from_decision() → VerbalStance [✅]
        ↓
[11] dm_agent.py  (ЕДИНСТВЕННЫЙ LLM-вызов)
    → получает: intent + emotion_tag + psychological_projection + stance
    → НЕ получает: числа стресса, trust, fear
    → генерирует текст нарратива
        ↓
Ответ игроку (SSE stream)
```

---

## 5. ФАЗЫ РАЗРАБОТКИ

### ✅ ФАЗА 0 — ИНФРАСТРУКТУРА (ЗАВЕРШЕНА)
- GameLoop, FastAPI, SSE streaming
- SceneStateManager + PersistencePort
- LLM провайдеры (llama.cpp)
- Базовые типы данных

### ✅ ФАЗА 1 — ЯДРО СИСТЕМЫ (ЗАВЕРШЕНА)
- R1 Memory Core (L1 Numerical, L2 Event с decay, L3 Identity)
- R2 DecisionHub (базовый scorer)
- R3 Verbalization (VerbalizationContext, VerbalStance, SceneContinuity)
- R4 Spatial System (LocationGraph, PerceptionFilter)
- R8 BreakProgressEngine (5 стадий, структуры определены)
- 73+ тестов DecisionHub, 180+ тестов R3

### ✅ ФАЗА 1.5 — ПСИХОЛОГИЧЕСКАЯ ИНТЕГРАЦИЯ (ЗАВЕРШЕНА)
- CognitivDistortionEngine (3 оси, Governor, DistortionProfile)
- ProjectionLayer: _build_psychological_projection() в scene_outcome_builder
- CausalLedger (cap=20) в state_applicator + npc_state
- models/psychological.py (DistortionProfile, CausalEntry)
- Commitment Model (R2.2): inertia, switching_cost, intent_progress

---

### 🚨 ФАЗА 2.1 — КРИТИЧЕСКИЕ БАГИ (ТЕКУЩИЙ ПРИОРИТЕТ)

**Все шесть багов должны быть закрыты до начала Фазы 2.0.**

#### БАГ R4 — PerceptionFilter fallback distance=999.0
```
Файл: services/npc/perception_filter.py:119
Симптом: 5/5 NPC при dist=5.0 пропускают фильтр (должны — только 0)
Корень: fallback возвращает 999.0 вместо конечного значения
Фикс: при отсутствии distance → использовать максимальный радиус сцены,
       НЕ 999.0. Добавить проверку distance < PERCEPTION_RADIUS[tier].
```

#### БАГ R2 — player_interacts отсутствует в emotion_map
```
Файл: services/npc/decision_hub.py:868 (область emotion_map)
Симптом: "Привет, Торнин" → intent=flee при stress_d=0.0
Корень: emotion_map не содержит "player_interacts" → нет emotion_tag
        → fear_drive (0.15) доминирует без контраста
Фикс: добавить "player_interacts" в emotion_map с нейтральным/позитивным
       смещением. Приоритет TALK/OBSERVE += 0.5, WARN/REPORT -= 0.4.
```

#### БАГ R8 — SESSION_REPLACED не сбрасывает NPC state
```
Файл: services/player_session_service.py:121
Симптом: stab=0.75 при первой смене игрока, stale emotion_tag → +0.35 к FLEE
Корень: player_session_service не сбрасывает emotion_tag NPC после REPLACED
Фикс: при SESSION_REPLACED → сбросить emotion_tag всех NPC до neutral.
       НЕ сбрасывать trust/fear (это постоянная память).
```

#### БАГ R5 — "пытаюсь взять" не триггерит бросок
```
Файл: services/action/dm_router.py (классификация)
Симптом: "пытаюсь взять меч" → нет провала, DM описывает попытку без броска
Корень: Router не классифицирует "пытаться X" как physical_action
Фикс: добавить паттерн "пытаюсь|стараюсь|пробую" → classify as action,
       НЕ как plain observation. Триггерить resolution_engine.
```

#### БАГ B.3 — add_event не дедуплицирует
```
Файл: services/scene/scene_continuity.py:61 (область add_event)
Симптом: "Началась драка" ×2 при разных event_type
Корень: нет проверки дубликатов в add_event()
Фикс: дедупликация по (event_type, tick) или по хешу описания за последние N тиков.
```

#### БАГ AsyncIO — world_sim_agent semaphore
```
Симптом: "Semaphore bound to different event loop" (повторяющийся)
Корень: world_sim_agent запускается в другом event loop
Фикс: изолировать world_sim_agent. Временно — запускать через
       asyncio.run_coroutine_threadsafe в основном loop.
       Долгосрочно — рефакторинг asyncio-слоя.
```

---

### 🔒 ФАЗА 2.0 — REACTION LAYER + CHARACTER FILTER
**Предусловие: Фаза 2.1 (все 6 багов) закрыта.**
**Разблокирует: Фазу 3 (Social), Фазу 4 (World Director).**
**Без этого: система = "марионетки", не "агенты".**

#### ШАГ 0.5 — Reaction Layer (физика мира)
```
Файлы создать:
- services/reaction/reaction_resolver.py
- services/reaction/micro_event.py
- services/reaction/reaction_rules.py

Что делает:
DecisionResult → MicroEvents (физические последствия)
Примеры правил:
  threat → NPC роняет предмет
  attack → NPC выходит из разговора
  intimidate → NPC отступает на 1.5м

Почему критично:
Без физических событий нет триггеров для Spatial Events (D.0.1).
Без Spatial Events нет фактов для Social Propagation.
Без Social Propagation нет материала для World Director.
```

#### ШАГ 2.0 — CharacterFilter (персонаж ≠ игрок)
```
Файлы создать:
- services/character/character_profile.py
- services/character/character_filter.py
- services/character/resistance_scorer.py

Модель:
CharacterProfile:
  self_integrity: float ∈ [0..1]  # способность сопротивляться
  values: Dict[str, float]         # {"honour": 0.8, "survival": 0.9}
  social_constraints: Dict[str, float]  # {"noble_bearing": 0.7}
  # persistence: character_profile.json (отдельно от NPC)

CharacterFilter.filter(intent, profile, state) → FilteredAction:
  resistance = self_integrity * value_conflict * (1 + stress/100)
  if resistance < 0.3: → ACCEPT (проходит без изменений)
  if resistance < 0.6: → MODIFY (ослабить действие)
  if resistance < 0.9: → RESIST (действие + последствия: стресс, стыд, репутация)
  if resistance >= 0.9: → REFUSE (редко! только при extreme conflict)

Точка вставки в пайплайне:
  ПОСЛЕ dm_router → ДО DecisionHub
  NPC видит filtered_action, не raw_intent

ВАЖНО: CharacterFilter — чистый Python scorer.
LLM не вызывается.
```

**Матрица Trust (3 направления — все должны быть реализованы):**
```
NPC → player:      меняется от действий персонажа  [✅ реализовано]
player → NPC:      НЕ меняется автоматически        [✅ баг исправлен]
character → NPC:   меняется через CharacterFilter   [🆕 ФАЗА 2.0]
```

---

### 🔧 ФАЗА 2.3 — СТАБИЛИЗАЦИЯ ЯДРА
**Предусловие: Фаза 2.0 завершена.**

#### C.1 — Distortion → DecisionHub как модификатор
```
Текущее состояние: CognitivDistortionEngine возвращает DistortionProfile,
  но не влияет на score() в DecisionHub.

Фикс: В DecisionHub добавить:
  distortion_bias = distortion_profile.threat_bias * event.intensity
  score(action) += distortion_bias

ВАЖНО: Distortion = модификатор ВОСПРИЯТИЯ, не источник решения.
Формула: effective_event = event * distortion
НЕ: distortion отдельно принимает решение.
```

#### C.2 — BehaviorMask: от override к constraint
```
Текущее состояние: BehaviorMask переписывает волю NPC жёстко:
  COLLAPSE→IDLE, FAKE_SUBMISSION→TALK, BETRAYAL→OBSERVE
ПРОБЛЕМА: неявный "второй DecisionHub" — маппинг не масштабируется.

Фикс: переход от жёсткого override к мягкому constraint:
  Вариант А: intent_score[constrained] *= mask_modifier (0.0–1.0)
  Вариант Б: allowed_intents = constrained_set (whitelist)

Рекомендуется Вариант А (гибче, не нужно поддерживать whitelist).
```

---

### 📡 ФАЗА 3 — СОЦИАЛЬНАЯ ПРОПАГАНДА
**Предусловие: Фаза 2.0 (Reaction Layer) + SceneEvent система.**

#### D.0.1 — Spatial Events
```
game_loop генерирует event_type при изменении distance
"подойти к NPC" → spatial_event → триггер для DecisionHub
```

#### D.0.2 — Social Graph
```
NPC-NPC связи: ревность, привязанность, вражда
Правило: "если игрок рядом с X, а я привязан к X → fear_spike"
```

#### D.1 — social_engine.py
```
RelationshipMatrix (NPC↔NPC)
Слухи: событие → distortion по хопам → trust-based propagation
Decay по хопам: важность слуха падает на каждом звене
```

---

### 🌍 ФАЗА 4 — WORLD DIRECTOR
**Предусловие: Фаза 3 (Social Propagation) + CharacterFilter.**

#### E.1 — Fronts
```
Давление мира на ПЕРСОНАЖА (не на игрока напрямую).
Front = маска, которую персонаж носит для мира.
Зависит: Social Graph + CharacterFilter.
```

#### E.2 — Consequence Accumulation
```
Накопленные последствия RESIST действий.
Влияют на self_integrity (истощение воли).
"Слишком часто подчинялся → легче подчиниться снова"
```

#### E.3 — Identity Erosion (персонаж)
```
Противоположность Break System NPC.
NPC ломается под давлением мира.
Персонаж теряет себя под давлением СОБСТВЕННЫХ компромиссов.
Зависит: E.2.
```

#### E.4 — Tick-Based World Loop
```
Scheduler → world_tick() независимо от игрока.
NPC живут по расписанию без player input.
Мир меняется во время long rest.
```

---

## 6. ПСИХОЭМОЦИОНАЛЬНАЯ МОДЕЛЬ NPC (ПОЛНАЯ)

### Три слоя личности

```
L0 — CORE (почти неизменяемый)          npc_profile.py
  aggression, empathy, dominance,
  jealousy, risk_tolerance

L1 — IDENTITY (убеждения, ломаемые)     npc_state.py → NPCIdentityL1
  loyalty, self_respect,
  moral_boundaries, trust_patterns

L2 — STATE (текущее состояние)          npc_state.py → NPCState
  fear, stress, dependency, resentment,
  willpower, identity_integrity
```

### Break System (R8) — стадии слома

```
Стадия 1: Сопротивление      willpower высокий, identity стабильна
Стадия 2: Трещины            fear↑, stress↑, identity↓
Стадия 3: Рационализация     self_justification, submission_logic
Стадия 4: Адаптация          dependency↑, willpower↓
Стадия 5: Деформация         identity_integrity↓↓, хаотичность

Триггер: pressure > willpower
  pressure = fear + stress + repeated_failures - support

Маски (behavior_mask):
  TRUE_SUBMISSION   (fear↑, dependency↑, resentment↓)
  FAKE_SUBMISSION   (fear↑, resentment↑, willpower ещё есть)
  BETRAYAL          (resentment↑↑, opportunity↑)
  RESISTANCE        (willpower↑)
  COLLAPSE          (identity_integrity≈0)

Opportunity Score (окно для тайного действия):
  = player_attention↓ + distance + weapon_access + allies
  При высоком opportunity → allow_hidden_action()

Защита от злоупотребления:
  Resistance scaling: каждый следующий NPC сложнее ломается
  Cost of Control: время + ресурсы + риск
  Необратимость: recovery_rate << decay_rate
  При trauma_marker: max_willpower capped
```

### Commitment Model (R2.2) ✅

```
commitment ∈ [0..1] — инерция текущего намерения
switching_cost — штраф за смену intent:
  age_cost    = commitment * 0.08
  emotion_cost = stress/100 * 0.06
  identity_cost = 0.04 если intent ≠ drive

Intent Decay:
  effective_stall > 6 тиков → инерция начинает убывать
  Смена intent → progress × 0.3 (цепочки не ломаются)
```

### Psychological Projection (R1.5) ✅

```
Вместо чисел LLM получает строку:
  psychological_state = _build_psychological_projection(scores_trace)

4 оси:
  arousal  (low/medium/high)       ← stress, fear_delta
  stance   (hostile/defensive/     ← trust, fear, intent_target
            neutral/cooperative)
  stability (stable/pressured/     ← identity_integrity, will_state
             unstable/breaking)
  mode     (passive/reactive/      ← intent, behavior_mask
            aggressive/deceptive)

Сборка: [arousal] + [stance] + [stability] + [mode]
Пример: high + defensive + unstable + reactive
  → "напряжён, защищается, поведение нестабильно"

~15-20 атомов. Не 10000 строк.
```

---

## 7. RESOLUTION LAYER (R5) — СТОХАСТИКА

```
Принципы (неприкосновенны):
  1. Кубик НЕ принимает решение — фиксирует отклонение от ожидания
  2. NPC учатся от GAP (actual - expected), не от результата напрямую
  3. Подготовка важнее действия (preparation_cap ≈ 80%)
  4. Нет 100% и 0%: clamp(0.05, 0.95)
  5. Randomness ТОЛЬКО в ResolutionEngine, не в DecisionHub

Формула:
  roll = d20 → normalize [0..1]
  final_value = clamp(roll * 0.65 + bias * 0.35, 0.05, 0.95)
  bias = stat_modifier + context_modifier + affinity_modifier + npc_state_modifier

Outcome Mapping:
  0.00–0.05 → крит. провал + отдача
  0.05–0.25 → провал
  0.25–0.50 → негативный частичный
  0.50–0.75 → позитивный частичный
  0.75–0.95 → успех
  0.95–1.00 → крит. успех

Gap System:
  gap = actual_success - expected_success
  gap < 0 → trauma_marker, stress↑, willpower↓
  gap > 0 → confidence↑, potential trait_boost
  gap ≈ 0 → стабильность

Trait Formation (через GAP, не через события):
  частый обман игрока → paranoia
  частые неожиданные успехи → overconfidence
  частые неожиданные провалы → anxiety
```

---

## 8. ПАМЯТЬ NPC (ТРЁХСЛОЙНАЯ МОДЕЛЬ)

```
L1 — Numerical Weights (только для DecisionHub)
  trust, fear, stress, resentment, dependency
  Не передаются в LLM никогда.

L2 — Event Memory (история с деградацией)
  EventMemory {
    event_type, target_id, importance,
    clarity ∈ [0..1],       # точность воспоминания
    confidence ∈ [0..1],    # уверенность NPC
    emotion_tag,            # angry/grateful/afraid...
    stage: MemoryStage,     # VIVID / FADING / ABSTRACT
  }
  Decay и distortion: неважные события искажаются.
  Важные события (|gap| высокий + stress) → trauma_marker, не искажаются.
  Передаётся в LLM как текстовые описания (без чисел).

L3 — Identity (черты из ResonanceEngine)
  Накапливается из ABSTRACT-воспоминаний.
  abstract + emotion_tag("angry") × 3 → trait "resentful" +0.1
  abstract + emotion_tag("grateful") × 5 → scheme "protect_player"

Tier-система (объём памяти):
  Minor NPC:  0–2 события
  Middle NPC: 3–5 событий
  Major NPC:  5–10 событий + сложная identity

Clarity влияет на вербализацию:
  clarity > 0.8 → "player_attacks (target=Люся)"   # конкретика
  clarity > 0.4 → "что-то связанное с Люсей"       # размыто
  clarity ≤ 0.4 → "нечто неприятное"               # абстракция
```

---

## 9. ЦЕНТРАЛЬНЫЙ КОНФИГ КОНСТАНТ (Central Math Config)

```python
# core/constants.py — единственное место всех "магических чисел"

# Commitment
COMMITMENT_BONUS_K = 0.15
SWITCHING_COST_BASE = 0.05
EFFECTIVE_STALL_THRESHOLD = 6  # тиков до начала decay

# Perception
PERCEPTION_RADIUS = {
    "minor": 5.0,   # метров
    "middle": 8.0,
    "major": 12.0,
}
PERCEPTION_FALLBACK_DISTANCE = 15.0  # НЕ 999.0

# Break System
BREAK_TRIGGER_RATIO = 1.0     # pressure > willpower * ratio
WILLPOWER_RECOVERY_RATE = 0.02   # за тик
IDENTITY_DECAY_RATE = 0.05       # под давлением

# Resolution
RESOLUTION_DICE_WEIGHT = 0.65
RESOLUTION_BIAS_WEIGHT = 0.35
RESOLUTION_MIN = 0.05
RESOLUTION_MAX = 0.95
PREPARATION_CAP = 0.80
GAP_TRAUMA_THRESHOLD = 0.35   # |gap| > этого → trauma_marker

# Memory
WORKING_MEMORY_SIZE = 20
NARRATIVE_FACTS_MAX = 2
MEMORY_DECAY_TICKS = 10        # каждые N тиков
DISTORTION_CLARITY_FLOOR = 0.1

# Distortion Governor
DISTORTION_MAX_TOTAL = 1.0
DISTORTION_AXIS_CAP = 0.6     # максимум одной оси

# LLM Token Budgets
TOKEN_BUDGET_MAJOR_NPC = 700
TOKEN_BUDGET_MIDDLE_NPC = 350
TOKEN_BUDGET_MINOR_NPC = 180
TOKEN_BUDGET_DM_CONTEXT = 2048

# Character Filter
RESISTANCE_ACCEPT = 0.3
RESISTANCE_MODIFY = 0.6
RESISTANCE_RESIST = 0.9

# Switching Cost
AGE_COST_K = 0.08
EMOTION_COST_K = 0.06
IDENTITY_COST_BASE = 0.04
```

---

## 10. РЕЕСТР УЯЗВИМОСТЕЙ И ЗАЩИТА

| Уязвимость | Защита |
|-----------|--------|
| Спам давлением на NPC | Resistance Scaling (каждый следующий NPC сложнее) + Cost of Control (ресурсы + время) |
| Механический ролевой костюм | Проверка правдоподобия "легенды". Простые комбо без ролевого отыгрыша — слабый эффект |
| Кубиковый спам (повторные попытки) | Штраф за повторные броски + Diminishing Returns |
| Тестирование памяти NPC | Decay + distortion + случайные искажения. Важные события не искажаются — но игрок это не знает |
| Вычисление формул score() | Скрытые коэффициенты. Числа никогда не показываются игроку напрямую |
| Fog of War через LLM | LLM никогда не получает числа. Только psychological_projection строкой |
| Залипание intent (inertia exploit) | Effective Stall > 6 тиков → decay инерции начинается |
| Мировой freeze без игрока | Tick-Based World Loop (Фаза 4): мир живёт независимо |

---

## 11. БЭКЛОГ (НЕ В ТЕКУЩИХ ФАЗАХ)

| Задача | Условие включения |
|--------|------------------|
| GOAP планировщик (R10.5) | Режим "Выживание", карта, голод/крафт |
| InternalVoice / WorldLegend (R10+) | ResonanceEngine зрелый, R5 полностью откалиброван |
| NPCScheme (R10+) | Social Graph (Фаза 3) завершён |
| SQLite long_term_store | Phase 2+ (PDF кампании) |
| PDF loader + RAG (knowledge/) | Phase 2+ |
| Мультиплеер (до 8 игроков) | Фаза 4 завершена |
| Пиксель-арт карта (R14) | После стабильного MVP |
| dm_validator.py (фильтр реальности) | После CharacterFilter (Фаза 2.0) |
| BODY_TRAIT / ROLE_MARKER | Удалить при следующей чистке кода |

---

## 12. ПОРЯДОК РАБОТЫ (СЛЕДУЮЩИЕ СЕССИИ)

```
СЕЙЧАС (Фаза 2.1):
  ☐ БАГ R4: perception_filter fallback → конечное число
  ☐ БАГ R2: добавить player_interacts в emotion_map
  ☐ БАГ R8: SESSION_REPLACED → сброс emotion_tag
  ☐ БАГ R5: "пытаюсь X" → классифицировать как action
  ☐ БАГ B.3: дедупликация в add_event
  ☐ БАГ AsyncIO: изолировать world_sim_agent

ПОТОМ (Фаза 2.0 — Reaction Layer):
  ☐ micro_event.py (структура)
  ☐ reaction_rules.py (правила: threat→drop)
  ☐ reaction_resolver.py (DecisionResult → MicroEvents)
  ☐ Интеграция в game_loop.py

ПОТОМ (Фаза 2.0 — CharacterFilter):
  ☐ character_profile.py (self_integrity, values)
  ☐ resistance_scorer.py (формула)
  ☐ character_filter.py (ACCEPT/MODIFY/RESIST/REFUSE)
  ☐ Вставка в пайплайн: после dm_router, до DecisionHub

ПОТОМ (Фаза 2.3 — Стабилизация ядра):
  ☐ C.1: distortion_bias → score() в DecisionHub
  ☐ C.2: BehaviorMask override → constraint (intent_score *= modifier)

ПОТОМ (Фаза 3 — Social):
  ☐ Spatial Events (game_loop генерирует при изменении distance)
  ☐ Social Graph (NPC-NPC связи)
  ☐ social_engine.py (слухи, decay по хопам)
```

---

*Документ синтезирован из: ROAD_MAP.md, Now.md, README.md, Индекс_файлов.md,*
*Слом.md, Стохастическое_распределение_DICE.md, Баги.md, Логи.md,*
*Предложения.md, backlog.md, Plan.md, ENIGMA_ROADMAP2.md*
