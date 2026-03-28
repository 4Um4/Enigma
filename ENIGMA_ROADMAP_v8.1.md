# ENIGMA — Дорожная карта реализации
## Версия 8.1 | Март 2026 | Актуальная

---

## Что изменилось vs v8.0

- Добавлены **решения для всех 6 выявленных рисков** (см. Раздел 3).
- Закрыты **5 открытых вопросов** (SceneChange, WTB, intent fallback, async, тесты).
- Phase 3B разбита на **4 подфазы** с критериями готовности.
- Уточнён официальный пайплайн: affordance → perception (порядок исправлен).
- `intent_parser.py` переведён в **опциональный fallback**, не основной путь.
- `event_bus.py` — **одна копия** в `events/`, `core/` только импортирует.
- `systems/` — **заглушки** до Phase 3E.

---

## 1. Описание проекта

### Что такое ENIGMA

ENIGMA — локальный движок настольной ролевой игры (TTRPG), где искусственный
интеллект выступает в роли Мастера (DM, Dungeon Master). Игра происходит в
текстовом формате: игрок пишет что делает его персонаж, движок отвечает живым
нарративом.

### Ключевое отличие от ChatGPT-ролеплея

Обычный ChatGPT-ролеплей — это stateless чат. Каждый ответ — отдельный акт,
мир сбрасывается. ENIGMA — это **симуляция живого мира**:

- Стул, сломанный в первой сцене, лежит сломанным в третьей.
- NPC помнит что ты ему угрожал и накапливает стресс.
- Стражник обходит коридор по расписанию даже когда ты не в комнате.
- Рынок закрывается ночью. Свеча догорает. Фракции реагируют на слухи.

### Как это достигается

**WorldState** — структура данных Python, единственный источник правды о мире.
LLM не хранит ничего в "памяти" — он получает срез WorldState как контекст и
генерирует только художественный текст.

**SceneChange** — каждое действие игрока производит строго типизированные
изменения WorldState через Python-объекты, а не через свободный текст LLM.

**EventBus** — изменения публикуются как события. Все подсистемы (NPC AI,
LifeEngine, FactionSystem) подписаны на нужные типы событий.

**Scheduler + world_tick()** — мир живёт по своему расписанию без участия
игрока.

**World Token Budget** — жёсткий лимит токенов на контекст мира (< 2048).
Автоматическое сжатие. LLM никогда не "забывает" начало сцены.

### Технический стек

| Компонент | Технология |
|-----------|-----------|
| Backend | FastAPI (Python 3.11+) |
| LLM | Gemma-3-12B локально (RTX 3070 Ti, 8 GB VRAM) |
| Frontend | HTML/JS, SSE-стриминг токенов |
| Память | JSON-файлы (LayeredMemory: session → campaign → world canon) |
| Правила | D&D 5e в Python (не в LLM) |
| Классификация | keyword-matching (0 мс), LLM только fallback |

### Главный принцип

> **Python считает. LLM рассказывает.**

Вся математика, правила, логика мира — Python. LLM получает готовый контекст
и генерирует только художественный текст. Это обеспечивает предсказуемость,
скорость и возможность тестирования каждого модуля отдельно.

---

## 2. Архитектура проекта (v8.1)

```
Enigma/
├── start_enigma.bat           ← единая точка входа
├── reload_enigma.bat
├── launcher.py
│
├── backend/
│   ├── app/
│   │   ├── main.py            ← FastAPI + startup → запускает GameLoop
│   │   │
│   │   ├── api/
│   │   │   ├── routes.py          ← REST (run_turn) — только транспорт
│   │   │   ├── routes_stream.py   ← SSE (stream_turn) — только транспорт
│   │   │   └── routes_debug.py
│   │   │
│   │   └── services/
│   │       │
│   │       ├── core/              ★ ЯДРО СИСТЕМЫ
│   │       │   ├── game_loop.py       ← единственная точка входа для хода
│   │       │   └── scheduler.py       ← world_tick() по таймеру (Phase 3B.4)
│   │       │   # NB: event_bus — только в events/, здесь не дублируется
│   │       │
│   │       ├── input/             ← ВВОД ИГРОКА
│   │       │   ├── action_classifier.py  ← keyword (0 мс) — основной путь
│   │       │   └── intent_parser.py      ← LLM fallback (только при UNKNOWN)
│   │       │
│   │       ├── action/            ← ОБРАБОТКА ХОДА (существующие модули)
│   │       │   ├── processor.py          ← classify + physics (Шаг 4)
│   │       │   ├── player_target_extractor.py  (Шаг 1)
│   │       │   └── python_engines.py     ← все движки за 1 вызов (Шаг 3)
│   │       │
│   │       ├── simulation/        ← ЕДИНСТВЕННЫЙ ИСТОЧНИК ПРАВДЫ
│   │       │   ├── world_state.py        ← расширенный SceneState (Phase 3B.2)
│   │       │   ├── scene_state_manager.py
│   │       │   ├── scene_change.py       ← типизированные изменения мира
│   │       │   └── context_builder.py    ← единый контекст для DM + NPC
│   │       │
│   │       ├── engines/           ← МАТЕМАТИЧЕСКИЕ ДВИЖКИ
│   │       │   ├── combat/
│   │       │   │   ├── combat_math.py
│   │       │   │   └── combat_turn_manager.py  (Phase 3D)
│   │       │   ├── physics/
│   │       │   │   └── physics_validator.py
│   │       │   ├── economy/       (Phase 3E)
│   │       │   ├── npc_ai/        ← бывшая npc_psychology/
│   │       │   │   ├── npc_cognition.py
│   │       │   │   ├── psyche_engine.py
│   │       │   │   ├── threat_assessor.py
│   │       │   │   ├── perception_engine.py
│   │       │   │   └── life_engine.py
│   │       │   └── world/
│   │       │       └── world_loader.py   (Phase 3D)
│   │       │
│   │       ├── systems/           ← ВЫСОКОУРОВНЕВЫЕ СИСТЕМЫ (Phase 3E+)
│   │       │   ├── __init__.py    # заглушка — функционала нет до Phase 3E
│   │       │   ├── rumor_system.py    # TODO: Phase 3E
│   │       │   ├── law_system.py      # TODO: Phase 3E
│   │       │   ├── faction_system.py  # TODO: Phase 3E
│   │       │   └── politics_system.py # TODO: Phase 3F
│   │       │
│   │       ├── events/            ← EVENT BUS (Phase 3B.1)
│   │       │   ├── event_bus.py       ← единственная копия EventBus
│   │       │   └── event_types.py     ← все типы событий (enum + dataclass)
│   │       │
│   │       ├── ai/                ← LLM-АГЕНТЫ (только рассказывают)
│   │       │   ├── dm_agent.py
│   │       │   ├── npc_agent.py
│   │       │   └── rules_agent.py
│   │       │
│   │       ├── output/            ← ВЫХОДНОЙ СЛОЙ
│   │       │   ├── narration.py       ← финальная сборка нарратива
│   │       │   └── ui_adapter.py      ← SSE-формат для frontend
│   │       │
│   │       ├── memory/            ← LayeredMemory (существующий)
│   │       └── llm/               ← router + providers (существующий)
│   │
│   └── data/
│       ├── campaigns/
│       ├── npcs/
│       ├── locations/
│       └── logs/
│
└── frontend/ui/index.html
```

---

## 3. Решения для выявленных рисков

### Риск 1: LLM Intent на каждый ход → критично для скорости

**Проблема:** LLM intent parser добавляет +5–15 сек на каждый ход при 8 GB VRAM.

**Решение — двухуровневая классификация:**

```
player text
    ↓
action_classifier.py    ← keyword matching, 0 мс, ВСЕГДА
    ↓
    если ActionType == UNKNOWN и confidence < 0.4:
        ↓
    intent_parser.py    ← LLM fallback, ТОЛЬКО в этом случае
        ↓
    structured action
```

**Реализация в `action/processor.py`:**

```python
INTENT_FALLBACK_THRESHOLD = 0.4  # confidence ниже этого → LLM fallback

def classify_with_fallback(self, action_text: str) -> tuple[ActionType, float]:
    act_type, confidence = classifier.classify_with_confidence(action_text)
    if act_type == ActionType.UNKNOWN and confidence < INTENT_FALLBACK_THRESHOLD:
        # LLM fallback — только здесь, не в основном пути
        act_type = self._llm_intent_fallback(action_text)
    return act_type, confidence
```

**Правило:** `intent_parser.py` никогда не вызывается в основном пути.
Ожидаемая частота fallback: < 5% ходов при хорошем classifier.

---

### Риск 2: EventBus / SceneChange — типы событий не формализованы

**Решение — полная схема SceneChange и EventType до старта Phase 3B.1:**

**`events/event_types.py` — исчерпывающий список:**

```python
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Optional
import time

class EventType(Enum):
    # Физический мир
    OBJECT_MOVED       = auto()  # объект переместился
    OBJECT_DESTROYED   = auto()  # объект уничтожен
    OBJECT_CHANGED     = auto()  # состояние объекта изменилось (дверь открыта)
    LIGHT_CHANGED      = auto()  # освещение изменилось
    SOUND_EMITTED      = auto()  # звук (слышат NPC в радиусе)
    SMELL_EMITTED      = auto()  # запах (слышат NPC в радиусе)

    # Персонаж / игрок
    PLAYER_MOVED       = auto()  # игрок сменил позицию
    PLAYER_ATTACKED    = auto()  # атака
    PLAYER_SPOKE       = auto()  # игрок сказал что-то
    PLAYER_USED_ITEM   = auto()  # использование предмета
    PLAYER_CAST_SPELL  = auto()  # заклинание

    # NPC
    NPC_STATE_CHANGED  = auto()  # стресс, доверие, etc.
    NPC_MOVED          = auto()  # NPC сменил позицию
    NPC_SPOKE          = auto()  # NPC сказал что-то

    # Мир
    TIME_PASSED        = auto()  # world_tick — прошло игровое время
    WEATHER_CHANGED    = auto()
    FACTION_EVENT      = auto()  # Phase 3E

@dataclass
class SceneChange:
    event_type:  EventType
    actor_id:    str                    # кто совершил действие (player_name или npc_id)
    target_id:   Optional[str] = None  # на кого/что направлено
    location:    str = ""
    parameters:  Dict[str, Any] = field(default_factory=dict)
    timestamp:   float = field(default_factory=time.time)
    visible_to:  list = field(default_factory=list)  # [] = видят все
    audible_to:  list = field(default_factory=list)  # [] = слышат все
    radius:      float = 999.0          # метры, для фильтрации perception
```

**Правило именования:** event_type описывает **что произошло в мире**,
не что хотел игрок. `PLAYER_ATTACKED` а не `PLAYER_CHOSE_ATTACK`.

---

### Риск 3: World Token Budget — нет явного места в пайплайне

**Решение — WTB применяется в `simulation/world_state.py` в двух точках:**

**Точка A** — при `world_state.update()` после применения SceneChange.
Неважные объекты (не в текущей локации, не активны) сжимаются до summary.

**Точка B** — при `context_builder.build_context()` перед отправкой агентам.
Финальный срез проверяется и обрезается по жёсткому лимиту.

**Реализация:**

```python
# simulation/world_state.py

WORLD_TOKEN_BUDGET = 2048  # жёсткий лимит

PRIORITY_WEIGHTS = {
    "current_location":  1.0,   # всегда включается
    "active_npcs":       0.9,   # NPC в текущей локации
    "player_inventory":  0.8,
    "recent_events":     0.7,   # последние 5 событий
    "other_locations":   0.2,   # сжатый summary
    "inactive_npcs":     0.1,   # только имя + статус
}

class WorldTokenBudget:
    def build_context_slice(self, world_state, location: str) -> dict:
        """
        Строит срез мира не превышающий WORLD_TOKEN_BUDGET токенов.
        Приоритет: текущая локация > активные NPC > инвентарь > история.
        """
        budget_remaining = WORLD_TOKEN_BUDGET
        result = {}

        # Всегда включаем текущую локацию
        loc_data   = world_state.get_location(location)
        loc_tokens = self._estimate_tokens(loc_data)
        if loc_tokens <= budget_remaining:
            result["location"] = loc_data
            budget_remaining  -= loc_tokens

        # Активные NPC — по приоритету
        for npc in world_state.get_npcs_in(location):
            npc_tokens = self._estimate_tokens(npc)
            if npc_tokens <= budget_remaining:
                result.setdefault("npcs", []).append(npc)
                budget_remaining -= npc_tokens
            else:
                # NPC не влезает целиком — добавляем только имя + статус
                result.setdefault("npcs", []).append({
                    "id": npc["id"], "name": npc["name"],
                    "status": npc.get("status", "здесь")
                })

        # Остальное — если бюджет позволяет
        if budget_remaining > 200:
            result["recent_events"] = world_state.get_recent_events(limit=5)

        return result

    def _estimate_tokens(self, obj) -> int:
        import json
        return len(json.dumps(obj, ensure_ascii=False)) // 4  # ~4 символа/токен
```

---

### Риск 4: Affordance/Perception — порядок важен

**Проблема:** если сначала perception, NPC видят физически невозможное событие.

**Решение — строгий порядок в пайплайне:**

```
1. AFFORDANCE CHECK (физически возможно?)
   physics_validator.validate()
   Если нет — SceneChange не создаётся. EventBus не получает событие.
   NPC никогда не видят невозможного.

2. PERCEPTION FILTER (кто это видит?)
   Только после affordance. SceneChange.visible_to и audible_to заполняются
   на основе позиций NPC, препятствий, освещения.

3. EVENT PUBLISH
   event_bus.publish(scene_change) — только после обоих фильтров.
```

**Правило:** `event_bus.publish()` вызывается ТОЛЬКО из `action/processor.py`,
никогда напрямую из агентов или sandbox_handler.

---

### Риск 5: Пустые systems/ засоряют импорты

**Решение:** каждый файл в `systems/` содержит заглушку с явным маркером.

```python
# systems/rumor_system.py
"""
RumorSystem — Phase 3E.

НЕ РЕАЛИЗОВАНО. Этот файл является заглушкой.
Не импортировать в production-код до Phase 3E.
"""

class RumorSystem:
    def __init__(self):
        raise NotImplementedError("RumorSystem реализуется в Phase 3E")
```

**Правило:** `systems/` не появляется ни в одном `import` до Phase 3E.
`game_loop.py` не знает о существовании `systems/`.

---

### Риск 6: Асинхронность Scheduler vs синхронный EventBus

**Проблема:** если world_tick() вызывает LLM каждый тик — мир "замерзает".

**Решение — два режима EventBus:**

```python
# events/event_bus.py

class EventBus:
    """
    Синхронный pub/sub для событий одного хода.
    Phase 3B.1: только синхронный режим.
    Phase 3B.4: добавляется async очередь для world_tick.
    """

    def __init__(self):
        self._handlers: dict[EventType, list] = {}
        self._queue:    list[SceneChange]     = []  # для world_tick

    def subscribe(self, event_type: EventType, handler):
        """Синхронная подписка. Обработчик вызывается немедленно."""
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: SceneChange) -> list:
        """
        Публикует событие. Вызывает всех подписчиков синхронно.
        Возвращает список результатов (для агрегации в game_loop).
        """
        results = []
        for handler in self._handlers.get(event.event_type, []):
            try:
                result = handler(event)
                if result:
                    results.append(result)
            except Exception as e:
                logger.error(f"[EVENT_BUS] Handler failed: {e}")
        return results

    def enqueue_for_tick(self, event: SceneChange):
        """
        Добавляет событие в очередь для обработки в world_tick().
        Не вызывает LLM — только Python-движки.
        Phase 3B.4: scheduler читает эту очередь каждые N минут.
        """
        self._queue.append(event)

    def flush_tick_queue(self) -> list[SceneChange]:
        """Возвращает накопленные события и очищает очередь."""
        events, self._queue = self._queue, []
        return events
```

**Правило:** `world_tick()` работает **без LLM**. Только Python-движки
обновляют WorldState. LLM видит результат уже при следующем ходе игрока.

```python
# core/scheduler.py

class WorldScheduler:
    async def world_tick(self, world_id: str, event_bus: EventBus):
        """
        Тик мира — только Python, никакого LLM.
        Запускается в фоне через asyncio, не блокирует ход игрока.
        """
        events = event_bus.flush_tick_queue()

        # Обновляем состояние мира (свечи, расписания NPC, погода)
        for event in events:
            await self._apply_world_event(event)

        # LifeEngine — NPC двигаются по расписанию
        await self.life_engine.tick(world_id)

        # WorldState сохраняется — DM увидит изменения на следующем ходу
        await self.world_state.save()
```

---

## 4. Официальный пайплайн одного хода (v8.1)

```
player text
    ↓
[input/]
action_classifier.py      ← keyword matching, 0 мс (ОСНОВНОЙ ПУТЬ)
    ↓ если UNKNOWN + confidence < 0.4
input/intent_parser.py    ← LLM fallback (РЕДКО, < 5% ходов)
    ↓
structured action (ActionType + parameters)
    ↓
[action/processor.py — Python только]
1. AFFORDANCE CHECK       ← физически возможно? (physics_validator)
   если нет → блокируем, SceneChange не создаётся, NPC ничего не видят
    ↓
2. PERCEPTION FILTER      ← кто видит это действие? (visible_to, audible_to)
    ↓
3. SceneChange объект     ← типизированный, со всеми полями
    ↓
[simulation/]
world_state.apply_change()← WorldState обновляется
    ↓
World Token Budget        ← сжатие неважного до 2048 токенов
    ↓
[events/]
event_bus.publish()       ← NPC, LifeEngine, Faction подписаны
    ↓
[engines/]
все Python-движки         ← combat, npc_ai, economy (параллельно)
    ↓
[core/]
world_tick() (async)      ← фоновый тик, не блокирует ответ
    ↓
[simulation/context_builder.py]
единый контекст           ← DM и NPC видят одно и то же
    ↓
[ai/ — LLM только здесь]
npc_agent.run()           ← реакции NPC
dm_agent.stream_narrate() ← нарратив (стриминг токенов)
    ↓
[output/]
narration.py + ui_adapter.py  ← SSE → frontend
```

---

## 5. Закрытые вопросы

### Q1: Как именно выглядит SceneChange?

```python
@dataclass
class SceneChange:
    event_type:  EventType           # обязательно
    actor_id:    str                 # player_name или npc_id
    target_id:   Optional[str]       # объект, NPC, локация
    location:    str                 # где произошло
    parameters:  Dict[str, Any]      # специфика действия
    timestamp:   float               # time.time()
    visible_to:  list[str]           # [] = все в локации
    audible_to:  list[str]           # [] = все в радиусе
    radius:      float               # метры для звука/запаха

# Пример — игрок ломает стул:
SceneChange(
    event_type  = EventType.OBJECT_DESTROYED,
    actor_id    = "Арагорн",
    target_id   = "chair_tavern_03",
    location    = "tavern_main",
    parameters  = {"object_name": "деревянный стул", "method": "силой"},
    visible_to  = [],       # видят все в tavern_main
    audible_to  = [],       # слышат все в радиусе
    radius      = 15.0,
)
```

### Q2: Где считать World Token Budget?

Два места, строго в таком порядке:

1. `world_state.apply_change()` → фоновое сжатие неактивных объектов.
2. `context_builder.build_context()` → финальная проверка перед LLM.

### Q3: Intent fallback через LLM — когда и как?

Условие запуска: `ActionType == UNKNOWN AND confidence < 0.4`.
`intent_parser.py` делает один LLM-вызов, возвращает `ActionType`.
Результат кэшируется на 60 сек по хэшу текста действия.

### Q4: Async world_tick() vs синхронный EventBus

EventBus синхронный — обработчики вызываются немедленно, без LLM.
`world_tick()` — `asyncio.create_task()`, не блокирует ответ игроку.
LLM никогда не вызывается внутри tick. Таймаут tick = 5 сек.

### Q5: Как тестировать Phase 3B.1 без DM и NPC AI?

```python
# tests/test_event_bus.py — без LLM, без FastAPI

def test_npc_reacts_to_sound():
    bus     = EventBus()
    results = []

    # Мок-обработчик вместо npc_agent
    def mock_npc_handler(event: SceneChange):
        if event.event_type == EventType.SOUND_EMITTED:
            results.append(f"NPC услышал звук от {event.actor_id}")

    bus.subscribe(EventType.SOUND_EMITTED, mock_npc_handler)

    event = SceneChange(
        event_type = EventType.SOUND_EMITTED,
        actor_id   = "player",
        location   = "tavern",
        parameters = {"intensity": "loud"},
        radius     = 10.0,
    )
    bus.publish(event)

    assert len(results) == 1
    assert "player" in results[0]
```

**Критерий готовности 3B.1:** все тесты проходят без поднятого FastAPI
и без загруженной LLM-модели.

---

## 6. Phase 3B — подфазы с критериями

### Phase 3B.1 — Event Foundation (3–4 дня)

**Файлы:**
- `events/event_types.py` — EventType enum + SceneChange dataclass
- `events/event_bus.py` — синхронный pub/sub
- Обновить `action/processor.py` — создаёт SceneChange после affordance

**Критерий готовности:**
```
sandbox делает SceneChange → event_bus.publish() → mock NPC handler получает событие
тест проходит без LLM, без FastAPI
```

---

### Phase 3B.2 — World State + Token Budget (4–5 дней)

**Файлы:**
- `simulation/world_state.py` — расширение SceneState (объекты, позиции NPC, время)
- `simulation/world_state.py` → `WorldTokenBudget` встроен внутрь
- Обновить `simulation/context_builder.py` — использует WorldState + WTB

**Критерий готовности:**
```
DM и NPC получают одинаковый контекст
Контекст никогда не превышает 2048 токенов
Сломанный объект виден в следующем ходе
```

---

### Phase 3B.3 — NPC Reactions (5–7 дней)

**Файлы:**
- `engines/npc_ai/` — perception_filter + affordance_resolver
- Обновить `npc_agent.py` — реагирует через event_bus, не напрямую
- Обновить `engines/npc_ai/psyche_engine.py` — decay стресса каждый ход

**Критерий готовности:**
```
Игрок ломает стул → event_bus → все NPC в комнате реагируют по-своему
NPC за стеной НЕ реагирует (perception filter работает)
Стресс NPC накапливается и убывает (decay)
```

---

### Phase 3B.4 — Scheduler + world_tick() (3–4 дня)

**Файлы:**
- `core/scheduler.py` — world_tick() в asyncio фоне
- Интеграция LifeEngine (существующий) с scheduler

**Критерий готовности:**
```
Без действия игрока прошло 10 мин игрового времени → свеча погасла
NPC ушёл на работу по расписанию
world_tick() не блокирует ответ DM (< 5 сек таймаут)
```

---

## 7. Итоговый план фаз

| Фаза | Срок | Статус | Примечание |
|------|------|--------|------------|
| 0–M + R + R2 + S.4.1 | — | ✅ ГОТОВО | Архитектура v8.1 |
| **3B.1** | 3–4 дня | ❌ | EventBus + SceneChange (сейчас) |
| **3B.2** | 4–5 дней | ❌ | WorldState + Token Budget |
| **3B.3** | 5–7 дней | ❌ | NPC Reactions + perception |
| **3B.4** | 3–4 дня | ❌ | Scheduler + world_tick() |
| **3C** | 1–2 нед | ❌ | Multi-Model (после 3B) |
| 3D | 2 нед | ❌ | LifeEngine полный |
| UI | 2–3 нед | ❌ | Параллельно с 3D |
| 3E | — | ❌ | systems/ (rumor, law, faction) |
| 3F+ | — | ❌ | После ≤10 сек на ход |

**До играбельной v1.0 (3B + 3C + UI):** ~6–8 недель
**До полной v1.0:** ~4–5 месяцев

---

## 8. Принципы (финальные, v8.1)

1. **Python считает. LLM рассказывает.** Вся логика мира — Python.
2. **WorldState — единственный источник истины.** Нет другой "памяти".
3. **Affordance перед Perception.** Невозможное не публикуется в EventBus.
4. **EventBus — одна копия** в `events/`. `core/` только импортирует.
5. **intent_parser.py — только fallback.** Никогда не в основном пути.
6. **systems/ — пустые до Phase 3E.** Заглушки с `NotImplementedError`.
7. **world_tick() без LLM.** Только Python. Таймаут 5 сек. Asyncio фон.
8. **World Token Budget обязателен.** Лимит 2048 токенов. Два места проверки.
9. **Каждый модуль тестируется без LLM.** Mock-обработчики, не боевые агенты.
10. **Один файл — одна ответственность.** Нет монолитов.

---

**Документ:** ENIGMA ROADMAP v8.1
**Обновлено:** 26 марта 2026
**Следующий шаг:** Phase 3B.1 — `events/event_types.py` и `events/event_bus.py`
**Первое действие:** показать текущий `simulation/scene_change.py` для аудита
типов перед написанием EventType enum.
