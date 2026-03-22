# ENIGMA — Локальный AI Dungeon Master
### Полная проектная документация v5.0 | Март 2026

---

## 🎯 Что это такое и зачем

Enigma — локальная компьютерная RPG в жанре D&D 5e, где роль Мастера Подземелий,
всех NPC и самого живого мира выполняет языковая модель, запущенная **полностью
на вашем компьютере** — без облака, без подписки, без интернета.

**Это не чат-бот в антураже фэнтези.** Это симулятор живого мира, где:

- Каждый NPC обладает психологией, драйвами, историей и помнит что ты делал
- Мир живёт и меняется независимо от игрока — LifeEngine тикает каждые 15 минут
- Физика и логика мира неумолимы — свиньи не летают, вода не горит
- От 1 до 8 игроков могут играть за одним компьютером по очереди
- **Любое** действие игрока обрабатывается — нет запрещённых путей, только последствия

**Главный принцип работы:**
```
Игрок пишет действие
        ↓
Python считает (0ms):
  ActionClassifier → PhysicsValidator → CombatMath/SandboxHandler
  → NPC Psychology → SceneState → player_target
        ↓
LLM интерпретирует (8–30 сек):
  Gemma-3-12B получает готовые числа и факты → превращает в живой нарратив
        ↓
Игрок видит живой текст (стриминг токенов с первого слова)
```

NPC умны не потому что LLM умная — а потому что **Python уже всё посчитал**: стресс,
страх, угрозу, статус, кому адресована речь, на каком расстоянии стоит игрок.
LLM получает готовый контекст и занимается только одним: красиво рассказывает.

---

## 🏛️ Архитектурные принципы (незыблемые)

**1. Python считает — LLM рассказывает.**
Урон, психология NPC, физика, стресс, репутация, пространство — всё это математика
Python. LLM получает числа и превращает их в атмосферный текст.

**2. Одна модель в VRAM.**
Gemma-3-12B — единственная активная модель. max_loaded=1 — жёсткое требование
при 8 GB VRAM, не архитектурный каприз.

**3. Любое действие обрабатывается.**
SandboxHandler (23 обработчика + TOP-100 паттернов). Нет запрещённых путей.

**4. Состояние — единственный источник правды.**
`characters.json`, `major_npcs.json`, `campaign_state.json` — только Python сервисы
меняют их через SceneChange. LLM не меняет состояние никогда.

**5. Мир живёт независимо от игрока.**
WorldScheduler тикает каждые 15 минут. LifeEngine двигает NPC по расписанию.

**6. Система generic — без хардкода.**
Персонажей может быть великое множество. Разнообразие действий — бесконечно.
Случиться может что угодно. Поэтому: никакого хардкода имён и ситуаций в коде.
Новый NPC = новый JSON. Новое поведение = новое правило в данных.

**7. Orchestrator — единственный источник игровой логики.**
`routes_stream.py` — только SSE транспорт. `orchestrator.py` — вся логика,
оба пути (синхронный и стриминговый) проходят через один и тот же движок.

---

## 🖥️ Железо и ограничения

| Компонент | Значение | Ограничение |
|---|---|---|
| GPU | RTX 3070 Ti | **8 GB VRAM** — 1 модель одновременно |
| CPU | Intel i7-9700F | 6 физ. ядер, AVX512 |
| RAM | 16 GB | Без роскоши, но достаточно |
| ОС | Windows 11 Россия | Кириллица в путях — всегда проверять кодировки |
| Python | 3.11.9 в `.venv` | Зафиксировано, не обновлять |
| llama.cpp | build 8236 | CUDA + AVX512 + flash attention |

**VRAM-бюджет (реальный, Март 2026):**
```
ОС + CUDA runtime:              ~500 MB
Gemma-3-12B-IT-Q4_K_M:        ~7 500 MB
KV-cache ctx=8192:             ~1 952 MB  (non-SWA + SWA, 4 слота)
Compute buffers:                 ~560 MB
─────────────────────────────────────────
Итого занято:                ~10 512 MB  (часть слоёв на CPU)

ngl=28 слоёв на GPU — баланс скорость/память.
max_loaded=1 — жёсткое требование железа.
```

**Скорость генерации (реальные данные из логов):**
```
Prefill:    ~1.3–2 ms/tok  → ~500–750 tok/sec   ← обработка промпта
Generation: ~123–138 ms/tok → ~7–8 tok/sec       ← генерация ответа
Итого 70–80 токенов:         ~8–13 сек           (Gemma-3-12B, ctx=8192)
```

**Активная модель:**
| Файл | Размер | Роль |
|---|---|---|
| `gemma-3-12b-it-q4_k_m.gguf` | ~6.8 GB | DM + все NPC + Rules + World — одна на всё |

**Резервные модели (не активны, не помещаются с Gemma одновременно):**
| Файл | Размер | Примечание |
|---|---|---|
| `Qwen2.5-7B-instruct-Q4_K_M.gguf` | ~4.1 GB | Резерв |
| `model.gguf` (Qwen3.5-9B) | ~5.3 GB | Требует 12 GB VRAM |
| `mistral-pygmalion-7b.Q5_K_M.gguf` | ~4.8 GB | Резерв |
| `mistral-pygmalion-7b.Q4_K_M.gguf` | ~4.0 GB | Резерв |
| `saiga_mistral_7b_model-q4_K.gguf` | ~4.0 GB | Резерв |
| `YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf` | ~4.5 GB | Резерв |

---

## 📁 Структура проекта

```
Enigma/
├── start_enigma.bat                  ← ЕДИНАЯ ТОЧКА ВХОДА ✅
├── reload_enigma.bat                 ← Полная перезагрузка (убивает процессы) ✅
├── launcher.py                       ← (будет) нативное окно без браузера ⏳
├── .venv/                            ← Python 3.11.9 окружение
├── requirements.txt
│
├── Models LLM/
│   ├── llama/                        ← llama.cpp бинари + CUDA DLL
│   │   ├── llama-server.exe          ← HTTP сервер LLM (порт 8080) ✅
│   │   ├── ggml-cuda.dll             ← CUDA ускорение
│   │   └── ggml-cpu-zen4.dll         ← CPU оптимизация для i7-9700F
│   ├── gemma-3-12b-it-q4_k_m.gguf   ← АКТИВНАЯ МОДЕЛЬ ✅
│   └── [резервные модели]
│
├── backend/                          ← FastAPI сервер (порт 8000)
│   ├── app/
│   │   ├── main.py                   ← FastAPI точка входа, startup checks ✅
│   │   │
│   │   ├── agents/                   ← LLM агенты (все используют Gemma-3-12B)
│   │   │   ├── dm_agent.py           ← DM нарратив, stream_narrate() ✅
│   │   │   ├── npc_agent.py          ← NPC диалоги, S.0 пространственный контекст ✅
│   │   │   ├── rules_agent.py        ← Правила D&D 5e ✅
│   │   │   ├── world_sim_agent.py    ← Мировые события ✅
│   │   │   └── memory_manager_agent.py ← Суммаризация ✅
│   │   │
│   │   ├── api/
│   │   │   ├── routes.py             ← REST эндпоинты ✅
│   │   │   ├── routes_stream.py      ← SSE транспорт (только доставка) ✅
│   │   │   └── routes_debug.py       ← /debug/vram, /health/agents ✅
│   │   │
│   │   ├── core/
│   │   │   ├── config.py             ← настройки, gemma_12b для всех агентов ✅
│   │   │   ├── runtime_config.py     ← динамические порты ✅
│   │   │   ├── error_logger.py       ← единый JSONL логгер ✅
│   │   │   └── settings_*.py         ← параметры агентов ✅
│   │   │
│   │   ├── models/
│   │   │   └── schemas.py            ← Pydantic схемы (model: Optional) ✅
│   │   │
│   │   └── services/
│   │       ├── orchestrator.py           ← ЕДИНЫЙ ИСТОЧНИК ЛОГИКИ ✅
│   │       │   ├── run_turn()            ← синхронный путь
│   │       │   ├── stream_turn()         ← стриминговый путь (новый) ✅
│   │       │   ├── _run_python_engines() ← все Python движки ✅
│   │       │   └── _extract_player_target() ← S.0 парсинг цели ✅
│   │       ├── action_classifier.py      ← 14 ActionType, <1ms ✅
│   │       ├── scene_state_manager.py    ← SceneStateManager ✅
│   │       │   ├── update_player_target() ← S.0 пространство ✅
│   │       │   └── build_npc_context_block() ← блок для NPC промпта ✅
│   │       ├── scene_change.py           ← SceneChange, 10 типов ✅
│   │       ├── world_scheduler.py        ← тикер 15 мин ✅
│   │       │
│   │       ├── npc/
│   │       │   ├── npc_cognition.py  ← драйвы, build_npc_prompt ✅
│   │       │   ├── psyche_engine.py  ← стресс, слом воли, breakpoint ✅
│   │       │   ├── threat_assessor.py ← оценка угрозы ✅
│   │       │   ├── perception_engine.py ← visible_markers → perceived_status ✅
│   │       │   ├── life_engine.py    ← расписание NPC, тики ✅ (базовый)
│   │       │   ├── reaction_priority.py  ⏳ Фаза S.4.2
│   │       │   ├── karma_engine.py       ⏳ Фаза 3B
│   │       │   ├── npc_generator.py      ⏳ Фаза 3B.0
│   │       │   └── social_mobility.py    ⏳ Фаза 3B
│   │       │
│   │       ├── game/
│   │       │   ├── combat_math.py        ← D&D 5e математика боя ✅
│   │       │   ├── physics_validator.py  ← нарушения физики → BLOCKED ✅
│   │       │   ├── sandbox_handler.py    ← 23 обработчика + TOP-100 ✅
│   │       │   │                           (SceneChange при success ⏳ S.4.1)
│   │       │   ├── turn_manager.py       ⏳ Фаза 5
│   │       │   ├── character_creation.py ⏳ Фаза 6
│   │       │   └── death_handler.py      ⏳
│   │       │
│   │       ├── memory/
│   │       │   ├── memory.py         ← LayeredMemory + JsonMemoryStore ✅
│   │       │   ├── memory_manager.py ⏳ Фаза 7
│   │       │   └── knowledge_base.py ⏳ Фаза 10
│   │       │
│   │       └── llm/
│   │           ├── provider.py           ✅
│   │           ├── provider_manager.py   ← ModelPool max_loaded=1 ✅
│   │           ├── llama_cpp_provider.py ← HTTP клиент + streaming ✅
│   │           ├── router.py             ← capability routing ✅
│   │           └── factory.py            ✅
│   │
│   ├── data/
│   │   ├── campaigns/demo-campaign/
│   │   │   ├── characters.json       ← персонаж игрока ✅
│   │   │   └── campaign_state.json   ← SceneState + история ✅
│   │   ├── npcs/
│   │   │   ├── major_npcs.json       ← 5 NPC с полной психологией + name_forms ✅
│   │   │   ├── mass_npc_templates.json ← 10 шаблонов ✅
│   │   │   └── generated/            ⏳ Фаза 3B.0
│   │   ├── locations/
│   │   │   └── location_templates.json ← 5 локаций с time_variants ✅
│   │   ├── Promt_AI.json             ← системный промпт на русском ✅
│   │   ├── pdf_drop/                 ← D&D книги (пусто, ждёт Фазу 10)
│   │   ├── knowledge_db/             ⏳ Фаза 10
│   │   ├── sessions/                 ← сессии игроков ✅
│   │   └── logs/                     ← JSONL логи ✅
│   │
│   └── tests/                        ← 9 тестов, все зелёные ✅
│
└── frontend/ui/index.html            ← SSE streaming + fallback POST ✅
```

---

## ⚙️ Полный цикл одного хода (Март 2026)

```
Игрок пишет действие в браузере
              ↓
    routes_stream.py (только транспорт)
              ↓
    orchestrator.stream_turn()  ← ЕДИНЫЙ ИСТОЧНИК ЛОГИКИ
              │
              ├─ [0ms]  ActionClassifier
              │         14 типов: COMBAT / SOCIAL / EXPLORE / SANDBOX / ...
              │
              ├─ [<1ms] PhysicsValidator
              │         "лечу без заклинания" → BLOCKED
              │         bypass: заклинания и способности персонажа
              │
              ├─ [<50ms] _run_python_engines():
              │
              │   ├─ CombatMath         → бросок d20, урон, крит (если COMBAT)
              │   ├─ SandboxHandler     → 23 обработчика + TOP-100 (если SANDBOX)
              │   ├─ LifeEngine.tick()  → NPC двигаются по расписанию
              │   │
              │   ├─ NPC Psychology блок (для каждого NPC в локации):
              │   │   ThreatAssessor   → threat_score из visible_markers
              │   │   PerceptionEngine → perceived_status игрока
              │   │   NPCCognition     → доминирующий драйв, дельты доверия
              │   │   PsycheEngine     → стресс, breakpoint, behavior_hint
              │   │   build_npc_prompt → system_prompt с психологией NPC
              │   │
              │   └─ S.0 блок:
              │       _extract_player_target() → target_npc_id + name_forms
              │       update_player_target()   → запись в SceneState
              │       Если только местоимение → сохраняем предыдущую цель
              │
              ├─ [8–13 сек] NPC агент (Gemma-3-12B):
              │   Промпт = ТВОЁ ПОЛОЖЕНИЕ В СЦЕНЕ + психология + история
              │   _resolve_active_npcs() → только правильный NPC отвечает
              │   _filter_npc_response() → постфильтр галлюцинаций
              │
              ├─ SSE: {"type":"npc", "data":[...]}  ← NPC реакции сразу
              │
              ├─ [8–13 сек] DM агент (Gemma-3-12B):
              │   Промпт = СОСТОЯНИЕ СЦЕНЫ + результаты Python + правила NPC
              │   stream_narrate() → токены идут в браузер по мере генерации
              │
              └─ SSE: {"type":"token"} × N  +  {"type":"done"}
```

---

## 🎭 NPC система

### Три уровня NPC

| Tier | Контекст в промпте | Когда |
|---|---|---|
| `major` | Полный JSON: психология, история, драйвы, visible_markers | Ключевые персонажи сюжета |
| `minor` | Сокращённый JSON | Жители, стражники, торговцы |
| `mass` | Архетип + настроение | Толпа, фоновые персонажи |

Модель одна для всех — разница только в объёме переданного контекста.

### Структура NPC JSON (полная, актуальная)

```json
{
  "id": "maid_lusya",
  "name": "Люся",
  "name_forms": ["люся", "люси", "люсе", "люсю", "люсей", "люс"],
  "tier": "minor",
  "gender": "женский",
  "description": "Молодая женщина в простом платье служанки...",

  "status_profile": {
    "freedom": 50, "wealth": 5, "power": 5,
    "title": "Служанка таверны", "faction_rank": {}
  },

  "visible_markers": ["maid_dress", "tray", "tired_eyes"],
  "hidden_truth": ["spy_for_thieves_guild"],

  "drives": {
    "control": 0.15, "significance": 0.20,
    "fear": 0.45, "desire": 0.20
  },

  "psyche": {
    "willpower": 35, "stress": 84, "breakpoint": 55,
    "loyalty_true": 20, "loyalty_fake": 55,
    "state": "coerced", "trauma_flags": ["threatened_in_past"]
  },

  "social_stats": {
    "trust": 0.12, "affection": 0.45,
    "fear_of_player": 0.92, "debt": 0
  },

  "relationships": {"player_default": 35, "tavern_keeper_tornin": 40},

  "routine": {
    "current": "serving_tables", "mood": "anxious",
    "schedule": {
      "08:00-23:00": "serving_tables",
      "23:00-08:00": "sleeping"
    }
  },

  "flags": {"is_enslaved": false, "knows_secret": true, "planning_revenge": false},
  "location": "tavern_silver_wolf",

  "hp": 15, "max_hp": 15,
  "combat_stats": {"ac": 10, "attack_bonus": 0, "damage": "1d4"},
  "abilities": {"strength": 8, "dexterity": 13, "constitution": 10,
                "intelligence": 12, "wisdom": 14, "charisma": 12}
}
```

**Ключевое поле `name_forms`** — явные падежи имени, заданные дизайнером.
Без него система вынуждена автогенерировать формы, что даёт ложные срабатывания
для коротких имён вроде "Тень" (→ "тен" → совпадение с "темно").
Новый персонаж = новый JSON с `name_forms`. Код менять не нужно.

### 8 Python движков NPC (статус на Март 2026)

```
1. THREAT ASSESSOR    ✅ — угроза от действия + visible_markers игрока
2. PERCEPTION ENGINE  ✅ — как игрок выглядит → perceived_status
3. PSYCHE ENGINE      ✅ — стресс → breakpoint → state: coerced/broken
4. NPC COGNITION      ✅ — доминирующий драйв, дельты trust/fear
5. LIFE ENGINE        ✅ — базовый: NPC следуют расписанию (sleeping/working)
6. LLM NPC AGENT      ✅ — получает всё посчитанное, озвучивает
7. REACTION PRIORITY  ⏳ S.4.2 — NPC реагируют сами на события
8. KARMA ENGINE       ⏳ 3B — репутация, цепные реакции по фракциям
```

### Состояния NPC (psyche.state)

| Состояние | Поведение |
|---|---|
| `free` | Следует драйвам, может отказать |
| `coerced` | Подчиняется из принуждения, ищет выход |
| `broken` | Воля сломлена, подчиняется из страха (loyalty_true падает) |
| `loyal` | Добровольно предан, может жертвовать собой |
| `deceptive` | loyalty_fake ≠ loyalty_true, планирует предательство |

Переход `stress > breakpoint` → автоматически меняет state на `broken`.
Реализовано в `psyche_engine.apply_stress()`.

### Как S.0 решает проблему пространства

До S.0 модель галлюцинировала расположение персонажей: "Люся протирает столы
в углу" — когда игрок стоит перед ней на коленях. Теперь каждый NPC получает
в начале своего промпта блок:

```
ТВОЁ ПОЛОЖЕНИЕ В СЦЕНЕ:
- Ты: у третьего стола, несёшь поднос
- Игрок: на коленях, расстояние до тебя: ~0.5 м
- ИГРОК ОБРАЩАЕТСЯ ИМЕННО К ТЕБЕ (Люся) — отвечай.
ВАЖНО: Игрок физически рядом с тобой (< 1.5 м).
Ты НЕ МОЖЕШЬ одновременно находиться в другом месте сцены.
```

`_extract_player_target()` в orchestrator — generic, без хардкода имён.
Ищет цель через `name_forms` из JSON + роле-ключевые слова из npc_id префикса.
Сохраняет предыдущую цель при использовании местоимений ("тебя", "тебе").

---

## 🌍 SceneState — состояние сцены

Принцип: **любой объект которого нет в SceneState — не существует**.
LLM только описывает SceneState словами, никогда не меняет его напрямую.
Изменения проходят через `SceneChange → validate → apply`.

```
SceneChange (10 типов):
  OBJECT_REMOVE    — объект исчезает (украден, уничтожен)
  OBJECT_STATE     — состояние меняется (open/broken/burning)
  OBJECT_ADD       — объект появляется
  OBJECT_MOVE      — объект перемещается
  NPC_STATE        — состояние NPC (poisoned/captured/sleeping)
  NPC_POSITION     — NPC меняет позицию/активность
  INVENTORY        — предмет добавляется/убирается у игрока
  ENVIRONMENT      — изменение окружения (свет, шум)
  EFFECT_ADD       — эффект на локацию (fire/darkness/smoke)
  EFFECT_REMOVE    — эффект снимается
```

SceneState в `campaign_state.json` содержит (актуально):
- `location_id` — текущая локация
- `objects` — объекты с состояниями и count
- `npc_positions` — позиции и активности NPC
- `environment` — свет, шум, время суток
- `active_effects` — активные эффекты
- `player_position` — текущая поза игрока ← S.0
- `player_target_npc` / `player_target_npc_name` ← S.0
- `player_target_object` ← S.0
- `player_distances` — расстояния до NPC в метрах ← S.0

LifeEngine читает `routine.schedule` каждого NPC и обновляет их позиции через
SceneChange без участия LLM. Торнин уходит спать в 22:00 — SceneState это знает.

---

## 🎲 Sandbox — любое действие обрабатывается

**Философия:** нет запрещённых путей — есть последствия в SceneState.

```python
class SandboxHandler:
    # 23 обработчика + TOP-100 нестандартных паттернов D&D 5e
    # Каждый обработчик при success=True должен порождать SceneChange
    # target_npc и target_object берутся из SceneState — не хардкод
```

Обработчики: FLEE, CAPTURE, ROMANCE, LIFE_CHOICE, INTIMIDATE, BRIBERY,
DECEPTION, PERSUASION, STEALTH, ACROBATICS, DISTRACTION, ANIMAL_INTERACTION,
CRAFTING, DISGUISE, PICKPOCKET, LOCKPICK, POISON, DIPLOMACY, SURRENDER,
TAUNT, IMPROVISED_WEAPON, CROWD_CONTROL, PHYSICAL + UNKNOWN (fallback TOP-100).

**Следующий шаг (S.4.1):** при `success=True` каждый обработчик генерирует
соответствующий SceneChange. Сейчас SandboxHandler работает, но SceneState
после него не меняется — это задача S.4.1.

---

## 📡 Streaming — архитектура SSE

**После рефакторинга S.0** существует единый путь для обоих режимов:

```
routes_stream.py        → orchestrator.stream_turn()
routes.py               → orchestrator.run_turn()
                                    ↓
                         _run_python_engines()  ← одинаково для обоих
                         npc_agent.react()      ← одинаково
                         dm_agent.stream_narrate() / dm_agent.narrate()
```

`routes_stream.py` — 60 строк. Вся игровая логика в `orchestrator.py`.
Добавить новую фичу = изменить orchestrator один раз, работает везде.

**SSE протокол событий:**
```python
{"type": "ping"}                                    # первое событие
{"type": "status",      "text": "Мастер думает..."} # статус
{"type": "action_type", "value": "SOCIAL"}          # тип действия для UI
{"type": "model",       "data": {...}}              # какая модель работает
{"type": "npc",         "data": ["Люся: ..."]}      # NPC реакции (до DM)
{"type": "token",       "text": "Вы ", "n": 1}     # токен DM нарратива
{"type": "done",        "tokens": 72, "ms": 9995}  # финал со статистикой
```

---

## 🧠 Система памяти (4 уровня)

```
УРОВЕНЬ 1: Оперативная (~500 токенов)
  recent_session — последние 2 хода текущей сессии
  Передаётся напрямую в промпт каждого NPC

УРОВЕНЬ 2: Сессия (~1000 токенов)
  session_memory_{campaign}.jsonl — события текущей сессии
  Читается при старте нового хода

УРОВЕНЬ 3: Кампания (~300 токенов)
  campaign_memory_{campaign}.jsonl — вся история кампании
  Gemma-12B суммаризирует в конце сессии (та же модель, economy mode)

УРОВЕНЬ 4: Мир (~300 токенов)
  world_canon.jsonl + ChromaDB/FAISS (PDF книги D&D) ⏳ Фаза 10
```

`LayeredMemory` + `JsonMemoryStore` реализованы и работают.
`MemoryManager` с бюджетом токенов — ⏳ Фаза 7.

---

## 📈 Текущее состояние (Март 2026)

| Компонент | Готовность | Примечание |
|---|---|---|
| Инфраструктура запуска | **100%** | start_enigma.bat, pre-flight, тесты ✅ |
| LLM интеграция | **95%** | Gemma-3-12B, ModelPool, streaming ✅ |
| Игровой цикл | **85%** | Orchestrator единый источник логики ✅ |
| Streaming SSE | **100%** | stream_turn() в orchestrator ✅ |
| Action Classifier | **100%** | 14 типов, <1ms ✅ |
| Physics Validator | **100%** | Правила мира, bypass ✅ |
| Боевая математика | **100%** | D&D 5e полная ✅ |
| Sandbox Handler | **100%** | 23 обработчика (SceneChange ⏳ S.4.1) |
| SceneStateManager S.0 | **100%** | player_target, расстояния, NPC блок ✅ |
| NPC адресация | **100%** | name_forms + роле-ключевые слова ✅ |
| NPC Psychology | **70%** | Threat/Perception/Psyche/Cognition ✅; Reaction/Karma ⏳ |
| LifeEngine | **40%** | Расписания работают, события/karma ⏳ |
| Система памяти | **65%** | LayeredMemory ✅, MemoryManager ⏳ |
| Error Interpreter | **90%** | 5 типов ошибок, JSONL логи ✅ |
| VRAM Monitor | **95%** | Без ложных утечек ✅ |
| Мультиплеер | **0%** | ⏳ Фаза 5 |
| Создание персонажа | **10%** | Математика ✅, диалог с DM ⏳ |
| RAG по PDF | **10%** | Заготовки есть ⏳ |
| PyGame UI | **0%** | ⏳ Фаза UI |
| **Общий прогресс** | **~70%** | |

---

## 📅 Дорожная карта (актуальная)

| Фаза | Описание | Срок | Статус |
|------|----------|------|--------|
| 0–M | Инфраструктура, стриминг, движки, Gemma-12B | — | ✅ |
| S.0 | SceneState в промпт, S.0 player_target, name_forms | 2 нед | ✅ |
| **S.4.1** | **SandboxHandler → SceneChange** | **2–3 дня** | **⬅️ СЛЕДУЮЩИЙ** |
| S.4.2 | ReactionPriority Queue | 2–3 дня | ❌ |
| 3B | Живой мир (NPCAutoGenerator, LifeEngine полный, KarmaEngine) | 2 нед | ❌ |
| UI | PyGame интерфейс | 2–3 нед | ❌ |
| 3C | Социальная сеть NPC (RumorNetwork, BeliefSystem) | 2 нед | ❌ |
| 3D | ActionLayerEngine, ShockEngine | 2–3 нед | ❌ |
| 5 | Мультиплеер 1–8 игроков | 2 нед | ❌ |
| 6 | Создание персонажа через DM | 1 нед | ❌ |
| 7 | MemoryManager с бюджетом токенов | 2 нед | ⚠️ частично |
| 4.5 | Эпизодическая кампания | 3 нед | ❌ |
| 8 | Аналитика (PlayerStats) | 1 нед | ❌ |
| 9 | World Simulator расширение | 1.5 нед | ❌ |
| 10 | RAG по PDF (ChromaDB/FAISS) | 2 нед | ❌ |
| 11 | Дистрибуция (.exe / PyInstaller) | 2 нед | ❌ |
| 12 | Полные правила D&D 5e | 3–4 нед | ❌ |

**До v1.0-playable (S.4.1 + S.4.2 + 3B + UI):** ~5–6 недель
**До полной v1.0 (+ 3C + 5 + 6 + 7):** ~3.5 месяца
**До релиза:** ~7 месяцев

---

## 🔧 Специальные возможности

### LLM Self-Debug — Error Interpreter ✅
5 типов ошибок: TIMEOUT | OOM | JSON_PARSE | CONTEXT_OVERFLOW | MODEL_FAIL.
Перехватывает, анализирует JSONL логи, выдаёт fix-рекомендации.
Логируется в `data/logs/enigma_YYYYMMDD.jsonl`.

### VRAM-Aware ModelPool ✅
```python
AGENT_PRIORITY = {"dm": 1, "rules": 2, "npc_major": 3, "npc_mass": 4}
# ModelPool.is_safe_to_load() — проверка перед каждой загрузкой
# max_loaded=1 — жёсткий лимит
```

### Стоп-токены Gemma-3 ✅
Gemma-3 генерирует служебные токены после ответа. Специальный фильтр:
```python
_GEMMA_STOP_TOKENS = [
    "<|file_separator|>", "<|end_of_turn|>", "<end_of_turn>",
    "<|im_end|>", "<|im_start|>", "</s>", ...
]
```
Применяется в `dm_agent` (потоковый буфер) и `npc_agent` (парсинг JSON).

### JSON-парсинг ответов NPC ✅
Gemma генерирует `"+3"` в числовых полях — нарушение JSON.
`_fix_json_numbers()` исправляет до парсинга. `_try_repair_json()` восстанавливает
через regex если `json.loads` упал.

### Постфильтр галлюцинаций NPC ✅
`_filter_npc_response()` — если игрок обращался к конкретному NPC,
а модель сгенерировала ответ от другого, фильтр возвращает "молчит".

---

## 🚀 Быстрый старт

```
1. Запустить start_enigma.bat
2. Подождать ~30 сек пока загрузится Gemma-3-12B
3. Открыть браузер: http://127.0.0.1:8000
4. Выбрать персонажа и начать играть

Для полной перезагрузки: reload_enigma.bat
Debug режим: F12 в браузере — психология NPC, SceneState
```

---

## ⚠️ Известные ограничения

- **Свечи не гаснут при краже** — SceneState обновляется правильно,
  но SandboxHandler ещё не генерирует SceneChange (задача S.4.1)
- **Торнин не отвечает ночью** — это не баг, это LifeEngine + расписание работает правильно
- **action_classifier** иногда неверно классифицирует "осматриваюсь" как COMBAT —
  не критично, NPC всё равно молчат при тихих действиях
- **Отсутствие морфологической библиотеки** — падежи имён NPC задаются вручную
  через `name_forms` в JSON. Без этого поля система делает автогенерацию
  которая работает для большинства имён, но может давать сбои на коротких (3-4 буквы)
- **Контекст 8192 токенов** — при длинных сессиях старые события вытесняются.
  MemoryManager с суммаризацией — ⏳ Фаза 7

---

**Документ:** ENIGMA README v5.0
**Обновлено:** Март 2026
**Следующий шаг:** Фаза S.4.1 — SandboxHandler генерирует SceneChange
