# ТЗ: СПРИНТ 31 — EMBODIED UI PERCEPTION & ELASTIC TIME ARCHITECTURE

**Проект:** ENIGMA Engine v0.5.5.0+  
**Спринт:** 31 (После R4 Spatial System, параллель с L1 Living Agent)  
**Архитектурные решения:** ADR-039 (Embodied Perception), ADR-058/059 (Dual-Time Ontology), ADR-060 (Movement Ontology)  
**Статус:** Исходная спецификация. Реализация в очереди.  
**Зависимости:** CAUSAL_CONTRACT v2.0, L1_LIVING_NPC (параллель), TraversalState API (постоянно)

---

## 0. ГЛАВНЫЙ ПРИНЦИП: ELASTIC TIME + SYMMETRIC PERCEPTION

### 0.1. Что меняется в спринте 31

**ДО:** Фронтенд предсказывает будущее (локальный pathfinding), время фиксировано.  
**ПОСЛЕ:** Фронтенд интерполирует настоящее, время растягивается/сжимается в зависимости от восприятия игрока.

**Единственный источник движения:** Бэкенд. Фронтенд только **рисует** то, что пришло через API.

### 0.2. Симметрия восприятия

Игрок и NPC получают одинаковую информацию через разные линзы:

```
Simulation Truth (CFRM, Deltas)
  ↓
L0 (Perception) — PhenomenologyProjectionService
  ↓
  ├─→ NPC: PerceptionEvent → PerceptualAttentionService → NPC decision
  └─→ Player: PerceptionEvent → PlayerPerceptionDTO → Frontend UI
```

**Закон:** Запрещено передать Игроку информацию, которую NPC не мог бы получить.

---

## 1. ЧАСТЬ A: EMBODIED UI PERCEPTION (Симметричная онтология восприятия)

### 1.1. Архитектурный контракт: Симметрия и Диафрагма

**Новый пайплайн (Единый для NPC и Игрока):**

```text
Simulation Truth (CFRM, State Deltas)
    ↓
PhenomenologyProjectionService (Генерация PerceptionEvent)
    ↓ (Семантические события: "замер", "крик", "запах_крови")
PerceptualAttentionService (Диафрагма: бюджет, кулдауны, затухание)
    ↓ (Фильтрация по приоритетам)
PlayerPerceptionDTO (Транспорт для "тупого" фронтенда)
    ↓
Frontend Renderer (Единственная интерпретация — пиксели)
```

### 1.2. ГЕНЕРАЦИЯ СМЫСЛОВ: PerceptionEvent

Бэкенд (через `PhenomenologyProjectionService`) переводит **каузальные возмущения** в **семантические события**.

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class PerceptionEvent:
    """Единица смысла, попадающая в поле внимания."""
    
    # Важность события (вычисляется из magnitude дельт)
    salience: float                    # 0.0-1.0
    
    # Категория события (диктует, на какой слой это попадает)
    category: Literal[
        "ATMOSPHERE",      # Фоновое давление ("напряжение в воздухе")
        "PERIPHERAL",      # Кинетика/движение ("кто-то шевельнулся")
        "CENTRAL",         # Фокус внимания ("звук, фраза, крик")
        "RUMOR",           # Слух, постфактум
        "RECONSTRUCTION"   # Что произошло без игрока (между сценами)
    ] = "ATMOSPHERE"
    
    # Наблюдение (внешнее, а не диагноз)
    # Вместо "боится" → "замер", "дрожит"
    # Вместо "злится" → "сжимает кулаки", "красное лицо"
    semantic_seed: str = ""
    
    # Где произошло
    source_cluster: str = ""
    
    # Когда это перестает быть актуальным
    expiration_tick: int = 0
```

**Запрет на телепатию:** Семантика формируется **только из внешних наблюдений** (`semantic_seed`). Вместо внутренних состояний.

### 1.3. СЛОИ ВНИМАНИЯ И МАППИНГ НА РЕНДЕР

#### Слой 0: Подсознательное восприятие (Телесный резонанс)
*Чувство, а не чтение. "Что-то не так".*

**Источник:** `AvatarStateDTO.motor_disruption` (физическое состояние аватара).

**Рендер (Дескринк — искажение восприятия без лага):**
- **ЗАПРЕТ:** Искусственная задержка ввода. Игра не должна "ломаться".
- **ВЫПОЛНЕНИЕ:** Вместо лага — инерция камеры, смазывание движения (motion trail), легкое отставание взгляда аватара, приглушение звуков, джиттер курсора.
- **Результат:** Управление остается честным, но мир начинает "плыть".

#### Слой 1: Периферическое восприятие (Наблюдение, не диагноз)
*Мимолетные сигналы. Никакой телепатии.*

**Источник:** `PerceptionEvent(category=PERIPHERAL)`.

**Рендер:** Изменение позы/поведения спрайта NPC + наблюдательный текст при наведении (hover).

**Правило:** Только внешние наблюдения:
- ❌ "Оцепенел от страха" → ✅ "Замер на месте"
- ❌ "Избегает вас" → ✅ "Отвел взгляд"
- ❌ "Торопливо уходит" → ✅ "Быстро шагает к выходу"
- ❌ "Нервничает" → ✅ "Нервно переминается"

#### Слой 2: Атмосфера места (Фоновая температура)
*Тихий индикатор давления.*

**Источник:** `PerceptionEvent(category=ATMOSPHERE)`.

**Рендер:** Маленький блок справа сверху с текстом.
- `"tension"` → *"Напряжение висит в воздухе"*
- `"calm"` → *"Обстановка спокойная"*
- `"unease"` → *"Что-то не нравится"*

#### Слой 3: Феноменологические сигналы (Центральное внимание)
*Слово, которое пробивает фокус.*

**Источник:** `PerceptionEvent(category=CENTRAL)`.

**Рендер:** Текст по центру экрана (fade-in/out).
- `"silence"` → *"Разговоры резко смолкли."*
- `"stare"` → *"Несколько взглядов устремились на вас."*
- `"crash"` → *"Раздался грохот!"*

#### Слой 4: Эхо мира (Добровольное внимание)
*Искаженные слухи.*

**Источник:** `PerceptionEvent(category=RUMOR)`.

**Рендер:** Иконка 🕯️ со счетчиком. Читается по клику (текст из `semantic_seed` + стадия мутации).

#### Слой 5: Каузальная реконструкция (Постфактум)
*Отчет о произошедшем без игрока.*

**Источник:** `PerceptionEvent(category=RECONSTRUCTION)`.

**Рендер:** Список при смене локации (события отфильтрованы по `expiration_tick`).

### 1.4. МЕХАНИКА ВНИМАНИЯ: Бюджет и Инерция

#### Конкуренция внимания (Attention Budget)

Игрок **не может воспринять всё одновременно**. Если происходит 5 событий, низкоприоритетные гасятся.

```python
@dataclass
class PerceptualAttentionService:
    """Диафрагма внимания игрока."""
    budget: float = 1.0  # Максимальная "пропускная способность"
    
    # Стоимость по категориям
    COST = {
        "CENTRAL": 0.6,
        "ATMOSPHERE": 0.2,
        "PERIPHERAL": 0.2,
        "RECONSTRUCTION": 0.8,  # Не конкурирует в моменте
    }
    
    def filter_perceptions(self, events: List[PerceptionEvent]) -> List[ActivePerception]:
        """
        Фильтрует события через диафрагму.
        Высокоприоритетные пробиваются, низкие глушатся.
        """
        # Сортировка по salience
        sorted_events = sorted(events, key=lambda e: e.salience, reverse=True)
        
        active = []
        remaining_budget = self.budget
        
        for event in sorted_events:
            cost = self.COST[event.category]
            if remaining_budget >= cost:
                # Пробил диафрагму
                active.append(ActivePerception(text=event.semantic_seed, intensity=1.0))
                remaining_budget -= cost
        
        return active
```

**Пример работы:**
1. Драка (`CENTRAL`, salience=0.8, cost=0.6). Бюджет: 1.0 - 0.6 = 0.4.
2. Крик (`CENTRAL`, salience=0.7, cost=0.6). Не проходит! Бюджет исчерпан.
3. Служанка замерла (`PERIPHERAL`, salience=0.5, cost=0.2). Проходит! Бюджет: 0.4 - 0.2 = 0.2.
4. Другой NPC отвернулся (`PERIPHERAL`, salience=0.3, cost=0.2). Не проходит, слишком мелко.

#### Временная инерция (Active Perception)

Восприятие не исчезает за один кадр. Оно **затухает**.

```python
@dataclass
class ActivePerception:
    """Активное восприятие игрока с инерцией затухания."""
    text: str
    intensity: float           # 1.0 = только что замечено, 0.0 = забыто
    decay_rate: float = -0.05  # За каждый тик
    created_tick: int = 0
    
    def tick(self) -> None:
        """Уменьшить интенсивность."""
        self.intensity += self.decay_rate
        if self.intensity < 0.1:
            self.is_active = False  # Стирается из памяти
```

Если `PerceptionEvent` пробил бюджет, он становится `ActivePerception`. На следующий тик его `intensity` падает. Фронтенд рендерит текст с прозрачностью, пропорциональной `intensity`.

### 1.5. ЕДИНЫЙ КОНТРАКТ: PlayerPerceptionDTO

Фронтенд получает этот объект и **ничего не вычисляет**.

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class AvatarDesyncDTO:
    """Визуальное искажение без поломки управления."""
    camera_inertia: float = 0.0     # Смещение/запаздывание камеры (pixels)
    motion_trail: float = 0.0        # Шлейф при движении (alpha multiplier)
    auditory_muffle: float = 0.0     # Глушение звуков (volume ratio)
    cursor_jitter: float = 0.0       # Джиттер курсора (pixels)

@dataclass
class PeripheralCueDTO:
    """Сигнал от периферии (изменение позы NPC)."""
    npc_id: str
    cue_type: str  # "FREEZE", "HURRY", "AVOID_GAZE", "PROTECTIVE"
    hover_text: str  # СТРОГО наблюдение: "Замер", "Отвел взгляд"

@dataclass
class ReconstructionEventDTO:
    """Событие, произошедшее без игрока (между сценами)."""
    semantic_seed: str
    source_cluster: str
    timestamp_game_seconds: float

@dataclass
class PlayerPerceptionDTO:
    """
    Линза восприятия игрока. Тупой рендер.
    Все вычисления произошли на бэкенде. Фронтенд только рисует.
    """
    
    # Слой 0: Подсознание (физическое состояние аватара)
    avatar_desync: Optional[AvatarDesyncDTO] = None
    
    # Слои 1-3: Активные восприятия (отсортированы по приоритету)
    active_perceptions: List[ActivePerception] = field(default_factory=list)
    
    # Слой 1: Периферия (кто сейчас выделяется в толпе)
    peripheral_cues: List[PeripheralCueDTO] = field(default_factory=list)
    
    # Слой 4: Эхо (слухи)
    echo_count: int = 0
    
    # Слой 5: Реконструкция (что произошло без игрока)
    reconstruction_events: List[ReconstructionEventDTO] = field(default_factory=list)
```

---

## 2. ЧАСТЬ B: ELASTIC TIME ARCHITECTURE (Двойная метрика времени)

### 2.1. Философия: Симуляция дискретна, восприятие непрерывно

**КЛЮЧЕВАЯ ИДЕЯ (ADR-058/059):**

Каузальный тик (`scene_state["tick"]`, +1 за шаг) **никогда не замедляется**. Причинность неделима.

Что замедляется/ускоряется:
- **Календарное время** (`game_time_seconds`) — скорость хода дня/ночи
- **Восприятие времени** (фронтенд) — как быстро игрок видит изменения

Структура:
```
Tick (дискретный): 1, 2, 3, 4, 5, ...
Calendar Time (непрерывный): 0.0s, 0.5s, 1.2s, 2.1s, 3.8s, ...
```

### 2.2. Механика Elastic Time (slow-mo при вводе)

**Цель:** Мир живёт постоянно (тики идут всегда), но когда игрок начинает вводить текст, скорость течения календарного времени снижается, давая время на реакцию.

**Как это работает:**

1. **Фронтенд постоянно отправляет `idle_tick` с параметром `time_scale`:**
   ```python
   # Когда игрок не печатает
   time_scale = 1.0  # Нормальный ход времени
   
   # Когда игрок начал печатать (фокус на TextInput)
   time_scale = 0.2  # Slow-mo: в 5 раз медленнее
   
   # После отправки сообщения (загрузка ответа)
   time_scale = 5.0  # Fast-forward: в 5 раз быстрее
   ```

2. **Бэкенд применяет `time_scale` к календарному времени:**
   ```python
   # В TickOrchestrator._advance_idle_time()
   GAME_TICK_INTERVAL = 2  # seconds per tick (baseline)
   new_game_time = Calendar.advance(
       current_seconds, 
       int(GAME_TICK_INTERVAL * time_scale)  # ELASTIC!
   )
   ```

3. **Результат:**
   - Каузальный тик **всегда** инкрементируется (+1)
   - NPC **всегда** думают и действуют
   - Физика **всегда** работает
   - Но календарное время растягивается/сжимается
   - Фронтенд плавно интерполирует движение (lerp основан на `duration_ticks`, не на секундах)

### 2.3. Интеграция в архитектуру

#### API Слой (`backend/app/api/routes.py`)

```python
@router.post("/api/game/idle_tick")
async def idle_tick(request: IdleTickRequest):
    """
    request.time_scale: float = 1.0  # Опциональный параметр
    """
    # Передать в GameLoop
    await game_loop.idle_tick(time_scale=request.time_scale)
```

#### GameLoop (`backend/app/services/game_loop/__init__.py`)

```python
async def idle_tick(self, time_scale: float = 1.0) -> None:
    """
    Args:
        time_scale: Множитель скорости календарного времени.
                    0.2 = slow-mo, 1.0 = нормально, 5.0 = fast-forward
    """
    await self.tick_orchestrator.advance_idle_time(time_scale=time_scale)
```

#### TickOrchestrator (`backend/app/services/tick_orchestrator.py`)

```python
def _advance_idle_time(self, time_scale: float = 1.0) -> None:
    """Продвинуть календарное время и каузальный тик на время простоя."""
    
    # КАУЗАЛЬНЫЙ ТИК ВСЕГДА +1
    self.world_state.scene_state["tick"] += 1
    
    # КАЛЕНДАРНОЕ ВРЕМЯ ЗАВИСИТ ОТ time_scale
    elapsed_seconds = self.GAME_TICK_INTERVAL_SECONDS * time_scale
    self.calendar.advance(elapsed_seconds)
```

### 2.4. Фронтенд: синхронизация локального времени с авторитетным

**Проблема:** Фронтенд локально считает время прохода (для плавной анимации), но при получении `idle_tick` из бэкенда время может рассинхронизироваться.

**Решение:** Плавная синхронизация (lerp) локального времени с авторитетным:

```python
# frontend/game_screen.py
class GameScreen:
    def on_idle_tick_response(self, snapshot: WorldSnapshotDTO):
        """
        snapshot.game_time_seconds — авторитетное время от бэкенда
        """
        # Рассчитать дельту
        delta = snapshot.game_time_seconds - self.local_game_time
        
        # Если рассинхронизация > 0.5 сек, синхронизировать плавно
        if abs(delta) > 0.5:
            # Lerp локального времени к авторитетному за 0.3 сек
            self.local_time_lerp_target = snapshot.game_time_seconds
            self.local_time_lerp_remaining = 0.3
        else:
            # Маленькое отклонение — просто скорректировать
            self.local_game_time = snapshot.game_time_seconds
    
    def update_frame(self, dt: float):
        # Обновить локальное время
        if self.local_time_lerp_remaining > 0:
            # Lerp в процессе
            alpha = 1.0 - (self.local_time_lerp_remaining / 0.3)
            self.local_game_time = lerp(
                self.local_game_time, 
                self.local_time_lerp_target, 
                alpha
            )
            self.local_time_lerp_remaining -= dt
        else:
            # Обычное продвижение
            self.local_game_time += dt
```

---

## 3. ЧАСТЬ C: ACTIVITY-BASED ANIMATION STATES

### 3.1. Что меняется

В `NPCPositionDTO` приходит поле `action` (idle, walking, talking, working).

```python
@dataclass
class NPCPositionDTO:
    npc_id: str
    x: float
    y: float
    cluster_id: str
    action: str = "idle"  # ← НОВОЕ
    action_target: str = ""  # Если action="talking", то с кем
```

### 3.2. Рендерер использует это для переключения стейт-машин анимации

**Было:**
```python
# Рандомные визуальные эффекты, неконтролируемые
if random() > 0.8:
    play_animation("idle_yawn")
```

**Стало:**
```python
# Авторитетные команды от бэкенда
animation_state = {
    "idle": ("idle_default", 1.0),
    "walking": ("walk", speed_multiplier),
    "talking": ("talk", 1.0),
    "working": ("work_pose", 1.0),  # Зависит от профессии
    "sleeping": ("sleep", 0.5),
}

sprite.set_animation(animation_state[npc_dto.action])
```

**Преимущества:**
- NPC больше не рандомно двигаются
- Действия сопряжены с каузальными решениями (`DecisionHub`)
- UI может показать, чем занят NPC

---

## 4. ТЕКУЩЕЕ СОСТОЯНИЕ И ИНСТРУКЦИЯ ДЛЯ ПРЕЕМНИКА

### 4.1. Что уже работает (Пост-спринт 30)

- ✅ Интерполяция `TraversalState` (NPC плавно движутся)
- ✅ Визуализация `initiative_suppression` (паралич воли)
- ✅ Deterministic Client (нет локального pathfinding)
- ✅ CAUSAL_CONTRACT соблюдается

### 4.2. Что нужно реализовать в спринте 31

1. **Player Movement Intent (WASD)** — переводить WASD в Intent, отправлять на бэкенд
2. **Elastic Time Synchronization** — плавная синхронизация локального времени
3. **Activity-based Animation** — использовать `action` поле для смены анимаций
4. **Embodied UI Perception** — внедрить `PlayerPerceptionDTO` и все 5 слоев восприятия

### 4.3. КРИТИЧЕСКАЯ ИНСТРУКЦИЯ: Синхронизация реальности

**ПЕРЕД тем как предложить любое изменение кода:**

```powershell
# 1. Проверить актуальные поля PerceptualKernel и инициатива
Get-Content "backend/app/models/cfrm.py" | Select-Object -Index (40..80)

# 2. Проверить контракт NPCPositionDTO
Select-String -Path "backend/app/domain/snapshot.py" -Pattern "class NPCPositionDTO|traversal_|action" | Select-Object LineNumber, Line

# 3. Проверить реализацию интерполяции в рендерере
Select-String -Path "frontend/scene_renderer.py" -Pattern "progress|waypoints|lerp" | Select-Object LineNumber, Line

# 4. Найти, где сейчас WASD обрабатывается
Select-String -Path "frontend/game_screen.py" -Pattern "K_w|K_a|K_s|K_d|held_keys" | Select-Object LineNumber, Line

# 5. Проверить, как бэкенд принимает действия
Select-String -Path "backend/app/services/game_loop/phase_1_input.py" -Pattern "IntentDTO|semantic_action" | Select-Object LineNumber, Line
```

**Без выполнения этих команд ты вслепую ломаешь работающую Dual-Time Ontology.**

---

## 5. КРИТЕРИИ УСПЕХА

### Embodied UI
1. ✅ NPC плавно перемещаются между точками в соответствии с `TraversalState`
2. ✅ Состояние паралича воли (`initiative_suppression`) визуально отличимо
3. ✅ Наблюдательные тексты не содержат телепатии ("замер" вместо "боится")
4. ✅ Бюджет внимания работает: драка гасит кружку, не наоборот
5. ✅ Восприятие затухает плавно, не мигает

### Elastic Time
1. ✅ При печати игрока время замедляется (slow-mo)
2. ✅ Каузальный тик **всегда** инкрементируется (не замедляется вместе с календарем)
3. ✅ NPC продолжают думать и действовать даже при slow-mo
4. ✅ Синхронизация локального времени не вызывает скачков
5. ✅ Фронтенд не падает при `idle_tick` с разными `time_scale`

### Player Movement
1. ✅ WASD генерирует Intent и отправляет на бэкенд
2. ✅ Фронтенд оптимистично рендерит ходьбу, пока ждет подтверждения
3. ✅ Бэкенд подтверждает позицию через `WorldSnapshotDTO`
4. ✅ Нет локального pathfinding, все маршруты считает бэкенд

### Activity-based Animation
1. ✅ `action` поле в `NPCPositionDTO` используется для переключения анимаций
2. ✅ Действия синхронизированы с `DecisionHub` (NPC не двигается, если дум)
3. ✅ Нет рандомных анимаций без авторитета бэкенда

---

## 6. ИЗВЕСТНЫЕ АРХИТЕКТУРНЫЕ РИСКИ

1. **`TICK_CATCHUP` убивает `TraversalState`:** При загрузке сейва требуется запрет ретро-симуляции (ADR-047).
2. **NPC идут в `entrance`:** Ожидается фикс маршрутизации на бэкенде, фронтенд должен отрисовывать корректно.
3. **Кэш-фантомы:** При изменении DTO очищать `__pycache__` перед запуском.

---

**Напутствие:**
Бэкенд научился компрессировать время. Твой долг — разархивировать его для глаз игрока, не придумывая за него. Симуляция честна, презентация прекрасна.
