# ENIGMA: ДОРОЖНАЯ КАРТА РАЗРАБОТКИ
## Архитектура эмерджентного RPG с автономными NPC

**Версия:** 2.0  
**Дата:** 2026-04-13  
**Статус:** Интеграция экономической и социальной систем

---

## 1. ФИЛОСОФИЯ ДИЗАЙНА

### 1.1 Принципы
- **Нет скриптовых квестов** — только математика выгоды и причинно-следственные связи
- **NPC как автономные агенты** — действуют между ходами игрока (World Tick)
- **Разделение личности и роли** — кто он (static) vs чем занимается (runtime)
- **Всё мутирует** — внешность, профессия, социальный статус меняются в процессе игры
- **Причинность прежде повествования** — CausalLedger → Decision → Verbalization

### 1.2 Поток данных
```
World Event → Social Propagation → PerceptionFilter (R4) → 
→ CausalLedger (R2.1.4) → DecisionHub (R2) → StateApplicator → 
→ SceneOutcome (R3) → DM Verbalization
```

---

## 2. ФАЙЛОВАЯ СТРУКТУРА

```
enigma/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI + startup
│   │   ├── api/
│   │   │   ├── routes.py               # REST endpoints
│   │   │   ├── routes_stream.py        # SSE для DM
│   │   │   └── routes_debug.py         # God Mode (CausalLedger viewer)
│   │   │
│   │   ├── models/                     # Датаклассы (чистые данные)
│   │   │   ├── npc_state.py            # R2.1 NPCState (runtime)
│   │   │   ├── npc_profile.py          # Static конфигурация NPC
│   │   │   ├── personality.py          # L0 Core (черты) + L1 Identity
│   │   │   ├── decision.py             # R2 DecisionResult, Intent
│   │   │   ├── candidates.py           # Кандидаты действий
│   │   │   ├── schemas.py              # Pydantic схемы API
│   │   │   ├── psychological.py        # DistortionProfile, CausalEntry
│   │   │   ├── economy.py              # EconomicProfile, Need, Transaction
│   │   │   └── social.py               # SocialGraph, Relationship
│   │   │
│   │   ├── agents/                     # LLM-агенты
│   │   │   ├── dm_agent.py             # Генерация повествования
│   │   │   ├── dm_orchestrator.py      # Главный фасад DM
│   │   │   ├── dm_router.py            # Парсинг ввода игрока
│   │   │   ├── dm_scene_builder.py     # R4 Spatial контекст
│   │   │   └── rules_agent.py          # Проверка правил (броски)
│   │   │
│   │   └── services/                   # ЯДРО ЛОГИКИ
│   │       ├── game_loop.py            # Координатор ходов + World Tick
│   │       │
│   │       ├── npc/                    # R1-R2: Интеллект NPC
│   │       │   ├── decision_hub.py     # [ЦЕНТР] Выбор intent (score)
│   │       │   ├── state_applicator.py # [ЗАПИСЬ] CausalLedger + мутации
│   │       │   ├── cognitive_distortion.py  # Искажения восприятия
│   │       │   ├── perception_filter.py     # R4 Фильтр по расстоянию
│   │       │   ├── npc_cognition.py         # Фасад когнитивного цикла
│   │       │   ├── opportunity_engine.py    # Генерация кандидатов (работа, торговля)
│   │       │   └── role_transition.py       # Смена профессий
│   │       │
│   │       ├── economy/                # Экономическая система
│   │       │   ├── transaction_engine.py    # NPC-to-NPC сделки
│   │       │   ├── market_simulator.py      # Цены, спрос/предложение
│   │       │   └── need_calculator.py       # Динамический расчет urgency
│   │       │
│   │       ├── social/                 # Социальная система
│   │       │   ├── social_graph.py          # Матрица связей NPC-NPC
│   │       │   ├── social_propagation.py    # Распространение слухов
│   │       │   └── reputation_engine.py     # Репутация в фракциях
│   │       │
│   │       ├── spatial/                # R4: Пространство
│   │       │   ├── location_graph.py
│   │       │   ├── local_space.py
│   │       │   └── spatial_events.py        # proximity_close/leave
│   │       │
│   │       ├── verbalization/          # R3: Вывод
│   │       │   ├── scene_outcome_builder.py
│   │       │   ├── verbal_stance.py
│   │       │   └── scene_continuity.py
│   │       │
│   │       └── persistence/            # Сохранения
│   │           ├── persistence_port.py
│   │           └── json_adapter.py
│   │
│   └── config/                         # КОНФИГУРАЦИЯ (read-only)
│       ├── npc/
│       │   ├── archetypes/             # Шаблоны ролей
│       │   │   ├── _base_humanoid.json
│       │   │   ├── tavern_keeper.json
│       │   │   ├── guard.json
│       │   │   ├── merchant.json
│       │   │   ├── soldier.json
│       │   │   ├── mercenary.json
│       │   │   └── peasant.json
│       │   │
│       │   ├── mixins/                 # Модификаторы archetype
│       │   │   ├── fallen_noble.json
│       │   │   ├── criminal_past.json
│       │   │   └── veteran.json
│       │   │
│       │   ├── individuals/            # Конкретные NPC (только дельта)
│       │   │   ├── tornin.json
│       │   │   ├── borko.json
│       │   │   ├── lusya.json
│       │   │   └── goran.json
│       │   │
│       │   └── social/                 # Связи
│       │       └── village_relations.json
│       │
│       ├── economy/
│       │   ├── needs_library.json      # Типы потребностей
│       │   ├── wages.json              # Ставки оплаты
│       │   └── goods_prices.json       # Базовые цены
│       │
│       └── world/
│           ├── locations.json
│           └── factions.json
│
├── saves/                              # RUNTIME СОХРАНЕНИЯ
│   └── session_{id}/
│       ├── npc_states/                 # Измененные состояния
│       │   ├── tavern_keeper_tornin.json
│       │   └── ...
│       ├── scene_facts.json            # Факты сцены (continuity)
│       ├── social_graph_state.json     # Текущие связи
│       └── player_state.json
│
└── tests/
    ├── unit/
    └── integration/
```

---

## 3. КЛЮЧЕВЫЕ СИСТЕМЫ

### 3.1 Разделение Static vs Runtime

**Static (config/npc/)** — задается разработчиком, не меняется:
- `identity` (имя, происхождение, базовая личность L0)
- `potential_roles` (чем теоретически может заниматься)
- `visual.baseline` (базовая внешность)

**Runtime (saves/ + NPCState)** — меняется в игре:
- `current_role` (текущая профессия)
- `visible_markers` (текущая внешность: шрамы, одежда)
- `psyche` (стресс, травмы, willpower)
- `resources` (золото, инвентарь)
- `relationships` (текущие отношения)
- `causal_ledger` (история событий)

### 3.2 Archetype System (Роли)

```python
# Archetype — пресет профессии
{
  "archetype_id": "tavern_keeper",
  "title": "Хозяин таверны",
  "activity_map": {...},
  "economic_profile": {
    "income_sources": ["tavern_revenue"],
    "needs": ["cleanliness", "security"],
    "resources": {"gold": 100}
  },
  "required_background": [],  # Кто может стать
  "transition_cost": {
    "gold": 0,
    "stress": 0
  }
}
```

**Смена роли** (Торнин → Солдат):
1. `RoleTransitionEngine.can_transition()` — проверка фона/ресурсов
2. `execute_transition()` — смена `current_role`, копирование `activity_map`
3. Запись в `role_history` и `CausalLedger`
4. Обновление `SocialGraph` (другие NPC реагируют)

### 3.3 Economic Engine

**Need** (потребность):
```python
@dataclass
class Need:
    type: str                    # "cleanliness", "security", "revenge"
    urgency: float               # 0.0-1.0 (динамический)
    base_urgency: float          # Базовое значение
    budget_share: float          # Доля золота, готовая тратить
    skill_required: str          # Что нужно от исполнителя
    payment_forms: List[str]     # ["gold", "food", "favor"]
```

**Transaction** (NPC-to-NPC):
```python
@dataclass
class Transaction:
    type: str                    # "sale", "employment", "bribe"
    actor: str                   # Кто предлагает
    target: str                  # Кому
    goods: Dict                  # Что передается
    payment: Dict                # Что получает
    reason: str                  # Причина (для CausalLedger)
```

**Opportunity Generation**:
- Когда NPC имеет `need` с `urgency > 0.6` → ищет исполнителя
- Если нет ресурсов → ищет в `social_graph` кого порекомендовать
- Если есть излишки → предлагает работу/торговлю

### 3.4 Social Graph & Propagation

**SocialGraph** (матрица связей):
```python
{
  "npc_a": {
    "npc_b": {
      "trust": 0.8,            # -1.0 до 1.0
      "affection": 0.3,        # Эмоциональная привязанность
      "fear": 0.1,
      "debt": 50,              # Долг (положительный = должен ему)
      "last_interaction": -15, # Тиков назад
      "shared_secrets": [...]  # Что знают друг о друге
    }
  }
}
```

**Propagation** (распространение событий):
- Событие (смерть, сделка, предательство) → `SocialPropagation`
- Распространение по графу с `decay` (0.8^x, где x — расстояние)
- Искажение через `trust_bias` (враги преувеличивают плохое)

### 3.5 DecisionHub (R2) — Расширенная версия

**Динамические Drives** (временные цели):
```python
temporary_drives: List[Drive] = [
    {
        "type": "vengeance",
        "target": "unknown_killer",
        "urgency": 0.9,
        "expiration": tick + 1000,
        "origin_event": "witnessed_death"
    }
]
```

**Кандидаты (Candidates)**:
1. **Встроенные**: COMBAT, FLEE, TALK, OBSERVE
2. **Экономические**: OFFER_JOB, REQUEST_SERVICE, TRADE, SELL_PROPERTY
3. **Социальные**: REDIRECT_TO_ALLY, SPREAD_RUMOR, CALL_FOR_HELP
4. **Ролевые**: CHANGE_ROLE, SEEK_PROMOTION

**Формула Score**:
```python
score = (
    base_urgency * 0.4 +
    identity_match * 0.3 +      # Соответствие L0 Core
    resource_capability * 0.2 + # Может ли себе позволить
    social_pressure * 0.1       # Что думают другие
) * distortion_modifier
```

### 3.6 CausalLedger (R2.1.4)

Запись каждого значимого события:
```python
@dataclass
class CausalEntry:
    tick: int
    source: str              # "witnessed_death", "sold_property", "player_attack"
    target: Optional[str]    # На кого направлено
    delta: Dict              # Что изменилось
    narrative: str           # Текстовое описание для DM
    emotional_impact: float  # Насколько повлияло на психику
```

Использование:
- **God Mode**: просмотр "почему NPC такой?"
- **DecisionHub**: `get_recent_traumas()` → влияет на fear
- **Verbalization**: `get_life_changing_events()` → для диалогов

---

## 4. ПЛАН РЕАЛИЗАЦИИ (ФАЗЫ)

### ФАЗА 1: РЕФАКТОРИНГ КОНФИГОВ [НЕДЕЛЯ 1-2]

**Цель**: Разделить static и runtime данные

**Задачи**:
1. Создать `config/npc/archetypes/` с шаблонами
2. Переписать `individuals/*.json` в формате "только дельта"
3. Создать `NPCProfileLoader` с наследованием (archetype + delta)
4. Перенести runtime-данные (stress, memory) из конфигов в `NPCState`

**Результат**: 
- Добавление нового NPC = 10-15 строк JSON
- Изменение профессии у всех NPC = правка 1 файла archetype

---

### ФАЗА 2: ЭКОНОМИЧЕСКИЙ ДВИЖОК [НЕДЕЛЯ 3-4]

**Цель**: NPC могут торговать и нанимать друг друга

**Задачи**:
1. Реализовать `NeedCalculator` (динамический urgency от условий)
2. Создать `OpportunityEngine` (генерация кандидатов на основе needs)
3. Реализовать `TransactionEngine` (NPC-to-NPC сделки)
4. Добавить economic кандидатов в DecisionHub:
   - `OFFER_JOB` (если есть need + ресурсы)
   - `REQUEST_SERVICE` (если need + нет ресурсов)
   - `REDIRECT` (если знает того, кто может помочь)

**Тестовый сценарий**:
- Торнин имеет `need:cleanliness urgency:0.8`
- Генерирует `Candidate(OFFER_JOB, wage=10)`
- Если игрок спрашивает о работе → предлагает
- Если игрок не подходит → ищет в `social_graph` кого порекомендовать (Люсю)

---

### ФАЗА 3: СОЦИАЛЬНЫЙ ГРАФ [НЕДЕЛЯ 5-6]

**Цель**: NPC знают друг о друге и передают информацию

**Задачи**:
1. Реализовать `SocialGraph` (загрузка из `config/npc/social/`)
2. Создать `SocialPropagation` (распространение событий)
3. Добавить социальные кандидаты:
   - `CALL_OUT_TO` (крикнуть Люсе в таверне)
   - `SPREAD_RUMOR` (рассказать о смерти)
4. Интеграция с R4: `proximity_close` → проверка `social_graph` на ревность/защиту

**Тестовый сценарий**:
- Игрок подходит к Люси (dist < 1.5)
- Торнин видит это (R4) + проверяет `social_graph["lucy"].affection = 0.8`
- Генерирует `Candidate(INTIMIDATE, reason=jealousy)`

---

### ФАЗА 4: СМЕНА РОЛЕЙ [НЕДЕЛЯ 7-8]

**Цель**: NPC могут менять профессию

**Задачи**:
1. Добавить `current_role` в `NPCState`
2. Создать `RoleTransitionEngine`
3. Добавить `CHANGE_ROLE` в DecisionHub
4. Реализовать `temporary_drives` (месть, жадность, страх)
5. Создать `World Tick` (ходы между действиями игрока)

**Тестовый сценарий** (Торнин → Солдат):
1. Люся погибает (событие)
2. `SocialPropagation` → Торнин узнает
3. `CausalEntry` создает `temporary_drive: vengeance`
4. `OpportunityEngine` → `Candidate(SELL_PROPERTY, reason=fund_vengeance)`
5. `TransactionEngine` → сделка с Гораном
6. `RoleTransitionEngine` → `current_role = "mercenary"`
7. `CausalLedger` записывает всю цепочку

---

### ФАЗА 5: PROACTIVE WORLD [НЕДЕЛЯ 9-10]

**Цель**: Мир живет без игрока

**Задачи**:
1. Реализовать `WorldTickEngine` (тикер раз в N секунд/ходов)
2. Добавить `Agenda` (планы NPC на будущее)
3. Симуляция оффлайн-активности (NPC торгуют, ссорятся, меняют работу)
4. `Spatial Events` (R4 активация): NPC замечают приближение друг друга

**Тестовый сценарий**:
- Игрок входит в таверну через 10 ходов
- Торнин уже продал таверну и ушел
- Горан (новый владелец) стоит за баром
- В `SceneContinuity` факт: "Торнин продал таверну Горану"

---

### ФАЗА 6: ИНТЕГРАЦИЯ И ПОЛИРОВКА [НЕДЕЛЯ 11-12]

**Задачи**:
1. Интеграция с существующей системой (R1-R9)
2. God Mode UI для просмотра CausalLedger
3. Балансировка формул (urgency, trust, score)
4. Тестирование эмерджентных сценариев

---

## 5. ПРИМЕР ЭМЕРДЖЕНТНОГО СЦЕНАРИЯ

### Сценарий: "Месть Торнина"

**Начальное состояние** (config):
```json
// tornin.json
{
  "archetype": "tavern_keeper",
  "origin": "former_soldier",
  "resources": {"gold": 100},
  "relationships": {"lusya": {"affection": 0.8}}
}
```

**Событие** (ход 15):
- Игрок убивает Люсу (или она погибает от другого NPC)
- `Event: npc_death` → `SocialPropagation`

**Реакция Торнина** (ход 16, World Tick):
1. **PerceptionFilter**: получает событие (dist=0, same location)
2. **CausalLedger**: `emotional_impact = 0.8 * 100 = 80 stress`
3. **Temporary Drive**: `vengeance` (urgency=0.9)
4. **DecisionHub**:
   - `INVESTIGATE` (score: 0.4) — узнать кто убийца
   - `SELL_PROPERTY` (score: 0.8) — нужны деньги на оружие
   - `DRINK` (score: 0.2) — слишком слабо
5. **Transaction**: Находит Горана, продает таверну за 400
6. **RoleTransition**: `tavern_keeper` → `mercenary`
7. **CausalLedger**: "Продал таверну, чтобы отомстить за Люсю"

**Встреча с игроком** (ход 25):
- Игрок входит в казармы
- **PerceptionFilter**: видит Торнина в доспехах
- **SceneOutcome**:
  - `visible_markers`: ["military_gear", "sword", "empty_eyes"]
  - `psychological_projection`: {"grief": 0.8, "vengeance": 0.9}
  - `intent`: SEEK_INFORMATION (ищет убийцу)
- **DM генерирует**: "Торнин смотрит сквозь тебя. 'Ты был в таверне той ночью. Видел кого-то подозрительного?'"

**Развитие** (если игрок соврал):
- `CausalEntry`: "Игрок соврал о присутствии"
- `trust` к игроку падает
- Если Торнин узнает правду позже → `temporary_drive: vengeance` может сменить target на игрока

---

## 6. ТЕХНИЧЕСКИЕ ДЕТАЛИ

### 6.1 Инициализация нового NPC (для разработчика)

```python
# 1. Создать файл config/npc/individuals/new_npc.json
{
  "id": "thief_redd",
  "archetype": "thief",
  "identity": {
    "name": "Рыжий",
    "description": "Щуплый парень с рыжими волосами..."
  },
  "delta": {
    "l0_core": {"greed": 0.9}
  },
  "location": "slums"
}

# 2. Добавить связи в config/npc/social/village_relations.json
{
  "thief_redd": {
    "thief_shadow": {"trust": 0.7, "faction": "guild"}
  }
}

# 3. Готово. Все остальное (activity_map, needs, drives) придет из archetype.
```

### 6.2 Добавление новой профессии

```python
# Создать config/npc/archetypes/alchemist.json
{
  "archetype_id": "alchemist",
  "extends": "_base_humanoid",
  "economic_profile": {
    "income_sources": ["potion_sales"],
    "needs": ["rare_ingredients", "laboratory_maintenance"],
    "resources": {"gold": 150, "herbs": 20}
  },
  "activity_map": {...},
  "required_background": ["academic_training"]  # Кто может стать
}
```

### 6.3 Отладка (God Mode)

```python
# GET /debug/npc/{id}/causal_ledger
{
  "npc": "tavern_keeper_tornin",
  "current_role": "mercenary",
  "ledger": [
    {"tick": 0, "event": "spawn", "role": "tavern_keeper"},
    {"tick": 15, "event": "witnessed_death", "target": "lusya", "stress_delta": +80},
    {"tick": 16, "event": "transaction", "sold": "tavern", "price": 400},
    {"tick": 17, "event": "role_transition", "from": "tavern_keeper", "to": "mercenary", "reason": "vengeance"},
    {"tick": 25, "event": "player_interaction", "trust_delta": -0.3, "reason": "player_lied_about_murder"}
  ],
  "temporary_drives": [
    {"type": "vengeance", "urgency": 0.9, "target": "unknown"}
  ]
}
```

---

## 7. РИСКИ И ОГРАНИЧЕНИЯ

### Производительность
- **Social Graph** при 50 NPC: O(n^2) = 2500 связей — приемлемо
- **DecisionHub** каждый тик: 50 NPC * 10 кандидатов = 500 score() — нормально
- **Propagation**: Ограничить радиус (max 3 hops) и частоту (не чаще раза в 5 тиков)

### Баланс
- **Urgency inflation**: Если все needs растут быстро → хаос
  - *Решение*: Капы на urgency (max 0.95), decay со временем
- **Economic collapse**: NPC быстро разоряются
  - *Решение*: Базовый доход от "мирной жизни" (аренда, проценты)

### LLM Costs
- **Verbalization**: Каждое изменение роли = запрос к DM
  - *Оптимизация*: Кэшировать описания типовых ситуаций

---

## 8. ЧЕКЛИСТ ЗАПУСКА MVP

- [ ] Рефакторинг конфигов (Фаза 1)
- [ ] Торнин предлагает работу уборщиком
- [ ] Торнин перенаправляет к Люсе, если занят
- [ ] Торнин продает таверну при высоком стрессе
- [ ] Торнин меняет роль на mercenary
- [ ] God Mode показывает CausalLedger
- [ ] 10 ходов без игрока (World Tick) не ломают мир

---

**Конец документа**

*Для обсуждения и уточнений используйте разделы по номерам (например, "Вопрос по Фазе 3").*
