# ТЗ: ENIGMA Causal Diagnostic System (CDS)

**Архитектурное решение:** ADR-059  
**Статус:** Этап 1 завершён. Этап 4 (DNA) реализован. Этап 2 (CausalChain) в очереди (расширен до Causal Graph Engine).  
**Спринт:** 40+  
**Приоритет:** Параллельная разработка — не блокирует игровые спринты.  
**Принцип:** Встраивается в `game_launcher.py`. Запускается при каждом старте игры. Пишет один markdown-файл + JSON-граф (новое). Читается LLM, не человеком (markdown), и системой (graph).

---

# 1. НАЗНАЧЕНИЕ CDS (УТОЧНЁННОЕ)

CDS — это не логгер и не пост-мортем отчёт.

CDS =  
**Causal Graph Compiler + System Mirror + Counterfactual Engine**

Он выполняет 3 функции:

1. Регистрирует события (Event Capture Layer)
2. Строит причинно-связанный граф (Causal Layer)
3. Позволяет задавать контрфактические вопросы (Counterfactual Layer)

---

# 2. СТАТУС РЕАЛИЗАЦИИ (АКТУАЛЬНО)

## 2.1 Что реализовано и работает

### 📦 diagnostics/ пакет:

- `pattern_registry.py`  
  → 37 regex-паттернов (decision_score, editor_json_found и др.)

- `causal_observer.py`  
  → пост-мортем анализ `cds_backend.log`  
  → dispatch событий (decision_score + editor_json_found)

- `health_checkers/tick_health.py`  
  → SHI через total_decisions  
  → on_individual_decision() делегат  
  → русская морфология `_pl()`

- `health_checkers/movement_health.py`  
  → per-NPC таблицы  
  → editor_json_locations для SCF-калибровки

- `git_reader.py`  
  → git log -5  
  → MUTATIONS.md (последние 3 записи)  
  → TODO scanning

- `report_renderer.py`  
  → 3 секции (#1/#2/#3)  
  → DNA блок  
  → русская морфология `_pluralize()`

- `dna_metrics.py`  
  → SHI, NPI, OBI, SCF, ADR, CVS  
  → delta tracking  
  → history.jsonl

---

## 2.2 Интеграция

- `game_launcher.py`
  → FileHandler init
  → logging.shutdown() перед экспортом

- `backend/app/main.py`
  → FileHandler
  → logger.info() (LLM server tracking)

- `backend/app/services/npc/decision_hub.py`
  → `[TRACE][DECISION_SCORE]` через logger.info

- `reports/LAST_SESSION.md`
  → перезапись при выходе

- `reports/dna_history.jsonl`
  → исторические DNA снимки

---

## 2.3 Уже решённые баги (Спринт 40)

| Баг | Причина | Фикс |
|-----|--------|------|
| SHI=0% (no decisions) | TickHealthChecker не имел on_individual_decision(), AttributeError глотался try/except | делегат добавлен в TickHealthChecker |
| SHI=0% (double count) | tick_decisions_end дублировал total_ticks через on_decisions_count() | вызов убран; SHI на total_decisions/total_ticks |
| SHI=0% (print loss) | [TRACE][DECISION_SCORE] через print(), невидим для CDS | print → logger.info в decision_hub.py |
| decision_score invisible | нет regex-паттерна | decision_score + editor_json_found паттерны добавлены (37 total) |
| SCF=0.5 false negative | _load_templates fallback при найденном editor JSON | editor_json_found → SCF=1.0 override |
| LLM invisible | llama-server статус через print(), не logger | logger.info добавлен в main.py |
| ObediencePressure=0 | NPC dicts используют "id", не "npc_id" | добавлена проверка n.get("id") в DirectiveInterpretationSubscriber |
| EntityType crash | EntityType не импортирован в world_snapshot_builder.py | импорт добавлен, NPI 0→86% |
| snapshot data loss | snapshot_npc_positions_to_dict не пробрасывал entity_type, initiative_suppression | оба поля добавлены |
| Russian grammar bug | "2 раз" вместо "2 раза" | _pluralize()/_pl() утилиты внедрены |

---

## 2.4 Известные проблемы

- `[R4A_WORKER]` может фильтроваться логгером root namespace  
- требуется валидация через log grep
- NPC координаты thief_shadow — корректны (не CDS ошибка)

---

# 3. НОВАЯ АРХИТЕКТУРА CDS (КРИТИЧЕСКОЕ ОБНОВЛЕНИЕ)

## 3.1 Переход от логгера к графу причинности

CDS теперь НЕ работает как линейный анализ:


LOG → PARSE → METRIC


CDS теперь:


EVENT → OBSERVATION → CAUSAL GRAPH → COUNTERFACTUAL ENGINE


---

# 3.2 Новый уровень: Causal Graph Layer (ЭТАП 2 РАСШИРЕН)

## 3.2.1 Causal Node

python
class CausalNode:
    event_id: str
    timestamp: float
    entity_scope: str

    preconditions: Dict
    postconditions: Dict

    confidence: float


---

## 3.2.2 Causal Edge (новое)

python
class CausalEdge:
    source_event_id: str
    target_event_id: str

    causal_type: str  # direct | indirect | probabilistic
    weight: float     # confidence score


---

## 3.2.3 Graph Construction

text
event → candidate causes → scored edges → causal graph


---

# 3.3 Counterfactual Layer (НОВОЕ)

CDS должен отвечать на вопросы:

* “Что было бы, если событие X не произошло?”
* “Что изменилось бы, если решение NPC было другим?”

python
class CounterfactualQuery:
    anchor_event: Event
    condition: str
    mode: ["remove_event", "invert_decision", "delay_event"]

class CounterfactualResult:
    divergence_score: float
    predicted_state_delta: dict


---

# 3.4 Observation vs Event (РАЗДЕЛЕНИЕ)

text
EVENT = что произошло в мире
OBSERVATION = как CDS это увидел


Из-за LOD и perception layers они НЕ идентичны.

---

# 4. МЕТРИКИ (РЕОРГАНИЗАЦИЯ DNA)

## 4.1 System Metrics

* SHI (System Health Index)
* OBI (Observer Bias Index)
* CVS (Consistency Validation Score)

---

## 4.2 Behavior Metrics

* NPI
* SCF
* ADR

---

## 4.3 Принцип

> Метрики больше не смешиваются между уровнями симуляции.

---

# 5. PATTERN SYSTEM (ОБНОВЛЕНИЕ)

## 5.1 Было

* regex-only PatternRegistry

## 5.2 Стало

python
PatternRegistry = {
    deterministic_rules,
    probabilistic_matchers,
    semantic_fallback (future)
}


---

# 6. ГЛАВНЫЙ АРХИТЕКТУРНЫЙ РИСК (ЗАКРЕПЛЁН)

## CDS может деградировать в:

> “систему, которая красиво объясняет, но неправильно понимает причинность”

---

## Контрмера:

* causal confidence scoring обязателен
* запрещены deterministic causal claims без confidence
* UNKNOWN_CAUSE_BUCKET обязателен

---

# 7. НОВЫЕ ФАЙЛЫ (ДОБАВИТЬ)


diagnostics/
    causal_graph/
        graph_builder.py
        causal_node.py
        causal_edge.py

    counterfactual/
        query_engine.py
        simulator.py


---

# 8. ВЫХОДНЫЕ ДАННЫЕ CDS (ИЗМЕНЕНО)

## 8.1 Было:


reports/LAST_SESSION.md


## 8.2 Стало:


reports/LAST_SESSION.md        (human-readable)
reports/causal_graph.json      (machine-readable)
reports/dna_history.jsonl      (unchanged)


---

# 9. ПЛАН ЭВОЛЮЦИИ

| Этап                           | Статус                  |
| ------------------------------ | ----------------------- |
| Stage 1 MVP                    | DONE                    |
| Stage 1.5 backend integration  | DONE                    |
| Stage 1.6 metrics + fixes      | DONE                    |
| Stage 2 causal chain           | EXPANDED (graph engine) |
| Stage 3 git + mutation reader  | DONE                    |
| Stage 4 DNA metrics            | DONE                    |
| Stage 5 realtime websocket CDS | PLANNED                 |

---

# 10. СТРАТЕГИЧЕСКИЙ ИТОГ

CDS больше не является:

* логгером
* диагностикой
* отчётом

CDS становится:

> **структурой, которая реконструирует причинность внутри сложной симуляции и фиксирует разницу между тем, что произошло, и тем, что могло произойти**

---

# 11. ФИНАЛЬНАЯ ДИАГНОСТИЧЕСКАЯ АКСИОМА

> Если CDS не может объяснить "почему это НЕ произошло" — он ещё не является каузальной системой