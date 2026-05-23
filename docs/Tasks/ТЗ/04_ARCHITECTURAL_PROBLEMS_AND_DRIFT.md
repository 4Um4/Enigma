# АРХИТЕКТУРНЫЙ АНАЛИЗ: 5 Ловушек и Онтологический Дрейф

**Автор критики:** Kami (META CODE ARCHITECT)  
**Дата анализа:** 2026-05-21  
**Оценка текущей архитектуры:** Идея 9.5/10, Реализация 6.5/10, Враг: швы между системами

---

## МЕТААНАЛИЗ: Что такое ENIGMA на самом деле

### Ти думаешь:
```
Симуляция для инди-игры (Rimworld-like)
```

### На самом деле это:
```
30% Игровой движок
35% Когнитивная архитектура (BDI-подобная)
20% Симулятор социальных агентов
15% Исследовательский фреймворк (для LLM-архитекторов)
───────────────
100% = Гибридная система повышенной сложности
```

**Следствие:** Ты постоянно упираешься в "странное ощущение сложности" потому что проектируешь не Rimworld, а **мини-среду искусственной социальной динамики**.

Это меняет всё.

---

## ПРОБЛЕМА #1: L1 СМЕШИВАЕТ ТРИ РАЗНЫХ ВРЕМЕННЫХ ГОРИЗОНТА

### Текущая структура:

```python
@dataclass
class LivingNPC:
    core: IdentityCore           # Меняется: ГОДЫ
    drives: DriveSystem          # Меняется: МИНУТЫ
    body: BodySchema             # Меняется: СЕКУНДЫ
    archetype: ArchetypeLabel    # Меняется: ТИКИ (10–100ms)
```

### Проблема:

Все четыре слоя живут в одной функции `apply_delta()`:

```python
npc.apply_delta("drives", "survival", 0.5)  # Может трогать всё сразу
```

Но они имеют разные:
- **Масштабы времени** (годы vs миллисекунды)
- **Инерции** (личность почти не меняется, фаза меняется моментально)
- **Скорости обновления** (core: раз в месяц, archetype: каждый тик)

### Что произойдет через 6–12 месяцев:

```python
# Баг-1: Fear растет, но Archetype не успевает обновиться
npc.apply_delta("drives", "survival", 0.2)
# fear переходит в 0.8, но archetype еще NEUTRAL
# NPC одновременно "LEADER ЖЕ БОИТСЯ"

# Баг-2: Боль гасит мана?
npc.apply_delta("body", "pain_threshold", -0.3)
# Почему это меняет mana_channel?

# Баг-3: IdentityCore "меняется"
npc.apply_delta("core", "rigidity", 0.1)
# Но core frozen! Или это должно быть в drives?

# Результат: apply_delta() становится чёрным ящиком
```

### Решение:

Разделить на слои с явными временными горизонтами:

```python
class LivingNPC:
    # СЛОЙ 1: TraitLayer (меняется в месяцы)
    core: IdentityCore  # Frozen, но имеет эволюцию
    
    # СЛОЙ 2: MotivationalLayer (меняется в минуты)
    drives: DriveSystem
    relationships: Dict[str, float]
    
    # СЛОЙ 3: PhysiologicalLayer (меняется в секунды)
    body: BodySchema
    health_status: HealthState
    
    # СЛОЙ 4: PhaseLayer (меняется в тики)
    archetype: ArchetypeLabel  # Вероятностная, не дискретная
    perceptual_state: PerceptualState
    
    def apply_delta(self, layer: str, attribute: str, delta: float):
        """Только изменяет соответствующий слой"""
        if layer == "traits":
            raise ValueError("Traits only change through evolution()")
        elif layer == "motiv":
            self.drives.apply_delta(attribute, delta, inertia=0.85)
        elif layer == "physio":
            self.body.apply_delta(attribute, delta, inertia=0.70)
        elif layer == "phase":
            self.archetype.shift_probability(attribute, delta, inertia=0.40)

    def evolve_traits(self, experience: TraumaEvent):
        """Редкое событие: травма может изменить core (годы интеграции)"""
        # Например, военная травма → base_fear повышается на 0.05
        # Но только через годы переживания, а не мгновенно
        pass
```

### Вероятность проблемы: **75%**

**Когда проявится:** Месяц 6–12, когда начнешь отлаживать поведение NPC на долгих прогулках.

---

## ПРОБЛЕМА #2: АРХЕТИПЫ ДИСКРЕТНЫЕ → МЕРЦАНИЕ ЛИЧНОСТИ

### Текущий код ArchetypeLabel:

```python
def update(self, core: IdentityCore, drives: DriveSystem):
    if drives.survival > 0.8 and core.base_fear > 0.7:
        self.social = SocialArchetype.BROKEN
    elif drives.stress < 0.3:
        self.social = SocialArchetype.NEUTRAL
```

### Проблема: Phase Transition Hysteresis

```
fear=0.69  → NEUTRAL
fear=0.70  → BROKEN
fear=0.69  → NEUTRAL
```

**Мерцание:**

```
Тик 231: fear = 0.695 → NEUTRAL → "NPC разговаривает с собой"
Тик 232: fear = 0.705 → BROKEN → "NPC замирает"
Тик 233: fear = 0.695 → NEUTRAL → "NPC снова разговаривает"
```

NPC выглядит психопатом с дергающимся поведением.

### Причина:

Нет гистерезиса. Переход происходит в одну точку (0.7), а не в диапазон.

### Решение:

Архетипы вероятностные, не дискретные:

```python
@dataclass
class ArchetypeProfile:
    """Вероятностный профиль, не дискретный выбор"""
    social: Dict[SocialArchetype, float] = field(default_factory=dict)
    violence: Dict[ViolenceArchetype, float] = field(default_factory=dict)
    
    # Пример:
    # social = {
    #     BROKEN: 0.15,
    #     COWARD: 0.35,
    #     CAUTIOUS: 0.40,
    #     NEUTRAL: 0.10
    # }
    
    def get_dominant(self) -> SocialArchetype:
        """Выбирает архетип по вероятности, не по порогу"""
        return max(self.social, key=self.social.get)
    
    def shift_toward(self, target: SocialArchetype, delta: float):
        """Плавное смещение профиля, не скачок"""
        for arch in self.social:
            if arch == target:
                self.social[arch] = min(1.0, self.social[arch] + delta)
            else:
                self.social[arch] = max(0.0, self.social[arch] - delta / 3)
        # Нормализовать до суммы = 1.0
        total = sum(self.social.values())
        for arch in self.social:
            self.social[arch] /= total

def update_archetype_profile(npc: LivingNPC):
    """Плавное обновление архетипа, не дискретное"""
    if npc.drives.survival > 0.8 and npc.core.base_fear > 0.7:
        npc.archetype.shift_toward(SocialArchetype.BROKEN, delta=0.05)
    elif npc.drives.stress < 0.2:
        npc.archetype.shift_toward(SocialArchetype.NEUTRAL, delta=0.03)
    # Остальные переходы...
    # Остаток "утекает" на доминирующий архетип
```

**Преимущество:**

```
Нет мерцания. Есть плавное скольжение психики.
```

### Вероятность проблемы: **90%**

**Когда проявится:** Месяц 2–3, когда заметишь "странное дергание" в поведении при edge-case стресса.

---

## ПРОБЛЕМА #3: ELASTIC TIME ЛОМАЕТ БИОЛОГИЧЕСКУЮ ЭКОНОМИКУ

### Текущая механика:

```python
# Фронтенд отправляет:
time_scale = 0.2  # Игрок печатает

# Бэкенд:
causal_tick += 1  # Всегда
game_time += 2 * 0.2 = 0.4 сек  # Растягивается
```

### Проблема: Разделение когнитивного и биологического времени

```
Игрок печатает 30 секунд реального времени

time_scale = 0.2

Каузальные тики: 200 тиков прошло
NPC думал 200 раз.

Календарное время: 40 секунд прошло
NPC "старел" 40 сек.
```

**Следствие:**

```python
# Нормальный цикл:
hunger_per_tick = 0.001
200 тиков × 0.001 = 0.2 hunger

# Elastic Time:
200 тиков × 0.001 = 0.2 hunger (НОРМАЛЬНО)
Но календарь: 40 сек вместо 200 сек

# Получается:
NPC думал 200 раз = должен голодать на 0.2
Но прошло только 40 сек календарного времени = должен голодать на 0.04

# ПРОТИВОРЕЧИЕ: 0.2 vs 0.04
```

### Что произойдет:

```
Игрок печатает 30 сек реального времени × 100 тиков (slow-mo)

Результат:
- NPC прожил 100 когнитивных циклов (полная ночь размышлений)
- Но календарь показывает только +30 секунд в игре
- NPC "не голоден, хотя думал целую ночь"

ИЛИ (обратная проблема):

Если привязать голод к тикам:
- Игрок печатает (slow-mo)
- NPC начинает молниеносно худеть
- "Я печатал 30 секунд, а NPC упал в обморок от голода"
```

### Корень проблемы:

Нельзя одновременно:
1. Привязать physiological к календарю
2. Привязать cognitive к тикам
3. Иметь разные скорости для них

### Решение: Двойная экономика

```python
class DriveSystem:
    # КОГНИТИВНЫЕ (привязаны к тикам, не к календарю)
    survival: float     # Меняется за тик
    autonomy: float     # Меняется за тик
    
    # ФИЗИОЛОГИЧЕСКИЕ (привязаны к календарю, не к тикам)
    satiety: float      # Меняется за game_time_seconds
    rest: float         # Меняется за game_time_seconds
    health: float       # Меняется за game_time_seconds

def apply_cognitive_pressure(npc, event):
    """Когнитивное давление: независимо от времени"""
    npc.drives.apply_delta("survival", 0.1, time_scale=1.0)  # Всегда 1:1

def decay_physiological_state(npc, elapsed_seconds):
    """Физиология: зависит от календарного времени"""
    # Голод растет с календарем, не с тиками
    hunger_delta = elapsed_seconds * 0.001  # Per second
    npc.drives.apply_delta("satiety", hunger_delta, time_scale=1.0)
    
    # Усталость растет с календарем
    fatigue_delta = elapsed_seconds * 0.0005  # Per second
    npc.drives.apply_delta("rest", fatigue_delta, time_scale=1.0)
```

**Результат:**

```
Elastic Time больше не ломает экономику.
Cognitive и Physiological развязаны.
```

### Вероятность проблемы: **70–80%**

**Когда проявится:** Месяц 4–5, когда заметишь, что долгие print-сессии создают странную физиологию у NPC.

---

## ПРОБЛЕМА #4: ATTENTION BUDGET СЛИШКОМ ЛИНЕЙНЫЙ

### Текущая механика:

```python
COST = {
    "CENTRAL": 0.6,
    "ATMOSPHERE": 0.2,
    "PERIPHERAL": 0.2,
}

# Просто сумма:
if remaining_budget >= cost:
    pebration passes
```

### Проблема: Внимание человека нелинейно

Реальность:
```
Выстрел (salience=0.9) + Крик (salience=0.8)
≠ 1.7 × бюджета

Они конкурируют нелинейно:
- Выстрел привлекает 85% внимания
- Крик привлекает еще 15% (остаток)
- Сумма = 100%, не 170%
```

### Что произойдет:

```python
# Текущая система:
drama_event = PerceptionEvent(salience=0.8, category="CENTRAL", cost=0.6)
scream_event = PerceptionEvent(salience=0.9, category="CENTRAL", cost=0.6)

if budget >= 0.6:
    drama passes
if budget >= 0.6:
    scream passes
    
# Обе проходят! Игрок слышит оба события одновременно.
# Это неправильно.
```

### Лучший подход: Нелинейное конкурирование

```python
@dataclass
class PerceptualAttentionService:
    max_salience: float = 1.0  # Максимальное значение, которое может быть
    novelty_decay: float = 0.1  # Привыкание снижает salience
    
    def filter_with_competition(self, events: List[PerceptionEvent]) -> List[ActivePerception]:
        """
        События конкурируют нелинейно:
        - Самое заметное событие берет до 80% внимания
        - Остальное распределяется среди других
        - Привыкание снижает salience со временем
        """
        # 1. Сортировка по salience
        sorted_events = sorted(events, key=lambda e: e.salience, reverse=True)
        
        # 2. Нелинейное распределение (не аддитивное)
        active = []
        attention_left = 1.0
        
        for i, event in enumerate(sorted_events):
            if attention_left < 0.05:
                break  # Слишком мало внимания
            
            # Доминирующее событие получает больше
            attention_fraction = attention_left * (1.0 - 0.3 * i)  # Экспоненциальный спад
            
            if attention_fraction > 0.1:  # Порог "заметности"
                # Учитывать новизну (привыкание)
                adjusted_salience = event.salience * (1.0 - self.novelty_decay)
                active.append(ActivePerception(
                    text=event.semantic_seed,
                    intensity=adjusted_salience,
                ))
                attention_left -= attention_fraction
        
        return active
```

### Вероятность проблемы: **60%**

**Когда проявится:** Месяц 5–8, когда NPC в сложных сценах с 3+ событиями начнет воспринимать их некорректно.

---

## ПРОБЛЕМА #5: ОНТОЛОГИЧЕСКИЙ ДРЕЙФ (ГЛАВНАЯ УГРОЗА)

### Текущее количество сущностей:

```
Уровень 0 (Дискретная симуляция):
- WorldRuntimeState
- TickOrchestrator

Уровень 1 (Восприятие):
- PerceptualKernel (CFRM)
- PerceptionEvent
- PerceptualAttentionService

Уровень 1.5 (Живой агент):
- IdentityCore
- DriveSystem
- BodySchema
- ArchetypeLabel
- LivingNPC

Уровень 2 (Давление):
- IntentPressureProfile
- IntentPressureResolver
- AmplifiedPressureProfile

Уровень 3 (Воля):
- WillpowerGate
- WillResponseDTO
- WillState
- AffectiveImprint

Уровень 4 (Аффект):
- AffectiveIntegrator
- EmotionTransition
- EmotionPayload

Уровень 5 (Решение):
- DecisionHub
- MovementGoal (LOD0/LOD1)

Уровень 6 (Пространство):
- SpatialService
- SpatialQueryService
- TraversalState

Уровень 7 (Восприятие игрока):
- PlayerPerceptionDTO
- PhenomenologyProjectionService
- ActivePerception

Уровень 8 (Восстановление):
- ReconstructionEventDTO

Уровень 9 (Диагностика):
- CausalObserver
- PatternRegistry
- HealthCheckers (Tick, Movement, Decision)

Итого: ~40 сущностей
```

### Прогнозируемый рост (Kami):

```
2026 (май): 15 систем
2026 (ноябрь): 25–30 систем
2027 (май): 40–50 систем
2027 (ноябрь): 60–70 систем
2028: 85+ систем
```

### Проблема: Количество связей растет экспоненциально

Если N сущностей, число связей ≈ N² / 2.

```
15 сущностей → 112 потенциальных связей
40 сущностей → 780 потенциальных связей
85 сущностей → 3612 потенциальных связей
```

**Через 18 месяцев: 3600+ потенциальных точек отказа.**

### Типичный сценарий распада:

```
2026 (май):
"NPC почему-то не подошел?"
Ответ: "TraversalState не инициализирован"
→ Быстрый фикс

2026 (ноябрь):
"NPC почему-то не подошел?"
Ответ: "TraversalState хорошо, но DecisionHub отказал"
Следствие: "DecisionHub ждал Affective, а Affective ждал Perception"
→ Медленный отладка (2–4 часа)

2027 (май):
"NPC почему-то не подошел?"
Ответ: "Это взаимодействие DecisionHub × WillpowerGate × Attention × Traversal × Reconstruction"
Количество переменных: 47
Количество тестов, нужных чтобы покрыть: 2^47 = 140 триллионов
→ Невозможно отладить локально

2027 (ноябрь):
"Ничего не работает"
Инженер: "Я уже не понимаю, что здесь происходит"
→ Полный рефакторинг или смерть проекта
```

### Признаки дрейфа (уже видны):

1. ✅ **BUG-001:** DirectiveSubscriber state desync
   - Это не просто баг, это **невидимая связь** между DirectiveSubscriber и npc_states
   
2. ✅ **BUG-002:** TICK_CATCHUP убивает TraversalState
   - Это не просто баг, это **столкновение двух онтологий** (дискретное vs непрерывное)

3. ✅ **BUG-005:** LegacyStateDeltaAdapter теряет PerceptionPayload
   - Это не просто баг, это **неправильная граница между системами**

4. ✅ **BUG-007:** LOD0/LOD1 interrupt logic
   - Это не просто баг, это **две конкурирующие онтологии движения**

### Решение: Архитектурный контроль роста

**Нужно делать:**

1. **Ограничить количество сущностей на уровне**
   ```
   Один уровень = максимум 5 сущностей
   Если больше → разбить на подуровни
   ```

2. **Явные границы между уровнями**
   ```
   L0 → L1: только через apply_delta()
   L1 → L2: только через get_dominant_drive()
   L2 → L5: только через MovementGoal
   ```

3. **Регулярные аудиты архитектуры**
   ```
   Каждый спринт: граф зависимостей
   Если цикличность → немедленный фикс
   ```

4. **CDS как страховка**
   ```
   Если NPC ведет себя странно:
   CDS показывает, на какой точке отказа
   Не гадаем, знаем
   ```

### Вероятность проблемы: **60–70%**

**Когда проявится:** Месяц 12–18, когда количество сущностей перейдет за 50–60 и начнут появляться взаимодействия третьего порядка.

---

## МАТРИЦА РИСКОВ (ПЕРЕПИСАННАЯ)

| Проблема | Вероятность | Когда проявится | Сложность фикса | Статус |
|----------|------------|-----------------|-----------------|--------|
| L1 временные горизонты | 75% | М 6–12 | Высокая | 🔴 Критична |
| Архетипы дискретные | 90% | М 2–3 | Средняя | 🔴 Критична |
| Elastic Time биология | 70–80% | М 4–5 | Высокая | 🟡 Высокая |
| Attention Budget | 60% | М 5–8 | Средняя | 🟡 Средняя |
| Онтологический дрейф | 60–70% | М 12–18 | **ОЧЕНЬ ВЫСОКАЯ** | 🔴 Критична |

---

## НЕОЖИДАННОЕ НАБЛЮДЕНИЕ KAMI

> "ENIGMA это гибрид: 30% движок + 35% архитектура + 20% симуляция + 15% исследование"

**Следствие:**

Ты не просто кодишь игру. Ты **исследуешь границы между**:
- игровыми движками
- когнитивными архитектурами
- мультиагентными симуляциями

**Это очень тяжело.** Потому что нет готовых паттернов. Нет best practices. Нет StackOverflow.

**Поэтому "странное ощущение сложности" — это не баг, это признак, что ты делаешь что-то оригинальное.**

---

## РЕКОМЕНДАЦИИ

### Немедленно (R7):

1. Разделить L1 на слои с явными временными горизонтами
2. Сделать архетипы вероятностными (не дискретными)
3. Развязать cognitive и physiological через двойную экономику
4. Внедрить нелинейную конкуренцию в Attention Budget

### До М 18:

1. Внедрить явные границы между уровнями
2. Ограничить количество сущностей на уровне (макс 5)
3. Регулярные архитектурные аудиты (раз в спринт)
4. Усилить CDS как страховку от дрейфа

### Стратегически (Долгосрок):

Начать готовиться к большому рефакторингу в **М 18–24**. К тому времени архитектура исчерпает свою емкость, и нужно будет переформатировать на следующий уровень абстракции.

---

**Итог:** Kami правилен. Враг не код и не производительность. Враг — **накопление онтологических швов и неконтролируемый рост сложности**.

Это решается не оптимизацией, а **дизайном контроля архитектурного роста**.
