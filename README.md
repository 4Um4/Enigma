# ENIGMA — локальный AI Dungeon Master (Deterministic NPC Engine)

Актуализация README: 2026-04-04
Статус: архитектура зафиксирована, переход к Decision Core

---

## 1. Что это за проект

**Enigma** — это локальная RPG-система нового типа:

> NPC — это не текст.
> NPC — это система числовых состояний, принимающая решения детерминированно.

Игрок взаимодействует с миром свободным текстом или действиями, а система:

```text
Игрок → Event → DecisionHub → NPCState → LLM (речь)
```

---

## 2. Главный принцип системы

```text
Python думает — LLM говорит.
```

* Python:

  * принимает решения
  * считает последствия
  * хранит состояние

* LLM:

  * НЕ думает
  * НЕ принимает решений
  * только озвучивает результат

---

## 3. Цель проекта

Создать систему, в которой NPC:

* ведут себя **причинно-следственно**
* **помнят** действия игрока (через веса)
* **реагируют последовательно**
* остаются **предсказуемыми, но не полностью**

Ограничения:

* локальный запуск
* 7B–13B модели
* ≤ 8 GB VRAM
* ≤ 4k токенов контекста

---

## 4. Архитектурное ядро

```text
Event
  ↓
DecisionHub.compute()     # read-only
  ↓
DecisionResult
  ↓
StateApplicator.apply()   # write-only (atomic)
  ↓
NPCState (source of truth)
  ↓
LLM (verbalization only)
```

---

## 5. Источник истины

### NPCState — единственный source of truth

Содержит:

* emotion
* stress
* intent
* relationship cache
* personality coefficients

Использование:

* DecisionHub читает ТОЛЬКО NPCState
* SceneState получает снимок после обновления

---

### SceneState

НЕ участвует в принятии решений.

Используется только как:

* визуальное состояние сцены
* позиции NPC
* объекты

---

## 6. Event Layer

Любое действие превращается в событие:

```python
Event(
    type="harassment",
    actor="player",
    target="npc_id",
    intensity=0.7
)
```

Фильтрация:

1. Distance
2. Perception (видимость)

→ NPC получают только релевантные события

---

## 7. Decision Hub (ядро интеллекта)

### Свойства:

* чистая функция (read-only)
* без LLM
* работает только с числами

---

### Формула

```python
score(action) =
    (drive_weight * context_relevance)
  + emotion_weight
  + relationship_modifier
  - (fear * risk)
  + randomness(±10%)
```

---

### Выход

```python
DecisionResult:
    intent
    emotion_delta
    stress_delta
    relationship_delta
```

---

## 8. State Applicator

Единственная точка записи в NPCState.

```python
apply(npc_state, decision_result) → new_npc_state
```

Гарантии:

* атомарность
* отсутствие partial updates
* детерминированность

---

## 9. NPCState

Содержит:

* emotion (накопительная)
* stress
* intent (сохраняется до следующего тика)
* relationship cache
* personality параметры

---

## 10. Relationship System

### Хранение:

* `RelationshipStore` (персистентный слой)
* JSON / будущая БД

### В NPCState:

* только кэш

---

### Пример:

```json
{
  "player→npc": {
    "trust": 35,
    "fear": 10,
    "debt": 0
  }
}
```

---

## 11. Memory = веса, не текст

Память влияет только на числа:

```text
player_help → trust +15
player_hit  → trust -20
```

Нет:

* retrieval
* embedding поиска
* текстовых воспоминаний в runtime

---

## 12. Life Engine

Фоновая симуляция:

* движение
* рутины
* физиология

НЕ принимает решений.

---

## 13. Частота решений

* Event-trigger — мгновенно
* Idle tick — раз в N секунд

---

## 14. LLM слой (verbalization)

### Вход:

```python
VerbalizationContext:
    npc_name
    emotion
    intent
    target
    scene_hint  # ≤ 100 токенов
```

---

### Ограничения:

LLM НЕ получает:

* raw input игрока
* память
* reasoning
* скрытые параметры

---

### Задача:

Только:

* речь
* короткое действие

---

## 15. Детерминизм

* randomness: ±10%
* seed фиксируется на сессию

---

## 16. Масштаб

* целевой: 10–30 NPC
* максимум: ~50

---

## 17. Текущее состояние разработки

### Завершено

* Memory Core (R1):

  * MemoryManager
  * WorkingMemory
  * Importance + decay
  * RelationshipStore
  * ContradictionResolver

---

### В процессе

* Decision Hub (R2)
* NPCState как централизованная модель

---

### Частично реализовано (legacy → будет заменено)

* npc_cognition.py
* psyche_engine.py
* reaction_priority.py

---

## 18. Структура проекта (сокращённо)

```text
backend/
  app/
    services/
      game_loop.py
      action/
      npc/
      memory/
      events/
      simulation/
      scene/
```

---

## 19. Runtime

```text
start_enigma.bat
  ↓
LLM server (127.0.0.1:8080)
  ↓
FastAPI backend (127.0.0.1:8000)
  ↓
Frontend (127.0.0.1:3000)
```

---

## 20. Ключевое отличие от других систем

Enigma не пытается сделать NPC "умными" через LLM.

Она делает их:

> **предсказуемыми системами с памятью и характером**

LLM — лишь голос.

---

## 21. Как должна работать система

```text
Игрок действует
↓
NPC интерпретирует событие через характер
↓
учитывает прошлый опыт (веса)
↓
принимает решение (DecisionHub)
↓
реакция становится частью состояния
↓
LLM выражает это словами
```

---

## 22. Критерий успеха

Игрок чувствует:

* NPC помнит
* NPC не противоречит себе
* NPC реагирует логично
* NPC можно понять и "читать"

---

## 23. Что считается ошибкой архитектуры

* LLM принимает решения
* память как текст
* reasoning через промпты
* скрытая логика вне Python

---

## 24. Направление развития

Следующий этап:

```
R2 → Decision Hub
```

---

## 25. Итог

```text
Это не чат-бот.
Это не генератор историй.

Это симулятор поведения.
```
