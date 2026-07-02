# TZ-INFRA-1: Infrastructure Foundation for MVP

**Версия ТЗ:** 1.0
**Дата:** 2026-06-29
**Спринты:** S98 (P0), S99 (P1), S100+ (P2)
**Статус:** Approved for implementation
**Предыдущий снимок:** V.0.5.3.2.7_Не_хватает_соединительной_ткани
**Текущий снимок:** V.0.5.3.2.8_Не_хватает_соединительной_ткани

---

## 1. Контекст

V.0.5.3.2.7 закрыла архитектурные долги (ТЗ-04 Spatial Authority, ТЗ-10 Pure Reducer, ADR-RCG routing через SceneChange). V.0.5.3.2.8 подтвердила: SHI=100%, PFI=0%, Causal Drift D локализован в `_compile_full_movement` (path blocked parity).

Но **6 инфраструктурных проблем** блокируют устойчивую разработку MVP «Люся»:

1. Нет CI → любая регрессия ловится только локально (56→65 failed между v7 и v8 — доказательство)
2. Нет mypy → type confusion при рефакторинге (DEBT-310.2 подпроблема 3 — пример)
3. AppAgent засоряет репо (1666 строк мёртвого кода)
4. Legacy dict растёт (59 точек двойной истины `from_legacy`/`write_to_legacy`/`state.hp`)
5. GameLoopBridge нарушает инкапсуляцию (прямой доступ к `_tick_scene`, `asyncio.run()` per turn)
6. Нет архитектурного QUICKSTART — порог входа для нового контрибьютора = недели

## 2. Цель

Создать инфраструктурный фундамент, который сделает разработку MVP «Люся» устойчивой к регрессиям и доступной для контрибьюторов.

## 3. Не-цели

- Не закрывает Causal Drift D (отдельная задача — ADR-DRIFT-D)
- Не делает декомпозицию `tick_orchestrator.py` (отдельная задача — DEBT-GOD-OBJECT)
- Не внедряет WorldScheduler (отдельная задача — ТЗ-09)
- Не закрывает регрессию тестов +9 failed (отдельная задача — DEBT-TEST-REGRESSION)

## 4. Актуальность проблем (по состоянию на V.0.5.3.2.8)

| # | Проблема | Статус | Доказательство |
|---|---|---|---|
| 1 | Нет CI/CD | ❌ АКТУАЛЬНО | `.github/` не существует. 109 test files, 23 533 строк тестов без автоматического запуска |
| 2 | GameLoopBridge — архитектурный запах | ❌ АКТУАЛЬНО | `frontend/game_loop_bridge.py:192,200` — `asyncio.run()` на каждый turn. `:256` — `self._loop.scene_manager.apply_changes()` — прямой доступ к internal |
| 3 | Legacy NPC dict | ❌ АКТУАЛЬНО | 59 совпадений `from_legacy`/`write_to_legacy`/`state.hp` в `backend/app/`. `state.hp` deprecated, но активно читается в `state_interpreter.py:216,228`, `phase_6_avatar.py:86`, `player_avatar_service.py:249` |
| 4 | AppAgent мёртвый код | ❌ АКТУАЛЬНО | 12 .py файлов, 1666 строк. 0 импортов из `backend/app/` или `frontend/`. LICENSE + README.md + config.yaml — отдельный проект |
| 5 | Нет mypy | ❌ АКТУАЛЬНО | Нет `mypy.ini`, нет `.mypy.ini`, нет `mypy` в `pyproject.toml`. При 102k LOC Python с frozen dataclass — критично |
| 6 | Нет QUICKSTART | ⚠️ ЧАСТИЧНО | В README есть `## Quick Start` (7 строк: install + run), но это установка, не понимание архитектуры. `tick_orchestrator.py` 3363 строк без руководства |
| 7 | Фаза 7 — gap в нумерации | ✅ НЕАКТУАЛЬНО | Фаза 7 существует: `_phase_7_windup_resolution` (строки 457, 2031). Execution Gate для ADR-O-310 (Windup). Gap закрыт в S95/S96 |

**Итог:** 6 из 7 проблем актуальны. Проблема 7 уже решена.

---

## 5. Патч Set A — CI/CD Foundation (P0)

### A.1: GitHub Actions workflow

**Файл:** `.github/workflows/test.yml` (новый)

**Требования:**
- Trigger: push на любую ветку + pull request
- Matrix: Python 3.11, 3.12 (project requires ≥3.11)
- OS: ubuntu-latest (Linux, не Windows — для воспроизводимости)
- Steps:
  1. Checkout
  2. Setup Python
  3. `pip install -r backend/requirements.txt`
  4. `pip install pymorphy3` (не в requirements — известный долг, закрывается в B.2)
  5. `cd backend && python -m pytest tests/ --tb=short --junitxml=test_results.xml`
  6. Upload test_results.xml as artifact
  7. `python scripts/lint_wall_clock.py` (§15 enforcement)

**Не запускать SUPERBOX в этом workflow** — долго, отдельно (см. A.2).

**Критерий готовности:** push → green checkmark в GitHub. Red — блокирует merge.

### A.2: SUPERBOX regression gate

**Файл:** `.github/workflows/superbox.yml` (новый)

**Требования:**
- Trigger: push на `V.0.5.3.*` ветки + manual dispatch
- Steps:
  1. Запуск `python -m tests.sandbox.SUPERBOX.run drift replay_determinism` (timeout 5 min)
  2. Парсинг output на `[DRIFT][D]` / `[DRIFT][C]` / `[DRIFT][E]`
  3. Fail если есть structural drift

**Не запускать `long_horizon`** — >90s, timeout.

**Критерий готовности:** Causal Drift D виден в CI (сейчас — только локально).

### A.3: pytest конфигурация cleanup

**Файлы:** `backend/pytest.ini` + `backend/pyproject.toml`

**Требования:**
- Удалить дублирование конфигурации (сейчас оба файла содержат `[tool:pytest]`)
- Оставить только `pyproject.toml` (PEP 621 standard)
- Добавить `--strict-markers` (уже есть в pytest.ini, нет в pyproject)
- Добавить `--ignore=backend/tests/sandbox/test_causal_bridge_integration.py` (collection error — `location_graph` удалён, тест ещё импортирует)
- Исправить `test_spatial_service.py` collection error (`compile_graph` возвращает 4 значения, тест ожидает 3)

**Критерий готовности:** `pytest --collect-only` — 0 errors.

---

## 6. Патч Set B — Code Cleanup (P1)

### B.1: Удаление AppAgent

**Файлы:** удалить `backend/AppAgent/` целиком

**Что удалить:**
- 12 .py файлов (1666 строк)
- LICENSE, README.md, config.yaml
- assets/ директория

**Действие:**
```bash
git rm -r backend/AppAgent/
```

**Обоснование:** 0 импортов из `backend/app/` или `frontend/`. Посторонний проект (CHI 2025 research), засоряет репозиторий.

**Критерий готовности:** `find . -path "*AppAgent*" -name "*.py"` → пусто.

### B.2: pygame в requirements.txt

**Файл:** `backend/requirements.txt`

**Было:**
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.9.2
pydantic-settings==2.5.2
python-multipart==0.0.9
psutil==6.0.0
pypdf==5.1.0
httpx==0.28.1
aiohttp==3.10.11
pytest==8.3.3
pymorphy3
```

**Стало:**
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.9.2
pydantic-settings==2.5.2
python-multipart==0.0.9
psutil==6.0.0
pypdf==5.1.0
httpx==0.28.1
aiohttp==3.10.11
pytest==8.3.3
pymorphy3==0.2.0
pygame==2.6.1
```

**Критерий готовности:** `pip install -r backend/requirements.txt` на чистой машине → `python game_launcher.py` запускается без `ModuleNotFoundError: pygame`.

**Критерий готовности:** `start_llm.bat` и `config.py` указывают на одну модель.

---

## 7. Патч Set C — Type Safety (P1)

### C.1: mypy configuration

**Файл:** `backend/pyproject.toml` (добавить секцию)

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_untyped_decorators = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
warn_unreachable = true
show_error_codes = true

# Исключения: тесты и sandbox (не production код)
[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

[[tool.mypy.overrides]]
module = "tests.sandbox.*"
ignore_errors = true
```

### C.2: mypy в CI

**Файл:** `.github/workflows/test.yml` (добавить step)

```yaml
- name: Type check (mypy)
  run: |
    pip install mypy
    cd backend && mypy app/ --strict
```

**Критерий готовности:** `mypy app/ --strict` — 0 errors в production коде (tests/sandbox исключены).

### C.3: Поэтапное внедрение

**Не запускать mypy strict сразу на всём проекте.** Это даст 1000+ errors. Вместо этого — поэтапно:

1. **Этап 1:** `mypy app/domain/` — domain layer (DTOs, enums, dataclasses)
2. **Этап 2:** `mypy app/models/` — data models
3. **Этап 3:** `mypy app/services/state/` — persistence layer
4. **Этап 4:** `mypy app/services/npc/` — NPC pipeline
5. **Этап 5:** `mypy app/services/` — все services
6. **Этап 6:** `mypy app/` — весь backend

Каждый этап — отдельный commit. CI сначала warns, потом fails.

**Критерий готовности этапа:** 0 mypy errors в соответствующей директории.

---

## 8. Патч Set D — Legacy NPC Dict Migration (P2)

### D.1: Inventory legacy usage

**Файл:** `docs/audits/ADR-LEGACY-IMPACT.md` (новый)

**Действие:** Задокументировать все 59 точек использования `from_legacy`/`write_to_legacy`/`state.hp`:

- Где читается `state.hp` (deprecated) вместо `body_state["current_hp"]` (canonical)
- Где `NPCStateAdapter.from_legacy` — точки входа в pipeline
- Где `write_to_legacy` — точки выхода в persistence

**Текущие точки чтения `state.hp` (deprecated):**
- `backend/app/services/verbalization/state_interpreter.py:216,228`
- `backend/app/services/game_loop/phase_6_avatar.py:86`
- `backend/app/services/player_avatar_service.py:249`

### D.2: Этапы миграции (без big-bang)

1. **Этап 1:** Убрать `state.hp` чтение из `state_interpreter.py:216,228` → читать `body_state["current_hp"]`
2. **Этап 2:** Убрать `state.hp` из `phase_6_avatar.py:86` → `body_state["current_hp"]`
3. **Этап 3:** Убрать `state.hp` из `player_avatar_service.py:249` → `body_state["current_hp"]`
4. **Этап 4:** Помечить `NPCState.hp` как `@deprecated` в `npc_state.py`
5. **Этап 5:** Через 2 спринта — удалить поле `hp` из `NPCState`

**Критерий готовности:** `grep -rn "state\.hp\b" backend/app/` → 0 (кроме `npc_state.py` deprecated поля).

---

## 9. Патч Set E — GameLoopBridge Refactor (P2)

### E.1: Eliminate `asyncio.run()` per turn

**Файл:** `frontend/game_loop_bridge.py`

**Проблема:** `asyncio.run(_collect())` (строка 192) и `pool.submit(asyncio.run, _collect())` (строка 200) создают новый event loop на каждый ход игрока.

**Решение:** Event loop reuse pattern:
- Один persistent event loop в отдельном потоке
- `asyncio.run_coroutine_threadsafe(coro, loop)` для вызовов из sync кода
- Loop живёт всё время работы игры, не пересоздаётся

### E.2: Eliminate `_tick_scene` access

**Файл:** `frontend/game_loop_bridge.py:256`

**Проблема:** `self._loop.scene_manager.apply_changes(campaign_id, changes, scene_state)` — прямой доступ к internal `scene_manager` через `_loop`.

**Решение:** Добавить в `GameLoop` public method:

```python
# backend/app/services/game_loop/__init__.py
def apply_changes(self, campaign_id: str, changes: list, scene_state: dict) -> None:
    """Public API for frontend bridge — no internal access."""
    self.scene_manager.apply_changes(campaign_id, changes, scene_state)
```

И в bridge:

```python
# Было:
self._loop.scene_manager.apply_changes(campaign_id, changes, scene_state)
# Стало:
self._loop.apply_changes(campaign_id, changes, scene_state)
```

**Критерий готовности:** `grep "_loop\.scene_manager\|_loop\._tick_scene" frontend/` → 0.

---

## 10. Патч Set F — QUICKSTART (P1)

### F.1: Архитектурный QUICKSTART документ

**Файл:** `docs/QUICKSTART.md` (новый)

**Структура:**

1. **«Один ход игрока» — end-to-end trace** (200 строк)
   - Игрок пишет «подойди к Люсе»
   - Phase 1: IntentCompressor → ActionType.MOVE
   - Phase 2: EventBus → EventDTO
   - Phase 3: MemoryManager.apply
   - Phase 4: TopicExtractor
   - Phase 5: DecisionHub → CommunicationIntent (через action_intent_bridge)
   - Phase 6: IntentEventAdapter → EventDTO
   - Phase 7: Windup Execution Gate
   - Phase 8: Handlers → StateDeltas
   - Phase 9: WorldSnapshotBuilder
   - Phase 10: Persistence
   - Что видит игрок (world_snapshot)

2. **«Карта файлов»** — какие файлы читать первыми
   - `tick_orchestrator.py` — phases (но 3363 строк, не читать целиком)
   - `decision_hub.py` — scoring
   - `life_engine.py` — NPC tick
   - `scene_state_manager.py` — commit boundary

3. **«Debug triage»** — если что-то сломалось, куда смотреть
   - `reports/LAST_SESSION.md` — DNA метрики
   - `backend/logs/cds_backend.log` — pipeline traces
   - `scripts/lint_wall_clock.py` — §15 violations
   - SUPERBOX `replay_determinism` — Causal Drift

4. **«Глоссарий»** — 20 ключевых терминов
   - SSOT, ADR, DTO, DRF Bus, KernelRNG, L1Chronicle, TraversalState, и т.д.

**Критерий готовности:** Новый контрибьютор (человек или LLM) читает QUICKSTART за 30 минут и понимает, как работает один ход.

---

## 11. Сводная таблица ТЗ

| Патч | Приоритет | Время (сессии) | Зависимости |
|---|---|---|---|
| A.1 GitHub Actions test | P0 | 1 | — |
| A.2 SUPERBOX gate | P0 | 1 | A.1 |
| A.3 pytest config cleanup | P0 | 1 | — |
| B.1 Удалить AppAgent | P1 | 0.5 | — |
| B.2 pygame в requirements | P1 | 0.1 | — |
| B.3 LLM path Qwen→Gemma | P1 | 0.1 | — |
| C.1 mypy config | P1 | 0.5 | — |
| C.2 mypy в CI | P1 | 0.5 | C.1, A.1 |
| C.3 mypy поэтапно | P2 | 3-5 | C.1 |
| D.1 Legacy inventory | P2 | 1 | — |
| D.2 Legacy миграция | P2 | 3-5 | D.1 |
| E.1 asyncio.run refactor | P2 | 2 | — |
| E.2 _tick_scene encapsulation | P2 | 1 | — |
| F.1 QUICKSTART doc | P1 | 2 | — |

**Итого:** ~15-20 сессий = ~2-3 недели при темпе 6 сессий/неделю.

---

## 12. Порядок внедрения

### Спринт S98 (P0, 3-4 сессии)

1. A.1 + A.2 + A.3 — CI/CD foundation
2. B.1 + B.2 + B.3 — быстрый cleanup (1 сессия)
3. Запустить CI → увидеть реальное состояние тестов
4. Зафиксировать baseline: сколько тестов проходит, сколько падает

### Спринт S99 (P1, 4-5 сессий)

5. C.1 + C.2 — mypy config + CI integration
6. F.1 — QUICKSTART документ
7. C.3 Этап 1-2 — mypy на domain + models

### Спринт S100+ (P2, параллельно с MVP)

8. D.1 + D.2 — Legacy миграция
9. E.1 + E.2 — GameLoopBridge refactor
10. C.3 Этап 3-6 — mypy на остальной код

---

## 13. Критическое предупреждение

**TZ-INFRA-1 не блокирует MVP «Люся».** Но без него:

- Causal Drift D (когда починят) может вернуться незамеченным
- Любой refactor (включая фикс Causal Drift D) рискует сломать 65+ тестов
- Новый контрибьютор (если будет) потратит недели на onboarding
- Type confusion будет повторяться (как в DEBT-310.2 подпроблема 3)

**Рекомендация:**
- S98 (CI/CD + cleanup) — **обязательно до MVP**
- S99 (QUICKSTART + mypy) — желательно
- S100+ (Legacy + Bridge) — можно после MVP

---

## 14. Критерии готовности TZ-INFRA-1

### S98 (P0) — обязателен

- [ ] `.github/workflows/test.yml` существует и green на push
- [ ] `.github/workflows/superbox.yml` существует и green на `V.0.5.3.*` push
- [ ] `pytest --collect-only` — 0 errors
- [ ] `backend/AppAgent/` удалён
- [ ] `pygame==2.6.1` в `requirements.txt`
- [ ] `config.py:49-51` указывает на Gemma, не Qwen

### S99 (P1) — желательно

- [ ] `mypy app/ --strict` — 0 errors (после C.3 Этап 1-2)
- [ ] `docs/QUICKSTART.md` существует
- [ ] Новый контрибьютор (LLM) читает QUICKSTART и может объяснить pipeline за 30 мин

### S100+ (P2) — параллельно с MVP

- [ ] `grep -rn "state\.hp\b" backend/app/` → 0 (кроме deprecated)
- [ ] `grep "_loop\.scene_manager\|_loop\._tick_scene" frontend/` → 0
- [ ] `asyncio.run()` не вызывается per-turn в `game_loop_bridge.py`

---

## 15. Связанные документы

- `docs/audits/ADR-DRIFT-D` — Causal Drift D (отдельная задача)
- `docs/audits/ADR-LEGACY-IMPACT.md` — Legacy inventory (D.1)
- `docs/QUICKSTART.md` — архитектурный QUICKSTART (F.1)
- `docs/Tasks/ТЗ/03_KNOWN_ISSUES_AND_BUGS.md` — баг-реестр
- `reports/LAST_SESSION.md` — текущее состояние симуляции

---

## 16. ADR-PRE-FLIGHT CHECKLIST

Перед внедрением каждого патча:

- [ ] PIPELINE_OBJECT определён
- [ ] OWNER определён
- [ ] CREATE → READ → TRANSFORM → APPLY → COMMIT → PROJECT реконструирован
- [ ] Single Source of Truth проверен
- [ ] Ownership boundaries проверены
- [ ] DTO и runtime contracts проверены
- [ ] FAIL_STAGE идентифицирован
- [ ] H1/H2/H3 с confidence построены
- [ ] FIX_SCOPE выбран минимальным
- [ ] Документы обновлены
- [ ] Локальные тесты/SUPERBOX пройдены
- [ ] Commit на named branch

---

**TZ-INFRA-1 готов к внедрению.**

Начать с S98: A.1 GitHub Actions → A.3 pytest cleanup → B.1 AppAgent removal → B.2 pygame → B.3 LLM path → A.2 SUPERBOX gate.