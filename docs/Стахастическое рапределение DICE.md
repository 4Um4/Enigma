# ENIGMA — EXPANDED ROADMAP (R1–R4 + STOCHASTIC RESOLUTION LAYER)

---

## R1 — MEMORY CORE (ОБНОВЛЁН)

```
R1.1 → R1.2 → R1.3 → R1.4 → R1.5
      + R1.6 NarrativeFacts
      + R1.7 TierConfig
```

### R1.6 — NarrativeFacts

* immutable (frozen)
* max 2 факта в runtime
* НЕ участвуют в логике
* используются ТОЛЬКО для explanation слоя

---

### R1.7 — TierConfig

* статическое назначение
* no runtime upgrade
* допускается только controlled respawn (новый NPC)

---

## R2 — DECISION CORE

### R2.1 — NPCState (расширение)

Добавлено:

* personality_base (immutable)
* active_traits (динамика)
* trauma_markers (долгосрочные сдвиги)
* narrative_cache (≤2 факта)

---

### R2.2 — DecisionHub

Добавлено:

* trait_modifier
* explanation_mode
* expected_success (**КРИТИЧЕСКОЕ ДОБАВЛЕНИЕ**)

---

#### Обновлённая формула:

```
score(action) =
    (drive_weight * context_relevance)
  + emotion_weight
  + relationship_modifier
  + trait_modifier
  - (fear * risk)
```

→ randomness убирается для действий, где используется Resolution Layer

---

#### Новый выход:

```python
DecisionResult:
    intent
    expected_success   # 0..1
    emotion_delta
    stress_delta
    relationship_delta
```

---

## R3 — INTEGRATION

* WorldPressure → EventBus
* VerbalizationContext → narrative_hints

---

## R4 — STOCHASTIC RESOLUTION LAYER (НОВЫЙ КЛЮЧЕВОЙ ЭТАП)

---

### R4.1 — ResolutionEngine

Новый слой между DecisionHub и StateApplicator:

```
DecisionHub
↓
ResolutionEngine   ← НОВЫЙ
↓
StateApplicator
```

---

#### Основная формула:

```python
roll = d20 → normalized [0..1]

final_value = clamp(
    roll * 0.65
  + bias * 0.35,
    0.05,
    0.95
)
```

---

#### Где bias:

```python
bias =
    stat_modifier
  + context_modifier
  + affinity_modifier
  + npc_state_modifier
```

---

### R4.2 — Outcome Mapping (градиент, НЕ бинарно)

| Диапазон  | Outcome               |
| --------- | --------------------- |
| 0.00–0.05 | крит. провал + отдача |
| 0.05–0.25 | провал                |
| 0.25–0.50 | негативный частичный  |
| 0.50–0.75 | позитивный частичный  |
| 0.75–0.95 | успех                 |
| 0.95–1.00 | крит. успех           |

---

### R4.3 — Prediction Gap (ядро обучения)

```python
gap = actual_success - expected_success
```

---

#### Интерпретация:

* gap < 0 → неожиданный провал → стресс / травма
* gap > 0 → неожиданный успех → уверенность
* gap ≈ 0 → стабильность

---

### R4.4 — Adaptation Layer (обучение NPC)

```python
adaptation =
    gap
  * learning_rate
  * stability_factor
```

---

#### Эффекты:

* active_traits обновляются
* trauma_markers формируются при |gap| > threshold
* relationship меняется через gap, а не напрямую outcome

---

### R4.5 — Trait Formation

Traits формируются не от событий, а от:

```
повторяющихся отклонений (gap)
```

---

#### Примеры:

* частый обман игрока → paranoia
* частые неожиданные успехи → overconfidence
* частые неожиданные провалы → anxiety

---

### R4.6 — Trauma System

Триггер:

```
|gap| высокий + высокий stress
```

---

Эффект:

* изменение весов DecisionHub
* долгосрочное поведение

---

## R5 — CHARACTER CONSTRAINT SYSTEM (PLAYER LAYER)

---

### R5.1 — ConstraintEngine

Новый слой ДО Event:

```
PlayerIntent
↓
ConstraintEngine   ← НОВЫЙ
↓
Event
```

---

### R5.2 — CharacterProfile

```python
CharacterProfile:
    traits
    willpower
    internal_conflicts
```

---

### R5.3 — Affinity System

```python
affinity = f(traits, intent)
```

---

#### Диапазоны:

| Affinity | Значение         |
| -------- | ---------------- |
| >0.7     | естественно      |
| 0.4–0.7  | допустимо        |
| 0.2–0.4  | сложно           |
| <0.2     | против характера |

---

---

### R5.4 — Effective Affinity

```python
effective_affinity =
    affinity + willpower * 0.5
```

---

### R5.5 — Цена отклонения

```python
stress += (1 - affinity) * k
```

---

Дополнительно:

* когнитивные искажения
* риск self-sabotage
* формирование новых traits

---

---

## R6 — CONTEXT PREPARATION SYSTEM

---

### Принцип:

```
Preparation > Execution
```

---

### ContextModifier:

```python
context_modifier =
    visibility
  + attention_level
  + npc_emotion
  + environment
```

---

### Важное:

* действия формируют состояние
* состояние влияет на вероятность
* вероятность влияет на outcome

---

---

## R7 — COMBAT SYSTEM (ADAPTED)

---

### R7.1 — Initiative

```python
initiative =
    reaction_speed
  + awareness
  + d20_noise
```

---

### R7.2 — Combat = Gradient System

НЕ:

```
hit / miss
```

А:

```
outcome_value → степень успеха
```

---

### R7.3 — Damage / Effect Mapping

| Outcome  | Результат           |
| -------- | ------------------- |
| низкий   | промах / уязвимость |
| средний  | частичный урон      |
| высокий  | сильный эффект      |
| максимум | крит / травма       |

---

---

## R8 — DICE SYSTEM STRATEGY

---

### Используемые кубики:

| Кубик | Назначение                   |
| ----- | ---------------------------- |
| d20   | хаос, игрок, риск            |
| 2d6   | эмоции                       |
| 3d6   | рутина / стабильные действия |
| d100  | скрытые проверки             |

---

---

## R9 — CORE DESIGN PRINCIPLES (КРИТИЧЕСКИЕ)

---

### 1. Кубик НЕ принимает решение

Он:

```
фиксирует отклонение от ожидания
```

---

### 2. NPC учатся НЕ от результата

А от:

```
разницы между ожиданием и результатом
```

---

### 3. Подготовка важнее действия

Игрок выигрывает не броском, а:

```
изменением состояния системы
```

---

### 4. Нет 100% и 0%

```python
clamp(0.05, 0.95)
```

---

### 5. Характер ограничивает, но не запрещает

* soft resistance > hard lock

---

### 6. Свобода = цена

Любое отклонение:

* стресс
* риск
* изменение личности

---

### 7. RNG не должен быть двойным

* убрать randomness из DecisionHub при использовании кубиков

---

### 8. Предсказуемость важнее удачи

Игрок должен понимать:

```
почему шанс был таким
```

---

### 9. Анти-эксплойт

* diminishing returns
* hidden modifiers
* cognitive load

---

### 10. Irreversibility

* автосейв после действия
* нет отката
* редкий reroll как ресурс

---

## R10 — UX СЛОЙ

---

### Отображение:

```
Шанс успеха: 62%
Факторы:
- стресс -10%
- доверие +15%
- внимание цели -20%
```

---

### Взаимодействие:

```
[Действие]
↓
[🎲 Бросить кубик]
↓
Outcome
```

---

---

# ФИНАЛЬНАЯ МОДЕЛЬ СИСТЕМЫ

```
Игрок
↓
ConstraintEngine
↓
Event
↓
DecisionHub (expected_success)
↓
ResolutionEngine (dice + bias)
↓
Outcome
↓
StateApplicator
↓
Обновление:
    - эмоций
    - отношений
    - traits
    - trauma
```

---

# СУТЬ

```
Это не система действий.
Это система управления вероятностями через состояние.
```

---

# КРИТИЧЕСКИЙ ВЫВОД

Если всё реализовано правильно:

Игрок не думает:

"повезёт или нет"

Он думает:

"в каком состоянии шанс станет приемлемым"

Вот расширенный текстовый блок дорожной карты с учётом последних уточнений про кубики, сложность действий, награды и психологию игрока. Всё оформлено для копирования и внедрения:

ENIGMA — локальный AI Dungeon Master (Decision + Dice Enhancements)
R1 — MEMORY CORE (ОБНОВЛЁН)

R1.1 → R1.2 → R1.3 → R1.4 → R1.5

R1.6 NarrativeFacts
frozen
max 2
не участвуют в логике
R1.7 TierConfig
static assignment
no runtime upgrade

Дополнения по кубикам и действиям:

Память влияет на веса событий и вероятность успеха действий.
Веса учитывают сложность действия и подготовку игрока.
Стоимость увеличения успеха растёт нелинейно: последние 20% сложнее достичь.
R2 — DECISION CORE
R2.1 NPCState

Добавлено:

personality_base
active_traits
trauma_markers
narrative_cache
dice_modifiers — смещение для бросков кубика исходя из состояния NPC
hidden_risk — скрытые точки отказа, влияющие на сложность действий игрока
R2.2 DecisionHub

Добавлено:

trait_modifier — учитывает характеристики NPC и игрока при расчёте действий
explanation_mode — скрытые подсказки для LLM о причинах решений
complexity_factor — повышает риск провала при сложных комбинациях действий
preparation_cap — максимальное смещение кубика при идеальной подготовке (≈80%)
failure_floor — минимальный шанс провала (≈20%)
reward_power — смещение кубика за успешные, сложные комбинации действий
partial_outcomes — градация результатов при провале (частичный успех, полный провал, провал с последствиями)
R3 — INTEGRATION
WorldPressure → EventBus
VerbalizationContext → narrative_hints
dice_feedback — UX-интерфейс показывает “почти всё подготовлено / риск остаётся”, а не точный %
story_rewards — система наград за правдоподобную ролевую комбинацию, позволяющая смещать итог броска
psychology_layer — игрок ощущает “меня предала удача”, а не “я недооценил систему”
Дополненные мудрые моменты для кубиков
Сложность действий:
Чем сложнее сцена, тем выше hidden_risk и тем меньше шанс идеального броска.
Простые действия почти детерминированы, сложные всегда содержат элемент случайности.
Награды:
Игрок может использовать reward_power для смещения кубика, но не может превысить preparation_cap.
Идеальная подготовка даёт 80% шанс успеха, но 20% риск провала всегда сохраняется.
Стоимость подготовки растёт нелинейно: последние 20% сложности требуют экспоненциальных усилий.
Провалы:
Даже при минимальном успехе есть градации: частичный успех, провал, провал с последствиями.
UX скрывает точную цифру, показывая лишь “высокий шанс / риск остаётся”.
Правдоподобие ролевой игры:
Система награждает за сложные комбинации действий и их реалистичное выполнение.
Наказания за неестественное поведение — скрытые, растущие индикаторы, например “рога” за неверную ролевую игру.
Хорошее отыгрывание роли приносит “нимб” и доступ к смещению кубика.
Детерминизм и случайность:
Randomness ±10%, seed фиксирован на сессию.
Игрок может управлять шансом, но не исходом — создаётся ощущение непредсказуемой богини Фортуны.
Связь подготовки и кубиков:
Все действия должны быть мотивированы внутренними ресурсами персонажа: навыки, предметы, окружение.
Игрок не может заставить персонажа действовать вопреки характеру без значительной подготовки.
Взаимодействие с NPC через подготовку + сложную сцену + кубик = единственный путь успешного обмана или действия.