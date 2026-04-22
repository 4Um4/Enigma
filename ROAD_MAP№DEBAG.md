```text
================================================================================
                        ENIGMA: ДОРОЖНАЯ КАРТА И АРХИТЕКТУРА (v2.0)
================================================================================

┌──────────────────────────────────────────────────────────────────────────────┐
│                         1. ЧТО УЖЕ СДЕЛАНО                                   │
└──────────────────────────────────────────────────────────────────────────────┘

██ ФАЗА 1 — ЗАКРЫТИЕ КОНТУРА [ЗАВЕРШЕНА]
════════════════════════════════════════════════════════════════════════════════
  ├─ 1.1 Убрать npc_agent из MAJOR сценариев ✅
  ├─ 1.3 Запретить TEXT→ENTITY (NarrativeExtractor.new_objects заблокирован) ✅
  └─ LifeEngine data-driven (activity_map вынесен в JSON) ✅

██ АУДИТ РЕАЛЬНОСТИ (ТЕХНИЧЕСКИЙ ДОЛГ И БАГИ)
════════════════════════════════════════════════════════════════════════════════
  ├─ R5 Resolution: нет бросков для физических действий ❌ [КРИТИЧНО]
  │     Лог: "пытаюсь взять меч" → нет провала, DM описывает попытку
  │     Корень: Router не классифицирует "пытаться" как INTENT_PHYSICAL
  ├─ R8 Break System: жёсткий override намерений ⚠️ [КРИТИЧНО]
  │     Корень: Маска COLLAPSE принудительно ставит IDLE, ломая Utility AI
  ├─ AsyncIO: World Sim Agent error ⚠️ [КРИТИЧНО]
  │     Корень: Semaphore bound to different event loop
  ├─ R4 PerceptionFilter: distance >= 5.0 не фильтрует ❌
  ├─ R2 DecisionHub: player_interacts → intent=flee ❌
  ├─ R8 Stability: не сбрасывается при смене сессии (SESSION_REPLACED) ⚠️
  └─ B.3 Continuity: events дублируются (нет дедупликации) ⚠️


┌──────────────────────────────────────────────────────────────────────────────┐
│             2. ИТЕРАТИВНЫЙ ПЛАН РАЗРАБОТКИ (СТРОГИЙ ПОРЯДОК)                 │
└──────────────────────────────────────────────────────────────────────────────┘
ПРИНЦИП: Каждая итерация завершается рабочим билдом. Никакого кода "в стол".

██ ИТЕРАЦИЯ 1 — ВОССТАНОВЛЕНИЕ ИНВАРИАНТОВ И HOTFIXES [БЛОКИРУЮЩИЙ ПРИОРИТЕТ]
════════════════════════════════════════════════════════════════════════════════
  [DoD - Definition of Done]: 
  - Игра запускается без AsyncIO ошибок.
  - Физические действия игрока обрабатываются кубиками (Rules Agent), а не фантазией LLM.
  - Слом воли NPC работает через веса (DecisionHub), а не через жесткую подмену (override).
  - Сессии сбрасываются чисто, NPC не реагирует на события вне радиуса 15м.

  ├─ 1.1 AsyncIO & Infrastructure Fix
  │     └─ Исправить инициализацию world_sim_agent (привязка к текущему event loop).
  ├─ 1.2 R5 Router & Physical Actions (Защита Инварианта)
  │     ├─ dm_router.py: Жесткое разделение INTENT_VERBAL и INTENT_PHYSICAL.
  │     └─ Интеграция: Любой INTENT_PHYSICAL обязан проходить через rules_agent (бросок кубиков) ДО StateApplicator.
  ├─ 1.3 R8 Break System Refactoring (Возврат к Utility AI)
  │     ├─ Убрать жесткий override (COLLAPSE → IDLE) из behavior_mask.py.
  │     └─ Внедрить mask_modifier: маска умножает веса (напр. FLEE * 3.0, ATTACK * 0.0). DecisionHub сам выбирает действие.
  └─ 1.4 State & Perception Hotfixes
        ├─ perception_filter.py: Добавить жесткий cap distance < 15.0m.
        ├─ emotion_map.json: player_interacts → neutral_tag.
        └─ player_session_service.py: Полный сброс stability и emotion_tag при SESSION_REPLACED.

██ ИТЕРАЦИЯ 2 — ФАЗА 2.0: CHARACTER FILTER (ПОЭТАПНОЕ ВНЕДРЕНИЕ)
════════════════════════════════════════════════════════════════════════════════
  [DoD - Definition of Done]: 
  - Слой CharacterFilter встроен в пайплайн между Router и DecisionHub.
  - NPC способен отказать (REFUSE) игроку на основе своих ценностей (self_integrity), не ломая Data Flow.

  ├─ 2.1 Stub Integration (Pass-through)
  │     ├─ Создать character_filter.py.
  │     ├─ Встроить в пайплайн: PlayerIntent → CharacterFilter → FilteredAction.
  │     └─ На этом этапе фильтр всегда возвращает ACCEPT. Билд работает.
  ├─ 2.2 REFUSE Logic (Базовое сопротивление)
  │     ├─ Добавить проверку self_integrity vs value_conflict.
  │     └─ Если конфликт критический → REFUSE (отказ от выполнения действия игрока).
  └─ 2.3 RESIST & MODIFY Logic (Мягкое сопротивление)
        └─ Реализовать ослабление действий (MODIFY) и добавление последствий (RESIST).

██ ИТЕРАЦИЯ 3 — СЕМАНТИЧЕСКАЯ КОМПРЕССИЯ И ЗАЩИТА ПАМЯТИ
════════════════════════════════════════════════════════════════════════════════
  [DoD - Definition of Done]: 
  - 50+ ходов в одной сессии не приводят к переполнению контекста LLM.
  - Дубликаты событий отсекаются. Старые события сжимаются в summary.

  ├─ 3.1 Event Deduplication
  │     └─ scene_continuity.py: Дедупликация в add_event по (event_type + target).
  ├─ 3.2 Importance Threshold (Фильтр мусора)
  │     └─ Внедрить порог важности: микро-события (почесал нос) не пишутся в L2 Event Memory, если importance < 0.3.
  └─ 3.3 Summary Compression
        ├─ memory_core.py: Динамический working_memory_cap (20 событий).
        └─ При превышении лимита → LLM сжимает старые события в summary_node.

██ ИТЕРАЦИЯ 4 — ФАЗА 3: ПРОАКТИВНОСТЬ (AGENDA LOOP)
════════════════════════════════════════════════════════════════════════════════
  [DoD - Definition of Done]: 
  - NPC инициирует действия (смена позы, реплика), если игрок бездействует.
  - Контекст не засоряется микро-тиками благодаря LOD (Level of Detail).

  ├─ 4.1 World Tick & LOD
  │     ├─ game_loop.py: Глобальный таймер (World Tick).
  │     └─ LOD: Тик обрабатывается полноценно только для NPC в радиусе 5м от игрока.
  ├─ 4.2 Spatial Events
  │     └─ Генерация event_type="proximity_close" и "proximity_leave" на основе изменения дистанции.
  └─ 4.3 Proactive Intents
        └─ Добавить в DecisionHub намерения: IDLE_ANIMATION, WANDER, INITIATE_CONVERSATION.

██ ИТЕРАЦИЯ 5 — ФАЗА 4: СОЦИАЛЬНАЯ ДИНАМИКА И ДАВЛЕНИЕ МИРА
════════════════════════════════════════════════════════════════════════════════
  [DoD - Definition of Done]: 
  - NPC реагируют на действия игрока с другими NPC (ревность, слухи).
  - NPC формируют "Фасады" (Fronts) для защиты от давления.

  ├─ 5.1 Social Graph & Rumors
  │     ├─ social_engine.py: Матрица отношений NPC-NPC.
  │     └─ Распространение слухов (передача summary_node с пониженным Confidence).
  ├─ 5.2 Fronts (Фасады)
  │     └─ Маски, которые NPC носит для мира (зависит от Social Propagation).
  └─ 5.3 Identity Erosion
        └─ Деградация self_integrity при частом использовании RESIST/MODIFY (из Итерации 2).


┌──────────────────────────────────────────────────────────────────────────────┐
│           3. АРХИТЕКТУРА ПРОЕКТА (РЕАЛЬНОСТЬ + ОБНОВЛЕННЫЙ ПЛАН)             │
└──────────────────────────────────────────────────────────────────────────────┘

enigma/
│
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI + startup
│   │   ├── api/                        # ТРАНСПОРТНЫЙ СЛОЙ
│   │   │
│   │   ├── models/                     # ЧИСТЫЕ ДАННЫЕ
│   │   │   ├── npc_state.py            # NPCState (динамика)
│   │   │   ├── decision.py             # Контракт DecisionResult
│   │   │   └── psychological.py        # ✅ DistortionProfile, CausalEntry
│   │   │
│   │   ├── agents/                     # LLM-агенты
│   │   │   ├── dm_agent.py             # Вербализатор
│   │   │   ├── rules_agent.py          # ⚠️ ОБЯЗАТЕЛЕН ДЛЯ ФИЗИКИ (Итерация 1)
│   │   │   └── world_sim_agent.py      # ⚠️ ТРЕБУЕТ ФИКСА ASYNCIO (Итерация 1)
│   │   │
│   │   └── services/                   # ЯДРО ЛОГИКИ
│   │       │
│   │       ├── character/              # 🆕 УРОВЕНЬ 2 — ПЕРСОНАЖ (Итерация 2)
│   │       │   ├── character_filter.py # PlayerIntent → FilteredAction
│   │       │   └── character_profile.py# self_integrity, values
│   │       │
│   │       ├── game_loop.py            # ★ КООРДИНАТОР ТАЙМИНГА (World Tick)
│   │       │
│   │       ├── action/                 # ★★★ DM SYSTEM (Парсинг и Роутинг)
│   │       │   ├── dm_orchestrator.py  
│   │       │   ├── dm_router.py        # ⚠️ ТРЕБУЕТ РАЗДЕЛЕНИЯ VERBAL/PHYSICAL
│   │       │   └── dm_scene_builder.py 
│   │       │
│   │       ├── npc/                    # ЯДРО ИНТЕЛЛЕКТА
│   │       │   ├── decision_hub.py     # [ЦЕНТР] Формула score()
│   │       │   ├── state_applicator.py # [ТОЧКА ЗАПИСИ] CausalLedger
│   │       │   ├── cognitive_distortion.py
│   │       │   ├── perception_filter.py# ⚠️ ТРЕБУЕТ CAP 15m
│   │       │   ├── break_progress_engine.py 
│   │       │   └── behavior_mask.py    # ⚠️ ТРЕБУЕТ ПЕРЕХОДА НА CONSTRAINTS
│   │       │
│   │       ├── resolution/             # МЕХАНИКА ИСХОДОВ
│   │       │   └── action_resolver.py  
│   │       │
│   │       ├── state/                  # УПРАВЛЕНИЕ МИРОМ
│   │       │   └── scene_state_manager.py   
│   │       │
│   │       ├── memory/                 # ПАМЯТЬ И КОМПРЕССИЯ (Итерация 3)
│   │       │   ├── working_memory.py   # ⚠️ ТРЕБУЕТ SUMMARY COMPRESSION
│   │       │   └── relationship_store.py
│   │       │
│   │       ├── verbalization/          # СЛОЙ ГОЛОСА (LLM)
│   │       │   ├── scene_outcome_builder.py 
│   │       │   └── verbal_stance.py    
│   │       │
│   │       └── social/                 # 🆕 СОЦИАЛЬНАЯ ДИНАМИКА (Итерация 5)
│   │           └── social_engine.py    # Слухи, связи NPC-NPC
│   │
│   └── data/                           # PERSISTENCE LAYER
│
└── frontend/                           # UI / UX LAYER


┌──────────────────────────────────────────────────────────────────────────────┐
│                    4. DATA FLOW (ОБНОВЛЕННЫЙ ПАЙПЛАЙН)                       │
└──────────────────────────────────────────────────────────────────────────────┘

RAW INPUT (PlayerIntent)
    │
    ▼
DM SYSTEM (Router)
    │
    ├──► [ЕСЛИ INTENT_PHYSICAL] ──► RULES AGENT (Бросок кубиков) ──► MicroEvents ──┐
    │                                                                              │
    └──► [ЕСЛИ INTENT_VERBAL] ────► CHARACTER FILTER (Итерация 2)                  │
                                        │                                          │
                                        ▼                                          │
                                  FilteredAction ◄─────────────────────────────────┘
                                        │
                                        ▼
                                  PERCEPTION FILTER (Cap 15m)
                                        │
                                        ▼
                                  CognitiveDistortionEngine
                                        │
                                        ▼
                                  DECISIONHUB (PURE SCORER)
                                  (Учитывает mask_modifiers из Break System)
                                        │
                                        ▼
                                  DecisionResult[]
                                        │
                                        ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║  СЛОЙ 1 — ФИЗИЧЕСКАЯ РЕАЛЬНОСТЬ                                              ║
║  StateApplicator (Пишет CausalEntry в CausalLedger)                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                        │
                                        ▼
╔══════════════════════════════════════════════════════════════════════════════╗
║  СЛОЙ 2 — СУБЪЕКТИВНАЯ РЕАЛЬНОСТЬ                                            ║
║  _build_psychological_projection() → NpcOutcome.psychological                ║
╚══════════════════════════════════════════════════════════════════════════════╝
                                        │
                                        ▼
                                  DMFrame
                                        │
                                        ▼
                                  LLM (ТОЛЬКО ВЕРБАЛИЗАЦИЯ)
                                        │
                                        ▼
                                  FINAL TEXT


================================================================================

0.1 ГЛАВНЫЙ ПРИНЦИП (НЕПРИКОСНОВЕНЕН)

```
LLM НЕ ПРИНИМАЕТ РЕШЕНИЯ.
LLM НЕ МЕНЯЕТ СОСТОЯНИЕ.
LLM НЕ ВЫДАЁТ ДЕЛЬТЫ.
```

**LLM = слой вербализации.** Получает `intent` (намерение), `emotion` (эмоция строкой) и сжатый контекст (Summary). Возвращает текст. Всё.

**Python = слой интеллекта.** `DecisionHub` считает `score(action)` по числовым весам. Только он решает что произойдет. Физические действия разрешаются через `Rules Agent` (кубики), а не через фантазию LLM.

**ГЛАВНЫЙ ИНВАРИАНТ СИСТЕМЫ:**
```text
Ни LLM, ни persistence не имеют права вводить новые факты.
LLM → только текст, не структура.
Parser → не создаёт сущности.
Commitment → не является фактом, только состоянием.
ХАРДКОД отдельных NPC ЗАПРЕЩЕН!!! Система должна быть масштабируемой.
```
```
****

Известные архитектурные долги:

Двери в стенах — нужно разделить на проходы в map_editor
PlayerMemory in-memory — нужна персистенция
Направления ("иду на север") — парсится, но move.direction не используется в game_loop
_npc_id_to_display загружает кэш лениво — можно сломаться если config/npc пустой

****

Архитектурный контракт свободной воли аватара:
Игрок нажимает / вводит
        ↓
   TextInput
        ↓
  ActionRouter ←── AvatarWill ──── self_integrity, stress, erosion
        ↓              ↓
   Нормальный       Сопротивление:
   поток            - искажение команды
        ↓           - задержка выполнения
MovementIntent      - прерывание разговора
   / DM Loop        - самостоятельное действие

   AvatarWill — НЕ DecisionHub. DecisionHub решает что делает NPC. AvatarWill решает насколько аватар подчиняется игроку.

Формула (упрощённо):

compliance = self_integrity × (1 - stress/100)
compliance < 0.3 → сопротивление возможно
erosion_accumulator > threshold → самостоятельные действия

****

Архитектурный анализ завершён. Вот что есть и что нужно:

**Уже есть (переиспользуем):**
- `WorldTickEngine.compute_proactive_decisions()` — решения NPC каждый тик
- `NeedEngine` — растёт hunger/thirst/urgency со временем
- `EconomicModifier` — голод усиливает TRADE, страх усиливает FLEE
- `DecisionHub` — финальный расчёт intent + score
- `StateApplicator` — применяет дельты к NPCState

**Нужно создать:**

```
backend/npc_sandbox.py
├── SandboxConfig — настройки симуляции
│   ├── npc_overrides: {npc_id: {money, stress, needs...}}
│   ├── tick_count: int
│   ├── locked: bool (запереть — нельзя покинуть локацию)
│   └── snapshot_interval: int (каждый N тиков — слепок)
│
├── Snapshot — состояние NPC в момент тика
│   ├── tick: int
│   ├── npc_id: str
│   ├── hp, stress, resentment, money, intent, score
│   ├── needs: {type: urgency}
│   └── deltas: что изменилось с прошлого слепка
│
├── NPCSandbox — ядро симуляции
│   ├── load_npcs() — грузит из config + применяет overrides
│   ├── run_tick() — один тик (NeedEngine → EconomicModifier → DecisionHub → StateApplicator)
│   ├── run_simulation() — цикл N тиков, собирает snapshots
│   └── results() — возвращает список Snapshot
│
└── SandboxReporter — вывод результатов
    ├── print_table() — консольная таблица (таблица по тикам)
    ├── save_csv() — CSV для Excel
    └── plot_charts() — matplotlib графики (опционально)
```

**Графики (примеры):**
1. Stress по тикам для каждого NPC (линии)
2. Money по тикам (линии)
3. Intent distribution (stacked bar — какой % тиков каждый intent)
4. "Кто выиграл/проиграл" — delta hp + delta money + delta stress за всю симуляцию

**Ключевой вопрос перед реализацией:**

`NeedEngine` обновляет `neglected_ticks` — но я не видел метод `tick()`. Нужно проверить как он вызывается:

```
Get-Content C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\services\economy\need_engine.py | Select-String -Pattern "def.*tick|def.*update|def.*compute" | Select-Object -Property LineNumber, Line
```

Делаем это или сначала посмотрим NeedEngine?

Предсуществующий долг (зафиксирован):
test_spatial_runtime_r4.py — нет location_templates.json
test_player_cognition_pipeline.py — сломан
OutcomeResult missing wound_severity/potential_conditions — физический движок
Фронтенд: выбор персонажа откатывает в главное меню


****

Это две большие задачи. Отвечу по порядку:

---

## LLM как вербализатор психологии

**Ответ: будет работать, если правильно расставить приоритеты.**

| Компонент | Задержка | Критично? |
|-----------|----------|-----------|
| Движок тиков | 50-100мс | Да |
| Решения NPC (DecisionHub) | 5-20мс | Да |
| Физика/коллизии | 16мс | Да |
| **Вербализация LLM** | 100-500мс | **Нет** |

LLM не должна быть в критическом пути. Правильная архитектура:

```
[WORLD TICK 50мс] → [NPC решения 20мс] → [Движение/бой 16мс]
                                                        ↓
                                              [Очередь событий]
                                                        ↓
                                         [LLM вербализация 300мс]
                                                        ↓
                                              [Обновление текста]
```

LLM **асинхронно** переводит сухие события в текст:
- Событие: `npc_id=thief, intent=TRADE, target=player`
- LLM: "Тень мелкого человека отделилась от стены. Нервный голос шепчет: 'Эй, путник... не хочешь ли купить кое-что?'"

**Модель для этого:**
- 7B-8B параметров (Llama, Mistral, Qwen)
- Квантизированная (4-bit) — влезет в 6-8GB VRAM
- Latency 100-200мс на короткий промпт
- Достаточно для "переводчика психологии"

---

## Адаптивные тики + WASD + LLM

Это **отдельная архитектурная сессия**, не одна правка. Причины:

1. **Не вижу pygame кода** — только `dump_*.py` скрипты на верхнем уровне
2. **Нужен рефакторинг game_loop** — сейчас он синхронный, запрос-ответ
3. **Связка backend ↔ frontend** — как они общаются? WebSocket? HTTP? Прямой импорт?

---

## Что мне нужно для работы

Выполни:

```
Get-ChildItem -Path "." -Directory | Where-Object { $_.FullName -notmatch "__pycache__|\.venv|\.git|node_modules" } | Select-Object Name
```

И если есть папка с pygame/UI:

```
Get-ChildItem -Path "." -Filter "*.py" -Recurse -Depth 3 | Where-Object { $_.FullName -notmatch "backend|__pycache__|\.venv" } | Select-Object FullName
```

---

## Предварительный план (если подтвердится структура)

**Фаза 1: Двойной цикл (backend)**
- Отделить "логический тик" от "хода игрока"
- Добавить параметр `tick_pace` в game_loop

**Фаза 2: WebSocket API (связка)**
- Backend публикует события мира в реальном времени
- Pygame подписывается и отображает

**Фаза 3: Адаптивные тики (pygame)**
- Отслеживать ввод (WASD vs текст)
- Динамически регулировать частоту запросов к backend

**Фаза 4: LLM вербализатор**
- Отдельный поток/процесс
- Очередь событий → LLM → очередь текстов
- Не блокирует игровой цикл

---

****

Создаю дорожную карту. После подтверждения — начинаем реализацию по шагам.

---

## ДОРОЖНАЯ КАРТА: Narrative Pipeline Refactor

**Цель:** LLM генерирует осмысленный текст вместо "Ничего не произошло" на моделях 7B.

---

### ФАЗА 1: SCENE_SUMMARY (сжатие контекста перед LLM)

**Задача:** LLM видит не 20 блоков инструкций, а 3-5 строк суть

**Пункт 1.1:** Создать `SceneNarrativeCompressor` в `backend/app/services/verbalization/`
- Вход: полный контекст (scene_state, npc_contexts, events)
- Выход: 3-5 строк Summary
- Формат: "[SCENE_SUMMARY]\n...\n[/SCENE_SUMMARY]"

**Пункт 1.2:** Интегрировать в `dm_agent.py` — вставлять Summary вместо сырых блоков

**Пункт 1.3:** Убрать из промпта: REGIME_BLOCK, PSYCH_ACTIONS, DM_PROMPT_BLOCK, CONTINUITY_FINAL, DM_FACTS_INJECTED, SCENE_EVENTS_DM

**Результат ожидаемый:** промпт сокращён с ~40 строк до ~15

---

### ФАЗА 2: Приоритет контента (ЧТО → КТО → КАК)

**Задача:** LLM видит информацию в порядке значимости, а не в порядке генерации

**Пункт 2.1:** Переструктурировать промпт `dm_agent._build_prompt()`:
```
1. [ACTION] Что сделал игрок
2. [FOCUS] Кто в фокусе (2-3 NPC с intent + regime)
3. [BACKGROUND] Остальные NPC (список, без деталей)
4. [SCENE] Объекты вокруг (только salience-отфильтрованные)
5. [RULES] Броски/проверки (если есть)
```

**Пункт 2.2:** Убрать дублирование: PSYCH_ACTIONS и REGIME_BLOCK содержат одни данные — оставить один блок

**Результат ожидаемый:** LLM не тонет в деталях, фокус на фокус- NPC

---

### ФАЗА 3: LLM = только оформление (не решения)

**Задача:** LLM не решает что делает NPC, а описывает результат

**Пункт 3.1:** Убрать из промпта: "NPC готовы отвечать", "decision_result", "intent=OBSERVE"
**Пункт 3.2:** Заменить на описания: "Люся смотрит на тебя", "Торнин стоит у стойки"

**Пункт 3.3:** R3 Direct Mode: не "сгенерируй реплики NPC", а "опиши что они делают"

**Результат ожидаемый:** LLM не путает описание с директивами

---

### ФАЗА 4: WORLD EVENT MEMORY (опционально, после ФАЗЫ 1-3)

**Задача:** NPC реагируют на события, которые не видели напрямую

**Пункт 4.1:** Создать `WorldEventMemory` — глобальный буфер последних N событий
**Пункт 4.2:** При генерации промпта — фильтровать события по дистанции и слуху
**Пункт 4.3:** Интегрировать в SCENE_SUMMARY: "Торнин слышал крик из-за угла"

**Результат ожидаемый:** мир консолидируется, NPC реагируют на далёкие события

---

### ПОРЯДОК РЕАЛИЗАЦИИ

| Шаг | Фаза | Изменение |
|---|---|---|
| 1 | 1.1 | Создать `SceneNarrativeCompressor` |
| 2 | 1.3 | Убрать мусор из промпта |
| 3 | 2.1 | Переструктурировать порядок блоков |
| 4 | 2.2 | Убрать дублирование PSYCH_ACTIONS/REGIME |
| 5 | 3.1 | Убрать decision-result из промпта |
| 6 | 3.2 | Заменить intent на описания |
| 7 | 3.3 | Переписать R3 directive |
| 8 | Тест | Запустить, проверить ответ LLM |
| 9 | 4.1-4.3 | WORLD EVENT MEMORY (после стабильности) |

---

Confirm — начинаем с Шага 1?

*****

scene_narrative_compressor.py

Есть предложение на рассмотерние:

**Да. Эти принципы — не «ещё один способ», а единственно верный способ сделать LLM-генерацию стабильной в игре.** Ваш текущий `SceneNarrativeCompressor` делает шаг в правильном направлении, но он всё ещё передаёт **контекст**, а не **контракт**. LLM видит `regime`, `intensity`, `stability` — и именно здесь рождается нестабильность: она начинает интерпретировать цифры по-своему.

Вот архитектурный рефакторинг, который превращает ваш код в боевой pipeline.

---

## 1. Текущие проблемы вашего кода

| Проблема | Почему это опасно |
|----------|-------------------|
| `intent`, `regime`, `intensity`, `stability` в промпте | LLM начинает *переинтерпретировать* состояние. `intensity=0.8` для неё может стать «яростно кричит», хотя система решила «сжато молчит» |
| `confusion +0.09` | Сырые цифры. LLM не знает шкалы, будет врать |
| `[SCENE_SUMMARY]` — это всё ещё narrative blob | Нет strict schema. LLM может проигнорировать часть или придумать своё |
| Нет `FallbackGenerator` | Если LLM вернёт мусор — NPC зависнет |
| Нет `ResponseValidator` | LLM может выдать 4 предложения вместо 2, изменить intent, добавить персонажа |
| `focus_npcs` может быть списком | Даже 3 NPC в фокусе — перегруз для 7B |

---

## 2. Целевая архитектура: 4 слоя

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: FocusSelector (уже есть R3 — оставляем)          │
│  → 1 NPC, максимум 2                                        │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2: StateInterpreter (НОВЫЙ)                          │
│  stress=18.5 ──→ "в панике"                                 │
│  intent=flee ──→ "пытается убежать"                         │
│  hp=12/15 ────→ "лёгкая рана"                               │
├─────────────────────────────────────────────────────────────┤
│  LAYER 3: SceneCompressor (РЕФАКТОРИНГ)                     │
│  ≤3 предложения, только факты, без цифр, без системных слов │
├─────────────────────────────────────────────────────────────┤
│  LAYER 4: ContractBuilder (НОВЫЙ)                           │
│  Формирует жёсткий JSON-контракт для LLM                    │
├─────────────────────────────────────────────────────────────┤
│  LLM (только оформляет, не решает)                          │
├─────────────────────────────────────────────────────────────┤
│  LAYER 5: PostProcessor (Validator + Fallback)              │
│  Проверяет structured output, приводит к канону             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Конкретный код рефакторинга

### 3.1 StateInterpreter (перевод чисел в человеческие состояния)

Этот слой гарантирует, что LLM никогда не увидит `stress=18.5` или `control=0.25`.

```python
from dataclasses import dataclass
from typing import List, Optional
from enum import Enum


class UrgencyLevel(str, Enum):
    CALM = "спокойна"
    ALERTED = "напряжена"
    SCARED = "напугана"
    PANIC = "в панике"
    BROKEN = "в шоке, не контролирует себя"


class PhysicalState(str, Enum):
    UNHARMED = "не ранена"
    SCRATCHED = "лёгкая рана"
    WOUNDED = "ранена"
    CRITICAL = "тяжело ранена"
    INCAPACITATED = "не может двигаться"


class IntentDescription(str, Enum):
    FLEE = "пытается убежать"
    FIGHT = "готова к драке"
    TALK = "хочет говорить"
    HIDE = "прячется"
    OBSERVE = "наблюдает осторожно"
    SURRENDER = "сдаётся"
    AID = "помогает"


@dataclass(frozen=True)
class NPCStateDescription:
    """Человекочитаемое состояние NPC. Ни одной цифры."""
    name: str
    intent: str           # "пытается убежать"
    emotional_state: str  # "в панике"
    physical_state: str   # "лёгкая рана"
    conditions: List[str] # ["shaken", "disarmed"]
    can_speak: bool
    can_move: bool


class StateInterpreter:
    """
    Единственное место, где числа превращаются в слова.
    Если дизайнер поменяет шкалу — меняем только здесь.
    """
    
    # Пороги психологического состояния (из вашей psycho_economy)
    STRESS_THRESHOLDS = [
        (0.8, UrgencyLevel.BROKEN),
        (0.6, UrgencyLevel.PANIC),
        (0.4, UrgencyLevel.SCARED),
        (0.2, UrgencyLevel.ALERTED),
    ]
    
    def interpret(
        self,
        npc_id: str,
        stress: float,           # 0.0-1.0 (нормализованная тревога)
        hp_ratio: float,         # 0.0-1.0
        intent_enum,             # Enum из вашей системы AI
        conditions: List[str],
        can_speak: bool,
        can_move: bool,
    ) -> NPCStateDescription:
        
        emotional = self._stress_to_word(stress)
        physical = self._hp_to_word(hp_ratio)
        intent_str = self._intent_to_word(intent_enum)
        
        return NPCStateDescription(
            name=npc_id,
            intent=intent_str,
            emotional_state=emotional,
            physical_state=physical,
            conditions=conditions,
            can_speak=can_speak,
            can_move=can_move,
        )
    
    def _stress_to_word(self, stress: float) -> str:
        for threshold, word in self.STRESS_THRESHOLDS:
            if stress >= threshold:
                return word.value
        return UrgencyLevel.CALM.value
    
    def _hp_to_word(self, ratio: float) -> str:
        if ratio <= 0.0: return PhysicalState.INCAPACITATED.value
        if ratio < 0.25: return PhysicalState.CRITICAL.value
        if ratio < 0.5: return PhysicalState.WOUNDED.value
        if ratio < 0.9: return PhysicalState.SCRATCHED.value
        return PhysicalState.UNHARMED.value
    
    def _intent_to_word(self, intent) -> str:
        mapping = {
            "flee": IntentDescription.FLEE,
            "attack": IntentDescription.FIGHT,
            "talk": IntentDescription.TALK,
            "hide": IntentDescription.HIDE,
            "observe": IntentDescription.OBSERVE,
            "surrender": IntentDescription.SURRENDER,
            "aid": IntentDescription.AID,
        }
        key = intent.value if hasattr(intent, "value") else str(intent).lower()
        return mapping.get(key, IntentDescription.OBSERVE).value
```

### 3.2 SceneCompressor (факты ≤3 предложения)

Ваш текущий метод `compress` рефакторим: убираем системные термины, оставляем только факты.

```python
@dataclass
class CompressedScene:
    """Результат сжатия. Только факты, никаких цифр."""
    what_happened: str      # "Игрок ударил Люсю. Она упала."
    where: str              # "В таверне."
    atmosphere: str         # "Напряжение."
    
    def to_prompt(self) -> str:
        parts = [self.what_happened]
        if self.where:
            parts.append(self.where)
        if self.atmosphere:
            parts.append(self.atmosphere)
        return " ".join(parts)


class SceneCompressor:
    """
    Заменяет ваш текущий compress().
    Выход: ≤3 предложения, только факты, без цифр.
    """
    
    def compress(
        self,
        player_action: str,
        target_state: Optional[NPCStateDescription],
        location_name: str,
        tension_level: str,   # уже интерпретированное: "спокойно" / "напряжение"
        nearby_danger: bool = False,
    ) -> CompressedScene:
        
        # Факт 1: Что сделал игрок и что произошло
        what = self._describe_action(player_action, target_state)
        
        # Факт 2: Где (если релевантно)
        where = f"В {location_name}." if location_name else ""
        
        # Факт 3: Атмосфера (только если не спокойно)
        atmosphere = ""
        if nearby_danger:
            atmosphere = "Рядом опасность."
        elif tension_level != "спокойно":
            atmosphere = tension_level.capitalize() + "."
        
        return CompressedScene(
            what_happened=what,
            where=where,
            atmosphere=atmosphere,
        )
    
    def _describe_action(self, action: str, target: Optional[NPCStateDescription]) -> str:
        if not target:
            return f"Игрок {action}."
        
        # Убираем системные глаголы из action, если они есть
        clean_action = action.replace("[", "").replace("]", "")
        
        # Добавляем последствия, если они фактические
        consequence = ""
        if target.physical_state != "не ранена":
            consequence = f" {target.name} {target.physical_state}."
        elif target.emotional_state != "спокойна":
            consequence = f" {target.name} {target.emotional_state}."
        
        return f"Игрок {clean_action}.{consequence}"
```

### 3.3 ContractBuilder (жёсткий контракт для LLM)

Это то, что реально уходит в LLM. Никаких `[SCENE_SUMMARY]`, только JSON.

```python
from typing import Literal


@dataclass(frozen=True)
class NarrativeContract:
    """
    Единственный источник правды для LLM.
    LLM не должна знать ничего, кроме этого контракта.
    """
    scene: str                    # CompressedScene.to_prompt()
    player_action: str
    npc: NPCStateDescription
    tone: Literal["calm", "tense", "violent", "intimate"]
    rules: dict
    task: str                     # Что именно должен сделать LLM


class ContractBuilder:
    DEFAULT_RULES = {
        "max_sentences": 2,
        "style": "natural_speech",
        "forbidden": ["придумывать события", "менять намерение NPC", "описывать мысли NPC"]
    }
    
    def build(
        self,
        compressed_scene: CompressedScene,
        player_action: str,
        npc_state: NPCStateDescription,
        tone: str = "tense",
    ) -> NarrativeContract:
        
        task = self._build_task(npc_state)
        
        return NarrativeContract(
            scene=compressed_scene.to_prompt(),
            player_action=player_action,
            npc=npc_state,
            tone=tone,
            rules=self.DEFAULT_RULES,
            task=task,
        )
    
    def _build_task(self, npc: NPCStateDescription) -> str:
        if not npc.can_speak:
            return "Опиши физическую реакцию NPC. Без диалога."
        if not npc.can_move:
            return "Опиши, как NPC реагирует, не вставая. Максимум 2 предложения."
        return "Опиши реакцию NPC естественной речью или действием."
    
    def to_system_prompt(self) -> str:
        """Фиксированный SYSTEM prompt. Меняется только при смене повествователя."""
        return (
            "Ты — игровой рассказчик. Твоя задача: оформить реакцию NPC "
            "на основе заданного состояния. НЕ придумывай новые события. "
            "НЕ меняй намерение NPC. Пиши кратко и естественно."
        )
    
    def to_user_prompt(self, contract: NarrativeContract) -> str:
        """Динамический USER prompt. Strict format."""
        npc = contract.npc
        
        lines = [
            f"[СЦЕНА]",
            contract.scene,
            "",
            f"[ИГРОК]",
            contract.player_action,
            "",
            f"[NPC]",
            f"Имя: {npc.name}",
            f"Состояние: {npc.emotional_state}",
            f"Намерение: {npc.intent}",
            f"Физически: {npc.physical_state}",
        ]
        if npc.conditions:
            lines.append(f"Условия: {', '.join(npc.conditions)}")
        lines.extend([
            f"Может говорить: {'да' if npc.can_speak else 'нет'}",
            f"Может двигаться: {'да' if npc.can_move else 'нет'}",
            "",
            f"[ЗАДАЧА]",
            contract.task,
            f"Максимум {contract.rules['max_sentences']} предложения.",
        ])
        
        return "\n".join(lines)
```

### 3.4 Structured Output + PostProcessing

```python
import json
from dataclasses import asdict


@dataclass
class NarrativeOutput:
    type: Literal["speech", "action", "mixed"]
    text: str
    emotion: str
    valid: bool = True  # выставляется валидатором


class ResponseValidator:
    """
    Второй слой контроля. LLM — ненадёжный компонент.
    """
    
    def __init__(self, contract: NarrativeContract):
        self.contract = contract
        self.max_len = contract.rules["max_sentences"] * 80  # ~80 симв./предложение
    
    def validate(self, raw_response: str) -> NarrativeOutput:
        # Парсим JSON (если LLM поддерживает structured output)
        try:
            data = json.loads(raw_response)
            text = data.get("text", "").strip()
            out_type = data.get("type", "action")
            emotion = data.get("emotion", self.contract.npc.emotional_state)
        except json.JSONDecodeError:
            # Fallback: трактуем как plain text
            text = raw_response.strip()
            out_type = self._detect_type(text)
            emotion = self.contract.npc.emotional_state
        
        # Проверка 1: пустой ответ
        if not text:
            return self._fallback("empty")
        
        # Проверка 2: слишком длинно
        if len(text) > self.max_len:
            text = self._truncate(text)
        
        # Проверка 3: NPC не может говорить, но text — диалог
        if not self.contract.npc.can_speak and out_type == "speech":
            out_type = "action"
            text = self._force_action(text)
        
        # Проверка 4: intent не изменился (heuristic)
        if self._intent_changed(text):
            return self._fallback("intent_violation")
        
        return NarrativeOutput(
            type=out_type,
            text=text,
            emotion=emotion,
            valid=True,
        )
    
    def _detect_type(self, text: str) -> str:
        if '"' in text or text.endswith(('.', '!', '?')) and len(text) < 60:
            return "speech"
        return "action"
    
    def _truncate(self, text: str) -> str:
        sentences = text.split('. ')
        return '. '.join(sentences[:self.contract.rules["max_sentences"]]) + '.'
    
    def _force_action(self, text: str) -> str:
        # Убираем кавычки, заменяем на действие
        return text.replace('"', '').replace("говорит", "издаёт звук")
    
    def _intent_changed(self, text: str) -> bool:
        # Простая эвристика: если LLM заставляет NPC атаковать, хотя intent=flee
        lower = text.lower()
        intent = self.contract.npc.intent
        
        if "flee" in intent and ("атакует" in lower or "набрасывается" in lower):
            return True
        if "surrender" in intent and ("убегает" in lower or "сражается" in lower):
            return True
        return False
    
    def _fallback(self, reason: str) -> NarrativeOutput:
        """Fallback на шаблоны. Критично для стабильности."""
        npc = self.contract.npc
        
        templates = {
            "flee": f"{npc.name} вскрикивает и отступает назад.",
            "fight": f"{npc.name} встаёт в боевую стойку.",
            "talk": f"{npc.name} поднимает руку, зовя на разговор.",
            "hide": f"{npc.name} прижимается к стене, стараясь не шевелиться.",
            "observe": f"{npc.name} внимательно смотрит на игрока.",
        }
        
        # Пытаемся найти по intent
        key = "observe"
        for k in templates:
            if k in npc.intent:
                key = k
                break
        
        return NarrativeOutput(
            type="action",
            text=templates[key],
            emotion=npc.emotional_state,
            valid=False,  # помечаем как fallback
        )
```

---

## 4. Как это связать с вашей психологией (PsychoEconomy)

Из `PsychoEconomy` вы получаете `stress`, `fear`, `control`. Это сырые числа. **StateInterpreter** — единственный мост между психологией и narrative:

```python
# В вашем game loop:
from psycho_economy import PsychoEconomy  # ваш файл

def process_npc_turn(npc, player_action):
    # 1. Психология считает состояние
    psycho = PsychoEconomy(npc.profile)
    stress = psycho.profile.fear * 0.6 + psycho.profile.desire * 0.3
    
    # 2. StateInterpreter переводит в слова
    interpreter = StateInterpreter()
    state = interpreter.interpret(
        npc_id=npc.id,
        stress=stress,
        hp_ratio=npc.hp / npc.max_hp,
        intent_enum=npc.ai.intent,
        conditions=npc.status_conditions,
        can_speak=npc.can_speak,
        can_move=npc.can_move,
    )
    
    # 3. Компрессия сцены
    compressor = SceneCompressor()
    scene = compressor.compress(
        player_action=player_action,
        target_state=state,
        location_name=npc.location.name,
        tension_level="напряжение" if stress > 0.5 else "спокойно",
    )
    
    # 4. Контракт
    builder = ContractBuilder()
    contract = builder.build(scene, player_action, state)
    
    # 5. LLM (только оформление!)
    system = builder.to_system_prompt()
    user = builder.to_user_prompt(contract)
    raw_llm = call_your_llm(system, user)  # ваш вызов
    
    # 6. Валидация
    validator = ResponseValidator(contract)
    result = validator.validate(raw_llm)
    
    return result.text  # Гарантированно валидный output
```

---

## 5. Что улучшить ещё (для масштаба)

| Улучшение | Зачем |
|-----------|-------|
| **Шаблоны по эмоциям** | Не только fallback, но и «вариации». `fear` + `panic` → 3 разных fallback-реплики, выбор random |
| **Tone Injection из Music/Audio** | Если в локации играет тревожная музыка, `tone="violent"` подаётся в Contract автоматически |
| **Memory Bank (2-3 строки)** | В контракт добавлять: «Ранее: игрок ударил её 2 минуты назад». Это не контекст, а **факт предыстории** |
| **Batch Generation** | Если 2 NPC в фокусе — не 2 вызова LLM, а 1 контракт с 2 NPC, разделёнными `[NPC]` блоками. Экономия токенов |
| **A/B Registry** | Логгировать `contract → raw_llm → validated_output`. Через месяц вы увидите, какие promt'ы валятся чаще |

---

## 6. Главное правило, которое стоит закрепить в коде

```python
# Добавьте это как документацию в ContractBuilder:

"""
ИНВАРИАНТЫ КОНТРАКТА:
1. LLM никогда не видит числовые значения (stress, hp, coordinates).
2. LLM никогда не видит системные enum'ы (intent, regime, posture).
3. LLM не может изменить intent NPC — он передан как строка-константа.
4. Если LLM нарушает контракт → мгновенный fallback, никаких retry.
5. Контракт < 1500 токенов всегда. Если больше → FocusSelector сработал неправильно.
"""
```

---

**Итог:** ваш текущий `compress` — хорошая заготовка. Но чтобы он стал **надёжным**, нужно разделить ответственность: **Focus** выбирает R3, **Interpreter** переводит цифры в слова, **Compressor** сжимает факты, **Contract** жёстко ограничивает LLM, **Validator** ловит диверсии. Тогда LLM действительно будет только «оформлять выбранное» — и ваша система станет предсказуемой.


Теперь полная картина оставшихся блоков:

Блок
Содержание
Текущая позиция
scene_block	Объекты и NPC в сцене	1-я
context_str	"УЖЕ БЫЛО СКАЗАНО" (guardrail)	2-я
player_state_block	HP, стресс игрока	3-я
actions	Что сделал игрок	4-я (зарыта!)
rules_str	Результаты бросков	5-я
npc_str	Реакции NPC	6-я
npc_actions_str	Физические действия NPC	7-я
world_str	Изменения мира	8-я
physics_warnings	Ограничения физики	9-я
python_engines_block	Результаты вычислений	10-я

Проблема: Действие игрока — триггер всего — на 4-й позиции. Сцена (объекты) — на 1-й.


Цепочка замкнулась:
_run_agent_safe → agent.run() → narrate() → EXCEPTION
→ except на строке 91 → jsonl_log({"error": str(e)}) → _fallback_narrate()
→ "Ничего не произошло."
Ошибка логируется в JSONL но не в консоль. Поэтому в терминале тишина. Нужно найти саму ошибку.

Корень #2 найден:
ModelRouter.request_for_agent() got an unexpected keyword argument 'agent'
Строка 404 в dm_agent.py передаёт agent="dm", но метод этого аргумента не принимает. Исключение ловится на строке 91 → фоллбэк → "Ничего не произошло."

При этом _run_agent_safe логирует SUCCESS потому что run() вернул валидный dict (фоллбэк) — ошибка замаскирована.


Прогресс: фиксы 1 и 2 сработали (нет R5 провала, нет unexpected keyword argument). Но теперь TIME OUT — DM-агент зависает.

Корень: deadlock. request_for_agent пытается использовать event loop главного потока, но главный поток ждёт завершения thread через asyncio.to_thread. Классический deadlock.


Now I understand the full picture. Let me trace the exact prompt flow:

game_loop.py builds npc_result with dm_frame inside, and npc_reactions: [] (empty)
game_loop.py passes this to dm_agent.narrate()
dm_agent._build_prompt() reads npc_result.get("npc_reactions", []) → empty list → npc_str = ""
dm_agent._build_prompt() does NOT use dm_frame at all! The dm_frame is passed but never read in _build_prompt()
BUT the log shows [DM_PROMPT_BLOCK] with "Ключевые NPC (фокус сцены):" text
to_dm_prompt_block() is only called in tests, not in production

## ДОРОЖНАЯ КАРТА: Почему LLM возвращает "Ничего не произошло"

Основано на реальных находках в коде, не на абстракциях.

---

### ЭТАП 1: Блокирующие противоречия (без этого ничего не работает)

**1.1 System prompt говорит "НЕ генерируй реплики NPC" — но R3 Direct требует их генерировать**

```
Promt_AI.json строка 10:  "НЕ генерируй реплики NPC — они идут отдельным каналом"
dm_agent.py строка 336 fallback: "DM (ты): описываешь мир И генерируешь реплики NPC"
```

`_get_system_prompt` загружает Promt_AI.json если файл > 20 символов. Файл загружается. Его строка 10 активна. Но R3 Direct mode передаёт DMFrame и ожидает что DM опишет реакции NPC включая реплики. **LLM получает противоречивый приказ: "не генерируй" + DMFrame с "Тень пытается убежать". Результат: "Ничего не произошло" — минимальный комплаенс.**

Исправление: Убрать строку 10 из Promt_AI.json или добавить условие для R3 mode.

**1.2 ПРАВИЛА РЕАКЦИЙ NPC дублируются 2 раза**

```
Promt_AI.json строки 39-59:  ПРАВИЛА РЕАКЦИЙ NPC (статический, всегда)
scene_state_manager.py строки 1495-1509: ПРАВИЛА РЕАКЦИЙ NPC (динамический, зависит от target)
```

Два одинаковых блока инструкций в одном промпте для 7B модели — шум и путаница.

Исправление: Убрать из Promt_AI.json (оставить динамический в scene_state_manager).

**1.3 CONTINUITY блок содержит сырые числа без шкалы**

```
[CONTINUITY_FINAL]
эмоциональный фон: confusion=+0.1
```

LLM не знает что значит 0.1. Это шум.

Исправление: Убрать числовые значения, оставить только flags и events.

---

### ЭТАП 2: Промпт слишком длинный для 7B (20+ блоков)

Текущий порядок в `_build_prompt`:

```
1. scene_block          — объекты + NPC позиции + ПРАВИЛА РЕАКЦИИ (дубликат!)
2. "Текущая локация"
3. player_state_block   — HP, стресс
4. context_str          — "УЖЕ БЫЛО СКАЗАНО"
5. "Изменения в мире"
6. physics_warnings
7. python_engines_block
8. "Действия игроков"   ← ТРИГГЕР ЗАРЫТ НА 8-Й ПОЗИЦИИ
9. "NPC не говорили ничего" ← ПУСТО в R3 (теперь заменён DMFrame)
10. "Физические действия NPC" ← ПУСТО в R3
11. "Результаты проверок" ← пустой при вербальном действии
12. continuity_block     — числа без шкалы
13. reaction_block       — иногда пустой
14. ЖЁСТКИЕ ПРАВИЛА (8 пунктов)
```

Проблемы:
- Действие игрока — триггер всего — на 8-й позиции
- 3 пустых блока (npc_str, npc_actions_str, rules_str при вербальном действии)
- Дублирование инструкций
- continuity_block с числами

**2.1 Убрать пустые блоки** — не выводить заголовок если содержимое пустое

**2.2 Переупорядочить: действие первое**

```
1. Действие игрока
2. DMFrame (NPC состояния)
3. scene_block (объекты + позиции + правила реакций)
4. player_state
5. continuity (только flags/events без чисел)
6. context_str (только если есть)
7. ЖЁСТКИЕ ПРАВИЛА (сокращённые)
```

**2.3 Убрать regime/psychological из DM_PROMPT_BLOCK** — regime это внутренний термин, LLM получает его через intent description ("пытается убежать"). Regime нужен только для диагностики в логах, не для промпта.

---

### ЭТАП 3: Качество NPC контента

**3.1 Intent байас у thief_shadow**

Из лога: "Привет Люся" → thief_shadow intent=flee, projection=defensive. Вор имеет высокий base fear → DecisionHub даёт flee на любое событие без проверки стимула.

Исправление: В decision_hub.py — если event_type=player_interacts (не угроза), intent=flee не пробивается без явной причины (бросок, proximity, угроза).

**3.2 Perception filter: 15m cap в замкнутом помещении**

`_can_see` строка 150: `if distance >= 15.0: return False`. В таверне 15м — это та же комната.

Исправление: Использовать location_graph — если NPC и игрок в одной зоне (room/area), distance cap не применяется.

---

### ЭТАП 4: Post-валидация (после стабильности Этап 1-3)

**4.1 Fallback при "Ничего не произошло"**

Если `dm_response` содержит "Ничего не произошло" — использовать fallback шаблон на основе DMFrame:
- focus NPC intent=flee → "Тень отступает к выходу"
- focus NPC intent=observe → "Люся смотрит на тебя"

**4.2 Валидация: DM не должен contradicт DMFrame**

Если DMFrame говорит "пытается убежать" а dm_response описывает "спокойно стоит" — это нарушение контракта.

---

### ПОРЯДОК РЕАЛИЗАЦИИ

| Шаг | Этап | Что | Файл |
|-----|------|-----|------|
| 1 | 1.1 | Убрать "НЕ генерируй реплики" из Promt_AI.json | Promt_AI.json |
| 2 | 1.2 | Убрать дублирующие ПРАВИЛА РЕАКЦИЙ из Promt_AI.json | Promt_AI.json |
| 3 | 1.3 | CONTINUITY без чисел | scene_continuity.py |
| 4 | 2.1 | Убрать пустые блоки из _build_prompt | dm_agent.py |
| 5 | 2.2 | Переупорядочить блоки (action first) | dm_agent.py |
| 6 | 2.3 | Убрать regime из to_dm_prompt_block | scene_outcome_builder.py |
| 7 | 3.1 | Intent flee без стимула → suppress | decision_hub.py |
| 8 | 3.2 | Perception: same-room override | perception_filter.py |
| 9 | 4.1 | Fallback при пустом ответе | dm_agent.py |
| 10 | Тест | Запуск, проверка | — |

---
****

Понял. Ты описал проблему правильно — **тики = 1 час убивают социальные сцены**. Сейчас попробую переформулировать твою задумку в модель, а ты скажешь где я ошибаюсь.

---

## Два режима времени

**Диалоговый режим** (TAB открыт, консоль в фокусе):
- Время **остановлено**
- Мир замер — NPC не двигаются, не уходит, не наступает ночь
- Игрок пишет → получает ответ
- Телеграф **выключен** — мир ждёт игрока

**Реактивный режим** (TAB не нажат, игрок ходит по миру):
- Время идёт **очень медленно** — секунды, не часы
- Мир может проявить инициативу: NPC подошёл, что-то сказал, произошло событие
- Но это **не polling каждые 5 сек** — это event-driven
- NPC сам решает подойти (decision_hub) → только тогда LLM озвучивает

---

## Телеграф — не таймер, а реакция

Сейчас: "жди 30 сек → спроси LLM что происходит" — это неправильно.

Правильно: 
1. Игрок открыл консоль → мир замер
2. Игрок **не успел** ничего написать за 30 сек → один телеграф: "NPC проявил инициативу"
3. После телеграфа — таймер сбрасывается, ждём ещё 30 сек
4. Если игрок написал → телеграф отменяется, мир отвечает на него

Телеграф = **"пока ты молчишь, кто-то другой проявил инициативу"**, а не "опиши что все делают".

---

## Тики — что они должны быть

Сейчас тик = 1 час. Это для long-rest и путешествий. Для таверны — бессмысленно.

Предложение: **тиков нет как таковых**. Время продвигается только когда:
- Игрок совершил действие (подошёл, ударил, сказал)
- Телеграф сработал (NPC проявил инициативу)
- Явный переход времени ("я жду час" → тогда можно продвинуть)

Нет действия → мир стоит. Это кинематографично — сцена ждёт твоего ввода.

---

## Порядок действий

Сейчас decision_hub сломан (WillState) → 0 decisions → телеграф — единственный способ получить реакцию мира. Поэтому он спамит.

**Шаг 1** — починить WillState (уже добавлен импорт, нужно проверить что этого достаточно)

**Шаг 2** — убрать спам: телеграф только после 30 сек тишины, не мгновенный перезапуск

**Шаг 3** — отключить idle_tick-ы пока консоль открыта (мир замер)

**Шаг 4** — позже: перепроектировать тики (убрать 1 час, сделать event-driven)

---

Где я ошибся в понимании?