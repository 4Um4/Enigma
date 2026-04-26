Отлично. Против быстрых решений, за чистоту. Вот **полный план Б-правильный** — без временных мостов, с ломкой текущей архитектуры ради целевой.

---

## ПОЛНЫЙ ПЛАН: Правильный мост Frontend ↔ Backend

### Фаза 1: Разрушение старого (1–2 дня)

**Цель:** Убрать прямые импорты frontend → backend, которые делают невозможным чистый мост.

**Шаг 1.1. Убить прямые импорты frontend → app**

Файл: `backend/game_screen.py`

Найти и удалить:
- `from app.services.player_cognition import ...`
- `from app.core.constants import ...`
- `from app.services.scene_state_manager import ...`

Заменить на:
- `from api_client import ...` (единственный канал)

**Шаг 1.2. Убить npc_movement.py прямой доступ к location_graph**

Файл: `backend/npc_movement.py`

Найти:
- `from app.services.spatial.location_graph import ...`

Заменить:
- Движение NPC получает граф через `WorldSnapshotDTO` (позиции, пути, препятствия), не строит свой граф.

**Шаг 1.3. Убить intent_parser.py прямой доступ к scene_state**

Файл: `backend/intent_parser.py`

Найти:
- `from app.services.scene_state_manager import ...`

Заменить:
- Парсер работает только с текстом + `IntentDTO`. Имена NPC приходят из `WorldSnapshotDTO` через frontend.

---

### Фаза 2: Построение domain-слоя (2–3 дня)

**Цель:** Единый язык данных между frontend и backend.

**Шаг 2.1. Дополнить domain/ новыми DTO**

Файл: `backend/app/domain/snapshot.py`

```python
# backend/app/domain/snapshot.py
# ЗАЧЕМ: единый снимок мира для frontend. Неизменяем после создания.
# Зависимости: dataclasses, typing
# Основные сущности: WorldSnapshotDTO, NPCPositionDTO, VisibleEventDTO

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class NPCPositionDTO:
    """Позиция одного NPC в мире."""
    npc_id: str
    x: float
    y: float
    location_id: str
    facing: str  # 'north', 'south', 'east', 'west'
    action: str   # 'idle', 'walking', 'talking', 'working'


@dataclass(frozen=True)
class VisibleEventDTO:
    """Событие, которое видит frontend."""
    event_id: str
    timestamp: float
    text: str
    actor_id: str
    visibility: str  # 'public', 'private', 'whisper'


@dataclass(frozen=True)
class WorldSnapshotDTO:
    """Снимок мира на конец тика. Единственное, что видит frontend."""
    tick: int
    timestamp: float
    player_position: Tuple[float, float]
    npc_positions: List[NPCPositionDTO]
    visible_events: List[VisibleEventDTO]
    available_actions: List[str]
    location_id: str
    weather: str
    time_of_day: str
```

**Шаг 2.2. Дополнить domain/ IntentDTO**

Файл: `backend/app/domain/intent.py`

```python
# backend/app/domain/intent.py
# ЗАЧЕМ: действие игрока, уходящее в backend.
# Зависимости: dataclasses
# Основные сущности: IntentDTO

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentDTO:
    """Намерение игрока. Dumb parser выдаёт это."""
    action: str      # 'go', 'talk', 'attack', 'look'
    target: str      # 'npc_lucy', 'door_north', 'sword'
    parameters: dict  # {'direction': 'north'}, {'topic': 'basement'}
    text: str        # оригинальный текст игрока
```

---

### Фаза 3: WorldSnapshotBuilder (3–4 дня)

**Цель:** Редуктор: события тика → снимок мира.

**Шаг 3.1. Создать WorldSnapshotBuilder**

Файл: `backend/app/services/integration/world_snapshot_builder.py`

```
path: backend/app/services/integration/world_snapshot_builder.py
Назначение: Собирает WorldSnapshotDTO из финального состояния тика. Не лезет в random сервисы.
Зависимости: app.domain.snapshot, app.services.spatial.location_graph, app.services.scene.scene_state_manager
Основные сущности: WorldSnapshotBuilder
```

```python
# backend/app/services/integration/world_snapshot_builder.py
# ЗАЧЕМ: единственная точка сборки снимка мира. Reducer: events → state.
# Не читает напрямую из NPCState, MemoryManager, DecisionHub.
# Читает только финальное состояние после всех фаз.

from typing import List
from app.domain.snapshot import WorldSnapshotDTO, NPCPositionDTO, VisibleEventDTO
from app.services.spatial.location_graph import LocationGraph
from app.services.scene.scene_state_manager import SceneStateManager


class WorldSnapshotBuilder:
    """Собирает WorldSnapshotDTO из финального состояния тика."""
    
    def __init__(
        self,
        location_graph: LocationGraph,
        scene_state: SceneStateManager,
    ) -> None:
        self._location_graph = location_graph
        self._scene_state = scene_state
    
    def build(self, tick: int) -> WorldSnapshotDTO:
        """Собирает снимок. Читает только финальное состояние."""
        # ЗАЧЕМ: не лезем внутрь NPC, не вызываем логику.
        # Только агрегируем то, что уже вычислено.
        npc_positions = self._extract_npc_positions()
        visible_events = self._extract_visible_events()
        
        return WorldSnapshotDTO(
            tick=tick,
            timestamp=self._scene_state.current_time,
            player_position=self._scene_state.player_position,
            npc_positions=npc_positions,
            visible_events=visible_events,
            available_actions=self._scene_state.available_actions,
            location_id=self._scene_state.current_location,
            weather=self._scene_state.weather,
            time_of_day=self._scene_state.time_of_day,
        )
    
    def _extract_npc_positions(self) -> List[NPCPositionDTO]:
        """Вытаскивает позиции из scene_state."""
        result = []
        for npc_id, data in self._scene_state.npc_states.items():
            result.append(NPCPositionDTO(
                npc_id=npc_id,
                x=data.get('x', 0.0),
                y=data.get('y', 0.0),
                location_id=data.get('location_id', ''),
                facing=data.get('facing', 'south'),
                action=data.get('action', 'idle'),
            ))
        return result
    
    def _extract_visible_events(self) -> List[VisibleEventDTO]:
        """Вытаскивает события, видимые frontend."""
        result = []
        for event in self._scene_state.recent_events:
            if event.visibility in ('public', 'private'):
                result.append(VisibleEventDTO(
                    event_id=event.id,
                    timestamp=event.timestamp,
                    text=event.text,
                    actor_id=event.source,
                    visibility=event.visibility,
                ))
        return result
```

---

### Фаза 4: API Routes (2 дня)

**Цель:** Единый эндпоинт для frontend.

**Шаг 4.1. Обновить routes.py**

Файл: `backend/app/api/routes.py`

Добавить:
```python
# GET /world_state — новый эндпоинт
@router.get("/world_state")
async def get_world_state(
    campaign_id: str,
    builder: WorldSnapshotBuilder = Depends(get_snapshot_builder),
) -> WorldSnapshotDTO:
    """Возвращает текущий снимок мира."""
    return builder.build(tick=current_tick)
```

**Шаг 4.2. Обновить api_client.py**

Файл: `backend/api_client.py`

Добавить:
```python
def get_world_state(self, campaign_id: str) -> WorldSnapshotDTO:
    """Единственный способ frontend узнать состояние мира."""
    response = self._get(f"/world_state?campaign_id={campaign_id}")
    return WorldSnapshotDTO(**response.json())
```

---

### Фаза 5: Frontend рендер (3–4 дня)

**Цель:** Pygame рисует NPC на основе WorldSnapshotDTO, а не прямых импортов.

**Шаг 5.1. Обновить game_screen.py**

Файл: `backend/game_screen.py`

БЫЛО:
```python
from app.services.scene_state_manager import SceneStateManager
# ...
scene_state = SceneStateManager.load(campaign_id)
for npc_id, data in scene_state.npc_states.items():
    draw_npc(data['x'], data['y'])
```

СТАЛО:
```python
from api_client import APIClient
from domain.snapshot import WorldSnapshotDTO
# ...
client = APIClient()
snapshot: WorldSnapshotDTO = client.get_world_state(campaign_id)
for pos in snapshot.npc_positions:
    draw_npc(pos.x, pos.y, pos.action)  # 'walking', 'idle' — анимация
```

**Шаг 5.2. Обновить npc_movement.py**

Файл: `backend/npc_movement.py`

БЫЛО:
```python
from app.services.spatial.location_graph import LocationGraph
# строит свой граф
```

СТАЛО:
```python
from domain.snapshot import WorldSnapshotDTO
# получает snapshot, двигает NPC по позициям
# не строит граф, использует snapshot.npc_positions
```

---

### Фаза 6: Интеграция в Tick Orchestrator (3–4 дня)

**Цель:** WorldSnapshotBuilder — фаза 9, PersistencePort — фаза 10.

**Шаг 6.1. Создать TickOrchestrator скелет**

Файл: `backend/app/services/orchestration/tick_orchestrator.py`

```
path: backend/app/services/orchestration/tick_orchestrator.py
Назначение: Единый дирижёр тика. 11 фаз, строгий порядок, контракты.
Зависимости: все фазы как отдельные модули
Основные сущности: TickOrchestrator
```

```python
# backend/app/services/orchestration/tick_orchestrator.py
# ЗАЧЕМ: единая точка входа для одного игрового тика.
# Никаких "свободных вызовов" вне фаз.

from typing import Optional
from app.domain.intent import IntentDTO
from app.domain.snapshot import WorldSnapshotDTO
from app.domain.events import EventDTO
from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder
from app.services.events.event_bus import EventBus
from app.services.memory.memory_processor import MemoryProcessor
from app.services.npc.decision_hub import DecisionHub


class TickOrchestrator:
    """Дирижёр одного игрового тика. 11 фаз."""
    
    def __init__(
        self,
        event_bus: EventBus,
        memory_processor: MemoryProcessor,
        decision_hub: DecisionHub,
        snapshot_builder: WorldSnapshotBuilder,
        # TODO: остальные фазы при внедрении
    ) -> None:
        self._event_bus = event_bus
        self._memory_processor = memory_processor
        self._decision_hub = decision_hub
        self._snapshot_builder = snapshot_builder
    
    async def tick(self, intent: Optional[IntentDTO]) -> WorldSnapshotDTO:
        """Один полный тик. Строгий порядок фаз."""
        # ФАЗА 1: Input
        event = self._adapt_intent(intent) if intent else None
        
        # ФАЗА 2-3: EventQueue + Drain Primary
        if event:
            self._event_bus.publish(event)
        self._drain_primary()
        
        # ФАЗА 4-5: TopicExtractor + DecisionHub
        # TODO: при внедрении
        
        # ФАЗА 6-8: IntentEventAdapter + EventQueue + Drain Secondary
        # TODO: при внедрении
        
        # ФАЗА 8.5: Meta Phase
        # TODO: decay, resonance, contradiction
        
        # ФАЗА 9: WorldSnapshotBuilder
        snapshot = self._snapshot_builder.build(tick=self._current_tick)
        
        # ФАЗА 10: PersistencePort
        # TODO: atomic commit
        
        return snapshot
    
    def _adapt_intent(self, intent: IntentDTO) -> EventDTO:
        """IntentDTO → EventDTO. ФАЗА 1."""
        # TODO: полная реализация
        pass
    
    def _drain_primary(self) -> None:
        """ФАЗА 3. Обработка очереди событий."""
        # TODO: drain queue, MemoryProcessor.apply
        pass
```

---

### Фаза 7: Тестирование и ломка (2–3 дня)

**Цель:** Убедиться, что frontend видит NPC, и старая архитектура полностью отключена.

**Шаг 7.1. Тест: frontend видит позиции**
```bash
python -m backend.game_launcher
# Ввод: "look around"
# Ожидаем: NPC отрисованы на карте, их позиции из WorldSnapshotDTO
```

**Шаг 7.2. Тест: нет прямых импортов**
```bash
grep -r "from app.services" backend/game_screen.py backend/npc_movement.py backend/intent_parser.py
# Ожидаем: пустой вывод
```

**Шаг 7.3. Тест: WorldSnapshotBuilder не лезет внутрь**
```bash
grep -r "NPCState\|DecisionHub\|MemoryManager" backend/app/services/integration/
# Ожидаем: пустой вывод (только scene_state, location_graph)
```

---

## ИТОГО: 7 фаз, 16–22 дня

| Фаза | Что ломается | Что строится | Дней |
|------|-----------|-----------|------|
| 1 | Прямые импорты frontend → app | Чистый frontend | 1–2 |
| 2 | — | domain/snapshot.py, domain/intent.py | 2–3 |
| 3 | — | WorldSnapshotBuilder | 3–4 |
| 4 | — | API routes, api_client | 2 |
| 5 | game_screen.py, npc_movement.py | Рендер по WorldSnapshotDTO | 3–4 |
| 6 | game_loop.py (частично) | TickOrchestrator скелет | 3–4 |
| 7 | Старая архитектура полностью | Тесты, проверка чистоты | 2–3 |

**После этого:** Frontend видит мир. Можно переходить к цели №2 (NPC movement с реальными потребностями), потому что результат будет **виден**.

Но нет, постой... Вот как правильно:

 Принял. Пять проблем — пять исправлений. Переписываю план.

---

## ИСПРАВЛЕННЫЙ ПЛАН: Правильный мост Frontend ↔ Backend

### Проблема 1 — npc_movement

**Ты прав.** Если backend двигает NPC, `npc_movement.py` во frontend — мёртвый код. Не адаптируем, не оставляем. **Удаляем** из frontend, переносим логику в backend.

**Решение:**
- `backend/npc_movement.py` → **удалить**
- `backend/movement_system.py` → оставляем (физика игрока, коллизии), но он работает с `WorldSnapshotDTO`, не строит граф
- Новый: `backend/app/services/spatial/npc_pathfinder.py` — backend строит маршрут, frontend получает готовую позицию

---

### Проблема 2 — intent_parser

**Ты прав.** "Поговори с ним" без контекста — провал.

**Решение:**
```python
# intent_parser.py — pure function, но snapshot-aware
def parse(text: str, snapshot: WorldSnapshotDTO) -> IntentDTO:
    """
    Чистая функция. Нет side effects.
    Но читает snapshot: кто рядом, куда смотрит игрок.
    """
    nearby_npcs = [n for n in snapshot.npc_positions 
                   if distance(n, snapshot.player_position) < 3.0]
    # "он" → ближайший NPC, смотрящий на игрока
```

---

### Проблема 3 — WorldSnapshotBuilder и SceneStateManager

**Ты прав.** SceneStateManager — скрытый "бог". Но это не баг, это **явный агрегат**.

**Решение:** Не скрывать, а **документировать контракт**.

```
WorldSnapshotBuilder читает ТОЛЬКО SceneStateManager.
SceneStateManager — единственный агрегат NPCState + spatial + events.
Если SceneStateManager расходится с EventBus — баг в EventBus, не в Builder.
```

**Дополнительно:** Добавить `version` в `SceneStateManager` — инкрементируется после каждого apply. Builder проверяет версию, отклоняет stale state.

---

### Проблема 4 — tick synchronization

**Ты прав.** Без `tick_id` frontend гоняется за призраками.

**Решение:** Добавить в `WorldSnapshotDTO`:
```python
@dataclass(frozen=True)
class WorldSnapshotDTO:
    tick: int              # номер тика
    version: int           # инкремент SceneStateManager
    last_event_id: UUID    # последнее обработанное событие
    # ... остальные поля
```

Frontend запрашивает:
```
GET /world_state?after_tick=42&after_event=uuid
```
Если backend на том же тике — возвращает `304 Not Modified`. Frontend не рендерит заново.

---

### Проблема 5 — разрушение без изоляции

**Ты прав.** Ломать без адаптера = сломать игру и не собрать обратно.

**Решение:** Временный адаптер — **Adapter Pattern**, не костыль.

```python
# backend/app/services/integration/legacy_adapter.py
# ЗАЧЕМ: мост между старым game_loop и новым TickOrchestrator.
# Будет удалён после полной миграции.

class LegacyGameLoopAdapter:
    """
    Оборачивает старый GameLoop._run_pipeline()
    в интерфейс TickOrchestrator.
    """
    def __init__(self, old_game_loop: GameLoop):
        self._old = old_game_loop
    
    async def tick(self, intent: Optional[IntentDTO]) -> WorldSnapshotDTO:
        # Вызываем старый pipeline
        old_response = await self._old.run_turn(
            ChatTurnRequest(actions=intent.text if intent else "")
        )
        # Конвертируем старый ответ в новый DTO
        return self._adapt_response(old_response)
    
    def _adapt_response(self, old: ChatTurnResponse) -> WorldSnapshotDTO:
        # TODO: маппинг полей
        pass
```

**Правило удаления:** Adapter живёт, пока TickOrchestrator не покроет 100% фаз. Потом — удалить без сожалений.

---

## ИСПРАВЛЕННЫЙ ПОЛНЫЙ ПЛАН

### Фаза 1: Изоляция через Adapter (2–3 дня)

**Не ломаем старое. Строим мост.**

- Создать `LegacyGameLoopAdapter`
- `game_screen.py` переключается на Adapter, не на прямые импорты
- `npc_movement.py` — **удалить** (frontend больше не двигает NPC)
- `intent_parser.py` — получает `WorldSnapshotDTO` (через Adapter)

**Проверка:** Игра работает. Но теперь через Adapter.

---

### Фаза 2: Domain-слой (2 дня)

- `domain/snapshot.py` — `WorldSnapshotDTO` + `NPCPositionDTO` + `VisibleEventDTO` + `tick` + `version` + `last_event_id`
- `domain/intent.py` — `IntentDTO` (snapshot-aware)

---

### Фаза 3: WorldSnapshotBuilder (3 дня)

- Читает ТОЛЬКО `SceneStateManager`
- Проверяет `version` — отклоняет stale
- Не лезет в `NPCState`, `DecisionHub`, `MemoryManager`

---

### Фаза 4: API + Synchronization (2 дня)

- `GET /world_state?after_tick=&after_event=`
- `304 Not Modified` если нет изменений
- `api_client.py` — кэширует snapshot, не запрашивает лишнее

---

### Фаза 5: Frontend рендер (3 дня)

- `game_screen.py` — рисует из `WorldSnapshotDTO`
- `movement_system.py` — коллизии игрока по snapshot
- **Нет `npc_movement.py`**

---

### Фаза 6: TickOrchestrator скелет (3 дня)

- 11 фаз, но пока только фазы 1, 9, 10 работают
- Остальные — заглушки, вызывают Adapter

---

### Фаза 7: Постепенная миграция фаз (5–7 дней)

- Фаза 3: MemoryProcessor → заменяет прямой вызов из Adapter
- Фаза 4: TopicExtractor
- Фаза 5: DecisionHub
- Фаза 6: IntentEventAdapter
- Фаза 7–8: EventQueue + Drain
- Фаза 8.5: Meta Phase

**Каждая фаза — отдельный PR. Adapter уменьшается.**

---

### Фаза 8: Удаление Adapter (1 день)

- Adapter пустой — удалить
- Старый `GameLoop._run_pipeline()` — удалить
- `ChatTurnResponse` — удалить (заменён на `WorldSnapshotDTO`)

---

## ИТОГО: 8 фаз, 21–26 дней

| Фаза | Что ломается | Что строится | Дней |
|------|-----------|-----------|------|
| 1 | Прямые импорты | LegacyGameLoopAdapter | 2–3 |
| 2 | — | Domain + version/sync | 2 |
| 3 | — | WorldSnapshotBuilder | 3 |
| 4 | — | API routes + sync | 2 |
| 5 | npc_movement.py | Frontend render | 3 |
| 6 | — | TickOrchestrator скелет | 3 |
| 7 | Старый pipeline постепенно | Новые фазы по одной | 5–7 |
| 8 | Adapter, старый GameLoop | Чистая архитектура | 1 |

**Главное отличие:** Не ломаем всё сразу. Ломаем через Adapter, фаза за фазой, с проверкой на каждом шаге.

Это не простое нарушение — пакет `player_cognition` глубоко связан с `app/`:

| Модуль | Тянет из app/ |
|---|---|
| `perception_layer.py` | `app.core.constants`, `app.services.npc.perception_filter`, `app.services.spatial.spatial_runtime` |
| `recognition_layer.py` | `app.services.scene_state_manager._npc_id_to_display` |
| `spatial_layer.py` | `app.services.spatial.spatial_runtime` |

Нельзя "перенести файл" — он разорвёт внутренние связи backend'а.

**Что реально происходит:** `game_screen` вызывает `build_perceived_scene(scene_state, config)` — это тяжёлая трансформация: полный scene_state → отфильтрованный "воспринятый" вид игрока. Это работа backend, а не frontend. Сейчас frontend делает её напрямую (в одном процессе).

**Как план это решает:** `WorldSnapshotBuilder` (Фаза 3) будет собирать perceived scene на backend и отдавать через DTO. Тогда `game_screen` просто заберёт готовый результат через `api_client`. Но для этого нужен `WorldSnapshotBuilder`.

**Предлагаю:** оставить `player_cognition` как единственное разрешённое нарушение на время Фаз 2–4. Когда `WorldSnapshotBuilder` будет готов — заменим одной строкой. Это не костыль, это порядок из плана.

Итого по Фазе 1 (очистка frontend):

| Нарушение | Статус |
|---|---|
| `sprite_resolver.py` | ✅ Перемещён в `backend/` |
| `intent_parser.py` | ✅ `npc_name_resolver.py` создан |
| `constants.py` (IDLE_TICK) | ✅ Перемещены в `backend/constants.py` |
| `game_loop_bridge.py` | ✅ Уже адаптер, не трогаем |
| `npc_movement.py` | 📋 Будет удалён в Фазе 5 |
| `player_cognition/` | ⏳ Ждёт WorldSnapshotBuilder (Фаза 3) |
| `decision_hub_sandbox.py` | ℹ️ Инструмент разработчика, не runtime |
| `npc_sandbox.py` | ℹ️ Инструмент разработчика, не runtime |
| `run_terminal_dm.py` | 📋 Отдельно проверим позже |

Фазы 2-4 готовы. Подведу промежуточный итог:

| Фаза | Что сделано | Статус |
|---|---|---|
| 1 | sprite_resolver → backend/, npc_name_resolver.py, constants.py | ✅ |
| 2 | domain/snapshot.py, domain/intent.py | ✅ |
| 3 | WorldSnapshotBuilder | ✅ |
| 4 | world_routes.py, get_world_state() в api_client | ✅ |
| 5 | game_screen рендер по WorldSnapshotDTO | ⬜ |

Фаза 5 — самое чувствительное. `game_screen.py` сейчас:
1. Получает `scene_state` напрямую (через bridge/gateway)
2. Прогоняет через `build_perceived_scene` (player_cognition — нарушение)
3. Рендерит результат

Нельзя заменить за один шаг — сломаем рендер. Нужно проверить что `get_world_state` вообще работает, прежде чем переключать game_screen.

Builder работает. Реальные данные: location, weather, time — всё извлекается. NPC=0 потому что в сохранении их нет.

**Проблема:** Фаза 5 (переключить game_screen на WorldSnapshotDTO) бессмысленна без NPC в scene_state. Мы перепишем рендер, запустим — и не увидим разницы, потому что рендерить нечего.

**Предлагаю:** зафиксировать Фазы 1-4 как готовые. Переключиться на цель №2 — заставить NPC появляться в `scene_state["npc_positions"]` через need-driven movement + schedule. Тогда когда вернёмся к Фазе 5 — будет что рендерить и мы увидим результат.

Итого сегодня:

| Фаза | Статус |
|---|---|
| 1 | ✅ Frontend очищен от 3 нарушений |
| 2 | ✅ domain/snapshot.py, domain/intent.py |
| 3 | ✅ WorldSnapshotBuilder |
| 4 | ✅ world_routes.py + get_world_state() |
| 5 | ⏸️ После появления NPC в scene_state |

Переходим к цели №2 — NPC в scene_state?