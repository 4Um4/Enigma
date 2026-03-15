# ENIGMA — Локальный AI Dungeon Master
### Полная проектная документация v2.0

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
Qwen3.5-9B Q4_K_M:        ~5300 MB  ← основная модель сейчас
KV-cache ctx=2048:           ~260 MB
Буфер безопасности:          ~700 MB
─────────────────────────────────────
Итого занято:              ~6760 MB  (82% VRAM)
Остаток:                   ~1430 MB
```

**Скорость генерации (реальные данные из логов):**
```
Prefill:    2.9 ms/tok  → 344 tok/sec   ← обработка промпта
Generation: 15.3 ms/tok →  65 tok/sec   ← генерация ответа
Итого 512 токенов:       ~8.2 сек
```

**Модели на диске:**
| Файл | Размер | Роль |
|---|---|---|
| `Qwen3.5-9B.gguf` | ~5.3 GB | DM — главный нарратор |
| `Qwen2.5-7B-instruct-Q4_K_M.gguf` | ~4.1 GB | World Sim — логика мира |
| `NPC-LLM-7B.Q4_K_M.gguf` | ~4.0 GB | NPC Major — важные персонажи |
| `NPC-LLM-7B.IQ4_XS.gguf` | ~2.5 GB | NPC Mass — толпа, быстрые реплики |
| `saiga_mistral_7b_model-q4_K.gguf` | ~4.0 GB | Rules — правила D&D 5e |
| `YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf` | ~4.5 GB | Memory — русская суммаризация |

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
│   ├── Qwen3.5-9B.gguf               ← DM агент
│   ├── Qwen2.5-7B-instruct-Q4_K_M.gguf ← World агент
│   ├── NPC-LLM-7B.Q4_K_M.gguf       ← NPC Major агент
│   ├── NPC-LLM-7B.IQ4_XS.gguf       ← NPC Mass агент
│   ├── saiga_mistral_7b_model-q4_K.gguf ← Rules агент
│   └── YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf ← Memory агент
│
├── backend/                          ← FastAPI сервер (порт 8000)
│   ├── app/
│   │   ├── main.py                   ← FastAPI точка входа, startup
│   │   │
│   │   ├── agents/                   ← LLM агенты
│   │   │   ├── dm_agent.py           ← Мастер Подземелий (Qwen9B)
│   │   │   ├── npc_agent.py          ← NPC Major (NPC-7B Q4)
│   │   │   ├── npc_mass_agent.py     ← NPC Mass (NPC-7B IQ4)
│   │   │   ├── rules_agent.py        ← Правила D&D (Saiga)
│   │   │   ├── world_sim_agent.py    ← Мир (Qwen7B)
│   │   │   └── memory_manager_agent.py ← Суммаризация (YandexGPT)
│   │   │
│   │   ├── api/
│   │   │   ├── routes.py             ← основные эндпоинты
│   │   │   ├── routes_stream.py      ← SSE стриминг токенов
│   │   │   └── routes_debug.py       ← /debug/vram, /debug/npc
│   │   │
│   │   ├── core/
│   │   │   ├── config.py             ← настройки + VRAM бюджеты
│   │   │   └── runtime_config.py     ← динамические порты
│   │   │
│   │   ├── models/
│   │   │   └── schemas.py            ← Pydantic схемы
│   │   │
│   │   └── services/
│   │       ├── orchestrator.py       ← главный дирижёр агентов
│   │       ├── action_classifier.py  ← определяет тип действия (Python, 0ms)
│   │       ├── agent_selector.py     ← выбирает нужных агентов
│   │       │
│   │       ├── npc/                  ← NPC движки (Python, без LLM)
│   │       │   ├── npc_cognition.py  ← драйвы, нормализация
│   │       │   ├── psyche_engine.py  ← стресс, слом воли, состояния
│   │       │   ├── threat_assessor.py ← оценка угрозы
│   │       │   ├── perception_engine.py ← видимые маркеры, статус
│   │       │   ├── life_engine.py    ← рутина, расписание, случайные события
│   │       │   ├── karma_engine.py   ← цепные реакции, репутация
│   │       │   └── social_mobility.py ← динамические роли
│   │       │
│   │       ├── game/
│   │       │   ├── combat_math.py    ← D&D 5e математика боя
│   │       │   ├── physics_validator.py ← нельзя летать без заклинания
│   │       │   ├── turn_manager.py   ← очередь ходов 1–8 игроков
│   │       │   ├── character_creation.py ← пошаговая генерация персонажа
│   │       │   ├── sandbox_handler.py ← нестандартные действия
│   │       │   └── death_handler.py  ← смерть не конец игры
│   │       │
│   │       ├── memory/
│   │       │   ├── memory.py         ← LayeredMemory (JSONL)
│   │       │   ├── memory_manager.py ← бюджет токенов, контекст
│   │       │   └── knowledge_base.py ← ChromaDB / FAISS для PDF
│   │       │
│   │       ├── analytics/
│   │       │   └── player_stats.py   ← статистика действий игроков
│   │       │
│   │       ├── llm/
│   │       │   ├── provider_manager.py ← ModelPool (max_loaded=1)
│   │       │   ├── llama_cpp_provider.py ← HTTP клиент + streaming
│   │       │   └── router.py         ← capability routing
│   │       │
│   │       ├── model_router.py       ← агент→модель маппинг
│   │       ├── vram_monitor.py       ← nvidia-smi мониторинг
│   │       └── error_interpreter.py  ← перехват + self-debug
│   │
│   ├── data/
│   │   ├── campaigns/
│   │   │   └── demo-campaign/
│   │   │       ├── characters.json   ← персонажи игроков
│   │   │       └── campaign_state.json ← состояние мира, локация
│   │   ├── npcs/
│   │   │   ├── major_npcs.json       ← важные NPC с полной психологией
│   │   │   └── mass_npc_templates.json ← шаблоны для толпы
│   │   ├── pdf_drop/                 ← D&D 5e книги на русском
│   │   ├── knowledge_db/             ← ChromaDB векторная база (генерируется)
│   │   ├── analytics/                ← статистика игроков
│   │   ├── sessions/                 ← сохранённые сессии
│   │   └── logs/                     ← JSONL структурированные логи
│   │
│   └── tests/
│       └── test_startup_checks.py
│
└── frontend/
    └── ui/
        └── index.html                ← всё в одном файле
```

---

## ⚙️ Полный цикл одного хода

```
Игрок(и) пишут действие(я)
           ↓
┌──────────────────────────────────────────────────────────────┐
│  ACTION CLASSIFIER (Python, <1ms)                           │
│  "расстёгивает ширинку" → тип: SANDBOX_UNCONVENTIONAL       │
│  "атакую гоблина"       → тип: COMBAT                       │
│  "говорю с трактирщиком" → тип: SOCIAL + npc="трактирщик"   │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  PHYSICS VALIDATOR (Python, <1ms)                           │
│  Проверяем: нарушается ли логика мира?                      │
│  "лечу без заклинания" → ОТКЛОНЕНО + объяснение             │
│  "расстёгивает ширинку" → ОК (физически возможно)           │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  AGENT SELECTOR (Python, <1ms)                              │
│  COMBAT → [rules, dm]                                       │
│  SOCIAL + major NPC → [npc_major, dm]                       │
│  SOCIAL + толпа → [npc_mass, dm]                            │
│  EXPLORE → [dm]                                             │
│  SANDBOX → [dm] с флагом unconventional=True                │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  PYTHON ENGINES (параллельно, <50ms суммарно)               │
│                                                             │
│  CombatMath      → броски, урон, AC (если бой)             │
│  NPCCognition    → драйвы, стресс, доверие (если NPC)      │
│  ThreatAssessor  → уровень угрозы (всегда)                  │
│  PerceptionEngine → что NPC видит в игроке (если NPC)      │
│  PsycheEngine    → состояние NPC (если NPC)                 │
│  KarmaEngine     → обновление репутации                     │
│  SandboxHandler  → правила для нестандартных действий       │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  LLM PIPELINE (последовательно, ModelPool max_loaded=1)     │
│                                                             │
│  Если нужен Rules:    switch→Saiga     → rules_result       │
│  Если нужен NPC:      switch→NPC-7B   → npc_result          │
│  Всегда:              switch→Qwen9B   → dm_result (стрим)   │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  STREAMING SSE → UI                                         │
│  Токены идут в браузер по мере генерации                    │
│  Первый токен: ~500ms после отправки запроса                │
│  В UI: таймер, счётчик токенов, название модели             │
└──────────────────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────────────────┐
│  PERSISTENCE                                                │
│  LayeredMemory.write() → JSONL файлы                        │
│  NPCState.save() → major_npcs.json                          │
│  CharacterService.update_hp() → characters.json             │
│  Analytics.record() → player_stats                          │
│  TurnManager.next() → следующий игрок                       │
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
| `major` | NPC-7B Q4_K_M (~4 GB) | Полный JSON, полная психология | Ключевые персонажи сюжета |
| `minor` | NPC-7B IQ4_XS (~2.5 GB) | Сокращённый JSON | Жители, стражники, торговцы |
| `mass` | NPC-7B IQ4_XS (шаблон) | Только архетип + настроение | Толпа, фоновые персонажи |

### 8 Python движков NPC (все работают до LLM, <50ms)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ИГРОК ДЕЙСТВУЕТ                                              │
│    "Говори где золото!" [heavy_armor, sword]                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. THREAT ASSESSOR (Python, <50ms)                              │
│    armor=30 + weapon=20 + action=30 = threat_score=80           │
│    → fear_of_player += 0.2                                      │
│    → stress += 40                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. PERCEPTION ENGINE (Python, <50ms)                            │
│    visible_markers проверяются против NPC знаний                │
│    → perceived_status: "high" (тяжёлые доспехи = опасен)       │
│    → social_permission: может угрожать                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. PSYCHE ENGINE (Python, <50ms)                                │
│    stress(60+40=100) > breakpoint(85)                           │
│    → state = 'broken'                                           │
│    → loyalty_true -= 30                                         │
│    → trauma_flags.append('threatened')                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. NPC COGNITION (Python, <50ms)                                │
│    dominant_drive = 'control' (0.60)                            │
│    state = 'broken' → overrides drive → survival mode           │
│    behavior_hint = "сломан, подчиняется из страха"              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. LLM NPC AGENT — получает ВСЁ уже посчитанное                │
│    "Гром: control=0.6, stress=100/85 СЛОМАН, угроза=80/100     │
│     fear_of_player=0.3, поведение: подчиняется из страха"      │
│    → "В-в сарае... под сеном... пожалуйста, не бейте..."       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. KARMA ENGINE (Python, <50ms)                                 │
│    reputation['cruel'] += 10                                    │
│    faction['village'] -= 15                                     │
│    if released: schedule_event(tick+3, "revenge_attempt")       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8. LIFE ENGINE (фон, каждые 15 мин)                             │
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
│ VRAM: 5.2/8 GB ▓▓▓▓▓▓░░  Модель: Qwen3.5-9B  65t/s │
└──────────────────────────────────────────────────────┘
```

---

## 📡 Streaming токенов — UI опыт

### Как работает

```
Запрос → llama-server (stream=true) → SSE события → UI
```

Каждый токен (слово/часть слова) отправляется отдельным SSE событием. Текст появляется как при наборе — живо, интерактивно.

### Метрики в реальном времени

```javascript
// Что показывается пока DM думает:

"⚔ Мастер думает...  ████████░░░  12.4с  |  247 токенов  |  65 tok/s  |  Qwen3.5-9B"
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

### JavaScript обработчик

```javascript
async function sendActionStream() {
  const source = new EventSource(...)  // или fetch со стримингом
  let tokenCount = 0
  const startTime = Date.now()
  
  source.onmessage = (e) => {
    const data = JSON.parse(e.data)
    
    if (data.type === 'token') {
      // Добавляем токен в чат — живое печатание
      appendToken(data.text)
      tokenCount++
      
      // Обновляем метрики
      const elapsed = (Date.now() - startTime) / 1000
      const tps = tokenCount / elapsed
      updateMetrics(elapsed, tokenCount, tps)
    }
    else if (data.type === 'done') {
      // Финальная статистика
      showTiming(data.timing)
      unlockInput()
    }
  }
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

## 💻 Отвязка от браузера — .exe файл

### Launcher (PyInstaller + pywebview)

```python
# launcher.py — главный .exe

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
        "-m", str(ROOT / "Models LLM" / "Qwen3.5-9B.gguf"),
        "--port", "8080", "-ngl", "33", "-c", "4096"
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
│                     │         │              │ VRAM: 5.2/8GB │
│                     │         │              │ Tokens: 412   │
│                     │         │              │ Time: 8.2s    │
└─────────────────────┘         └──────────────┴───────────────┘
```

---

## 🔧 Genius Features

### 1. LLM Self-Debug Mode
При ошибке разбора JSON от агента — другая модель анализирует и исправляет:
```python
try:
    result = json.loads(llm_response)
except json.JSONDecodeError:
    # Saiga анализирует сломанный ответ
    fix_prompt = f"Исправь невалидный JSON: {llm_response}"
    fixed = rules_agent.run(fix_prompt)
    result = json.loads(fixed)
```

### 2. VRAM-Aware Priority Queue
При нехватке памяти — приоритет: DM > Rules > NPC Major > NPC Mass > World > Memory
```python
AGENT_PRIORITY = {"dm": 1, "rules": 2, "npc_major": 3, 
                   "npc_mass": 4, "world": 5, "memory": 6}
```

### 3. Offline-First RAG Cache
Векторные эмбеддинги PDF книг генерируются при первом запуске, кэшируются в FAISS-индекс. Поиск мгновенный, без сети.

### 4. Player Memory Editor
Игрок может просматривать и редактировать "известные факты" о себе. Прозрачность памяти системы.

---

## 📅 Итоговый план реализации

| # | Этап | Срок | Ключевой результат |
|---|---|---|---|
| 0 | Стабилизация | 2 дня | Правильная модель, 800 токенов, начальная локация |
| 1 | Streaming SSE | 1 нед | Текст появляется по мере генерации + таймер |
| 2 | Action Classifier | 1 нед | Python классификатор типов действий |
| 3 | Combat Math | 1 нед | D&D 5e математика без LLM |
| 4 | NPC Python Engines | 2 нед | 8 движков психологии, все без LLM |
| 5 | Мультиплеер 1–8 | 2 нед | Turn Manager, очередь, групповой DM |
| 6 | Все агенты активны | 2 нед | Saiga/NPC/World используются по назначению |
| 7 | Sandbox Handler | 1 нед | Любое действие обрабатывается |
| 8 | Создание персонажа | 1 нед | DM ведёт диалог, Python считает |
| 9 | Система памяти | 2 нед | 4 уровня, Memory Manager, YandexGPT суммаризация |
| 10 | Аналитика | 1 нед | Статистика игроков, итоги сессии |
| 11 | .exe файл | 2 нед | PyInstaller + pywebview, без браузера |
| 12 | RAG по PDF | 2 нед | ChromaDB / FAISS, индексация книг |

**До первой полностью играбельной версии:** ~4–5 месяцев.
**До минимальной играбельной (без RAG и .exe):** ~2 месяца.

---

## 📈 Текущее состояние

| Компонент | Готовность |
|---|---|
| Инфраструктура запуска | 95% |
| LLM интеграция (базовая) | 70% |
| Игровой цикл (ход→ответ) | 45% |
| Streaming токенов | 0% |
| NPC психология (Python) | 0% |
| Мультиплеер | 0% |
| Боевая математика | 20% |
| Sandbox (любые действия) | 0% |
| Создание персонажа | 10% |
| Система памяти | 50% |
| Аналитика | 0% |
| .exe файл | 0% |
| RAG по PDF | 5% |
| **Общий прогресс** | **~35%** |

---

## 🏛️ Ключевые архитектурные принципы

**1. Python считает — LLM рассказывает.**
Урон, хиты, психология NPC, физика, стресс, репутация — всё это математика в Python. LLM получает готовые числа и превращает их в живую историю.

**2. Один llama-server, одна модель в VRAM.**
max_loaded=1 — это не ограничение, это архитектурное решение. Action Classifier минимизирует количество переключений.

**3. Любое действие игрока обрабатывается.**
Нет запрещённых путей — есть последствия. SandboxHandler превращает даже самые странные действия в осмысленные ситуации.

**4. Состояние — единственный источник правды.**
`characters.json`, `major_npcs.json`, `campaign_state.json` — никакая LLM не меняет их напрямую. Только Python сервисы через API.

**5. Мир живёт независимо от игрока.**
LifeEngine тикает каждые 15 минут. NPC ходят на работу, спят, ссорятся, влюбляются. Игрок возвращается в мир который жил без него.
