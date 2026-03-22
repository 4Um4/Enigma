# ENIGMA — Локальный AI Dungeon Master
### Полная проектная документация v4.0 | Март 2026

> **Изменения vs v3.0:**
> Переход на Gemma-3-12B как единственную модель (вместо пяти).
> Обновлён VRAM-бюджет. Обновлены статусы реализации.
> Добавлена философия generic-архитектуры.
> Устаревшие модели перенесены в раздел "Резерв".

---

## 🎯 Философия и цель

Enigma — это локальная компьютерная RPG в жанре D&D 5e, где роль Мастера
Подземелий, всех NPC и самого живого мира выполняет языковая модель,
запущенная **полностью на вашем компьютере**, без облака и интернета.

**Не просто чат-бот в антураже D&D.** Это симулятор живого мира где:
- Каждый NPC имеет психологию, драйвы, историю и помнит что вы делали
- Мир живёт и меняется независимо от игрока — каждые 15 минут
- Физика и логика мира неумолимы — свиньи не летают, вода не горит
- За одним компьютером могут играть от 1 до 8 человек по очереди
- **Любое** действие игрока обрабатывается — нет запрещённых путей

**Главный принцип:**
```
Python считает (мгновенно, 0ms)
    ↓
LLM интерпретирует (8–30 сек)
    ↓
Игрок видит живой текст (стриминг токенов)
```

NPC умны не потому что LLM умная, а потому что **Python уже всё посчитал** —
стресс, страх, угрозу, статус — и LLM получает готовые числа для драматизации.

**Архитектурный принцип (добавлен v4.0):**
```
Персонажей может быть великое множество.
Разнообразие действий — бесконечно.
Случиться может что угодно.

→ Никакого хардкода имён и ситуаций в коде.
→ Всё поведение — из данных (JSON) + общих правил (Python).
→ Новый NPC = новый JSON. Новое действие = новый паттерн.
```

---

## 🖥️ Характеристики компьютера и ограничения

| Компонент | Значение | Ограничение |
|---|---|---|
| GPU | RTX 3070 Ti | **8 GB VRAM** — 1 модель в памяти одновременно |
| CPU | Intel i7-9700F | 6 физ. ядер, AVX512 |
| RAM | 16 GB | Достаточно, без роскоши |
| ОС | Windows 11 Россия | Кириллица в путях — проверять кодировки |
| Python | 3.11.9 в `.venv` | Фиксировано, не обновлять |
| llama.cpp | build 8224 | CUDA + AVX512 + flash attention |

**VRAM-бюджет (актуальный, Март 2026):**
```
ОС + CUDA runtime:              ~500 MB
Gemma-3-12B-IT-Q4_K_M:        ~7 500 MB  ← единственная активная модель
KV-cache ctx=2048:               ~256 MB
─────────────────────────────────────────
Итого занято:                 ~8 256 MB  (~103% VRAM)

⚠ Критично: модель едва помещается в 8 GB.
   ngl=33 (часть слоёв на CPU) — баланс скорость/память.
   max_loaded=1 — не архитектурное решение, а жёсткое требование железа.
```

**Скорость генерации (реальные данные):**
```
Prefill:    ~3 ms/tok  → ~333 tok/sec   ← обработка промпта
Generation: ~16 ms/tok →  ~62 tok/sec   ← генерация ответа
Итого 512 токенов:       ~8–10 сек      (Gemma-3-12B-IT-Q4_K_M, ctx=2048)
```

**Активная модель:**
| Файл | Размер | Роль |
|---|---|---|
| `Gemma-3-12B-IT-Q4_K_M.gguf` | ~7.5 GB | DM + все NPC + Rules + World |

**Резерв (не активны — не помещаются вместе с Gemma в VRAM):**
| Файл | Размер | Статус |
|---|---|---|
| `Qwen2.5-7B-instruct-Q4_K_M.gguf` | ~4.1 GB | Резерв — может использоваться если перейти с Gemma |
| `mistral-pygmalion-7b.Q5_K_M.gguf` | ~4.8 GB | Резерв |
| `mistral-pygmalion-7b.Q4_K_M.gguf` | ~4.0 GB | Резерв |
| `saiga_mistral_7b_model-q4_K.gguf` | ~4.0 GB | Резерв |
| `YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf` | ~4.5 GB | Резерв |
| `Qwen3.5-9B.gguf` | ~5.3 GB | Резерв (требует 12 GB VRAM) |

---

## 📁 Структура проекта

```
Enigma/
├── start_enigma.bat                  ← ЕДИНАЯ ТОЧКА ВХОДА ✅
├── launcher.py                       ← (будет) нативное окно без браузера
├── .venv/                            ← Python 3.11.9 окружение
├── requirements.txt
│
├── Models LLM/
│   ├── llama/                        ← llama.cpp бинари + CUDA DLL
│   │   ├── llama-server.exe          ← HTTP сервер LLM (порт 8080) ✅
│   │   ├── ggml-cuda.dll
│   │   └── ggml-cpu-zen4.dll
│   ├── Gemma-3-12B-IT-Q4_K_M.gguf   ← АКТИВНАЯ МОДЕЛЬ ✅
│   └── [резервные модели]/
│
├── backend/                          ← FastAPI сервер (порт 8000)
│   ├── app/
│   │   ├── main.py                   ← FastAPI точка входа ✅
│   │   │
│   │   ├── agents/
│   │   │   ├── dm_agent.py           ← DM (Gemma-3-12B) ✅
│   │   │   ├── npc_agent.py          ← NPC Major (Gemma-3-12B) ✅
│   │   │   ├── rules_agent.py        ← Правила D&D (Gemma-3-12B) ✅
│   │   │   ├── world_sim_agent.py    ← Мир (Gemma-3-12B) ✅
│   │   │   └── memory_manager_agent.py ← Суммаризация (Gemma-3-12B) ✅
│   │   │
│   │   ├── api/
│   │   │   ├── routes.py             ✅
│   │   │   ├── routes_stream.py      ← SSE стриминг ✅
│   │   │   └── routes_debug.py       ← /debug/vram, /health/agents ✅
│   │   │
│   │   ├── core/
│   │   │   ├── config.py             ← gemma_12b для всех агентов ✅
│   │   │   ├── runtime_config.py     ✅
│   │   │   ├── error_logger.py       ✅
│   │   │   └── settings_*.py         ✅
│   │   │
│   │   └── services/
│   │       ├── orchestrator.py           ✅
│   │       ├── action_classifier.py      ← 14 ActionType ✅
│   │       ├── context_builder.py        ✅
│   │       ├── scene_state_manager.py    ← SceneStateManager, 7 методов ✅
│   │       ├── scene_change.py           ← SceneChange, 10 типов ✅
│   │       ├── world_scheduler.py        ← тикер 15 мин ✅
│   │       │
│   │       ├── npc/
│   │       │   ├── npc_cognition.py  ← драйвы, физ. состояния ✅
│   │       │   ├── psyche_engine.py  ← стресс, слом воли ✅
│   │       │   ├── threat_assessor.py ✅
│   │       │   ├── perception_engine.py ✅
│   │       │   ├── reaction_priority.py  ⏳ Фаза S.4.2
│   │       │   ├── life_engine.py        ⏳ Фаза 3B
│   │       │   ├── karma_engine.py       ⏳ Фаза 3B
│   │       │   ├── npc_generator.py      ⏳ Фаза 3B.0
│   │       │   └── social_mobility.py    ⏳ Фаза 3B
│   │       │
│   │       ├── game/
│   │       │   ├── combat_math.py        ✅
│   │       │   ├── physics_validator.py  ✅
│   │       │   ├── sandbox_handler.py    ← 23 обработчика ✅ (SceneChange ⏳ S.4.1)
│   │       │   ├── turn_manager.py       ⏳ Фаза 5
│   │       │   ├── character_creation.py ⏳ Фаза 6
│   │       │   └── death_handler.py      ⏳
│   │       │
│   │       ├── memory/
│   │       │   ├── memory.py             ← LayeredMemory + JsonMemoryStore ✅
│   │       │   ├── memory_manager.py     ⏳ Фаза 7
│   │       │   └── knowledge_base.py     ⏳ Фаза 10
│   │       │
│   │       └── llm/
│   │           ├── provider.py           ✅
│   │           ├── provider_manager.py   ← ModelPool max_loaded=1 ✅
│   │           ├── llama_cpp_provider.py ✅
│   │           ├── router.py             ← gemma_12b первая для всех ✅
│   │           └── factory.py            ✅
│   │
│   ├── data/
│   │   ├── campaigns/demo-campaign/
│   │   │   ├── characters.json       ✅
│   │   │   └── campaign_state.json   ✅
│   │   ├── npcs/
│   │   │   ├── major_npcs.json       ← 5 NPC с полной психологией ✅
│   │   │   ├── mass_npc_templates.json ← 10 шаблонов ✅
│   │   │   └── generated/            ⏳ Фаза 3B.0
│   │   ├── location_templates.json   ← 5 локаций с time_variants ✅
│   │   ├── Promt_AI.json             ← системный промпт на русском ✅
│   │   ├── pdf_drop/                 ← D&D книги на русском (пусто)
│   │   ├── knowledge_db/             ⏳ Фаза 10
│   │   ├── sessions/                 ✅
│   │   └── logs/                     ← JSONL структурированные логи ✅
│   │
│   └── tests/                        ← все базовые тесты ✅
│
├── frontend/ui/index.html            ← SSE streaming, fallback POST ✅
└── ui/                               ← PyGame UI ⏳ Фаза UI
    ├── launcher.py
    ├── game_window.py
    ├── api_client.py
    └── panels/
```

---

## ⚙️ Полный цикл одного хода

```
Игрок пишет действие
        ↓
┌──────────────────────────────────────────────────────────────┐
│  ACTION CLASSIFIER (Python, <1ms)   ✅                        │
│  14 типов действий, учёт склонений                           │
│  "атакую гоблина"      → COMBAT                              │
│  "говорю с трактирщиком" → SOCIAL + target_npc="трактирщик" │
│  "краду свечи"         → SANDBOX + target_object="свечи"    │
└──────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────────┐
│  PHYSICS VALIDATOR (Python, <1ms)   ✅                        │
│  "лечу без заклинания" → ОТКЛОНЕНО                          │
│  bypass: заклинания и способности персонажа                  │
└──────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────────┐
│  PYTHON ENGINES (последовательно, <50ms суммарно)            │
│                                                             │
│  CombatMath       → броски, урон, AC              ✅         │
│  SandboxHandler   → 23 обработчика + TOP-100      ✅         │
│    └─ SceneChange → обновление SceneState         ⏳ S.4.1  │
│  NPCCognition     → драйвы, стресс                ✅         │
│  ThreatAssessor   → уровень угрозы                ✅         │
│  PerceptionEngine → что NPC видит в игроке        ✅         │
│  PsycheEngine     → состояние NPC                 ✅         │
│  ReactionPriority → кто реагирует сам             ⏳ S.4.2  │
│  KarmaEngine      → обновление репутации          ⏳ 3B     │
└──────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────────┐
│  SCENESTATE CONTEXT BUILDER (Python, <5ms)                   │
│  Позиции, расстояния, player_target_npc/object               │
│  → первый блок промпта DM и каждого NPC           ⏳ S.0    │
└──────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────────┐
│  LLM PIPELINE (ModelPool max_loaded=1)                       │
│  Все агенты → Gemma-3-12B-IT-Q4_K_M                         │
│  Только одна модель в VRAM одновременно                      │
└──────────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────────┐
│  STREAMING SSE → UI   ✅                                     │
│  stream_tokens() → routes_stream.py → getReader() в JS      │
│  Первый токен: ~500ms после запроса                         │
│  Fallback: POST если ReadableStream недоступен              │
└──────────────────────────────────────────────────────────────┘
```

---

## 🎭 NPC система — полная архитектура

### Три уровня NPC

| Tier | Модель | JSON | Когда |
|---|---|---|---|
| `major` | Gemma-3-12B (полный контекст) | Полный JSON, полная психология | Ключевые персонажи |
| `minor` | Gemma-3-12B (сокращённый контекст) | Сокращённый JSON | Жители, стражники, торговцы |
| `mass` | Gemma-3-12B (шаблонный контекст) | Архетип + настроение | Толпа, фоновые персонажи |

Разница между уровнями — в объёме JSON-контекста, переданного в промпт.
Модель одна для всех.

### Структура NPC JSON (без изменений, v4.0)

```json
{
  "id": "farmer_grom_01",
  "name": "Гром",
  "tier": "minor",
  "role": "farmer",

  "status_profile": {
    "freedom": 50, "wealth": 10, "power": 5,
    "title": "Крестьянин", "faction_rank": {}
  },

  "visible_markers": ["tunic", "hoe", "calloused_hands"],
  "hidden_truth": ["former_soldier"],

  "drives": {
    "control": 0.60, "significance": 0.10,
    "fear": 0.25, "desire": 0.05
  },

  "psyche": {
    "willpower": 45, "stress": 30, "breakpoint": 85,
    "loyalty_true": 50, "loyalty_false": 50,
    "state": "free", "trauma_flags": []
  },

  "social_stats": {
    "trust": 0.50, "affection": 0.40,
    "fear_of_player": 0.10, "debt": 0
  },

  "relationships": {
    "player_aria": 50, "wife_elena": 80,
    "merchant_grok": -20
  },

  "routine": {
    "current": "plowing", "mood": "neutral",
    "interrupted": false,
    "schedule": {
      "06:00-18:00": "working",
      "18:00-22:00": "family_time",
      "22:00-06:00": "sleeping"
    }
  },

  "recent_events": [],
  "flags": {
    "has_gold": false, "knows_secret": false,
    "is_enslaved": false, "planning_revenge": false
  },

  "memory_trace": [],
  "location": "village_fields"
}
```

### 8 Python движков NPC

```
1. THREAT ASSESSOR    ✅ — угроза от действия игрока
2. PERCEPTION ENGINE  ✅ — что NPC видит (visible_markers)
3. PSYCHE ENGINE      ✅ — стресс, слом воли, состояния
4. NPC COGNITION      ✅ — доминирующий драйв, behavior_hint
5. REACTION PRIORITY  ⏳ S.4.2 — кто реагирует сам и с каким приоритетом
6. LLM NPC AGENT      ✅ — получает всё посчитанное, озвучивает
7. KARMA ENGINE       ⏳ 3B — репутация, цепные реакции
8. LIFE ENGINE        ⏳ 3B — рутина, расписание, фоновые события
```

### Состояния NPC (psyche.state)

| Состояние | Поведение |
|---|---|
| `free` | Следует драйвам, может отказать |
| `coerced` | Подчиняется, ненавидит, ищет выход |
| `broken` | Подчиняется из страха, loyalty_true падает |
| `loyal` | Помогает добровольно, может жертвовать собой |
| `deceptive` | loyalty_fake ≠ loyalty_true, планирует предательство |

### Видимые маркеры (влияют на perceived_status)

| Маркер | Влияние на статус | Влияние на угрозу |
|---|---|---|
| `slave_collar` | −50 | — |
| `royal_crown` | +50 | — |
| `heavy_armor` | — | +30 |
| `rags` | −20 | — |
| `weapon_melee` | — | +20 |
| `chains` | −40 | — |
| `guild_badge` | +10..+30 зависит от фракции | — |

---

## 🌍 SceneState — состояние сцены

SceneStateManager управляет текущим состоянием игрового мира.
Обновляется через SceneChange (10 типов), никогда напрямую.

```
SceneChange типы:
  OBJECT_REMOVE    — объект исчезает из сцены
  OBJECT_STATE     — состояние объекта меняется (open/broken/on_fire)
  OBJECT_ADD       — объект появляется
  NPC_STATE        — состояние NPC (poisoned/captured/sleeping)
  NPC_POSITION     — NPC меняет позицию/активность
  INVENTORY_ADD    — предмет добавляется игроку
  INVENTORY_REMOVE — предмет убирается у игрока
  EFFECT_ADD       — эффект на локацию (fire/darkness/smoke)
  EFFECT_REMOVE    — эффект снимается
  LIGHTING_CHANGE  — изменение освещения
```

SceneState включает (после S.0):
- Позиция и расстояния игрока
- Список активных NPC с позициями
- player_target_npc, player_target_object
- Объекты и их текущие состояния
- Активные эффекты

---

## 🎲 Открытый мир — любое действие обрабатывается

**Философия Sandbox:** Нет запрещённых путей — есть последствия.

```python
class SandboxHandler:
    # 23 обработчика + TOP-100 нестандартных паттернов
    # Каждый обработчик при success=True порождает SceneChange
    # target берётся из SceneState.player_target_npc/object
    # Имена не хардкодятся
```

**Примеры:**

```
"Краду свечи" → target_object="свечи"
  Python: STEAL success → SceneChange(OBJECT_REMOVE, "свечи")
                        + SceneChange(INVENTORY_ADD, player, "свечи")
  Следующий ход DM: SceneState знает что темно → описывает темноту

"Ломаю стол" → target_object="стол"
  Python: BREAK success → SceneChange(OBJECT_STATE, "стол", "broken")

"Отравляю Трактирщика" → target_npc="Трактирщик" (любое имя)
  Python: POISON success → SceneChange(NPC_STATE, target_npc, "poisoned")
```

---

## 📡 Streaming токенов — UI опыт ✅ РЕАЛИЗОВАН

**SSE протокол:**
```python
{"type": "status",  "text": "Мастер думает..."}
{"type": "token",   "text": "Вы ", "count": 1}
{"type": "npc",     "data": [{"name": "...", "speech": "..."}]}
{"type": "combat",  "data": {"hit": true, "damage": 8}}
{"type": "done",    "timing": {"total_ms": 8240, "tokens": 512, "tok_per_sec": 62}}
```

Метрики в UI:
```
"⚔ Мастер думает...  ████████░░░  12.4с | 247 токенов | 62 tok/s | Gemma-12B"
```

---

## 🧠 Система памяти — 4 уровня

```
УРОВЕНЬ 1: Оперативная (~500 токенов)
  Последние 5 обменов → прямо в промпт

УРОВЕНЬ 2: Сессия (~1000 токенов)
  session_memory_{campaign}.jsonl — последние 20 событий

УРОВЕНЬ 3: Кампания (~300 токенов)
  Gemma-12B суммаризирует в конце сессии (та же модель, economy mode)

УРОВЕНЬ 4: Мир (~300 токенов)
  world_canon.jsonl + ChromaDB (PDF книги) ⏳ Фаза 10
```

LayeredMemory + JsonMemoryStore реализованы ✅
MemoryManager с бюджетом токенов — ⏳ Фаза 7

---

## 🎲 Создание персонажа (D&D 5e)

**Три способа генерации характеристик:**
- 4d6 drop lowest (популярный)
- Стандартный массив [15, 14, 13, 12, 10, 8]
- Point buy (27 очков)

**Математика (реализована в character_service.py):**
```python
modifier   = (score - 10) // 2
prof_bonus = 2 + (level - 1) // 4
hp_lvl1    = HIT_DIE[class_name] + constitution_modifier
ac_unarmed = 10 + dexterity_modifier
```

**Диалог создания через DM** — ⏳ Фаза 6

---

## 👥 Мультиплеер 1–8 игроков

**Архитектура TurnManager** — ⏳ Фаза 5

```
Обычный режим:
  Игрок1 → (DM) → Игрок2 → (DM) → Игрок3 → новый раунд

Боевой режим:
  Все бросают инициативу (Python: d20 + Ловкость)
  Порядок: по убыванию инициативы
  Враги ходят в свою очередь (ReactionPriority автоматически)

DM при round_resolution получает ВСЕ действия раунда →
описывает их все вместе — живая нарративная сцена
```

---

## 📊 Аналитика — ⏳ Фаза 8

Итоги сессии для каждого игрока:
```
╔══════════════════════════════════════╗
║  ИТОГИ СЕССИИ — Арагорн             ║
╠══════════════════════════════════════╣
║  ⚔  Убито противников:    7        ║
║  💰 Золото: +120 / -45             ║
║  ❤  Урон получено:        34 HP    ║
║  👥 Репутация (средняя):  +42      ║
║  🎭 Нестандартных действий: 3      ║
╚══════════════════════════════════════╝
```

---

## 🔧 Genius Features

### 1. LLM Self-Debug — Error Interpreter ✅
5 типов ошибок: TIMEOUT | OOM | JSON_PARSE | CONTEXT_OVERFLOW | MODEL_FAIL
Логируется в `data/logs/enigma_YYYYMMDD.jsonl`.

### 2. VRAM-Aware Priority Queue ✅
```python
AGENT_PRIORITY = {"dm": 1, "rules": 2, "npc_major": 3,
                  "npc_mass": 4, "world": 5, "memory": 6}
# ModelPool.is_safe_to_load() — проверка перед каждой загрузкой
```

### 3. Context Builder ✅
Динамически собирает контекст: SceneState → NPC данные →
результаты python_engines → память. Бюджет токенов строго соблюдается.

### 4. Offline-First RAG Cache ⏳ Фаза 10
FAISS-индекс PDF книг. Заготовки: `pdf_drop_importer.py`, `knowledge_ingest.py`.

### 5. SceneState Spatial Context ⏳ Фаза S.0
Позиции, расстояния, player_target → первым блоком в промпт.
Устраняет галлюцинации модели о положении персонажей.

### 6. Reaction Priority Queue ⏳ Фаза S.4.2
NPC реагируют сами на события, затрагивающие их интересы.
Python считает приоритет — LLM озвучивает.

---

## 💻 Нативное окно (launcher.py) — ⏳ Фаза 11

PyInstaller + pywebview → `.exe` без браузера.
Заготовки в `build/`. Текущий fallback: `index.html` в браузере.

---

## 📅 Текущий план (Март 2026)

| # | Этап | Срок | Статус |
|---|---|---|---|
| S.0 | SceneState в промпт | 2 дня | **⬅️ СЛЕДУЮЩИЙ** |
| S.4.1 | Sandbox → SceneChange | 2–3 дня | ❌ |
| S.4.2 | ReactionPriority Queue | 2–3 дня | ❌ |
| 3B | Живой мир (NPC + LifeEngine) | 2 нед | ❌ |
| UI | PyGame интерфейс | 2–3 нед | ❌ |
| 3C | Социальная сеть NPC | 2 нед | ❌ |
| 5 | Мультиплеер | 2 нед | ❌ |
| 6 | Создание персонажа | 1 нед | ❌ |
| 7 | MemoryManager | 2 нед | ⚠️ частично |
| 8–12 | Аналитика, RAG, .exe | — | ❌/⚠️ |

**До v1.0-playable (S.0–S.4.2 + 3B + UI):** ~6–7 недель
**До полной v1.0:** ~3.5 месяца
**До релиза:** ~7 месяцев

---

## 📈 Текущее состояние (Март 2026)

| Компонент | Готовность | Примечание |
|---|---|---|
| Инфраструктура запуска | **100%** | start_enigma.bat, pre-flight |
| LLM интеграция | **95%** | Gemma-3-12B, ModelPool, streaming |
| Игровой цикл | **80%** | Orchestrator, ActionClassifier, PhysicsValidator |
| Streaming SSE | **100%** | SSE + getReader() + fallback + метрики |
| Action Classifier | **100%** | 14 типов, приоритеты |
| Physics Validator | **100%** | Правила мира, bypass |
| Боевая математика | **100%** | D&D 5e полная |
| Sandbox Handler | **100%** | 23 обработчика (SceneChange — S.4.1) |
| SceneStateManager | **90%** | Структура готова, контекст в промпт — S.0 |
| NPC движки Python | **60%** | Cognition/Psyche/Threat/Perception ✅; Reaction/Life/Karma ⏳ |
| Система памяти | **65%** | LayeredMemory ✅, MemoryManager ⏳ |
| Error Interpreter | **90%** | 5 типов, JSONL, fix-рекомендации |
| VRAM Monitor | **95%** | Без ложных утечек |
| Context Builder | **85%** | SceneState-блок — S.0 |
| Мультиплеер | **0%** | Фаза 5 |
| Создание персонажа | **10%** | Математика ✅, диалог с DM ⏳ |
| RAG по PDF | **10%** | Заготовки есть |
| **Общий прогресс** | **~65%** | |

---

## 🏛️ Ключевые архитектурные принципы

1. **Python считает — LLM рассказывает.**
   Урон, психология, физика, стресс, репутация — математика Python.
   LLM получает числа → превращает в историю.

2. **Одна модель в VRAM.**
   Gemma-3-12B — единственная активная модель. max_loaded=1 — жёсткое
   требование при 8 GB VRAM.

3. **Любое действие обрабатывается.**
   SandboxHandler (23 обработчика + TOP-100). Нет запрещённых путей.

4. **Состояние — единственный источник правды.**
   `characters.json`, `major_npcs.json`, `campaign_state.json` — только
   Python сервисы меняют их через SceneChange. LLM — никогда напрямую.

5. **Мир живёт независимо от игрока.**
   WorldScheduler тикает каждые 15 минут. LifeEngine (Фаза 3B) двигает
   NPC по расписанию без участия игрока.

6. **Система generic.**
   Никакого хардкода имён персонажей или конкретных ситуаций в коде.
   Новый NPC = новый JSON. Новая роль = новая запись в duty_map.
   Персонажей может быть великое множество — система не должна этого знать.

---

**Документ:** ENIGMA README v4.0
**Обновлено:** Март 2026
