# ENIGMA — АКТУАЛЬНАЯ АРХИТЕКТУРА (FINAL SPEC)

## 0. ЦЕЛЬ СИСТЕМЫ

Создать локальную RPG-систему, в которой NPC демонстрируют:
— причинно-следственное поведение
— устойчивость реакций
— предсказуемость без полной детерминированности

При ограничениях:
— локальный запуск
— LLM 7B–13B
— VRAM ≤ 16GB
— контекст ≤ 4k токенов
— Cuda ядра
---

## 1. КЛЮЧЕВОЙ ПРИНЦИП

**LLM НЕ ПРИНИМАЕТ РЕШЕНИЯ.**

LLM = слой выражения
Python = слой интеллекта

NPC — это **система числовых сил**, а не текстовых рассуждений.

---

## 2. АРХИТЕКТУРНОЕ ЯДРО

```
Event
  ↓
DecisionHub.compute()        # read-only
  ↓
DecisionResult
  ↓
StateApplicator.apply()      # write-only (atomic)
  ↓
NPCState (source of truth)
  ↓
LLM (verbalization only)
```

---

## 3. ИСТОЧНИК ПРАВДЫ

### NPCState — единственный источник истины

Содержит:

* emotion
* stress
* intent
* relationship cache
* active_traits (динамические модификаторы)
* trauma_markers

Использование:

* DecisionHub читает ТОЛЬКО NPCState
* SceneState получает снимок после обновления

---

### SceneState

НЕ участвует в принятии решений.

Используется как:

* визуальное состояние сцены
* координаты
* объекты

---

## 4. EVENT LAYER

Любое действие → Event

```python
Event(
    type="harassment",
    actor="player",
    target="lusya",
    intensity=0.7
)
```

Фильтрация:

1. Радиус
2. Perception (видимость, препятствия)

→ NPC получают только релевантные события

---

## 5. DECISION HUB (ЯДРО ИНТЕЛЛЕКТА)

### Свойства:

* чистая функция (read-only)
* не изменяет состояние
* не использует LLM
* работает только с числами

---

### Вход:

```python
npc_state
event
context
```

---

### Action Space:

* фиксированный enum
* фильтр доступности:

  * физическое состояние
  * дистанция
  * ограничения

---

### Формула:

```python
score(action) =
    (drive_weight * context_relevance)
  + emotion_weight
  + relationship_modifier
  + trait_modifier
  - (fear * risk)
  + randomness(±10%)
```

---

### Дополнение: Trait System (вместо изменения personality)

```python
effective_modifier =
    personality_base
  + active_traits
```

* personality_base — неизменен
* active_traits — накапливаются и затухают

---

### Выход:

```python
DecisionResult:
    intent
    emotion_delta
    stress_delta
    relationship_delta
    narrative_facts  # optional, только если intent=EXPLAIN
```

---

## 6. STATE APPLICATOR

Единственная точка записи в NPCState.

```python
apply(npc_state, decision_result) → new_npc_state
```

Гарантии:

* атомарность
* отсутствие partial updates
* детерминизм

---

## 7. NPC СОСТОЯНИЕ (NPCState)

Содержит:

* emotion
* stress
* intent
* relationship cache
* personality_base (immutable)
* active_traits
* trauma_markers
* narrative_cache (max 2 факта для объяснения)

---

## 8. RELATIONSHIP SYSTEM

### Хранение:

* RelationshipStore (персистентный слой)

### В NPCState:

* только кэш

---

### Пример:

```json
"player→tornin": {
  "trust": 35,
  "fear": 10,
  "debt": 0
}
```

---

## 9. MEMORY SYSTEM

### 9.1 Core Memory (веса)

Память влияет только на числа:

```text
player_hit → trust -20  
player_help → trust +15  
```

---

### 9.2 NarrativeFacts (ограниченный слой фактов)

Используется ТОЛЬКО для объяснения игроку.

```python
@dataclass(frozen=True)
class NarrativeFact:
    event_type: str
    target_id: str
    emotion_tag: str
    day: int
    importance: float
```

---

### Ограничения:

* read-only для LLM
* write-only через StateApplicator
* max 2 факта в контексте
* НЕТ semantic search
* НЕТ retrieval по вопросу игрока

---

## 10. LIFE ENGINE

Фоновая симуляция:

* движение
* рутины
* физиология

НЕ принимает решений.

---

## 11. DECISION FREQUENCY

* Event-trigger — мгновенно
* Idle tick — раз в N секунд

---

## 12. EXPLANATION (через DecisionHub)

Explanation НЕ является отдельным слоем.

Это режим DecisionHub:

```python
if context.explanation_mode:
    return DecisionResult(
        intent=Intent.EXPLAIN,
        narrative_facts=top_2_facts
    )
```

---

## 13. LLM СЛОЙ (VERBALIZATION)

### Вход:

```python
VerbalizationContext:
    npc_name
    emotion
    intent
    target
    scene_hint
    narrative_hints  # max 2, только при EXPLAIN
```

---

### Ограничения:

LLM НЕ получает:

* raw input игрока
* reasoning
* скрытые параметры
* полный memory

---

### Задача:

* выразить intent
* сформулировать речь

---

## 14. WORLD PRESSURE ENGINE

НЕ изменяет NPC напрямую.

Работает только через события:

```python
event_bus.publish(Event(...))
```

---

## 15. NPC TIER SYSTEM

Статическая конфигурация:

* Tier 0 — mass NPC
* Tier 1 — minor NPC
* Tier 2 — major NPC

---

### Запрещено:

* runtime upgrade

---

### Допускается:

* controlled awakening через spawn нового NPC

---

## 16. ДЕТЕРМИНИЗМ

* randomness ±10%
* seed фиксируется per session

---

## 17. МАСШТАБ

* целевой: 10–30 NPC
* максимум: ~50

---

## 18. КРИТЕРИЙ УСПЕХА

Игрок ощущает:

* NPC помнит
* NPC объясняет причины
* NPC реагирует последовательно
* NPC остаётся понятным

---

# 19. R1 — MEMORY CORE (ОБНОВЛЁН)

```
R1.1 → R1.2 → R1.3 → R1.4 → R1.5
      + R1.6 NarrativeFacts
      + R1.7 TierConfig
```

---

## R1.6 — NarrativeFacts

* frozen
* max 2
* не участвуют в логике

---

## R1.7 — TierConfig

* static assignment
* no runtime upgrade

---

# 20. R2 — DECISION CORE

## R2.1 NPCState

Добавлено:

* personality_base
* active_traits
* trauma_markers
* narrative_cache

---

## R2.2 DecisionHub

Добавлено:

* trait_modifier
* explanation_mode

---

# 21. R3 — INTEGRATION

* WorldPressure → EventBus
* VerbalizationContext → narrative_hints

---

# 22. СТАРЫЙ ПЛАН — УДАЛЁН

Удалено:

* orchestrator
* LLM-driven логика
* memory как текст
* semantic retrieval
* reasoning через промпты
