# 📋 ТЗ: ENIGMA Space-Time Autonomy System (R7.D)

**Спринт:** R7.D (параллель R7.A, R7.B, R7.C)  
**Зависимости:** R4 (SpatialService), R3 (DecisionHub), CAUSAL_CONTRACT v2.0  
**Блокирует:** R8 (Scaling), R9 (Navigation Polish), R10+ (дальние регионы)  
**Приоритет:** 🔴 КРИТИЧЕСКИЙ (фундамент масштабирования)  
**Статус:** Исполняемое техническое задание

---

## 📌 ИСХОДНАЯ СИТУАЦИЯ

### Текущее состояние
```python
# Старая модель (ломается при масштабировании):

while game_running:
    tick += 1
    
    # Игрок делает шаг → мир реагирует
    player.step()
    
    # Весь мир считается полностью
    for npc in all_npcs:
        npc.think()        # LOD0-только
        npc.move()
        npc.perceive()
    
    # Если NPC далеко:
    # ничего не считается ❌
    # или ломается ❌
    
    render()
```

**Проблемы:**
1. ❌ Мир зависит от того, где стоит игрок (нарушение причинности)
2. ❌ Дальние NPC либо мёртвые, либо спамят в LOD
3. ❌ При смене локации нужна ретросимуляция (BUG-002)
4. ❌ Нет четких слоев детализации

### Желаемое состояние (из запроса)
```python
# Новая модель (масштабируемая):

world_clock.tick()  # Независимо от игрока

# Только рядом с игроком — полная симуляция
lod_manager.update_lod(player_position)

# Дальше — упрощение
# Очень далеко — статистика
# Всё считается, но по-разному

# При смене локации:
# сжимаем LOD0, разворачиваем новую LOD0
# ретросимуляция ❌, компрессия-декомпрессия ✅
```

---

## 🎯 ЦЕЛИ

1. **Независимость времени**: Мир идёт сам, игрок — зритель
2. **Масштабируемость**: От одной комнаты до континента
3. **Причинность**: Далекие события влияют через давление, не через ретро
4. **Управляемость**: LOD система снижает нагрузку
5. **Честность**: Игрок подчиняется тем же законам, что и NPC

---

## 📐 ФУНДАМЕНТАЛЬНАЯ ТЕОРИЯ

### Закон 1: Время Независимо

```python
# ЗАПРЕТ:
❌ while game_running:
       player.action() → tick += 1

# ЗАКОН:
✅ WorldClock:
       tick += 1  # всегда
       
   # Затем остальное (игрок, NPC, мир)
   player.perceive()  # игрок видит уже существующий мир
```

**Почему это критично:**

Если мир ждет игрока, получается:
```
Сценарий 1: Игрок стоит в комнате
├─ Тики не идут
├─ NPC не думают
├─ Огонь свечи не горит
├─ Голод не растет
├─ Раны не заживают
└─ ВСЕ ЗАКОНЫ ФИЗИКИ ЗАМОРОЖЕНЫ

Сценарий 2: Игрок делает шаг
├─ Мир внезапно делает скачок
├─ NPC приходят в себя
├─ 1 шаг = 100 тиков? Случайное число?
└─ Причинность РАЗЛОМАНА
```

**Правильно:**
```python
class WorldClock:
    tick: int = 0
    
    def advance(self) -> None:
        """Идет ВСЕГДА, независимо от игрока."""
        self.tick += 1
        
        # Периферийные системы считаются отдельно:
        # - время не зависит от них
        # - они зависят от времени
```

---

### Закон 2: Пространство Слоится

```
Мир существует одновременно на разных уровнях детализации.

Рядом с игроком = HIGH FIDELITY
Далеко от игрока = LOW FIDELITY
Очень далеко = ABSTRACT STATISTICS
```

**LOD слои:**

| Слой | Дистанция | Что моделируем | Частота | Пример |
|------|-----------|---|---|---|
| **LOD0** | Рядом (комната) | Полная физика, каждый NPC | Каждый тик | Игрок видит вора, вор думает полностью |
| **LOD1** | Соседняя область | Упрощённые движения, агрегированные решения | Каждые 5–10 тиков | Торговец идет в город, но его маршрут только progress_velocity |
| **LOD2** | Дальний регион | События, результаты, не процессы | Каждые 100+ тиков | На войне произошло сражение → государство ослаблено на 20% |
| **LOD3** | Абстрактный мир | Чистая статистика, NPC могут не быть объектами | День/неделя | Регион: население ±5%, урожай ±10% |

---

### Закон 3: Время Единое

```python
# ЗАПРЕТ (v3.0 ошибка):
❌ CausalTime
  BiologicalTime  
  NarrativeTime
  GameTime
  
# Это запутанность, не система.

# ЗАКОН:
✅ WorldClock:
    tick: int = 0
    
   # Всё остальное — производная:
   game_seconds = tick * TICK_DELTA
   game_hours = game_seconds / 3600
   game_days = game_hours / 24
   season = calculate_season(game_days)
```

Один часовой механизм.

Разные циферблаты (для удобства UI/персонажа).

---

### Закон 4: Игрок Двигает Прожектор, Не Время

```
┌─────────────────────────────┐
│       Мир существует        │  ← идет всегда
│         (WorldClock)        │     независимо
└─────────────────────────────┘

        Игрок движется
             ↓
    Луч прожектора (LOD0)
    перемещается в пространстве
             ↓
┌─────────────────────────────┐
│  ← Сжать LOD0   | Развернуть LOD2 → │
│     (уходим)    |  (приходим)       │
└─────────────────────────────┘
```

**Математически:**

```python
# Когда игрок движется:
player_position = (x, y)

# Вычисляем, что теперь в LOD0:
lod0_region = spatial_service.get_sphere(
    center=player_position,
    radius=LOD0_RADIUS  # например, 30 метров
)

# ВСЕ НПЦ в lod0_region остаются в LOD0
# ВСЕ НПЦ вне lod0_region → LOD1/LOD2

# Когда игрок пересекает границу в новую локацию:
old_location = current_location
new_location = spatial_service.get_location(player_position)

if old_location != new_location:
    compress_state(old_location)  # сжать
    expand_state(new_location)    # развернуть
    # тики идут дальше, ничего не восстанавливаем ❌
```

---

### Закон 5: Причинность Важнее Пространства

```python
# Пример: На другом конце континента началась война

# Игрок даже не видит, НО:

world_state.regions["kingdom_b"].pressure[
    "military_threat"
] += 0.3

# Это давление проходит через экономику:
world_state.regions["kingdom_b"].trade -= 15%

# Беженцы идут в соседние регионы (включая рядом с игроком):
world_state.regions["neighbor"].population += 20

# И вот:
merchant_near_player.mood = "worried"  # ← причина: война далеко!
merchant_near_player.trade_offers = ["sell_cheap"]

# Игрок видит: торговец грустный
# Игрок не видит: войну
# Но видит следствие

# Это правильно.
```

---

## 🏗️ АРХИТЕКТУРА

### Компонент 1: WorldClock

```python
# Файл: backend/app/services/time/world_clock.py

from dataclasses import dataclass
from typing import Callable

@dataclass
class WorldClock:
    """
    Глобальный часовой механизм ENIGMA.
    
    Идет ВСЕГДА, независимо от игрока, NPC, событий.
    Это источник истины для времени.
    
    Ничто в мире не может замедлить, ускорить или остановить WorldClock.
    """
    
    tick: int = 0
    TICK_DELTA: float = 0.016  # примерно 60 FPS, но это условно
    
    def advance(self) -> None:
        """
        Продвинуть время на один тик.
        
        Вызывается ОДИН раз за итерацию игрового цикла.
        До всех остальных систем.
        """
        self.tick += 1
    
    @property
    def game_seconds(self) -> float:
        """Прошло игровых секунд с начала игры."""
        return self.tick * self.TICK_DELTA
    
    @property
    def game_hours(self) -> float:
        """Прошло игровых часов."""
        return self.game_seconds / 3600
    
    @property
    def game_days(self) -> int:
        """День (в секундах в одном дне 86400)."""
        return int(self.game_seconds // 86400)
    
    @property
    def time_of_day(self) -> float:
        """Время суток (0.0 = полночь, 12.0 = полдень, 24.0 = полночь)."""
        seconds_in_day = self.game_seconds % 86400
        return (seconds_in_day / 86400) * 24
    
    @property
    def season(self) -> str:
        """Сезон года (Spring, Summer, Autumn, Winter)."""
        day_of_year = self.game_days % 365
        if day_of_year < 91:
            return "Spring"
        elif day_of_year < 182:
            return "Summer"
        elif day_of_year < 273:
            return "Autumn"
        else:
            return "Winter"
    
    def is_tick_multiple(self, frequency: int) -> bool:
        """
        Проверка: это кратный тик?
        
        Используется для LOD систем:
        if world_clock.is_tick_multiple(10):
            update_lod1()  # каждые 10 тиков
        """
        return self.tick % frequency == 0
```

**Использование:**

```python
# main.py или game_loop.py

world_clock = WorldClock()

while game_running:
    # ПЕРВОЕ: продвинуть время
    world_clock.advance()
    
    # ВТОРОЕ: обновить игрока
    player_input = get_input()
    player.act(player_input)
    
    # ТРЕТЬЕ: обновить LOD
    lod_manager.update(player.position, world_clock)
    
    # ЧЕТВЁРТОЕ: обновить NPC (по LOD)
    for npc in npcs_in_lod0:
        npc.tick(world_clock)
    for npc in npcs_in_lod1:
        if world_clock.is_tick_multiple(10):
            npc.tick_lod1(world_clock)
    for npc in npcs_in_lod2:
        if world_clock.is_tick_multiple(100):
            npc.tick_lod2(world_clock)
    
    # ПЯТОЕ: применить давление из LOD3
    if world_clock.is_tick_multiple(1000):
        apply_global_pressures()
    
    render()
```

---

### Компонент 2: LODManager

```python
# Файл: backend/app/services/spatial/lod_manager.py

from dataclasses import dataclass
from enum import Enum
from typing import Set, List, Tuple

class LODLevel(Enum):
    LOD0 = 0  # Полная симуляция
    LOD1 = 1  # Упрощённая
    LOD2 = 2  # Событийная
    LOD3 = 3  # Статистическая

@dataclass
class LODConfiguration:
    """Параметры LOD системы."""
    lod0_radius: float = 30.0       # метров
    lod1_radius: float = 100.0
    lod2_radius: float = 500.0
    lod3_radius: float = float('inf')
    
    lod1_frequency: int = 10        # каждые 10 тиков
    lod2_frequency: int = 100       # каждые 100 тиков
    lod3_frequency: int = 1000      # каждые 1000 тиков

@dataclass
class NPCLODState:
    """Состояние NPC в LOD системе."""
    npc_id: str
    current_lod: LODLevel
    previous_lod: LODLevel
    
    # Для LOD1+: сжатое состояние
    position: Tuple[float, float]
    progress_toward_goal: float = 0.0
    compressed_state: dict = None

class LODManager:
    """
    Управляет уровнем детализации для NPC и объектов.
    
    Отвечает за:
    - определение LOD уровня для каждого NPC
    - миграцию NPC между LOD уровнями
    - сжатие/развёртку состояния при переходе
    - синхронизацию частот обновления
    """
    
    def __init__(self, spatial_service, config: LODConfiguration = None):
        self.spatial = spatial_service
        self.config = config or LODConfiguration()
        
        # Текущее состояние
        self.npc_lod_states: Dict[str, NPCLODState] = {}
        self.current_player_position: Tuple[float, float] = (0, 0)
    
    def update(self, player_position: Tuple[float, float], world_clock) -> None:
        """
        Обновить LOD для всех NPC на основе позиции игрока.
        
        Вызывается каждый тик (но обновляет LOD только если игрок движется).
        """
        self.current_player_position = player_position
        
        # Переиндексировать всех NPC
        for npc_id, npc_state in self.get_all_npc_states().items():
            distance = self._distance(npc_state.location_id, player_position)
            new_lod = self._determine_lod(distance)
            
            # Если LOD изменился → миграция
            if npc_state.current_lod != new_lod:
                self._migrate_npc(npc_id, npc_state.current_lod, new_lod)
    
    def _determine_lod(self, distance: float) -> LODLevel:
        """На основе расстояния определить LOD."""
        if distance <= self.config.lod0_radius:
            return LODLevel.LOD0
        elif distance <= self.config.lod1_radius:
            return LODLevel.LOD1
        elif distance <= self.config.lod2_radius:
            return LODLevel.LOD2
        else:
            return LODLevel.LOD3
    
    def _migrate_npc(self, npc_id: str, from_lod: LODLevel, to_lod: LODLevel) -> None:
        """Перемигрировать NPC между LOD уровнями."""
        npc_state = self.npc_lod_states[npc_id]
        
        if to_lod > from_lod:
            # Движение вниз по детализации → СЖИМАЕМ
            self._compress_npc(npc_id, to_lod)
        else:
            # Движение вверх по детализации → РАЗВОРАЧИВАЕМ
            self._expand_npc(npc_id, from_lod)
        
        npc_state.previous_lod = from_lod
        npc_state.current_lod = to_lod
    
    def _compress_npc(self, npc_id: str, target_lod: LODLevel) -> None:
        """
        Сжать состояние NPC при движении вниз по детализации.
        
        Пример:
        - LOD0: полное состояние (position, emotions, goals, memory, ...)
        - LOD1: {position, progress_toward_goal, average_mood}
        - LOD2: {route_progress, activity_type, estimated_time_to_arrival}
        """
        npc_state_full = self.spatial.get_npc_state(npc_id)
        
        if target_lod == LODLevel.LOD1:
            compressed = {
                "position": npc_state_full.position,
                "progress": npc_state_full.movement_state.progress if hasattr(npc_state_full, 'movement_state') else 0.0,
                "mood": npc_state_full.emotions.base_affect if hasattr(npc_state_full, 'emotions') else 0.0,
                "goal_type": npc_state_full.current_goal.goal_type if hasattr(npc_state_full, 'current_goal') else "idle",
            }
        elif target_lod == LODLevel.LOD2:
            compressed = {
                "position": npc_state_full.position,
                "activity": self._classify_activity(npc_state_full),
                "route_eta": self._estimate_eta(npc_state_full),
            }
        elif target_lod == LODLevel.LOD3:
            # LOD3 даже может не иметь позиции как объекта
            compressed = {
                "settlement": npc_state_full.settlement_id,
                "role": npc_state_full.role,
            }
        
        self.npc_lod_states[npc_id].compressed_state = compressed
    
    def _expand_npc(self, npc_id: str, previous_lod: LODLevel) -> None:
        """
        Развернуть состояние NPC при движении вверх по детализации.
        
        Примечание: полное состояние может быть восстановлено из:
        1. сжатого состояния (если оно было сохранено)
        2. историческое воспроизведение из compressed_state
        3. random interpolation (если ничего не было сохранено)
        
        ЗАПРЕТ: не делать ретросимуляцию!
        """
        # Читаем сжатое состояние
        compressed = self.npc_lod_states[npc_id].compressed_state
        
        # Восстанавливаем в LOD0
        # Это может быть упрощённое восстановление, главное — причинно верное
        npc_state_expanded = self._reconstruct_from_compressed(npc_id, compressed)
        
        # Записываем обратно в основное состояние
        self.spatial.update_npc_state(npc_id, npc_state_expanded)
    
    def get_all_npc_states(self) -> Dict[str, NPCState]:
        """Получить состояния всех NPC."""
        return self.spatial.get_all_npc_states()
    
    def _distance(self, location_id: str, point: Tuple[float, float]) -> float:
        """Расстояние от точки до локации."""
        # TODO: интегрировать с SpatialService
        return 0.0  # заглушка
    
    def _classify_activity(self, npc_state) -> str:
        """Классифицировать текущую активность NPC."""
        # TODO: логика классификации
        return "idle"
    
    def _estimate_eta(self, npc_state) -> float:
        """Оценить ETA до пункта назначения."""
        # TODO: логика расчёта
        return 0.0
    
    def _reconstruct_from_compressed(self, npc_id: str, compressed: dict):
        """Восстановить полное состояние из сжатого."""
        # TODO: логика восстановления
        pass
```

---

### Компонент 3: Mutation Pipeline

Это **критический фикс** из новых документов. Сейчас в коде может быть:

```python
perception.on_event() → mutates emotion ❌
affect.on_event() → mutates decision ❌
decision.on_event() → mutates memory ❌
memory.on_event() → mutates perception ❌

Вероятность циклов: 100%
```

**Правильно:**

```python
Event
  → Signal (инертная копия события)
  → Evaluation (анализ без мутаций)
  → Intent (что хочется сделать)
  → MutationProposal (предложение на изменение)
  → Validation (MIK проверяет инварианты)
  → Apply (ЕДИНСТВЕННОЕ место, где меняется состояние)
```

```python
# Файл: backend/app/services/state/mutation_pipeline.py

from dataclasses import dataclass
from typing import Protocol, Any
from enum import Enum

class MutationPhase(Enum):
    SIGNAL = "signal"           # Инертная копия события
    EVALUATION = "evaluation"   # Анализ без побочных эффектов
    INTENT = "intent"          # Выражение намерения
    PROPOSAL = "proposal"      # Предложение на мутацию
    VALIDATION = "validation"  # Проверка инвариантов (MIK)
    APPLICATION = "application" # Применение (ЕДИНСТВЕННЫЙ момент мутации)

@dataclass
class MutationProposal:
    """Предложение на изменение состояния."""
    phase: MutationPhase
    target_entity_id: str
    changes: dict  # {field_name: new_value}
    source: str    # от кого это предложение ("WillpowerGate", "AffectiveIntegrator", и т.д.)
    causal_chain: list = None  # цепь причин для Causal Grounding

@dataclass
class MutationResult:
    """Результат применения мутации."""
    success: bool
    applied_changes: dict = None
    validation_errors: list = None
    mik_violations: list = None

class MIK:
    """
    Minimal Invariant Kernel.
    
    Проверяет инварианты перед Apply.
    
    Инварианты (примеры):
    - Эмоция не может быть > 1.0
    - Позиция должна быть в известной локации
    - Если NPC мёртв, он не может двигаться
    - Память не может содержать событий в будущем
    """
    
    def __init__(self):
        self.invariants: List[Callable] = [
            self._check_emotion_bounds,
            self._check_position_validity,
            self._check_death_constraint,
            self._check_temporal_order,
        ]
    
    def validate(self, proposal: MutationProposal, current_state: dict) -> Tuple[bool, List[str]]:
        """
        Проверить, что предложение не нарушает инварианты.
        
        Возвращает (is_valid, list_of_violations)
        """
        violations = []
        
        for invariant in self.invariants:
            result = invariant(proposal, current_state)
            if not result["valid"]:
                violations.extend(result["violations"])
        
        return len(violations) == 0, violations
    
    def _check_emotion_bounds(self, proposal: MutationProposal, state: dict) -> dict:
        """Эмоции в диапазоне [0, 1]."""
        if "emotions" in proposal.changes:
            emotions = proposal.changes["emotions"]
            for key, val in emotions.items():
                if not (0.0 <= val <= 1.0):
                    return {
                        "valid": False,
                        "violations": [f"Emotion {key}={val} outside bounds [0, 1]"]
                    }
        return {"valid": True, "violations": []}
    
    def _check_position_validity(self, proposal: MutationProposal, state: dict) -> dict:
        """Позиция должна быть в известной локации."""
        # TODO: интегрировать с SpatialService
        return {"valid": True, "violations": []}
    
    def _check_death_constraint(self, proposal: MutationProposal, state: dict) -> dict:
        """Если мёртв, не может двигаться."""
        # TODO: проверка
        return {"valid": True, "violations": []}
    
    def _check_temporal_order(self, proposal: MutationProposal, state: dict) -> dict:
        """Память не может содержать событий в будущем."""
        # TODO: проверка временного порядка
        return {"valid": True, "violations": []}

class StateApplicator:
    """
    ЕДИНСТВЕННЫЙ класс, который может менять состояние.
    
    Все остальные компоненты:
    - создают MutationProposal
    - StateApplicator их применяет (если MIK согласен)
    """
    
    def __init__(self, mik: MIK, spatial_service):
        self.mik = mik
        self.spatial = spatial_service
        self.mutation_log = []  # для Causal Grounding
    
    def apply(self, proposal: MutationProposal) -> MutationResult:
        """
        Применить предложение на мутацию.
        
        Процесс:
        1. Получить текущее состояние
        2. Проверить MIK
        3. Если OK → применить
        4. Залогировать для Causal Grounding
        """
        
        # Шаг 1: Получить текущее состояние
        current_state = self.spatial.get_entity_state(proposal.target_entity_id)
        
        # Шаг 2: Проверить MIK
        is_valid, violations = self.mik.validate(proposal, current_state)
        
        if not is_valid:
            return MutationResult(
                success=False,
                validation_errors=violations
            )
        
        # Шаг 3: Применить
        for field, new_value in proposal.changes.items():
            current_state[field] = new_value
        
        # Шаг 4: Залогировать
        self.mutation_log.append({
            "timestamp": datetime.now(),
            "proposal": proposal,
            "source": proposal.source,
            "causal_chain": proposal.causal_chain or [],
        })
        
        # Шаг 5: Сохранить
        self.spatial.update_entity_state(proposal.target_entity_id, current_state)
        
        return MutationResult(
            success=True,
            applied_changes=proposal.changes
        )

class CausalGrounding:
    """
    Отслеживание причин каждого состояния.
    
    Вместо:
    ```
    fear=0.8
    ```
    
    Имеем:
    ```
    fear=0.8
    because:
      event_12 (player_attacked) at tick 1500
      → threat_signal → affect_integration → emotion_update
    ```
    """
    
    def __init__(self, state_applicator: StateApplicator):
        self.applicator = state_applicator
    
    def get_causal_history(self, entity_id: str, field: str) -> List[dict]:
        """
        Получить полную цепь причин для значения поля.
        """
        history = []
        
        for log_entry in self.applicator.mutation_log:
            if log_entry["proposal"].target_entity_id == entity_id:
                if field in log_entry["proposal"].changes:
                    history.append({
                        "timestamp": log_entry["timestamp"],
                        "source": log_entry["source"],
                        "causal_chain": log_entry["causal_chain"],
                        "new_value": log_entry["proposal"].changes[field],
                    })
        
        return history
```

---

## 🔗 ИНТЕГРАЦИЯ С СУЩЕСТВУЮЩЕЙ АРХИТЕКТУРОЙ

### Где использовать WorldClock

В `main.py` / `game_loop.py`:

```python
# Файл: backend/app/main.py или backend/app/game_loop.py

from services.time.world_clock import WorldClock
from services.spatial.lod_manager import LODManager
from services.state.mutation_pipeline import StateApplicator, MIK, CausalGrounding

world_clock = WorldClock()
lod_manager = LODManager(spatial_service)
mik = MIK()
state_applicator = StateApplicator(mik, spatial_service)
causal_grounding = CausalGrounding(state_applicator)

while game_running:
    # ===== ФАЗА 0: Мировое время =====
    world_clock.advance()
    
    # ===== ФАЗА 1: Ввод игрока =====
    player_input = get_player_input()
    player_intent = semantic_compression(player_input)
    
    # ===== ФАЗА 2: Обновление LOD =====
    player_position = player.get_position()
    lod_manager.update(player_position, world_clock)
    
    # ===== ФАЗА 3: Возможное изменение локации =====
    if player.changed_location():
        old_location = player.previous_location
        new_location = player.current_location
        
        # Сжать старую локацию
        state_applicator.compress_location(old_location)
        
        # Развернуть новую локацию
        state_applicator.expand_location(new_location)
    
    # ===== ФАЗА 4: LOD0 — полная симуляция =====
    npcs_lod0 = lod_manager.get_npcs_in_lod(LODLevel.LOD0)
    for npc in npcs_lod0:
        # Весь каузальный цикл:
        # Intent → Pressure → Decision → Movement → Result
        npc.process_tick(
            world_clock=world_clock,
            state_applicator=state_applicator,
            causal_grounding=causal_grounding
        )
    
    # ===== ФАЗА 5: LOD1 — упрощённая (каждые 10 тиков) =====
    if world_clock.is_tick_multiple(10):
        npcs_lod1 = lod_manager.get_npcs_in_lod(LODLevel.LOD1)
        for npc in npcs_lod1:
            npc.process_tick_lod1(world_clock, state_applicator)
    
    # ===== ФАЗА 6: LOD2 — событийная (каждые 100 тиков) =====
    if world_clock.is_tick_multiple(100):
        npcs_lod2 = lod_manager.get_npcs_in_lod(LODLevel.LOD2)
        for npc in npcs_lod2:
            npc.process_tick_lod2(world_clock, state_applicator)
    
    # ===== ФАЗА 7: LOD3 — статистическая (каждые 1000 тиков) =====
    if world_clock.is_tick_multiple(1000):
        apply_global_pressures(world_clock, state_applicator)
    
    # ===== ФАЗА 8: Восприятие игрока =====
    player_perception = perceive_world(
        player_position=player.position,
        lod_manager=lod_manager,
        world_clock=world_clock
    )
    
    # ===== ФАЗА 9: Рендер =====
    render(player_perception, world_clock)

```

---

## 📊 ИНТЕГРАЦИЯ С CAUSAL_CONTRACT

### Новые запреты (добавить в CAUSAL_CONTRACT § 4)

```
4.5. Запреты на Время и Пространство

17. **Зависимость времени от игрока:** 
    ❌ tick += 1 внутри player.action()
    ✅ world_clock.advance() перед всем

18. **Ретросимуляция дальних регионов:**
    ❌ for i in range(missed_ticks): npc.tick()
    ✅ compress_state() / expand_state() при смене локации

19. **Прямое редактирование сжатого состояния:**
    ❌ lod_state.compressed["mood"] = 0.5
    ✅ только через StateApplicator

20. **Время как свойство сущности:**
    ❌ npc.birth_time = world_clock.tick (сохраняем абсолютный тик)
    ✅ только производные (age, time_alive, и т.д. как функции WorldClock)

21. **Множественные источники LOD уровня:**
    ❌ NPC сам определяет свой LOD
    ✅ только LODManager определяет LOD для всех
```

---

## 📋 ТЕСТЫ (Sandbox)

```python
# Файл: backend/tests/sandbox/test_space_time_autonomy.py

import pytest
from services.time.world_clock import WorldClock
from services.spatial.lod_manager import LODManager, LODLevel
from services.state.mutation_pipeline import StateApplicator, MIK

class TestWorldClockIndependence:
    """Тики независимы от движения игрока."""
    
    def test_world_clock_advances_without_player_input(self):
        """Время идет, даже если игрок стоит."""
        clock = WorldClock()
        initial_tick = clock.tick
        
        # Игрок ничего не делает
        # (не вызываем player.action())
        
        clock.advance()
        
        assert clock.tick == initial_tick + 1
    
    def test_no_retro_simulation_on_location_change(self):
        """При смене локации нет ретро-симуляции."""
        # Игрок уходит из локации A в локацию B
        # Локация A сжимается
        # Локация B разворачивается
        # Ничего не пересчитывается
        
        # TODO: реализовать тест
        pass
    
    def test_npc_think_when_player_moves(self):
        """NPC думают ВСЕГДА, не только когда игрок двигается."""
        # TODO: реализовать тест
        pass

class TestLODSystem:
    """LOD система правильно переключает уровни."""
    
    def test_npc_in_lod0_gets_full_simulation(self):
        """NPC в LOD0 получает полную симуляцию."""
        lod_manager = LODManager(spatial_service)
        npc = NPCFactory.create_npc()
        npc.position = (0, 0)  # рядом с игроком
        
        lod_manager.update((0, 0), world_clock)
        
        assert lod_manager.get_lod_for_npc(npc.id) == LODLevel.LOD0
    
    def test_npc_in_lod1_gets_simplified_simulation(self):
        """NPC в LOD1 обновляется каждые 10 тиков."""
        # TODO: реализовать тест
        pass
    
    def test_state_compression_preserves_causality(self):
        """Сжатие состояния не нарушает причинность."""
        # Сжимаем NPC
        # Компрессированное состояние содержит достаточно информации
        # чтобы восстановить поведение при развёртке
        # (но не через ретро-симуляцию)
        
        # TODO: реализовать тест
        pass

class TestMutationPipeline:
    """Mutation Pipeline соблюдает инварианты."""
    
    def test_only_state_applicator_mutates_state(self):
        """Только StateApplicator может менять состояние."""
        # Пытаемся менять состояние напрямую → ошибка
        # Пытаемся через StateApplicator → OK
        
        # TODO: реализовать тест
        pass
    
    def test_mik_validates_before_apply(self):
        """MIK проверяет инварианты перед Apply."""
        # Предложение: emotion=1.5 (нарушение MIK)
        # Результат: rejected
        
        # TODO: реализовать тест
        pass
    
    def test_causal_grounding_logs_all_mutations(self):
        """CausalGrounding логирует все мутации."""
        # Меняем fear несколько раз
        # Запрашиваем causal_history("npc_1", "fear")
        # Получаем полную цепь причин
        
        # TODO: реализовать тест
        pass

class TestCausalityNotBroken:
    """Причинность системы не нарушена."""
    
    def test_distant_events_affect_nearby_npc_through_pressure(self):
        """Далекие события влияют через давление, не напрямую."""
        # На другом конце мира началась война
        # Но игрок это не видит
        # Однако торговец рядом становится грустнее (через давление)
        
        # TODO: реализовать тест
        pass
    
    def test_no_closed_causal_loops(self):
        """Нет замкнутых циклов в причинности."""
        # Perception → Affect → Decision → Action → Perception (и снова)
        # Это замкнутый цикл (BAD)
        
        # Должно быть:
        # Event → Signal → Evaluation → Intent → Mutation → Apply
        # Apply → Perception (но не обратно в одном тике)
        
        # TODO: реализовать тест
        pass

class TestPlayerSymmetry:
    """Игрок подчиняется тем же законам, что и NPC."""
    
    def test_player_affected_by_world_pressures(self):
        """Игрок испытывает давление от мира."""
        # Война далеко → давление на игрока
        # Игрок не может игнорировать гравитацию
        
        # TODO: реализовать тест
        pass
    
    def test_player_respects_membrane_rules(self):
        """Игрок не может телепортироваться, как NPC."""
        # Игрок должен пройти через мембраны
        # Игрок не может увидеть сквозь стены
        
        # TODO: реализовать тест
        pass
```

---

## 🎯 ВЛИЯНИЕ ДЕЙСТВИЯ ИГРОКА НА МИР

### Локальное влияние (рядом)

```python
# Игрок атакует вора
# → Давление насилия на вора (ПРЯМО)
# → Давление угрозы на других NPC рядом (через perception)
# → Эмоции обновляются

player.attack(target_id="thief_shadow")
  → AttackIntent
    → IntentPressure(violence=0.9, self_risk=0.2)
    → WillpowerGate
    → ThiefState.psyche.identity_damage += 0.1
    → ThiefState.emotions.fear += 0.3
    → OtherNPC.emotions.threat_level += 0.1 (через perception)
```

### Дальнее влияние (через причинность)

```python
# Игрок убивает главу гильдии
# → Давление на экономику города (не прямое, через структуру)
# → Если город в LOD2, влияние идет статистически

player.kill(npc_id="guild_master")
  → CausalPressure("authority_collapse")
  → city_state.pressure["power_vacuum"] += 0.5
  → city_state.economy -= 10%
  → city_state.population_mood -= 0.2
  → (когда игрок приходит в город) NPC грустнее, товары дороже
```

### Статистическое влияние (LOD3)

```python
# Игрок торгует в LOD3 регионе
# → давление на регион через торговлю, не через NPC

player.trade(region_id="far_kingdom", goods=1000, price=0.5)
  → region_state.trade_activity += 0.1
  → region_state.wealth += 500
  → (со временем) регион развивается или рушится
```

---

## 📈 МАТРИЦА РИСКОВ И ПРЕИМУЩЕСТВ

| Аспект | Риск | Преимущество | Стоимость реализации |
|--------|------|--------------|---------------------|
| **Независимое время** | Сложность синхронизации UI | Честная симуляция, масштабируемость | Средняя |
| **LOD система** | Артефакты при переходе | Масштабируемость с миллионами NPC | Высокая |
| **Compression/Expansion** | Потеря деталей | Нет ретросимуляции, безопасно | Высокая |
| **Mutation Pipeline** | Производительность (все через StateApplicator) | Без циклических зависимостей, причинность честная | Средняя |
| **MIK + Causal Grounding** | Отладка сложнее | Инварианты гарантированы, полная история событий | Средняя |

---

## 📍 ROADMAP РЕАЛИЗАЦИИ

### Фаза 1 (R7.D.1): Базовое время

- [ ] Реализовать `WorldClock` (все код выше)
- [ ] Интегрировать в `main.py`
- [ ] Тесты: `test_world_clock_advances_without_player_input`
- [ ] Убедиться, что тики идут независимо от игрока

**Время:** 2–3 часа

### Фаза 2 (R7.D.2): LOD система

- [ ] Реализовать `LODManager`
- [ ] Написать `_determine_lod()`, `_migrate_npc()`
- [ ] Интегрировать с `SpatialService`
- [ ] Тесты: `test_npc_in_lod0_gets_full_simulation`

**Время:** 4–6 часов

### Фаза 3 (R7.D.3): Compression/Expansion

- [ ] Реализовать `_compress_npc()`, `_expand_npc()`
- [ ] Реализовать `_reconstruct_from_compressed()`
- [ ] Интегрировать со сменой локации
- [ ] Тесты: `test_state_compression_preserves_causality`

**Время:** 6–8 часов

### Фаза 4 (R7.D.4): Mutation Pipeline + MIK

- [ ] Реализовать `StateApplicator`, `MIK`
- [ ] Переделать все компоненты, чтобы они создавали `MutationProposal`, а не прямую мутацию
- [ ] Тесты: `test_only_state_applicator_mutates_state`, `test_mik_validates_before_apply`

**Время:** 10–12 часов

### Фаза 5 (R7.D.5): CausalGrounding

- [ ] Реализовать логирование в `StateApplicator`
- [ ] Реализовать `CausalGrounding.get_causal_history()`
- [ ] Интегрировать в UI (показать игроку причины эмоций NPC)
- [ ] Тесты: `test_causal_grounding_logs_all_mutations`

**Время:** 4–5 часов

**Итого:** ~25–35 часов работы

---

## 🎓 ФИЛОСОФСКАЯ ОСНОВА

### Отличие от TICK_CATCHUP

**Старая ошибка (BUG-002):**
```python
while game_running:
    player.move()  # игрок делает шаг
    
    # Мир "просыпается" и считает пропущенные тики
    for _ in range(missed_ticks):
        for npc in all_npcs:
            npc.think()  # ретросимуляция
```

**Новый способ (Space-Time Autonomy):**
```python
while game_running:
    world_clock.advance()  # мир идет ВСЕГДА
    
    player.move()          # игрок двигает луч прожектора
    
    # Состояние NPC сжимается/разворачивается, но не пересчитывается
```

### Отличие от "игрок движет время"

**Старая модель:**
```
Игрок думает → игрок делает → время идет → мир реагирует

Проблема: если игрок не делает, мир замёрзнет
```

**Новая модель:**
```
Время идет → игрок воспринимает → игрок действует → мир продолжает идти

Преимущество: мир честен, игрок это наблюдает, но не контролирует
```

---

**Это ТЗ готово к реализации. Начинаем с Фазы 1 (WorldClock).**