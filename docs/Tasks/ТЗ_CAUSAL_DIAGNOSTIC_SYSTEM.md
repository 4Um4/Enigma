path: /project/docs/Tasks/ТЗ_CAUSAL_DIAGNOSTIC_SYSTEM.md
Назначение: Техническое задание на систему каузальной диагностики (CDS) для обеспечения наблюдаемости LLM-архитекторов.
Зависимости: game_launcher.py, diagnostics/, reports/
Основные сущности: CausalObserver, LAST_SESSION.md, PatternRegistry, CausalChainBuilder

# ТЗ: ENIGMA Causal Diagnostic System (CDS)

**Архитектурное решение:** [ADR-059](../audits/ADR-059_IMPACT.md)
**Статус:** Этап 1 завершён. Этап 4 (DNA) реализован. Этап 2 (CausalChain) в очереди.
**Спринт:** 39.
**Приоритет:** Параллельная разработка — не блокирует игровые спринты.
**Принцип:** Встраивается в `game_launcher.py`. Запускается при каждом старте игры. Пишет один markdown-файл. Читается LLM, не человеком.

---

## СТАТУС РЕАЛИЗАЦИИ (актуально на 2026-05-19)

### Что реализовано и работает:

**Файлы пакета `diagnostics/`:**
- `pattern_registry.py` — 30+ откалиброванных regex-паттернов (включая `[\w.]+` для EventType)
- `causal_observer.py` — пост-мортем читатель `cds_backend.log`, без перехвата stdout
- `health_checkers/tick_health.py` — счётчики тиков, LLM-вызовов, decisions + `on_individual_decision()`
- `health_checkers/movement_health.py` — per-NPC таблица: intent, координаты, traversal
- `git_reader.py` — git log -5, MUTATIONS.md (последние 3 записи), TODO-скан через PowerShell
- `report_renderer.py` — три секции (#1/#2/#3) + секция DNA
- `dna_metrics.py` — 6 метрик: SHI, NPI, OBI, SCF, ADR, CVS + дельта от прошлой сессии + history.jsonl

**Интеграция:**
- `game_launcher.py` — инициализация `FileHandler` в процессе Pygame, `logging.shutdown()` перед экспортом
- `backend/app/main.py` — инициализация `FileHandler` в подпроцессе Uvicorn (общий файл)
- `reports/LAST_SESSION.md` — перезаписывается при каждом выходе из игры
- `reports/history/` — архив по дате
- `reports/dna_history.jsonl` — история DNA-снимков для дельт

**Что работает в отчёте (Этап 1.5):**
- Кампания и игрок ✅
- Координаты всех 6 NPC ✅
- LLM-вызовы и ответы (R4A_WORKER) ✅
- Решения NPC (DECISION_HUB) ✅
- Директивы и ObediencePressure ✅
- TODO-файлы ✅
- git log ✅
- MUTATIONS.md ✅
- DNA-таблица с интерпретацией и дельтами ✅
- Spatial fallback детектирование ✅
- node_not_found детектирование ✅

### Решённая архитектурная проблема: источник данных для CDS (Этап 1.5)

**Проблема:** Backend работает через DirectBridge (импорт в тот же процесс). Ключевые события шли через `print()` в stdout, который нельзя перехватить без поломки SSE.

**Решение (Реализовано):**
Пост-мортем анализ через общий лог-файл `backend/logs/cds_backend.log`. Оба процесса (Pygame и Uvicorn) пишут в него через стандартный `logging.FileHandler`. CDS читает файл после завершения игры.

**Выполненные шаги:**
1. В `game_launcher.py` добавлен `FileHandler` для корневого логгера с уровнем `INFO`.
2. В `backend/app/main.py` добавлен `FileHandler` для подпроцесса Uvicorn.
3. Критические `print()` заменены на `logger.info()`:
   - `backend/app/services/npc/life_engine.py` — `[TICK_DECISIONS]`
   - `backend/app/services/integration/world_snapshot_builder.py` — `[TRACE][SNAPSHOT]`
   - `backend/app/services/player_session_service.py` — `[SESSION_LOADED]`
   - `frontend/game_screen.py` — `[IDLE_TICK]`
   - `backend/app/services/npc/decision_hub.py` — `[DECISION_HUB]` (с `debug` на `info`)
   - `backend/app/services/npc/state_applicator.py` — `[STATE_APPLIED]` (с `debug` на `info`)
4. LLM-телеметрия в `backend/app/services/llm/router.py` переведена на `_root_logger.info()` (чтобы обойти фильтрацию дочерних логгеров).
5. `CausalObserver` переписан на пост-мортем чтение файла вместо `TeeStream`.

### Известные проблемы (требуют фикса в следующем спринте)

**SHI=0% при наличии решений:** Метрика `Decisions > 0` показывает 0, хотя NPC принимают решения. Причина: `[R3_DIRECT] 0 decisions` (маркер DM-фрейма) перезаписывает счётчик `decisions_nonzero_ticks`, обнуляя его каждый тик. Требуется разделение: R3_DIRECT считает только DM-фокус, а `on_individual_decision()` считает реальные решения NPC.

### Что осталось по этапам:

| Этап | Статус | Описание |
|------|--------|----------|
| Этап 1 MVP | ✅ DONE | Три секции, git, TODO, MUTATIONS |
| Этап 1.5 | ✅ DONE | FileHandler в backend → CDS читает post-mortem |
| Этап 2 | ⬜ ОЧЕРЕДЬ | CausalChainBuilder: связать события в цепи по NPC |
| Этап 3 | ✅ DONE | Git Reader + MUTATIONS parser |
| Этап 4 | ✅ DONE | DNA-метрики: SHI, NPI, OBI, SCF, ADR, CVS |
```