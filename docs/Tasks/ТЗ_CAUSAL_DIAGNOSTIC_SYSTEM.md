```markdown
# ENIGMA Causal Diagnostic System (CDS) vNext — STRICT OBSERVABILITY CORE

**Версия:** 4.0 (Reframed Architecture)  
**Назначение:** Детектируемая причинная наблюдаемость системы ENIGMA  
**Принцип:** CDS = измерительный прибор, НЕ интерпретатор, НЕ объяснитель  
**Формат вывода:** `ENIGMA Session State` (3 архитектора + DNA слой)  
**Ключевая гарантия:** 100% детерминированность отчёта при одинаковом логе  

---

# 0. ФУНДАМЕНТАЛЬНАЯ АКСИОМА CDS

CDS НЕ:
- не объясняет “почему”
- не определяет смысл событий
- не классифицирует психологические состояния
- не использует доменные термины как интерпретацию

CDS ДЕЛАЕТ ТОЛЬКО:
- фиксирует события
- связывает причинные ребра
- считает метрики
- показывает отклонения от ожидаемых паттернов

---

# 1. АРХИТЕКТУРА CDS

## 1.1 CORE PIPELINE

```

LOG FILES (raw events)
↓
Event Parser (strict schema validation)
↓
Causal Graph Builder (deterministic edges only)
↓
Metrics Engine (pure math)
↓
Session State Renderer (ENIGMA Session State)

````

---

## 1.2 ЗАПРЕЩЕНО В PIPELINE

- NLP-интерпретации событий
- “психологические причины”
- “архетипические объяснения”
- “фантомные сущности”
- выводы о “смысле системы”

---

# 2. ФОРМАТ СОБЫТИЯ (CANONICAL EVENT MODEL)

```python
@dataclass(frozen=True)
class Event:
    event_id: str
    timestamp: float
    event_type: str

    source_system: str
    target_system: str | None

    npc_id: str | None
    entity_id: str | None

    payload: dict

    causal_parent_id: str | None
````

---

# 3. CAUSAL GRAPH (СТРОГОЕ ПРЕДСТАВЛЕНИЕ)

## 3.1 Узлы

```
Node = Event
```

## 3.2 Ребро

```
Edge:
  from_event_id
  to_event_id
  relation_type: enum[
      TRIGGERS,
      PRODUCES,
      CONSUMES,
      INVALIDATES
  ]
```

---

## 3.3 ЗАПРЕТ

CDS НЕ строит:

* “логические объяснения”
* “семантические связи”
* “интерпретируемые зависимости”

ТОЛЬКО:

* прямые event-to-event связи

---

# 4. METRICS ENGINE (DNA СЛОЙ)

## 4.1 МЕТРИКИ (строго математические)

```text
SHI  = count(DECISION_EVENTS) / tick_count
NPI  = valid_npc_positions / total_npc
OBI  = directive_applied / directive_issued
SCF  = valid_spatial_links / total_spatial_requests
ADR  = todo_count / resolved_issues
CVS  = events_per_minute
```

---

## 4.2 ПРАВИЛО МЕТРИК

* никакой семантики
* никакой оценки (“плохо”, “хорошо”)
* только числа + delta

---

## 4.3 DNA HISTORY

```
dna_history.jsonl
→ append-only
→ no rewriting
→ deterministic replay possible
```

---

# 5. ENIGMA SESSION STATE FORMAT (ОБЯЗАТЕЛЬНЫЙ OUTPUT)

## 5.1 СТРУКТУРА

```markdown
# ENIGMA Session State

## SESSION METADATA
- campaign_id
- player_id
- duration
- tick_count

---

## DNA METRICS
| Metric | Value | Δ |
|--------|------|---|

---

## #1 ARCHITECT (CODE LAYER)
### Active Events:
- EventType ...
- EventType ...

### Causal Edges:
- A → B (TRIGGERS)

### Broken Links:
- unresolved_event_id

---

## #2 ARCHITECT (UI LAYER)
### Spatial Events:
- node resolution status
- fallback usage count

### Render State:
- npc_positions
- missing_nodes

---

## #3 ARCHITECT (SIMULATION LAYER)
### NPC Events:
- DECISION_EVENTS
- MOVEMENT_EVENTS

### Pipeline Status:
- tick_health
- decision_health

---

## CAUSAL BREAKS
- event_id → missing target
- unresolved edges

---

## RAW STATISTICS
- event_count
- edge_count
- orphan_events
```

---

# 6. STRICT RULES ДЕТЕРМИНИЗМА

## 6.1 ОБЯЗАТЕЛЬНО

* одинаковый input log → одинаковый output
* никакой randomness
* никакой LLM-inference внутри CDS core

---

## 6.2 ЗАПРЕЩЕНО

* “догадки о причинах”
* “возможные интерпретации”
* “архетипические выводы”

---

# 7. CAUSAL VALIDATION RULES

## CDS фиксирует только:

### VALID:

```
NPC_DECISION → MOVEMENT_REQUEST
MOVEMENT_REQUEST → NODE_RESOLUTION
NODE_RESOLUTION → POSITION_UPDATE
```

---

### INVALID (НЕ СУЩЕСТВУЕТ В CDS):

```
“NPC испугался”
“NPC решил убежать из-за страха”
“архетип BROKEN активировался”
```

---

# 8. ERROR MODEL

## CDS может фиксировать только:

```
- missing_node
- null_reference
- invalid_transition
- orphan_event
```

---

## НЕ МОЖЕТ:

* объяснять “почему это плохо”
* связывать с психологией
* давать смысловой диагноз

---

# 9. DESIGN GUARANTEE

CDS гарантирует:

### 9.1

Полная воспроизводимость

### 9.2

Нулевая семантическая утечка

### 9.3

Отсутствие онтологического дрейфа внутри CDS

---

# 10. ПРИЧИНА ПЕРЕРАБОТКИ (КРАТКО)

Предыдущая CDS версия:

* содержала интерпретатор внутри наблюдателя
* создавалась “иллюзия понимания”
* разрушала границу между логом и моделью мира

---

# 11. ФИЛОСОФИЯ vNEXT

> “CDS не знает, что происходит.
> CDS знает только, что произошло и как это связано.”

---

# 12. РЕЗУЛЬТАТ

CDS vNext =

```
CAUSAL GRAPH ENGINE
+ METRIC ENGINE
+ STRICT EVENT LOGGER
+ DETERMINISTIC REPORT RENDERER
```

И НЕ БОЛЬШЕ.

---

```
```
