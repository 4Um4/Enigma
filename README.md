# ENIGMA — Локальный AI Dungeon Master
### Полная проектная документация v3.0

---

## 🎯 Философия и цель

Enigma — это локальная компьютерная RPG в жанре D&D 5e, где роль Мастера Подземелий, всех NPC и самого живого мира выполняют языковые модели (LLM), запущенные **полностью на вашем компьютере**, без облака и интернета.

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

NPC умны не потому что LLM умная, а потому что **Python уже всё посчитал** — стресс, страх, угрозу, статус — и LLM получает готовые числа для драматизации.

---

## 🖥️ Характеристики компьютера и ограничения

| Компонент | Значение | Ограничение |
|---|---|---|
| GPU | RTX 3070 Ti | **8 GB VRAM** — 1 модель в памяти одновременно |
| CPU | Intel i7-9700F | 6 физ. ядер, AVX512, Zen4 |
| RAM | 16 GB | Достаточно, но без роскоши |
| ОС | Windows 11 Россия | Кириллица в путях — проверять кодировки |
| Python | 3.11.9 в `.venv` | Фиксировано, не обновлять |
| llama.cpp | build 8224 | CUDA + AVX512 + flash attention |

**VRAM-бюджет (аксиома архитектуры):**
```
ОС + CUDA runtime:          ~500 MB
Qwen2.5-7B Q4_K_M:        ~4500 MB  ← основная модель (DM/World)
KV-cache ctx=2048:           ~256 MB
Буфер безопасности:          ~500 MB
─────────────────────────────────────
Итого занято:              ~5756 MB  (70% VRAM)
Остаток:                   ~2436 MB  (запас под NPC-модели)
```

> **Примечание:** Qwen3.5-9B (~5500 MB) исключён из активного маппинга агентов — при ctx=2048 не остаётся буфера. Оставлен в конфиге для будущего (12+ GB GPU).

**Скорость генерации (реальные данные из логов):**
```
Prefill:    2.9 ms/tok  → 344 tok/sec   ← обработка промпта
Generation: 15.3 ms/tok →  65 tok/sec   ← генерация ответа
Итого 512 токенов:       ~8.2 сек       (Qwen2.5-7B Q4_K_M, ctx=2048)
```

**Модели на диске:**
| Файл | Размер | Роль |
|---|---|---|
| `Qwen2.5-7B-instruct-Q4_K_M.gguf` | ~4.1 GB | DM — главный нарратор + World Sim |
| `Qwen3.5-9B.gguf` | ~5.3 GB | Резерв (требует 12 GB GPU, сейчас не активен) |
| `mistral-pygmalion-7b.Q5_K_M.gguf` | ~4.8 GB | NPC Major — важные персонажи |
| `mistral-pygmalion-7b.Q4_K_M.gguf` | ~4.0 GB | NPC Mass — толпа, быстрые реплики |
| `saiga_mistral_7b_model-q4_K.gguf` | ~4.0 GB | Rules + Memory — правила D&D 5e и суммаризация |
| `YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf` | ~4.5 GB | Memory — русская суммаризация (резерв) |

---

## 📁 Структура проекта (полная)

```
Enigma/
├── start_enigma.bat                  ← ЕДИНАЯ ТОЧКА ВХОДА
├── launcher.py                       ← (будет) .exe через PyInstaller+WebView2
├── .venv/                            ← Python 3.11.9 окружение
├── requirements.txt                  ← корневые зависимости
│
├── Models LLM/
│   ├── llama/                        ← llama.cpp бинари + CUDA DLL
│   │   ├── llama-server.exe          ← HTTP сервер LLM (порт 8080)
│   │   ├── llama-cli.exe
│   │   ├── ggml-cuda.dll             ← CUDA ускорение
│   │   ├── ggml-cpu-zen4.dll         ← CPU оптимизация для i7-9700F
│   │   └── [прочие DLL/EXE]
│   ├── qwen2.5-7b-instruct-q4_k_m.gguf   ← DM + World агент (активен)
│   ├── Qwen3.5-9B.gguf                   ← резерв (требует 12 GB VRAM, не активен)
│   ├── mistral-pygmalion-7b.Q5_K_M.gguf  ← NPC Major агент (активен)
│   ├── mistral-pygmalion-7b.Q4_K_M.gguf  ← NPC Mass агент (активен)
│   ├── saiga_mistral_7b_model-q4_K.gguf  ← Rules + Memory агент (активен)
│   └── YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf ← Memory резерв
│
├── backend/                          ← FastAPI сервер (порт 8000)
│   ├── app/
│   │   ├── main.py                   ← FastAPI точка входа, startup
│   │   │
│   │   ├── agents/                   ← LLM агенты
│   │   │   ├── dm_agent.py           ← Мастер Подземелий (Qwen2.5-7B) ✅
│   │   │   ├── npc_agent.py          ← NPC Major (Mistral Pygmalion Q5_K_M) ✅
│   │   │   ├── rules_agent.py        ← Правила D&D (Saiga) ✅
│   │   │   ├── world_sim_agent.py    ← Мир (Qwen2.5-7B) ✅
│   │   │   └── memory_manager_agent.py ← Суммаризация (Saiga/YandexGPT) ✅
│   │   │   ─ npc_mass_agent.py       ← NPC Mass (Pygmalion Q4_K_M) [⏳ не создан]
│   │   │
│   │   ├── api/
│   │   │   ├── routes.py             ← основные эндпоинты ✅
│   │   │   ├── routes_stream.py      ← SSE стриминг токенов ✅
│   │   │   └── routes_debug.py       ← /debug/vram, /health/agents, /logs-tail ✅
│   │   │
│   │   ├── core/
│   │   │   ├── config.py             ← настройки + VRAM бюджеты ✅
│   │   │   ├── runtime_config.py     ← динамические порты ✅
│   │   │   ├── error_logger.py       ← единый JSONL логгер ошибок ✅
│   │   │   ├── settings_dm.py        ← параметры DM агента ✅
│   │   │   ├── settings_npc.py       ← параметры NPC агентов ✅
│   │   │   ├── settings_rules.py     ← параметры Rules агента ✅
│   │   │   └── settings_world.py     ← параметры World агента ✅
│   │   │
│   │   ├── models/
│   │   │   └── schemas.py            ← Pydantic схемы
│   │   │
│   │   └── services/
│   │       ├── orchestrator.py           ← главный дирижёр агентов ✅
│   │       ├── action_classifier.py      ← 14 ActionType, приоритеты (Python, 0ms) ✅
│   │       ├── context_builder.py        ← динамический сборщик контекста LLM ✅
│   │       ├── campaign_state_service.py ← состояние кампании ✅
│   │       ├── character_service.py      ← сервис персонажей ✅
│   │       ├── combat_service.py         ← боевой сервис ✅
│   │       ├── adventure_loader.py       ← загрузка приключений ✅
│   │       ├── player_session_service.py ← сессии игроков ✅
│   │       ├── prompt_loader.py          ← загрузка системных промптов ✅
│   │       ├── readiness.py              ← pre-flight проверки ✅
│   │       ├── logging_tools.py          ← JSONL логирование ✅
│   │       ├── pdf_drop_importer.py      ← импорт PDF книг ✅
│   │       ├── knowledge_ingest.py       ← индексация знаний ✅
│   │       ├── world_scheduler.py        ← периодические тики мира ✅
│   │       │
│   │       ├── npc/                  ← NPC движки (Python, без LLM) [⏳ НЕ СОЗДАН]
│   │       │   ├── npc_cognition.py  ← драйвы, нормализация
│   │       │   ├── psyche_engine.py  ← стресс, слом воли, состояния
│   │       │   ├── threat_assessor.py ← оценка угрозы
│   │       │   ├── perception_engine.py ← видимые маркеры, статус
│   │       │   ├── life_engine.py    ← рутина, расписание, случайные события
│   │       │   ├── karma_engine.py   ← цепные реакции, репутация
│   │       │   └── social_mobility.py ← динамические роли
│   │       │
│   │       ├── game/
│   │       │   ├── combat_math.py        ← D&D 5e математика боя ✅
│   │       │   ├── physics_validator.py  ← нельзя летать без заклинания ✅
│   │       │   ├── sandbox_handler.py    ← нестандартные действия (23 обработчика) ✅
│   │       │   ├── turn_manager.py       ← очередь ходов 1–8 игроков [⏳ не создан]
│   │       │   ├── character_creation.py ← пошаговая генерация персонажа [⏳ не создан]
│   │       │   └── death_handler.py      ← смерть не конец игры [⏳ не создан]
│   │       │
│   │       ├── memory/
│   │       │   ├── memory.py         ← LayeredMemory + JsonMemoryStore (JSONL) ✅
│   │       │   ├── memory_manager.py ← бюджет токенов, контекст [⏳ не создан]
│   │       │   └── knowledge_base.py ← ChromaDB / FAISS для PDF [⏳ не создан]
│   │       │
│   │       ├── analytics/
│   │       │   └── player_stats.py   ← статистика действий игроков [⏳ не создан]
│   │       │
│   │       ├── llm/
│   │       │   ├── provider.py           ← базовый класс провайдера ✅
│   │       │   ├── provider_manager.py   ← ModelPool (max_loaded=1) ✅
│   │       │   ├── llama_cpp_provider.py ← HTTP клиент + streaming ✅
│   │       │   ├── router.py             ← capability routing ✅
│   │       │   └── factory.py            ← фабрика провайдеров ✅
│   │       │
│   │       ├── model_router.py       ← агент→модель маппинг ✅
│   │       ├── vram_monitor.py       ← nvidia-smi мониторинг (baseline fix) ✅
│   │       └── error_interpreter.py  ← перехват + self-debug (5 типов) ✅
│   │
│   ├── data/
│   │   ├── campaigns/
│   │   │   ├── demo-campaign/
│   │   │   │   ├── characters.json   ← персонажи игроков ✅
│   │   │   │   └── campaign_state.json ← состояние мира, локация ✅ (⚠ current_location="unknown")
│   │   │   └── test-campaign/        ← тестовая кампания ✅
│   │   ├── npcs/                     ← [⏳ НЕ СОЗДАН] данные NPC
│   │   │   ├── major_npcs.json       ← важные NPC с полной психологией
│   │   │   └── mass_npc_templates.json ← шаблоны для толпы
│   │   ├── pdf_drop/                 ← D&D 5e книги на русском ✅ (пусто)
│   │   ├── knowledge_db/             ← ChromaDB векторная база [⏳ не генерируется]
│   │   ├── sessions/                 ← сохранённые сессии ✅
│   │   └── logs/                     ← JSONL структурированные логи ✅
│   │
│   └── tests/
│       ├── test_startup_checks.py    ✅
│       ├── test_services.py          ✅
│       ├── test_error_interpreter.py ✅
│       ├── test_full_error_logging.py ✅
│       ├── test_llm.py               ✅ (требует запущенного сервера)
│       ├── test_main.py              ✅
│       ├── test_package.py           ✅
│       ├── test_provider_manager.py  ✅
│       └── test_run_terminal_dm.py   ✅
│
└── frontend/
    └── ui/
        └── index.html                ← всё в одном файле ✅ (SSE streaming, fallback POST, метрики)
```

---

## ⚙️ Полный цикл одного хода

```
Игрок(и) пишут действие(я)
           ↓
┌──────────────────────────────────────────────────────────────┐
│  ACTION CLASSIFIER (Python, <1ms)   ✅ РЕАЛИЗОВАН            │
│  "расстёгивает ширинку" → тип: SANDBOX_PHYSICAL             │
│  "атакую гоблина"       → тип: COMBAT                       │
│  "говорю с трактирщиком" → тип: SOCIAL + npc="трактирщик"   │
│  14 типов действий, словари с учётом склонений               │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  PHYSICS VALIDATOR (Python, <1ms)   ✅ РЕАЛИЗОВАН            │
│  Проверяем: нарушается ли логика мира?                      │
│  "лечу без заклинания" → ОТКЛОНЕНО + объяснение             │
│  "расстёгивает ширинку" → ОК (физически возможно)           │
│  bypass через заклинания и способности персонажа             │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  AGENT SELECTOR (встроен в ActionClassifier, <1ms) ✅        │
│  COMBAT → [rules, dm]                                       │
│  SOCIAL + major NPC → [npc_major, dm]                       │
│  SOCIAL + толпа → [npc_mass, dm]                            │
│  EXPLORE → [dm]                                             │
│  SANDBOX → [dm] с флагом unconventional=True                │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  PYTHON ENGINES (последовательно, <50ms суммарно)            │
│                                                             │
│  CombatMath      → броски, урон, AC (если бой)     ✅       │
│  SandboxHandler  → 23 обработчика + TOP-100         ✅       │
│  NPCCognition    → драйвы, стресс, доверие          ⏳ Фаза 3│
│  ThreatAssessor  → уровень угрозы                   ⏳ Фаза 3│
│  PerceptionEngine → что NPC видит в игроке          ⏳ Фаза 3│
│  PsycheEngine    → состояние NPC                    ⏳ Фаза 3│
│  KarmaEngine     → обновление репутации             ⏳ Фаза 3│
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  LLM PIPELINE (последовательно, ModelPool max_loaded=1)     │
│                                                             │
│  Если нужен Rules:    switch→Saiga             → rules_result│
│  Если нужен NPC:      switch→Pygmalion Q5_K_M  → npc_result │
│  Всегда:              switch→Qwen2.5-7B        → dm_result  │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  STREAMING SSE → UI   ✅ РЕАЛИЗОВАН                         │
│  stream_tokens() → routes_stream.py → getReader() в JS      │
│  Первый токен: ~500ms после отправки запроса                │
│  В UI: таймер, счётчик tok/s, прогресс-бар, состояния      │
│  Fallback: обычный POST если ReadableStream недоступен       │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  PERSISTENCE                                                │
│  LayeredMemory.write() → JSONL файлы                ✅       │
│  NPCState.save() → major_npcs.json            ⏳ Фаза 3     │
│  CharacterService.update_hp() → characters.json     ✅       │
│  Analytics.record() → player_stats            ⏳ Фаза 8     │
│  TurnManager.next() → следующий игрок         ⏳ Фаза 5     │
└──────────────────────────────────────────────────────────────┘
```

---

## 🎭 NPC система — полная архитектура

### Структура NPC JSON

```json
{
  "id": "farmer_grom_01",
  "name": "Гром",
  "tier": "minor",

  "status_profile": {
    "freedom": 50,
    "wealth": 10,
    "power": 5,
    "title": "Крестьянин",
    "faction_rank": {}
  },

  "visible_markers": ["tunic", "hoe", "calloused_hands"],
  "hidden_truth": ["former_soldier"],

  "drives": {
    "control":      0.60,
    "significance": 0.10,
    "fear":         0.25,
    "desire":       0.05
  },

  "psyche": {
    "willpower":    45,
    "stress":       30,
    "breakpoint":   85,
    "loyalty_true":  50,
    "loyalty_fake":  50,
    "state":        "free",
    "trauma_flags": []
  },

  "social_stats": {
    "trust":          0.50,
    "affection":      0.40,
    "fear_of_player": 0.10,
    "debt":           0
  },

  "relationships": {
    "player_aria":    50,
    "wife_elena":     80,
    "merchant_grok": -20,
    "guild_thieves": -50
  },

  "routine": {
    "current":     "plowing",
    "mood":        "neutral",
    "interrupted": false,
    "next_task":   "feed_children",
    "schedule": {
      "06:00-18:00": "working",
      "18:00-22:00": "family_time",
      "22:00-06:00": "sleeping"
    }
  },

  "recent_events": [
    {"tick": 104, "event": "tax_collector_taken_coins", "impact": "anger"},
    {"tick": 108, "event": "child_broke_tool",          "impact": "frustration"}
  ],

  "flags": {
    "has_gold":      false,
    "knows_secret":  false,
    "is_enslaved":   false,
    "owed_debt":     false,
    "planning_revenge": false
  },

  "memory_trace": [],
  "history": [],
  "location": "village_fields"
}
```

### Три уровня NPC

| Tier | Модель | JSON | Когда |
|---|---|---|---|
| `major` | Mistral Pygmalion 7B Q5_K_M (~4.8 GB) | Полный JSON, полная психология | Ключевые персонажи сюжета |
| `minor` | Mistral Pygmalion 7B Q4_K_M (~4.0 GB) | Сокращённый JSON | Жители, стражники, торговцы |
| `mass` | Mistral Pygmalion 7B Q4_K_M (шаблон) | Только архетип + настроение | Толпа, фоновые персонажи |

### 8 Python движков NPC (цель — <50ms суммарно) [⏳ Фаза 3 — не реализованы]

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ИГРОК ДЕЙСТВУЕТ                                              │
│    "Говори где золото!" [heavy_armor, sword]                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. THREAT ASSESSOR (Python, <50ms)   ⏳ Фаза 3                  │
│    armor=30 + weapon=20 + action=30 = threat_score=80           │
│    → fear_of_player += 0.2                                      │
│    → stress += 40                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. PERCEPTION ENGINE (Python, <50ms)   ⏳ Фаза 3                │
│    visible_markers проверяются против NPC знаний                │
│    → perceived_status: "high" (тяжёлые доспехи = опасен)       │
│    → social_permission: может угрожать                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. PSYCHE ENGINE (Python, <50ms)   ⏳ Фаза 3                    │
│    stress(60+40=100) > breakpoint(85)                           │
│    → state = 'broken'                                           │
│    → loyalty_true -= 30                                         │
│    → trauma_flags.append('threatened')                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. NPC COGNITION (Python, <50ms)   ⏳ Фаза 3                    │
│    dominant_drive = 'control' (0.60)                            │
│    state = 'broken' → overrides drive → survival mode           │
│    behavior_hint = "сломан, подчиняется из страха"              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. LLM NPC AGENT — получает ВСЁ уже посчитанное                │
│    "Гром: control=0.6, stress=100/85 СЛОМАН, угроза=80/100     │
│     fear_of_player=0.3, поведение: подчиняется из страха"      │
│    Модель: Mistral Pygmalion 7B Q5_K_M (Major NPCs)             │
│    → "В-в сарае... под сеном... пожалуйста, не бейте..."       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. KARMA ENGINE (Python, <50ms)   ⏳ Фаза 3                     │
│    reputation['cruel'] += 10                                    │
│    faction['village'] -= 15                                     │
│    if released: schedule_event(tick+3, "revenge_attempt")       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. LIFE ENGINE (фон, каждые 15 мин)   ⏳ Фаза 3                 │
│    routine обновляется (время дня)                              │
│    random_events проверяются (5% шанс)                          │
│    stress снижается если в безопасности (-5/тик)                │
└─────────────────────────────────────────────────────────────────┘
```

### Состояния NPC (psyche.state)

| Состояние | Описание | Поведение |
|---|---|---|
| `free` | Свободен, действует по воле | Следует драйвам, может отказать |
| `coerced` | Принуждён, сопротивляется | Делает но с ненавистью, ищет выход |
| `broken` | Воля сломлена, страх | Подчиняется, loyalty_true падает |
| `loyal` | Добровольно предан | Помогает, защищает, может жертвовать собой |
| `deceptive` | Притворяется лояльным | loyalty_fake ≠ loyalty_true, планирует предательство |

### Драйвы NPC (ядро личности, сумма = 1.0)

| Драйв | Диапазон | Пример речи |
|---|---|---|
| `control` | 0.0–1.0 | «Давай по порядку», «Нужен план» |
| `significance` | 0.0–1.0 | «Я важен», «Это ниже моего достоинства» |
| `fear` | 0.0–1.0 | «Осторожно», «А вдруг не получится?» |
| `desire` | 0.0–1.0 | «Интересно!», «Рискнём!», «А что если?» |

### Таблица поведения NPC (примеры)

| Драйв | Стресс | Статус | Восприятие | Действие | Реакция |
|---|---|---|---|---|---|
| control=0.7 | 20 | 50 | high | Угроза | «Давай обсудим разумно» |
| fear=0.8 | 50 | 50 | high | Угроза | «Пожалуйста, не надо!» |
| desire=0.7 | 30 | 50 | high | Взятка | «Сколько предлагаешь?» |
| any | 85 | 50 | high | Угроза | «Ладно... но это не конец» |
| any | 95+ | 50 | high | Угроза | «Я всё скажу! Только не бейте!» |
| any | 40 | 0 | low | Приказ | «Пошёл ты!» (игнорирует) |
| any | 40 | 100 | high | Приказ | «Слушаюсь, господин!» |

### Inner Thought (прозрачность для DM / debug)

```python
inner_thought = f"""
[Внутренняя мысль {npc.name}]
Драйв доминирующий: {dominant_drive}
Стресс: {npc.psyche['stress']}/100
Состояние: {npc.psyche['state']}
Истинная лояльность: {npc.psyche['loyalty_true']}
Что видит в игроке: {perception['perceived_status']}
План: {'подчиниться и ждать' if state == 'broken' else 'действовать по ситуации'}
"""
```
Игрок **не видит** inner_thought — только DM и Debug Mode.

### Видимые маркеры (влияют на восприятие)

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

## 🎲 Открытый мир — любое действие обрабатывается

### Философия Sandbox

Игрок может делать **что угодно**. Задача архитектуры — **не сломаться**, а отреагировать логично.

```python
class SandboxHandler:
    """
    Обрабатывает нестандартные действия игрока.
    Нет запрещённых путей — есть последствия.
    """
    
    UNCONVENTIONAL_PATTERNS = [
        # (паттерн, тип реакции, бросок если нужен)
        (r"мочусь|расстёгивает ширинку|справляет нужду",
         "social_violation", "charisma_dc_15"),
        
        (r"убегаю|спасаюсь бегством|не хочу драться",
         "flee_attempt", "dexterity_dc_varies"),
        
        (r"хочу стать фермером|покупаю землю|строю дом",
         "life_choice", None),  # нет броска — просто начало пути
        
        (r"беру в плен|захватываю|связываю",
         "capture_attempt", "strength_vs_strength"),
        
        (r"продаю|покупаю на рынке|как раба",
         "trade_human", "karma_check"),
        
        (r"сплю с|ухаживаю за|влюбляюсь",
         "romance_attempt", "charisma_dc_varies"),
    ]
    
    def handle(self, action: str, player: CharacterSheet,
               game_state: GameState) -> SandboxResult:
        
        for pattern, reaction_type, roll_type in self.UNCONVENTIONAL_PATTERNS:
            if re.search(pattern, action.lower()):
                return self._process_reaction(
                    reaction_type, roll_type, player, game_state
                )
        
        # Совсем необычное — передаём DM с пометкой "нестандартное"
        return SandboxResult(type="dm_improvise", context=action)
```

### Примеры обработки нестандартных ситуаций

**Игрок хочет помочиться в таверне:**
```
Python: тип=social_violation, бросок=Харизма DC 15
Если провал (d20+мод < 15):
  → tavern_reputation -= 20
  → npc_reactions: гнев/смех/отвращение (автоматически)
DM получает: "игрок справил нужду публично, реакция: негативная"
DM описывает: хозяин хватается за дубину, посетители шарахаются...
```

**Игрок пацифист, убегает от босса:**
```
Python: тип=flee_attempt, бросок=Ловкость vs Скорость босса
Bosses не стоят на месте — LifeEngine двигает их по расписанию
Если босс быстрее → Combat: преследование
Если убежал → мир запоминает (karma: truce_broken / coward / wise)
```

**Игрок хочет стать фермером:**
```
Python: тип=life_choice, нет броска
TurnManager: особый режим "мирная жизнь"
WorldScheduler: тикает быстрее (1 тик = 1 день)
LifeEngine: рутина "farming" → seasons, crops, relationships
NPCCognition: романтические отношения → trust растёт
Через N тиков: children (новые NPC с relationship=parent)
Karma: накапливается reputation["peaceful_farmer"]
DM описывает каждый тик как короткую виньетку
```

**Игрок берёт NPC в плен:**
```
Python: тип=capture, бросок=Сила vs Сила NPC
Если захвачен:
  → NPC.psyche.state = "coerced"
  → NPC.flags.is_enslaved = true
  → NPC.visible_markers += ["chains"]
  → karma["cruel"] += 15
  → faction[NPC.faction] -= 30 (начнут искать)
Слом воли: 
  → PsycheEngine считает: давление × время = breakpoint
  → При stress > breakpoint: state = "broken"
  → При broken: NPC делает что скажут НО loyalty_true = -100
  → Через N тиков при broken: может попытаться сбежать (5% шанс/тик)
```

**Смерть игрока — не конец:**
```python
class DeathHandler:
    def handle_player_death(self, dead_player: str, 
                             party: list[str]) -> DeathResult:
        # Остальные продолжают играть
        active_players = [p for p in party if p != dead_player]
        
        options = {
            "continue_without": "Остальные продолжают, мёртвый наблюдает",
            "resurrection":     "Можно поднять если есть клирик/артефакт",
            "new_character":    "Мёртвый создаёт нового персонажа",
            "join_later":       "Новый персонаж появляется позже по сюжету",
        }
        
        # Мир реагирует на смерть
        self.karma_engine.record_death(dead_player)
        # NPC которые знали игрока — реагируют (горе, облегчение, выгода)
        self.life_engine.notify_npcs_of_death(dead_player)
        
        return DeathResult(active_players=active_players, options=options)
```

---

## 👥 Мультиплеер 1–8 игроков

### Архитектура сессии

```json
{
  "campaign_id": "demo-campaign",
  "players": [
    {
      "name": "Арагорн",
      "character": {...},
      "is_active": true,
      "acted_this_round": true,
      "last_action": "атакую гоблина слева"
    },
    {
      "name": "Леголас",
      "character": {...},
      "is_active": true,
      "acted_this_round": false,
      "last_action": null
    }
  ],
  "current_player_index": 1,
  "turn_number": 5,
  "round": 2,
  "phase": "player_input"
}
```

### Turn Manager

```python
class TurnManager:
    MAX_PLAYERS = 8
    
    def next_turn(self) -> PlayerSlot:
        """После того как игрок отправил действие — переходит к следующему."""
        self._current_idx = (self._current_idx + 1) % len(self._players)
        if self._current_idx == 0:
            self._round += 1
            # Новый раунд: DM описывает ВСЕ действия раунда вместе
            return self._trigger_round_resolution()
        return self.current_player()
    
    def _trigger_round_resolution(self):
        """
        Все игроки походили — DM описывает что произошло.
        Получает все действия раунда сразу.
        """
        all_actions = self.get_all_actions_this_round()
        # DM промпт получает список действий всех игроков
        # и реагирует на всех сразу — более живая нарративная сцена
```

### Правила очерёдности

```
Обычный режим:
  Арагорн → (DM отвечает) → Леголас → (DM отвечает) → Гимли → (DM отвечает)
  → новый раунд

Боевой режим (инициатива):
  Все бросают инициативу (Python: d20 + Ловкость)
  Порядок хода: по убыванию инициативы
  Враги ходят в свою очередь (NPC cognition автоматически)

Мирный режим:
  Порядок произвольный, можно пропустить ход
  DM отвечает после каждого игрока отдельно
```

### UI для мультиплеера

```
┌──────────────────────────────────────────────────────┐
│  ENIGMA                           ⚙ F12:Debug [✕]   │
├────────────────┬─────────────────────────────────────┤
│  Игроки:       │  ⚔ Мастер подземелий                │
│                │  Вы входите в таверну...             │
│  ➜ Арагорн    │                                     │
│    HP: 28/28   │  ▶ Арагорн: осматриваюсь            │
│    AC: 16      │                                     │
│                │  Мастер отвечает...  ████░ 8.2s     │
│    Леголас     │                                     │
│    HP: 24/24   ├─────────────────────────────────────┤
│                │  ВАШ ХОД: Арагорн                   │
│    Гимли       │  ┌───────────────────────────┐      │
│    HP: 22/22   │  │ Опишите действие...       │      │
│                │  └───────────────────────────┘      │
│  Раунд 2       │           [Действие] [Пропустить]   │
│  Ход 3/3       │                                     │
├────────────────┴─────────────────────────────────────┤
│ VRAM: 4.5/8 GB ▓▓▓▓▓░░░  Модель: Qwen2.5-7B  65t/s │
└──────────────────────────────────────────────────────┘
```

---

## 📡 Streaming токенов — UI опыт ✅ РЕАЛИЗОВАН

### Как работает

```
Запрос → POST /api/game/action/stream → llama-server (stream=true) → SSE события → UI
```

Каждый токен отправляется отдельным SSE событием. Текст появляется как при наборе. Реализовано полностью — `llama_cpp_provider.stream_tokens()` → `dm_agent.stream_narrate()` → `routes_stream.py` → `index.html` с `getReader()`.

### Метрики в реальном времени

```javascript
// Что показывается пока DM думает:

"⚔ Мастер думает...  ████████░░░  12.4с  |  247 токенов  |  65 tok/s  |  Qwen2.5-7B"
                      ↑ прогресс    ↑ таймер   ↑ счётчик    ↑ скорость   ↑ модель
```

### SSE протокол

```python
# Типы событий от сервера к клиенту:

{"type": "status",  "text": "Переключаю модель..."}     # подготовка
{"type": "status",  "text": "Мастер думает..."}         # генерация началась
{"type": "token",   "text": "Вы ", "count": 1}          # токен
{"type": "token",   "text": "видите", "count": 2}       # токен
{"type": "token",   "text": " таверну", "count": 3}     # токен
...
{"type": "npc",     "data": [{name: "Торнин", speech: "..."}]}
{"type": "combat",  "data": {hit: true, damage: 8}}
{"type": "done",    "timing": {total_ms: 8240, tokens: 512, tok_per_sec: 65}}
```

### JavaScript обработчик ✅ (реализован в index.html)

```javascript
// Реальная реализация — fetch + getReader() (не EventSource)
async function sendActionStream(text) {
  const res = await fetch(API + "/game/action/stream", {
    method: "POST", body: JSON.stringify({player, campaign, action: text})
  })
  const reader = res.body.getReader()
  
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    
    // Декодируем SSE строки, парсим JSON-события
    const data = parseSSEChunk(value)
    
    if (data.type === 'token') {
      appendToken(data.text)       // Живое печатание в чат
      updateStreamMetrics(...)     // tok/s, прогресс-бар, таймер
    }
    else if (data.type === 'done') {
      showFinalStats(data)
      unlockInput()
    }
  }
}

// Fallback если ReadableStream недоступен
if (typeof ReadableStream !== "undefined") {
  await sendActionStream(text)
} else {
  await sendActionFallback(text)  // обычный POST
}
```

---

## 🧠 Система памяти — 4 уровня

```
УРОВЕНЬ 1: Оперативная (текущий ход)
  Последние 5 обменов → прямо в промпт
  Бюджет: ~500 токенов

УРОВЕНЬ 2: Сессия (текущая игровая сессия)
  session_memory_{campaign}.jsonl
  Последние 20 событий → читаются каждый ход
  Бюджет: ~1000 токенов

УРОВЕНЬ 3: Кампания (вся история)
  campaign_memory_{campaign}.jsonl
  YandexGPT суммаризирует в конце сессии → ~300 токенов
  "Краткое прошлое" передаётся DM

УРОВЕНЬ 4: Мир (постоянные факты)
  world_canon_{world}.jsonl + ChromaDB (PDF книги)
  RAG поиск по запросу → только релевантные куски
  Бюджет: ~300 токенов
```

### Memory Manager — бюджет токенов

```python
class MemoryManager:
    TOKEN_BUDGET = 800  # из 4096 токенов контекста
    
    def build_context(self, campaign_id, agent_type, location) -> str:
        # 1. Локация + время (всегда, ~100 токенов)
        # 2. Кто присутствует (~50 токенов)
        # 3. Последние события (до 400 токенов)
        # 4. Резюме кампании (если DM, ~200 токенов)
        # 5. RAG результат (если lore_query, ~150 токенов)
        # Итого: не превышает 800 токенов
```

---

## 🎲 Создание персонажа (D&D 5e)

### Три способа генерации характеристик

**A. Бросок 4d6 (популярный):**
```python
def roll_4d6_drop_lowest():
    rolls = [random.randint(1, 6) for _ in range(4)]
    return sum(sorted(rolls)[1:])  # убрать минимум

scores = [roll_4d6_drop_lowest() for _ in range(6)]
```

**B. Стандартный массив:**
```python
STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]
```

**C. Покупка очков (27 очков):**
```python
POINT_BUY_COST = {8:0, 9:1, 10:2, 11:3, 12:4, 13:5, 14:7, 15:9}
POINT_BUY_BUDGET = 27
```

### Математика персонажа

```python
modifier = (score - 10) // 2          # модификатор характеристики
prof_bonus = 2 + (level - 1) // 4     # бонус мастерства
hp_lvl1 = HIT_DIE[class_name] + constitution_modifier  # максимум на 1 уровне
ac_unarmored = 10 + dexterity_modifier  # КД без доспехов
```

### Диалог создания персонажа (DM ведёт)

```
DM: "Кто ты по происхождению?"
Игрок: "Эльф"
  → Python: шаг 1 пройден, раса = "эльф"
  
DM: "Высший или лесной?"
Игрок: "Лесной"
  → Python: бонусы +2 Ловкость, +1 Мудрость

DM: "Кем ты стал в этом мире?"
Игрок: "Плутом"
  → Python: класс = "плут", кость хитов = d8

DM: "Как распределить характеристики?"
Игрок: "Брось кубики"
  → Python: бросает 4d6×6, показывает результаты
  → Игрок распределяет

  [В конце Python всё посчитал]
DM: "Итак, Леголас: Ловкость 18 (+4), КД 14, Хиты 9, 
     Бонус мастерства +2. Ты готов к приключению."
```

---

## 📊 Аналитика и статистика игроков

```python
class PlayerAnalytics:
    """
    Записывает и агрегирует статистику каждого игрока.
    Отображается в конце сессии / по запросу.
    """
    
    def record_action(self, player: str, action: str, 
                       action_type: str, outcome: dict):
        stats = self._load(player)
        
        # Базовые счётчики
        stats["total_actions"] += 1
        stats["actions_by_type"][action_type] += 1
        
        # Боевая статистика
        if action_type == "combat":
            stats["kills"] += outcome.get("killed_npc", 0)
            stats["damage_dealt"] += outcome.get("damage", 0)
            stats["damage_taken"] += outcome.get("damage_received", 0)
        
        # Социальная статистика
        if action_type == "social":
            result = outcome.get("result")
            if result == "persuaded": stats["persuasions"] += 1
            if result == "failed":    stats["social_failures"] += 1
        
        # Нестандартные действия
        if action_type == "unconventional":
            stats["unconventional_actions"] += 1
            stats["unconventional_log"].append(action[:50])
        
        # Репутация
        stats["avg_reputation"] = self._calc_avg_reputation(player)
        
        # Экономика
        stats["gold_earned"] += outcome.get("gold_gained", 0)
        stats["gold_spent"]  += outcome.get("gold_spent", 0)
        
        self._save(player, stats)
    
    def get_session_summary(self, player: str) -> dict:
        """Резюме сессии для показа игроку."""
        stats = self._load(player)
        return {
            "session_title":      "Тёмная ночь в таверне",
            "kills":              stats["kills"],
            "gold_net":           stats["gold_earned"] - stats["gold_spent"],
            "avg_reputation":     stats["avg_reputation"],
            "most_used_action":   stats["top_action_type"],
            "weirdest_action":    stats["unconventional_log"][-1] if stats["unconventional_log"] else None,
            "deaths":             stats["deaths"],
            "quests_completed":   stats["quests_completed"],
            "relationships":      stats["significant_relationships"],
        }
```

**Что показывается игрокам в конце сессии:**
```
╔══════════════════════════════════════╗
║  ИТОГИ СЕССИИ — Арагорн             ║
╠══════════════════════════════════════╣
║  ⚔  Убито противников:    7        ║
║  💰 Золото: +120 / -45             ║
║  ❤  Урон получено:        34 HP    ║
║  👥 Репутация (средняя):  +42      ║
║  🎭 Нестандартных действий: 3      ║
║  💬 Самое странное: "мочится       ║
║     на гоблина"                    ║
║  🏆 Самое частое: исследование     ║
╚══════════════════════════════════════╝
```

---

## 💻 Отвязка от браузера — .exe файл [⏳ Фаза 11]

### Launcher (PyInstaller + pywebview)

```python
# launcher.py — главный .exe (в разработке, заготовки есть в build/)

import webview
import threading
import uvicorn
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent

def start_llm_server():
    """Запускаем llama-server в фоне."""
    subprocess.Popen([
        str(ROOT / "Models LLM" / "llama" / "llama-server.exe"),
        "-m", str(ROOT / "Models LLM" / "qwen2.5-7b-instruct-q4_k_m.gguf"),
        "--port", "8080", "-ngl", "28", "-c", "2048",
        "--n-predict", "800", "--threads", "6"
    ])

def start_backend():
    """FastAPI в фоновом потоке."""
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

def wait_for_port(port, timeout=60):
    import socket, time
    start = time.time()
    while time.time() - start < timeout:
        try:
            socket.connect_ex(("127.0.0.1", port))
            return True
        except:
            time.sleep(0.5)
    return False

def main():
    # Запускаем LLM и backend
    start_llm_server()
    threading.Thread(target=start_backend, daemon=True).start()
    
    wait_for_port(8000)
    wait_for_port(8080)
    
    # Нативное окно — никакого браузера
    window = webview.create_window(
        title="ENIGMA — Local AI Dungeon Master",
        url="http://127.0.0.1:8000",
        width=1280,
        height=800,
        min_size=(900, 600),
        confirm_close=True,
    )
    
    webview.start(debug=False)
    
    # При закрытии окна — останавливаем всё
    cleanup()

if __name__ == "__main__":
    main()
```

### Встроенный Debug Mode (F12)

```
НОРМАЛЬНЫЙ РЕЖИМ:               DEBUG РЕЖИМ (F12):
┌─────────────────────┐         ┌──────────────────────────────┐
│ ENIGMA              │         │ ENIGMA          [Debug ON]   │
│                     │    →    ├──────────────┬───────────────┤
│ [чат]               │         │ [чат]        │ GAME DEBUG    │
│                     │         │              │ Action: social│
│ [ввод]              │         │ [ввод]       │ Agent: npc_maj│
│                     │         │              │ NPC stress:75 │
│                     │         │              │ VRAM: 4.5/8GB │
│                     │         │              │ Tokens: 412   │
│                     │         │              │ Time: 8.2s    │
└─────────────────────┘         └──────────────┴───────────────┘
```

---

## 🔧 Genius Features

### 1. LLM Self-Debug — Error Interpreter ✅ РЕАЛИЗОВАН
Error Interpreter (singleton) перехватывает 5 типов ошибок (timeout, OOM, JSON parse, context overflow, model fail), анализирует JSONL логи и выдаёт fix-рекомендации. Логируется в `data/logs/enigma_YYYYMMDD.jsonl`.
```python
# error_interpreter.py — обрабатывает ошибки LLM-агентов
# 5 типов: TIMEOUT | OOM | JSON_PARSE | CONTEXT_OVERFLOW | MODEL_FAIL
get_error_interpreter().interpret(error_type, context, traceback)
```

### 2. VRAM-Aware Priority Queue ✅ РЕАЛИЗОВАН
При нехватке памяти — приоритет загрузки моделей:
```python
# config.py — agent_model_map
AGENT_PRIORITY = {"dm": 1, "rules": 2, "npc_major": 3, 
                   "npc_mass": 4, "world": 5, "memory": 6}
# ModelPool.is_safe_to_load(model_vram_mb) — проверка перед загрузкой
```

### 3. Offline-First RAG Cache ⏳ Фаза 10
Векторные эмбеддинги PDF книг генерируются при первом запуске, кэшируются в FAISS-индекс. Поиск мгновенный, без сети. Заготовки: `pdf_drop_importer.py`, `knowledge_ingest.py`.

### 4. Player Memory Editor ⏳ Будущая фаза
Игрок может просматривать и редактировать "известные факты" о себе. Прозрачность памяти системы.

### 5. Context Builder ✅ РЕАЛИЗОВАН
`context_builder.py` — динамически собирает контекст для LLM: системный промпт из `Promt_AI.json`, релевантные факты кампании, память сессии, результаты python_engines. Поддерживает бюджет токенов на агента (DM: 2048, NPC: 1024, Rules: 1024).

---

## 📅 Итоговый план реализации

| # | Этап | Срок | Ключевой результат | Статус |
|---|---|---|---|---|
| 0 | Стабилизация | 2 дня | 800 токенов, GPU_LAYERS=33, context_builder | ✅ 95% |
| 1 | Streaming SSE | 1 нед | Текст появляется по мере генерации + таймер | ✅ ГОТОВО |
| 2 | Action Classifier + PhysicsValidator | 1 нед | Python классификатор типов действий | ✅ ГОТОВО |
| 3 | Combat Math + Sandbox Handler | 2 нед | D&D 5e математика + любые действия | ✅ ГОТОВО |
| 4 | NPC Python Engines | 2 нед | 8 движков психологии (Фаза 3A–3B) | ⏳ ТЕКУЩИЙ ЭТАП |
| 5 | Все агенты активны | 1.5 нед | Pygmalion/Saiga/World по назначению | ⏳ |
| 6 | Мультиплеер 1–8 | 2 нед | TurnManager, очередь, групповой DM | ⏳ |
| 7 | Создание персонажа | 1 нед | DM ведёт диалог, Python считает | ⏳ |
| 8 | Система памяти | 2 нед | Memory Manager, суммаризация | ⏳ (LayeredMemory готов) |
| 9 | Аналитика | 1 нед | Статистика игроков, итоги сессии | ⏳ |
| 10 | World Simulator | 1.5 нед | WorldScheduler полноценный | ⏳ (базовый готов) |
| 11 | RAG по PDF | 2 нед | ChromaDB / FAISS, индексация книг | ⏳ (заготовки) |
| 12 | .exe файл | 2 нед | PyInstaller + pywebview, без браузера | ⏳ |

**До v1.0-playable (Этапы 0–6):** ~2.5 месяца от сейчас.
**До полного релиза:** ~5–6 месяцев.

---

## 📈 Текущее состояние

| Компонент | Готовность | Примечание |
|---|---|---|
| Инфраструктура запуска | 98% | start_enigma.bat, pre-flight, динамические порты |
| LLM интеграция (базовая) | 90% | ModelPool, lazy loading, VRAM-aware, streaming |
| Игровой цикл (ход→ответ) | 80% | Orchestrator, ActionClassifier, PhysicsValidator интегрированы |
| Streaming токенов | **100%** | SSE + getReader() + fallback POST + метрики |
| Action Classifier | **100%** | 14 типов, приоритеты, get_required_agents() |
| Physics Validator | **100%** | Правила мира, bypass через заклинания |
| Боевая математика | **100%** | attack_roll, damage, initiative, death saves, grid |
| Sandbox (любые действия) | **100%** | 23 обработчика + TOP-100 нестандартных |
| NPC психология (Python) | 0% | ⏳ Фаза 3A — текущий этап |
| Система памяти | 65% | LayeredMemory + JsonMemoryStore готовы, Manager нет |
| Error Interpreter | 90% | 5 типов ошибок, JSONL логи, fix-рекомендации |
| VRAM Monitor | 95% | baseline fix, get_vram_budget(), ложных утечек нет |
| Context Builder | 85% | динамический сборщик, релевантные факты |
| Мультиплеер | 0% | ⏳ Фаза 5 |
| Создание персонажа | 10% | Математика готова, диалог с DM нет |
| Аналитика | 0% | ⏳ Фаза 8 |
| .exe файл | 5% | Заготовки build/, pywebview |
| RAG по PDF | 10% | pdf_drop_importer.py + knowledge_ingest.py есть |
| **Общий прогресс** | **~60%** | |

---

## 🏛️ Ключевые архитектурные принципы

**1. Python считает — LLM рассказывает.**
Урон, хиты, психология NPC, физика, стресс, репутация — всё это математика в Python. LLM получает готовые числа и превращает их в живую историю. Реализовано: CombatMath, PhysicsValidator, SandboxHandler, ActionClassifier. В разработке: NPC-движки (Фаза 3).

**2. Один llama-server, одна модель в VRAM.**
max_loaded=1 — это не ограничение, это архитектурное решение для 8 GB VRAM. ModelPool с lazy loading. Маппинг агентов: DM/World → Qwen2.5-7B, NPC Major → Pygmalion Q5_K_M, NPC Mass → Pygmalion Q4_K_M, Rules/Memory → Saiga 7B.

**3. Любое действие игрока обрабатывается.**
Нет запрещённых путей — есть последствия. SandboxHandler (23 обработчика + TOP-100 нестандартных ситуаций) превращает даже самые странные действия в осмысленные ситуации. Полностью реализован.

**4. Состояние — единственный источник правды.**
`characters.json`, `major_npcs.json` (создаётся в Фазе 3), `campaign_state.json` — никакая LLM не меняет их напрямую. Только Python сервисы через API.

**5. Мир живёт независимо от игрока.**
WorldScheduler тикает каждые 15 минут (базовая реализация готова). Полноценный LifeEngine с расписаниями NPC, случайными событиями и стресс-механикой — в Фазе 3B.
