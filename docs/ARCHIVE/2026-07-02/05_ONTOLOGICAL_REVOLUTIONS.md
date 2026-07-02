# ОНТОЛОГИЧЕСКИЕ ПРОБЛЕМЫ: 5 Фундаментальных переворотов

**Критик:** Kami (META CODE ARCHITECT)  
**Дата анализа:** 2026-05-21  
**Тип проблем:** Не симптомы, а причины классов ошибок  
**Уровень:** Переворот фундаментальной архитектуры ENIGMA

---

## МЕТААНАЛИЗ: От Симптомов к Причинам

### Было (Симптомы):
```
"BUG-001: DirectiveSubscriber не получает state"
→ Фикс: добавить инъекцию состояния

"BUG-002: TICK_CATCHUP ломает TraversalState"
→ Фикс: убить ретро-симуляцию

"BUG-007: LOD0/LOD1 конфликтуют"
→ Фикс: добавить приоритизацию
```

### Стало (Причины):
```
"Нет явного разделения временных горизонтов"
→ Фикс: TemporalDomain (переворот архитектуры)

"Архетипы независимы вместо геометрически противоположных"
→ Фикс: PhaseSpace (не Dict)

"Отсутствует narrative time"
→ Фикс: TimeDomain с 3 компонентами

"Неконтролируемый рост причинных связей"
→ Фикс: CouplingBudget (метрика связанности)

"Отсутствуют обратные связи (ожидание → восприятие)"
→ Фикс: ExpectationLoop (теория поведения)
```

**Переход:** "Фиксируем баги" → "Контролируем пространство возможных багов" → **"Переворачиваем онтологию"**

---

## ПРОБЛЕМА #1: ТЫ ГРУППИРУЕШЬ ПО СУЩНОСТЯМ, А НЕ ПО ВРЕМЕНИ

### Текущая структура (неправильная):

```python
class LivingNPC:
    traits: TraitLayer        # "это старые вещи"
    motivations: MotivLayer   # "это текущие потребности"
    physiology: PhysioLayer   # "это тело"
    phase: PhaseLayer         # "это текущее состояние"
```

**Думание:** "Группируем по типу сущности"

### Реальная структура (правильная):

```
Голод       → SITUATIONAL (часы)
Страх       → REACTIVE (тики/секунды)
Убеждение   → ADAPTIVE (дни/недели)
Личность    → STRUCTURAL (месяцы/годы)
Травма      → STRUCTURAL (годы/жизнь)
Любовь      → ADAPTIVE (дни/месяцы)
Политика    → STRUCTURAL (месяцы/годы)
Привычка    → ADAPTIVE (дни)
Вера        → STRUCTURAL (годы)
```

**Думание:** "Время порождает слой, не наоборот"

### Правильная онтология:

```python
from enum import Enum

class TemporalDomain(Enum):
    """Время порождает слой, не наоборот"""
    
    REACTIVE = 0.01      # Тики (10-100ms)
    SITUATIONAL = 1.0    # Секунды/минуты (1m-1h)
    ADAPTIVE = 86400     # Дни (1d-1w)
    STRUCTURAL = 2592000 # Месяцы/годы (1m-10y)

# Теперь новые сущности добавляются просто:

class NPCMind:
    """Ум агента организован по временным доменам, не по типам"""
    
    reactive_states: Dict[str, float]        # fear, anger, attention
    situational_states: Dict[str, float]     # hunger, pain, curiosity
    adaptive_states: Dict[str, float]        # habit, skill, trust
    structural_states: Dict[str, float]      # personality, trauma, belief
    
    def apply_temporal_delta(self, domain: TemporalDomain, key: str, delta: float):
        """
        Применить изменение в правильный слой по времени.
        Не нужно думать "это в какой Layer", нужно думать "это живет в каком времени?"
        """
        # Инерция зависит от временного горизонта
        inertia = {
            TemporalDomain.REACTIVE: 0.10,      # Мгновенная реакция
            TemporalDomain.SITUATIONAL: 0.50,   # Медленное развитие
            TemporalDomain.ADAPTIVE: 0.80,      # Упорная память
            TemporalDomain.STRUCTURAL: 0.95,    # Почти неизменная
        }
        
        container = {
            TemporalDomain.REACTIVE: self.reactive_states,
            TemporalDomain.SITUATIONAL: self.situational_states,
            TemporalDomain.ADAPTIVE: self.adaptive_states,
            TemporalDomain.STRUCTURAL: self.structural_states,
        }[domain]
        
        current = container.get(key, 0.0)
        weight = inertia[domain]
        new_value = (current * weight) + (delta * (1 - weight))
        container[key] = max(0.0, min(1.0, new_value))
```

### Почему это критично:

Через год появятся новые состояния:

```python
faith              # STRUCTURAL (годы)
political_identity # STRUCTURAL (годы)
shame              # ADAPTIVE (дни)
infatuation        # SITUATIONAL (часы)
muscle_memory      # ADAPTIVE (недели)
```

**Без TemporalDomain вопрос станет:** "В какой Layer это класть?"  
**С TemporalDomain вопрос ясен:** "В какой TemporalDomain это живет?"

### Вероятность проблемы: **80%**

**Когда проявится:** Месяц 9–12, когда добавишь психологические состояния и поймешь, что классификация слоев неправильная.

---

## ПРОБЛЕМА #2: АРХЕТИПЫ КАК ВЕРОЯТНОСТНЫЙ DICT, А НЕ КАК ФАЗОВОЕ ПРОСТРАНСТВО

### Текущий подход (неправильный):

```python
archetype.social = {
    BROKEN: 0.15,
    COWARD: 0.35,
    CAUTIOUS: 0.40,
    NEUTRAL: 0.10,
}
```

**Предполагает:** Архетипы независимы друг от друга.

**Реальность:** Архетипы **геометрически противоположны**.

```
BROKEN (-0.9, -0.8) ←──────→ LEADER (+0.8, +0.9)
                     расстояние в пространстве

Иметь одновременно:
BROKEN: 0.5
LEADER: 0.5

это психологически невозможно.
```

### Правильный подход: Многомерное фазовое пространство

```python
class PersonalityPhaseSpace:
    """
    Архетипы как точки в многомерном пространстве.
    Не вероятности, а позиции на осях.
    """
    
    # Оси (каждая от -1.0 до +1.0)
    # Ось 1: Страх ↔ Агрессия
    fear_aggression_axis: float  # -1.0 = трус, +1.0 = агрессор
    
    # Ось 2: Подчинение ↔ Доминирование
    submission_dominance_axis: float  # -1.0 = раб, +1.0 = тиран
    
    # Ось 3: Изоляция ↔ Социальность
    isolation_social_axis: float  # -1.0 = отшельник, +1.0 = стадный
    
    # Определение архетипов как точек в пространстве
    ARCHETYPES = {
        "BROKEN": (-0.9, -0.9, +0.1),       # трус, раб, одинок
        "COWARD": (-0.8, -0.6, -0.2),       # боится, подчиняется
        "CAUTIOUS": (-0.3, +0.1, +0.4),     # осторожен, нейтрален, социален
        "NEUTRAL": (0.0, 0.0, 0.0),         # центр
        "PROTECTIVE": (+0.2, +0.3, +0.8),   # смелый, защитник, социален
        "LEADER": (+0.7, +0.8, +0.6),       # агрессор, доминант, социален
        "TYRANT": (+0.9, +0.95, -0.5),      # агрессор, тиран, одинок
    }
    
    def get_current_position(self) -> Tuple[float, float, float]:
        """Текущее положение в фазовом пространстве"""
        return (
            self.fear_aggression_axis,
            self.submission_dominance_axis,
            self.isolation_social_axis,
        )
    
    def get_nearest_archetype(self) -> str:
        """Какой архетип ближайший в пространстве?"""
        current = self.get_current_position()
        nearest = min(
            self.ARCHETYPES.items(),
            key=lambda arch: self._distance(current, arch[1])
        )
        return nearest[0]
    
    def shift_toward_archetype(self, target: str, magnitude: float):
        """Плавный сдвиг в фазовом пространстве (не скачок)"""
        target_pos = self.ARCHETYPES[target]
        
        # Каждая ось двигается независимо
        self.fear_aggression_axis = self._lerp(
            self.fear_aggression_axis,
            target_pos[0],
            magnitude
        )
        self.submission_dominance_axis = self._lerp(
            self.submission_dominance_axis,
            target_pos[1],
            magnitude
        )
        self.isolation_social_axis = self._lerp(
            self.isolation_social_axis,
            target_pos[2],
            magnitude
        )
    
    @staticmethod
    def _distance(p1: Tuple, p2: Tuple) -> float:
        """Евклидово расстояние в фазовом пространстве"""
        return sum((a - b) ** 2 for a, b in zip(p1, p2)) ** 0.5
    
    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        """Линейная интерполяция"""
        return a + (b - a) * t
```

### Почему это критично:

**Старый подход:**
```python
BROKEN: 0.5
LEADER: 0.5
```
Это валидное состояние. Но оно психологически невозможно.

**Новый подход:**
```python
distance(BROKEN, LEADER) ≈ 2.8
Между ними лежит большое расстояние.
Нельзя быть одновременно на обоих концах.
```

### Вероятность проблемы: **75–90%**

**Когда проявится:** Месяц 6–8, когда NPC начнет мерцать между противоположными архетипами при стрессе.

---

## ПРОБЛЕМА #3: ELASTIC TIME СКРЫВАЕТ ТРЕТИЙ ТИП ВРЕМЕНИ — NARRATIVE TIME

### Текущая модель:

```python
class TimeDomain:
    causal_ticks: int          # Дискретные тики
    game_time_seconds: float   # Календарное время
```

**Проблема:** Забыли еще один тип времени.

### Пример:

Игрок печатает:
```
"Я долго смотрю в окно"
```

Реально:
```
2 секунды ввода текста (реальное время)
```

Что происходит:

```
Realtick: 2000ms

Causal Ticks (при time_scale=1.0): 200 тиков
→ NPC может думать 200 мыслей

Game Time (при time_scale=0.2): 400 символов × 0.2 = 80ms
→ Почти мгновенно в игре

Narrative Time (что интендовал игрок): 30 минут созерцания
→ NPC должен пережить глубокие размышления
→ Physiology должна пройти 30 минут голода
```

### Правильная модель:

```python
class TimeDomain:
    """Три ортогональных измерения времени"""
    
    # Тип 1: Причинное время (дискретные шаги)
    causal_ticks: int          # 1, 2, 3, 4, ... (никогда не замедляется)
    
    # Тип 2: Биологическое время (непрерывное, растягивается/сжимается)
    biological_seconds: float  # Зависит от time_scale
    
    # Тип 3: Нарративное время (описано игроком)
    narrative_seconds: float   # "Я долго смотрю" = 30 минут
    
    # Инструмент:Intent Parser → Narrative Duration
    # "долго" → +30 минут
    # "мгновенно" → +2 секунды
    # "некоторое время" → +5 минут

class IntentWithNarrativeTime:
    """Intent содержит нарративное время"""
    
    semantic_action: str       # "look_window"
    narrative_duration: float  # Извлечено из текста игрока
    
    # Пример:
    # "Я долго смотрю в окно"
    # → {action: "look_window", narrative: 1800.0}

def decay_physiological_state(npc, narrative_seconds: float):
    """Физиология развивается по нарративному времени, не по игровому"""
    
    hunger_delta = narrative_seconds * 0.001
    fatigue_delta = narrative_seconds * 0.0005
    
    npc.apply_delta("situational", "satiety", hunger_delta)
    npc.apply_delta("situational", "rest", fatigue_delta)
    
    # Результат: если игрок сказал "долго смотрю", NPC будет голоден
    # Несмотря на то, что game_time прошло мало
```

### Пример работы трех времен:

```python
# Игрок печатает Intent: "Я долго смотрю в окно"
# Real time: 3 секунды печати
# Causal ticks: 300 (при 100 tick/sec)
# Game time: 300 * 0.2 (slow-mo) = 60ms
# Narrative time: 1800 (30 минут, из текста)

# Результат:
# Когнитивно: NPC думал 300 мыслей
# Физиологически: NPC проголодался на +0.001*1800 = 1.8
# Но игровое время показывает только +60ms

# Это правильно! Нарративное время описывает суть действия,
# а не ограничивается игровой скоростью.
```

### Почему это критично:

Без Narrative Time получишь:

```
Игрок: "Я долго молчу и размышляю"
Система: "0.06 seconds passed"
NPC: "Ничего не произошло"
```

Вместо:

```
Игрок: "Я долго молчу и размышляю"
Система: "Narrative time: 30 minutes"
NPC: "(глубокие размышления)"
Physiological: "(проголодался)"
```

### Вероятность проблемы: **70–80%**

**Когда проявится:** Месяц 4–6, когда игрок начнет описывать долгие действия и заметит, что NPC не реагирует соответственно.

---

## ПРОБЛЕМА #4: COUPLING BUDGET, НЕ LIMIT ON ENTITIES

### Текущая (неправильная) защита:

```
"Максимум 5 сущностей на уровень"
```

### Реальная (правильная) защита:

```
"Максимум N причинных связей"
```

### Пример различия:

#### Вариант A: 5 сущностей, полносвязная граф

```python
class Level1:
    perception: PerceptionEvent     # знает: ?
    attention: AttentionService     # знает: ?
    archetype: ArchetypeLabel       # знает: ?
    drive: DriveSystem              # знает: ?
    temporal: TemporalDomain        # знает: ?

# Каждая знает остальные 4
Связи: 5 × 4 / 2 = 10 связей
```

#### Вариант B: 15 сущностей, линейная граф

```python
perception → attention → archetype → drive → temporal
    ↓
    phase_space
    
# Каждая знает только соседей (макс 2)
Связи: ≈14 связей
```

**Вариант B имеет 3× больше сущностей, но меньше связей!**

### Правильная метрика: CouplingScore

```python
class ArchitectureHealthCheck:
    """CDS должен отслеживать это"""
    
    def compute_coupling_score(self, entity: str) -> float:
        """
        Сколько других сущностей знает данная сущность?
        Нормализовано от 0 до 1.
        """
        dependencies = self._get_dependencies(entity)
        return len(dependencies) / MAX_ALLOWED_DEPENDENCIES
    
    def compute_level_coupling(self, level: str) -> float:
        """Суммарная связанность уровня"""
        entities = self._get_entities_at_level(level)
        scores = [self.compute_coupling_score(e) for e in entities]
        return sum(scores) / len(scores)
    
    def system_health_check(self) -> Dict[str, float]:
        """Каждый уровень должен иметь score < 0.5"""
        return {
            "L0_perception": self.compute_level_coupling("L0"),
            "L1_body": self.compute_level_coupling("L1"),
            "L2_behavior": self.compute_level_coupling("L2"),
            "L5_decision": self.compute_level_coupling("L5"),
            # Если score > 0.5 → тревога
        }

# CDS интегрирует это в LAST_SESSION.md:
# "COUPLING WARNING: L2 Behavior score = 0.72 (> 0.5 threshold)"
# → Немедленный рефакторинг
```

### Почему это критично:

**Без контроля связанности:**

```
Month 12:
- 50 сущностей
- Средняя сущность знает 12 других
- Граф полносвязный
- Разбор причины любого бага: перебор 2^50 вариантов
```

**С контролем связанности:**

```
Month 12:
- 80 сущностей
- Каждая знает максимум 2–3 других
- Граф линейный/древовидный
- Разбор причины: перебор 2^3 = 8 вариантов
```

### Вероятность проблемы: **95%**

**Когда проявится:** Месяц 15–18, когда архитектура достигнет критической массы и станет неразбираемой.

---

## ПРОБЛЕМА #5: EXPECTATION LOOP (ДОЛГОСРОЧНАЯ КРИТИЧНОСТЬ)

### Текущая архитектура (реактивная):

```
World State
    ↓
Perception
    ↓
Affect
    ↓
Decision
    ↓
Action
```

**NPC = реактивный организм**

### Реальная архитектура (с ожиданиями):

```
World State
    ↓
Prediction (что я ожидаю)
    ↓
Perception (что я вижу)
    ↓
Comparison (ожидание vs реальность)
    ↓
Surprise/Confirmation
    ↓
Affect
    ↓
Decision
    ↓
Action
    ↓
Update Prediction
```

**NPC = агент с моделью мира**

### Следствие expectation loop:

```python
# Сценарий 1: NPC ожидает атаку

npc.prediction = {
    "danger_level": 0.8,  # Я ожидаю опасность
    "attack_likely": 0.9,
}

# Восприятие:
# Игрок поднял руку мирно

npc.perception = {
    "player_gesture": "raise_hand",  # Нейтральный жест
}

# БЕЗ Expectation Loop:
# "Игрок поднял руку" → нейтральная интерпретация
# NPC: "Привет"

# С Expectation Loop:
# "Я ожидаю атаку" → "Рука поднята" → "Это замах!"
# NPC: "Ааа! Убийца!"
```

### Реализация:

```python
class AgentWithExpectations:
    """Агент с моделью мира"""
    
    def __init__(self, npc_id: str):
        self.predictions: Dict[str, float] = {}  # Что я ожидаю
        self.perceptions: Dict[str, float] = {}  # Что я вижу
        self.surprise_level: float = 0.0
    
    def predict_next_state(self) -> Dict:
        """Агент предсказывает следующее состояние"""
        # На основе памяти и опыта
        return {
            "danger_level": self._estimate_danger(),
            "social_pressure": self._estimate_social_tension(),
            "resource_availability": self._estimate_resources(),
        }
    
    def perceive_actual_state(self) -> Dict:
        """Агент видит реальное состояние"""
        # Через PerceptionEvent и Attention
        return self._get_perception_events()
    
    def compute_prediction_error(self):
        """Ошибка предсказания"""
        predictions = self.predict_next_state()
        perceptions = self.perceive_actual_state()
        
        self.surprise_level = sum(
            abs(predictions[k] - perceptions.get(k, 0.0))
            for k in predictions
        )
        
        # Высокая ошибка → высокий surprise
        # Surprise → переоценка модели мира
    
    def update_world_model(self):
        """Обновить прогнозы на основе ошибок"""
        if self.surprise_level > 0.5:
            # Моя модель неправильна
            # Пересчитать ожидания
            self._retrain_predictor()
    
    def affect_from_surprise(self) -> EmotionPayload:
        """Неожиданность порождает эмоции"""
        if self.surprise_level > 0.8:
            return EmotionPayload(emotion="shocked", intensity=0.7)
        elif self.surprise_level > 0.5:
            return EmotionPayload(emotion="confused", intensity=0.4)
        else:
            return EmotionPayload(emotion="calm", intensity=0.0)
```

### Почему это критично:

**Без Expectation Loop:**
```
NPC видит незнакомца → боится (реактивно)
NPC видит друга → доверяет (реактивно)
Нет контекста, нет предсказания.
```

**С Expectation Loop:**
```
NPC видит незнакомца, но ожидал его приход → не боится
NPC видит друга, но ожидал врага → удивлен, настороже
Поведение базируется на моделе мира.
```

### Вероятность проблемы: **90% (долгосрочно)**

**Когда проявится:** Месяц 18+, когда захочешь, чтобы NPC имели "персональную историю" и "контекст".

---

## МАТРИЦА ОНТОЛОГИЧЕСКИХ ПРЕВОРОТОВ

| Проблема | Текущий подход | Правильный подход | Вероятность | Когда |
|----------|---|---|---|---|
| #1 Слои | Group by Entity | Group by TemporalDomain | 80% | М 9–12 |
| #2 Архетипы | Dict[Archetype, float] | PhaseSpace (оси) | 75–90% | М 6–8 |
| #3 Время | 2 типа (causal, bio) | 3 типа (+ narrative) | 70–80% | М 4–6 |
| #4 Связи | Limit entities | Coupling budget | 95% | М 15–18 |
| #5 Агентность | Реактивный | С ожиданиями | 90% | М 18+ |

---

## СТРАТЕГИЧЕСКИЙ ВЫВОДЫ

### Текущая оценка: **9.0–9.2 / 10** (с исправлениями)

### После этих 5 переворотов: **9.5–9.8 / 10**

### Главное изменение:

**БЫЛО:**
```
"много интересных систем"
```

**СТАЛО:**
```
"единая теория поведения мира"
```

### Ключевой вопрос теперь:

**Не:** "Какие ещё системы добавить?"

**А:** "Какие новые сущности **запретить** появляться без перестройки онтологии?"

---

## РЕКОМЕНДАЦИИ ПО ВНЕДРЕНИЮ

### Фаза 1 (R7): Переворот времени и архетипов
- [ ] Введить TemporalDomain (вместо Layer)
- [ ] Переписать архетипы как PhaseSpace
- [ ] Добавить Narrative Time в Intent

### Фаза 2 (R8): Контроль связанности
- [ ] Внедрить CouplingScore в CDS
- [ ] Установить пороги (max 0.5 на уровень)
- [ ] Регулярные аудиты (раз в спринт)

### Фаза 3 (R9+): Expectation Loop
- [ ] Добавить PredictionModel в AgentMind
- [ ] Интегрировать surprise в Affect
- [ ] Обновлять world_model на основе ошибок

---

**Переворот завершен. ENIGMA теперь строится не на системах, а на онтологии.**
