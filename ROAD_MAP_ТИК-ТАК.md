┌─────────────────────────────────────────────────────────────────────────────┐
│           АРХИТЕКТУРА ПРОЕКТА (РЕАЛЬНОСТЬ + ДОЛГ)                           │
└─────────────────────────────────────────────────────────────────────────────┘

enigma/
│
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI + startup
│   │   ├── api/                        # ТРАНСПОРТНЫЙ СЛОЙ
│   │   │   ├── routes.py               # REST
│   │   │   ├── routes_stream.py        # SSE
│   │   │   └── routes_debug.py         # God Mode
│   │   │
│   │   ├── models/                     # ЧИСТЫЕ ДАННЫЕ
│   │   │   ├── npc_state.py            # ✅ R2.1 NPCState (динамика) + CausalLedger
│   │   │   ├── behavior_mask.py        # ✅ R8 BehaviorMask, BehaviorMaskState
│   │   │   ├── candidates.py           # Кандидаты действий
│   │   │   ├── npc_profile.py          # L0 Core Profile (из JSON)
│   │   │   ├── character.py            # ✅ CharacterProfile + ValueSet (ФАЗА 2.0)
│   │   │   ├── schemas.py              # Pydantic схемы API
│   │   │   ├── psychological.py        # ✅ DistortionProfile, CausalEntry
│   │   │   ├── scene_mode.py           # ✅ SceneMode (EXPLORATION/INTERACTION/COMBAT)
│   │   │   ├── economy.py              # ✅ Need, Transaction, EconomicProfile
│   │   │   ├── physical.py             # ✅ PhysicalOutcome, Condition, Wound, ThreatAccumulator [ФАЗА 4.5]
│   │   │   ├── event_resolution.py      # ✅ EventResolutionResult, ReflexConstraint, StateChange [ФАЗА 4.5]
│   │   │   └── social.py               # ✅ Relationship (base/runtime), Rumor, PropagationResult
│   │   │
│   │   ├── agents/                     # LLM-агенты
│   │   │   ├── dm_agent.py             # Вербализатор
│   │   │   └── rules_agent.py          # ✅ Интегрирован с Router (Итерация 1)
│   │   │
│   │   ├── core/                       # БАЗОВЫЕ МЕХАНИЗМЫ (не знают об игре)
│   │   │   ├── event_bus.py            # Шина событий
│   │   │   ├── event_types.py          # Типизированные события
│   │   │   ├── constants.py            # ✅ Central Math Config (все веса, капы, формулы) [СОЗДАН]
│   │   │   └── security.py             # Анти-спам, rate limiting
│   │   │
│   │   └── services/                   # ЯДРО ЛОГИКИ
│   │       │
│   │       ├── reaction/               # 🆕 ШАГ 0.5 — REACTION LAYER (физика мира)
│   │       │   ├── reaction_resolver.py # DecisionResult → MicroEvents
│   │       │   ├── micro_event.py       # Структура микро-события
│   │       │   └── reaction_rules.py    # Правила: threat→drop, attack→disrupt
│   │       │
│   │       ├── character/              # 🆕 ФАЗА 2.0 — ПЕРСОНАЖ (после Reaction)
│   │       │   └── character_filter.py # PlayerIntent → FilteredAction (включает resistance scorer)
│   │       │
│   │       ├── game_loop.py            # ★ КООРДИНАТОР + Reaction + Rules интеграция
│   │       │                           # ✅ legacy paths → commit() [ШАГ 1]
│   │       ├── scene_state_manager.py  # ✅ Source of Truth (фасад)
│   │       │
│   │       ├── action/                 # ★★★ DM SYSTEM (реальный путь, НЕ dm/)
│   │       │   ├── dm_orchestrator.py  # Главный фасад
│   │       │   ├── dm_router.py        # ✅ action_mode VERBAL/PHYSICAL (Итерация 1)
│   │       │   ├── dm_scene_builder.py # R4 Spatial контекст
│   │       │   ├── object_resolver.py  # Разрешение объектов
│   │       │   ├── player_target_extractor.py
│   │       │   └─ [ДОЛГ] dm_validator.py    # ⚠️ НЕ СУЩЕСТВУЕТ
│   │       │
│   │       ├── npc/                    # R2 — ЯДРО ИНТЕЛЛЕКТА
│   │       │   ├── decision_hub.py     # ✅ BehaviorMask modifier (Итерация 1)
│   │       │   ├── state_applicator.py # CausalLedger
│   │       │   ├── cognitive_distortion.py  # ✅ Governor + tracking
│   │       │   ├── perception_filter.py     # ✅ cap 15m (Итерация 1)
│   │       │   ├── npc_cognition.py         # Фасад когнитивного цикла
│   │       │   ├── npc_loader.py            # JSON → объекты (будет расширён для archetype+delta)
│   │       │   ├── life_engine.py           # Data-driven активности ✅
│   │       │   ├── threat_assessor.py       # Оценка угрозы
│   │       │   ├── psyche_engine.py         # Психологические режимы
│   │       │   ├── break_progress_engine.py # R8 Прогресс слома
│   │       │   ├── reaction_priority.py     # Приоритеты реакций
│   │       │   ├── resolution_engine.py     # R5 Gap System (психология)
│   │       │   ├── math_utils.py            # Утилиты
│   │       │   ├── condition_engine.py      # ✅ Тикер conditions (bleeding/stunned) [ФАЗА 4.5]
│   │       │   ├── role_transition.py       # ✅ Смена профессий (validation + execution) [ФАЗА 4-ROLE]
│   │       │
│   │       # cognition/ и engines/ — НЕ СУЩЕСТВУЮТ (фантомы, удалены из дерева)
│   │       │
│   │       ├── social/                 # ✅ СОЦИАЛЬНАЯ СИСТЕМА (ШАГ D ЗАВЕРШЁН)
│   │       │   ├── social_engine.py         # ✅ BFS propagation + trust distortion [ШАГ D]
│   │       │   └── reputation_engine.py     # ✅ Репутация в фракциях [ФАЗА 3.5]
│   │       │
│   │       ├── economy/                # ✅ ЭКОНОМИЧЕСКАЯ СИСТЕМА (ФАЗА 2.4)
│   │       │   ├── transaction_engine.py    # NPC-to-NPC сделки
│   │       │   ├── need_engine.py           # Tick потребностей + NeedDrive
│   │       │   ├── economic_modifier.py     # Модификаторы score для DecisionHub
│   │       │   └── opportunity_engine.py    # Генерация кандидатов из needs
│   │       │
│   │       ├── spatial/                # R4 + ФАЗА 3 — ПРОСТРАНСТВЕННАЯ СИСТЕМА
│   │       │   ├── location_graph.py        # R4 Граф локаций
│   │       │   ├── spatial_runtime.py       # R4 Runtime расстояний
│   │       │   └── spatial_events.py        # ✅ detect_transitions (ФАЗА 3.1)
│   │       │
│   │       ├── resolution/                  # ✅ ФАЗА 4.5 — Физическое разрешение
│   │       │   ├── physical_resolver.py     # Кубик + формула → PhysicalOutcome
│   │       │   └── __init__.py
│   │       # npc/resolution_engine.py — R5 Gap System (психология, отдельный слой)
│   │       │
│   │       ├── state/                  # R4 — УПРАВЛЕНИЕ МИРОМ
│   │       │   ├── (scene_state_manager.py вынесен в services/)
│   │       │   ├── context_builder.py       # shared_context
│   │       │   ├── json_persistence_adapter.py
│   │       │   └── persistence_port.py
│   │       │
│   │       ├── memory/                 # R1 — ПАМЯТЬ
│   │       │   ├── working_memory.py        # Краткосрочная
│   │       │   ├── relationship_store.py    # Матрица отношений
│   │       │   ├── layered_memory.py        # L1/L2/L3
│   │       │   ├── memory_manager.py        # Фасад
│   │       │   ├── resonance_engine.py      # L3 Identity
│   │       │   ├── importance_engine.py     # Вес событий
│   │       │   └── contradiction_resolver.py
│   │       │
│   │       ├── verbalization/          # R3 — СЛОЙ ГОЛОСА
│   │       │   ├── scene_outcome_builder.py # ✅ stance интегрирован [ШАГ B.2]
│   │       │   ├── verbal_stance.py         # ✅ [ШАГ B.2] Intent → Stance mapping
│   │       │   ├── scene_continuity.py      # ✅ [ШАГ B.3/B.4] flags, tension, emotion
│   │       │   ├── scene_to_dm_adapter.py   # Адаптер для DM
│   │       │   ├── verbalization_context.py # Контекст вербализации
│   │       │   └── prompt_loader.py         # Загрузка промптов
│   │       │
│   │       ├── events/                 # Шина событий
│   │       │   ├── event_bus.py
│   │       │   └── event_types.py
│   │       │
│   │       ├── scene/                  # Парсинг нарратива + фильтрация
│   │       │   ├── narrative_extractor.py
│   │       │   └── salience_engine.py      # Фильтрация объектов по режиму сцены
│   │       │
│   │       ├── simulation/             # Симуляция мира (legacy)
│   │       │   └── world_state.py      # ⚠️ TODO: аудит необходимости
│   │       │
│   │       └── llm/                    # LLM провайдеры
│   │           ├── router.py           # ✅ Ленивый Semaphore (Итерация 1)
│   │           ├── provider.py
│   │           ├── provider_manager.py
│   │           ├── llama_cpp_provider.py
│   │           ├── factory.py
│   │           ├── health.py
│   │           └── parser.py
│   │
│   └── data/                           # PERSISTENCE LAYER
│       ├── insults_ru.json             # Словарь мата для DM Router
│       └── sessions/                   # Сохранения
│
├── frontend/                           # UI / UX LAYER
│   └── ui/index.html                   
│
├── config/                             # STATIC CONFIG LAYER (read-only)
│   ├── npc/
│   │   ├── archetypes/                 # Шаблоны ролей (только чтение)
│   │   │   ├── _base_humanoid.json
│   │   │   ├── tavern_keeper.json
│   │   │   ├── guard.json
│   │   │   ├── maid.json
│   │   │   ├── merchant.json
│   │   │   └── thief.json
│   │   │
│   │   ├── mixins/                     # Модификаторы archetype
│   │   │   └── veteran.json
│   │   │
│   │   ├── individuals/                # Конкретные NPC (ТОЛЬКО дельта от archetype)
│   │   │   ├── tornin.json
│   │   │   ├── borko.json
│   │   │   ├── lusya.json
│   │   │   ├── goran.json
│   │   │   ├── shadow.json
│   │   │   └── blacksmith.json
│   │   │
│   │   └── social/                     # Статичные связи NPC-NPC
│   │       └── village_relations.json
│   │
│   # economy/ — НЕ СУЩЕСТВУЕТ (константы в models/economy.py)
│   └── world/                          # ✅ Фракции мира [ФАЗА 3.5]
│       └── factions.json               # 4 фракции: гильдия_воров, городская_стража, торговая_гильдия, таверна
│
├── saves/                              # RUNTIME СОХРАНЕНИЯ (отдельно от config)
│   └── session_{id}/
│       ├── npc_states/                 # Изменённые состояния NPC
│       ├── scene_facts.json            # Факты сцены (continuity)
│       ├── social_graph_state.json     # Текущие связи (мутируют)
│       └── player_state.json

================================================================================
0. ТРЁХУРОВНЕВАЯ МОДЕЛЬ АГЕНТОВ (ФУНДАМЕНТ)
┌─────────────────────────────────────────────────────────────────────────────┐
│ УРОВЕНЬ 1 — ИГРОК (внешний оператор) │
│ ├─ Вводит намерение │
│ ├─ НЕ обязан подчиняться логике мира │
│ └─ "Сделай X" — это ЗАПРОС, не приказ миру │
├─────────────────────────────────────────────────────────────────────────────┤
│ УРОВЕНЬ 2 — ПЕРСОНАЖ (агент в мире) ← КЛЮЧЕВОЙ НОВЫЙ СЛОЙ │
│ ├─ Имеет характер (ценности, страх, социальные рамки) │
│ ├─ Имеет ограничения │
│ ├─ МОЖЕТ НЕ СОГЛАСИТЬСЯ с игроком │
│ └─ Мягкое сопротивление: ослабить / изменить форму / добавить последствия│
├─────────────────────────────────────────────────────────────────────────────┤
│ УРОВЕНЬ 3 — NPC (интерпретатор действий) │
│ ├─ Видит ДЕЙСТВИЕ ПЕРСОНАЖА, не намерение игрока │
│ └─ Реагирует на то, что произошло, а не на то, что хотел игрок │
└─────────────────────────────────────────────────────────────────────────────┘

DATA FLOW ПЕРСОНАЖА:
PlayerIntent → CharacterFilter → FinalAction → NPC perception

CharacterFilter ПРОВЕРЯЕТ:
├─ Ценности (self_integrity, pride, honour)
├─ Страх (физический, социальный, экзистенциальный)
├─ Социальные рамки (статус, репутация, роль)
└─ Текущее состояние (стресс, усталость, влияние)

РЕЗУЛЬТАТ CharacterFilter:
├─ ACCEPT: действие проходит без изменений
├─ MODIFY: действие ослаблено или изменено
├─ RESIST: действие с последствиями (стресс, стыд, репутация)
└─ REFUSE: отказ (только при высоком self_integrity + крайнем конфликте)

МАТРИЦА TRUST (3 направления, не 2):
├─ NPC→player: меняется от действий персонажа ✅ УЖЕ РЕАЛИЗОВАНО
├─ player→NPC: НЕ меняется автоматически от действий ❌ БЫЛ БАГ (исправлен)
└─ character→NPC: меняется через CharacterFilter 🆕 НОВЫЙ СЛОЙ

================================================================================

## ЦЕНТРАЛЬНЫЙ КОНФИГ КОНСТАНТ (Central Math Config)

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

# Life Engine
MINOR_TICK_INTERVAL = 3
RANDOM_EVENT_CHANCE = 0.05
STRESS_RECOVERY_SAFE = 5
STRESS_RECOVERY_SLEEPING = 15
TICK_SAVE_INTERVAL = 10
MAX_CACHED_CAMPAIGNS = 100
CAMPAIGN_TTL_SECONDS = 3600
MACRO_SIM_THRESHOLD_SECONDS = 3600


## Дорожная карта

### Текущее состояние: мир мёртвый
- WillState не импортирован → decision_hub крашится → 0 decisions
- Телеграф спамит мгновенно (нет задержки между перезапусками)
- Idle_tick каждый 5 сек вызывает LLM — дорогой и бессмысленный
- Тики = 1 час глобально

---

### Фаза 1: Остановить кровотечение

**Цель:** мир должен хотя бы дышать, а не спамить мусор.

**1.1** WillState — импорт уже добавлен, проверить что decision_hub теперь выдаёт decisions (один запуск игры)

**1.2** Телеграф — убрать мгновенный перезапуск. Сейчас строка 410-415 `game_screen.py` перезапускает телеграф сразу после ответа. Добавить **минимальный интервал** (не 30 сек — это потом, а хотя бы 15 сек чтобы перестать спамить пока не реализована фаза 3)

**1.3** Idle_tick — убрать LLM-вызов из тика. Сейчас idle_tick → pipeline → LLM. Тик должен обновлять **внутренние состояния** NPC (stress, intent accumulation), но **не вызывать LLM**. LLM вызывается только когда есть что вербализовать.

---

### Фаза 2: Два слоя тиков

**Цель:** разделить "думание" и "говорение".

**2.1** Дешёвый тик — работает **всегда**, даже в диалоговом режиме:
- Обновляет внутренние состояния NPC (decision_hub без LLM)
- Накапливает давление, намерения, proximity-триггеры
- Частота зависит от расстояния: близкие NPC — каждые 2-3 сек, дальние — каждые 10-15 сек
- **Без LLM-вызова** — чистая математика

**2.2** Дорогой тик — только когда есть что вербализовать:
- NPC принял решение с достаточным давлением
- Произошло событие (подошёл, крикнул, упал)
- Игрок совершил действие
- **Вызывает LLM** для озвучки

---

### Фаза 3: Телеграф = окно, не таймер

**Цель:** убрать фиксированные 30 сек, сделать pressure-driven.

**3.1** Убрать таймер 30 сек из `game_screen.py`

**3.2** Телеграф триггерится когда:
- Дешёвый тик обнаружил что у NPC накопилось давление выше порога
- NPC подошёл к игроку (proximity-триггер)
- Произошло событие в зоне восприятия

**3.3** Если давления нет и ничего не произошло — телеграф **не срабатывает**, мир просто ждёт. Иногда это будет 5 сек (агрессивный NPC), иногда 2 мин (спокойная сцена), иногда никогда.

**3.4** После телеграфа — порог сбрасывается, следующий только когда давление накопится снова.

---

### Фаза 4: Локальные тики вместо глобального часа

**Цель:** таверна не проживает год за один разговор.

**4.1** Убрать "1 час за тик" из `world_tick_engine.py`

**4.2** Время продвигается только от **действий**:
- Игрок сказал что-то → +0 секунд (диалог)
- Игрок подошил к двери → +10 секунд
- Игрок сказал "я жду час" → +1 час
- Телеграф сработал (NPC проявил инициативу) → +30 секунд
- Явный переход: "идём к таверне" → рассчитать по расстоянию

**4.3** Частота дешёвых тиков — не время, а **расстояние**:
- NPC в 5м → тик каждые 2 сек (реагирует быстро)
- NPC в 15м → тик каждые 8 сек
- NPC в другой комнате → тик каждые 30 сек
- NPC в другом городе → нет тика

---

### Фаза 5: Decision hub работает всегда

**Цель:** мир думает даже когда молчишь.

**5.1** Убрать зависимость decision_hub от `is_dialogue` флага

**5.2** Decision_hub вызывается в каждом дешёвом тике для NPC в зоне восприятия

**5.3** Решения накапливаются, но не вербализуются пока давление ниже порога

**5.4** Когда давление превышает порог → помечается как "ready to verbalize" → следующий дорогой тик вызывает LLM

---

### Приоритет выполнения

| Порядок | Что | Результат |
|---------|-----|-----------|
| 1 | 1.1 WillState | Decision hub не крашится |
| 2 | 1.3 Idle_tick без LLM | Перестаёт спамить LLM каждые 5 сек |
| 3 | 1.2 Телеграф минимальный интервал | Перестаёт спамить телеграф |
| 4 | 2.1 Дешёвый тик | Мир думает без LLM |
| 5 | 2.2 + 3.x Телеграф pressure-driven | Инициатива от NPC, не от таймера |
| 6 | 4.x Локальные тики | Время не летит |
| 7 | 5.x Decision hub всегда | Мир дышит |

---

Начинаем с шага 1.1 — проверяем что WillState импорт починил decision_hub. Запускай игру, пиши что видишь в логе — есть ли теперь decisions вместо `0 decisions → DMFrame`.

******

Фаза 1 завершена полностью. Итого исправлено:

1.1 ✅ WillState — decision_hub работает (6 decisions)
1.2 ✅ Телеграф не спамит
1.3 ✅ Idle tick уже без LLM (было по дизайну)

Итого Фаза 2.1:

Компонент
Статус
Distance-based интервал (клиент)	✅ 2с/8с/30с
DecisionHub в idle_tick (бэкенд)	✅ Без LLM
Правильный загрузчик NPC	✅ load_npcs_merged
Порог 0.5 для триггера	✅ Спокойная сцена не спамит


Итого Фаза 2.1 + 2.2 + 3.x завершена:
Компонент
Результат
Distance-based интервал	✅ 2с/8с/30с по расстоянию до NPC
DecisionHub в idle_tick	✅ Чистая математика, без LLM
Pressure accumulation	✅ 10% от score за тик, 5% decay
Pressure-driven telegraph	✅ Триггер при давлении ≥ 0.5
Сброс после триггера	✅ NPC "выразил" намерение → давление сброшено
Человекочитаемый текст	✅ "Борко хочет что-то сообщить" вместо технического

Дорожная карта выполнена:

Фаза
Статус
Результат
1.1 WillState	✅	Decision hub не крашится
1.2 Телеграф интервал	✅	Не спамит мгновенно
1.3 Idle tick без LLM	✅	Было по дизайну
2.1 Дешёвый тик	✅	2с/8с/30с по расстоянию
2.2 DecisionHub в idle	✅	Чистая математика
3.x Pressure-driven	✅	Накопление → триггер → сброс
4.x Время от действий	✅	Диалог = 0 сек, ходьба = 10 сек
5.x Decision hub всегда	✅	В каждом idle tick

Что изменилось в мире:

NPC думают даже когда молчишь (DecisionHub в idle tick)
Телеграфы органичные: "торнин хочет что-то сообщить", "thief_shadow хочет предупредить"
Время не летит — привязано к действиям, не к тикам
Интервал тиков зависит от расстояния до ближайшего NPC
Мир теперь дышит.

две параллельные легаси-системы времени в routes.py:334-347 и api_client.py:340-358, которые мутируют time_of_day напрямую, минуя Calendar. Это технический долг, но сейчас объясняет [TIME_WALK].