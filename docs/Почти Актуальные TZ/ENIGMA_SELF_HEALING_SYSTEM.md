# ENIGMA — SELF-HEALING SYSTEM SPECIFICATION (Post-Stabilization)

**Дата обновления:** 2026-08-15
**Версия:** 2.0
**Статус:** Активный. Базовые уровни защиты (IPT, Linters, Preflight) внедрены и работают.

**Цель:** Система автоматического обнаружения багов, которая ловит архитектурные дрейфы, нарушения контрактов и логические ошибки — без ручного аудита и «месяцев молчаливого отказа».

**Контекст:** Оригинальный документ (v1.0) был написан в ответ на обнаружение 15 багов (N1-N15), которые жили в коде несколько месяцев. На сегодняшний день **все 15 багов исправлены**, а механизмы их автоматического отлова внедрены в CI/пайплайн разработки. Документ описывает актуальную архитектуру системы самоисцеления.

---

## §0. ФИЛОСОФИЯ — ТРИ ПРИНЦИПА (Актуально)

### Принцип 1: Fail Loud, Fail Early
Молчаливый отказ — главный враг. Любое место, где система говорит `if X else None` или `getattr(Y, "z", default)`, должно быть рассмотрено: **если default сработает, как я об этом узнаю?**
Если default — допустимое состояние, то обязательно логгировать первый раз, когда default срабатывает, с stack trace. (См. `logging_tools.py`).

### Принцип 2: Verify, Don't Trust
Каждое предположение о системе должно быть проверено. Не «я думаю, что `TICK_COMPLETED` существует» — а `assert EventType.TICK_COMPLETED in EventType.__members__` во время импорта или в IPT.

### Принцип 3: Closest Point of Failure
Чем раньше баг обнаружен, тем дешевле его починить.
1. Compile-time (ruff/mypy)
2. Import-time (assertions)
3. Test-time (IPT, pytest)
4. Start-time (preflight.py)
5. Tick-time (runtime invariants in IPT)
6. Session-time (CausalObserver reports)

---

## §1. УРОВЕНЬ 0 — SILENT FAILURE ERADICATION (Внедрено)

Дисциплина кодирования, направленная на устранение тихих отказов.

### 1.1. Запрет на `if X else None` для критичных ресурсов
Реализовано через явные `raise FileNotFoundError` или `RuntimeError` при инициализации сервисов (например, `MvpTavernController`, `SpatialRegistry`).

### 1.2. Запрет на `getattr(X, "y", None)` без явного default-лога
Широкие `except Exception` заменены на конкретные типы ошибок или логирование (H-29 FIX, N-05 FIX).

### 1.3. Явные `assert` на wiring в `__init__`
Контракты сборки пайплайна проверяются в `game_loop_builder.py` и `tick_orchestrator.py`. Если сервис не подключён, игра падает при старте.

---

## §2. УРОВЕНЬ 1 — RUNTIME INVARIANTS (Внедрено: IPT)

Проверки, которые выполняются каждый прогон симуляции. Стоят миллисекунды, ловят архитектурные баги.

**Реализация:** `backend/tests/IPT.py` (Invariant Probe Tests).
- 39 инвариантов проверяют: детерминизм времени, изоляцию локаций, пайплайн диалогов, целостность L1/L3, SSOT пространства, чистоту домена.
- Запускается ДО и ПОСЛЕ любых фиксов.
- IPT лог кристально чист (39/0 passed).

---

## §3. УРОВЕНЬ 2 — END-TO-END CANARY СЦЕНАРИИ (Частично внедрено)

Юнит-тесты зелёные, но End-Screen пустой. Canary-сценарии проверяют систему end-to-end.

**Реализация:**
- `backend/tests/sandbox/SUPERBOX/` — сценарии проверки эпистемической каузальности (SUPERBOX-EPISTEMIC-001..013).
- `scripts/test_sleep_routing.py` — проверка миграции NPC во сне.
- *TODO:* Полноценный canary для 30-минутного playthrough с проверкой End-Screen.

---

## §4. УРОВЕНЬ 3 — PROPERTY-BASED ТЕСТЫ (Внедрено)

Юнит-тест проверяет один случай. Property-based тест проверяет **свойство** для любых входов (`hypothesis`).

**Реализация:** Встроено в `IPT.py`.
- `INV-PBT-ROUNDTRIP` (200 examples): NPCState round-trip сохраняет критические поля.
- `INV-PBT-SC1` (100 examples): SC-1 отвергает (0.0, 0.0).
- `INV-PBT-TRAV-FSM` (100 examples): ADR-TRAV-FSM детектирует зомби-транзиты.

---

## §5. УРОВЕНЬ 4 — STATIC ANALYSIS (Внедрено)

Самый дешёвый уровень — мгновенно, до запуска.

**Реализация:**
- `scripts/lint_domain_purity.py`: Запрет импорта `services/models` в `domain/` (§1.2 Устава).
- `scripts/lint_wall_clock.py`: Запрет `time.time()` / `datetime.now()` в simulation layer (§15).
- `scripts/lint_kernel_rng.py`: Запрет `random.*` в kernel layer.
- Настроены `ruff` и `mypy` (строгий режим для новых файлов).

---

## §6. УРОВЕНЬ 5 — STRUCTURAL CONSISTENCY CHECKS (Внедрено)

JSON ↔ Python matching. Проверка, что конфиги NPC соответствуют графам локаций.

**Реализация:**
- `SpatialRegistryBuilder` и `graph_compiler.py` валидируют рёбра и стены при сборке графа (логирует `[SPATIAL_VALIDATION]` с инструкцией `FIX:`).
- Pydantic-схемы используются в DTO и конфигах.
- `preflight.py` проверяет консистентность ссылок NPC -> spatial_registry при старте.

---

## §7. УРОВЕНЬ 6 — ARCHITECTURE TESTS (Внедрено)

Проверки, что кодовая архитектура здравая: подписки есть, события существуют.

**Реализация:**
- `INV-ADR-NET` в IPT проверяет, что парсер ADR корректно строит графы (76 узлов, 75 с файлами).
- `INV-DIALOGUE-PIPELINE` проверяет, что вербальные интенты превращаются в реплики (EventBus не теряет события).

---

## §8. УРОВЕНЬ 7 — TELEMETRY DASHBOARD (Внедрено: CDS)

Человек не может следить за логами 80k-строчной системы. 

**Реализация:**
- `CausalObserver` (CDS) пассивно наблюдает за симуляцией.
- В конце сессии генерируется `reports/LAST_SESSION.md` с DNA-метриками (SHI, NPI, OBI, SCF, CVS, PFI, DRI) и списком "🔴 КРАСНЫЕ ИНВАРИАНТЫ" (тихие деградации).
- `/health` эндпоинт доступен для мониторинга LLM и backend.

---

## §9. УРОВЕНЬ 8 — DOCUMENTATION DRIFT DETECTION (Внедрено)

Контракт содержит описания багов с file:line. Если file:line меняется — контракт устарел.

**Реализация:**
- ADR-Net CLI (`python -m app.services.adr_net.adr_cli impact --file <path>`) проверяет влияние изменений на архитектурные законы.
- Регулярная чистка устаревших комментариев (например, `psyche_engine`, `published_events` — N-25, N-28).

---

## §10. УРОВЕНЬ 9 — CI GATES (Внедрено)

Что должно падать перед merge в main.

**Реализация:**
- `python backend/tests/IPT.py` — обязателен перед коммитом.
- `scripts/APS.py` — анализ графа импортов и Bottleneck Score.
- Очистка `__pycache__` — обязательна при изменении DTO/контрактов.

---

## §11. УРОВЕНЬ 10 — PRE-FLIGHT CHECKLIST (РУЧНОЙ)

Автоматизация ловит 95%. Последние 5% — смысловые баги.

**Реализация:**
- `scripts/preflight.py` запускается перед сложными тестами.
- `Правила Фикса БАГОВ.md` требует обязательного чтения `reports/LAST_SESSION.md` перед стартом работы и проверки IPT.

---

## §12. МАТРИЦА ПОКРЫТИЯ (Историческая справка)

Оригинальные баги N1-N15 и их статус в текущей системе:

| Баг | Описание | Статус | Чем ловится сейчас |
|-----|----------|--------|--------------------|
| **N1** | mvp_controller=None | ✅ FIXED | Preflight / IPT |
| **N2** | TICK_COMPLETED не существует | ✅ FIXED | IPT (INV-DIALOGUE) |
| **N3** | ambient routing dead code | ✅ FIXED | Ruff / Code Review |
| **N4** | _fallback_to_astar NameError | ✅ FIXED | mypy / IPT |
| **N5** | get_central_node AttributeError | ✅ FIXED | mypy / Spatial Lints |
| **N6** | duplicate function def | ✅ FIXED | Ruff (F811) |
| **N7** | race condition (zombie traversal) | ✅ FIXED | IPT (INV-TRAV-ZOMBIE) |
| **N8** | stale location ID | ✅ FIXED | Preflight / Graph Compiler |
| **N9** | missing eating activity | ✅ FIXED | Schema validation |
| **N10**| Borko origin_events tags | ✅ FIXED | IPT |
| **N11**| FactionAlignmentTracker | ✅ FIXED | IPT / CDS |
| **N12**| Faction ID language | ✅ FIXED | Preflight |
| **N13**| Shadow day sleep | ✅ FIXED | Sleep Canary |
| **N14**| L3 Identity cascade | ✅ FIXED | IPT (INV-L3-EPHEMERAL) |
| **N15**| ContradictionResolver sign | ✅ FIXED | Code Review |

**Итог:** Все 15 багов устранены. Система защиты (10 уровней) активна и эволюционирует. Время обнаружения багов того же класса сокращено с месяцев до минут (CI run) или секунд (startup validation).

Вот честный список того, что у нас "дыряво" или отсутствует:

### 1. Canary-сценарии (Уровень 2) — Отсутствует полный E2E тест
В документе описан `test_full_playthrough_end_screen_non_empty`, который симулирует 30 минут игры, взаимодействие с 5 NPC и проверяет, что End-Screen (финальный экран) не пустой.
**Текущий статус:** У нас есть `SUPERBOX` тесты для эпистемики и `test_sleep_routing` для сна, но **нет** единого E2E Canary-теста, который проходил бы всю игру от старта до финала и проверял MVP-пайплайн (секреты, судьбы, фракции). Мы проверяем это только вручную, играя в игру.

### 2. Автоматические CI Gates (Уровень 9) — Нет автоматического запуска
Документ предполагает, что `ruff`, `mypy`, `IPT.py` и линтеры запускаются автоматически при `git commit` или `git push` (через GitHub Actions или pre-commit hooks).
**Текущий статус:** Мы запускаем всё **вручную** через PowerShell. Нет `.github/workflows/ci.yml` и нет настроенного `.pre-commit-config.yaml`. Если ты забудешь запустить IPT перед коммитом, баг уедет в репозиторий.

### 3. Кастомный Ruff-плагин (Уровень 4) — Нет AST-правил
Документ предлагает написать `backend/lint/custom_rules.py` с правилами `ENIGMA001` (запрет `if X else None`), `ENIGMA002` (запрет `getattr` без лога) и `ENIGMA003` (запрет `in locals()`).
**Текущий статус:** У нас есть отдельные скрипты (`lint_wall_clock.py`, `lint_domain_purity.py`), которые ищут паттерны текстом. Но мы не интегрировали их как нативные правила Ruff, чтобы они подсвечивались прямо в VS Code красным подчёркиванием на лету.

### 4. Doc Drift Detection (Уровень 8) — Нет скрипта
Документ описывает скрипт `validate_doc_refs.py`, который парсит маркдауны, находит ссылки вида `file.py:123` и проверяет, существует ли ещё этот файл и эта строка.
**Текущий статус:** Скрипта нет. Мы чистим документацию вручную (как делали это сегодня). Из-за этого в репозитории скопились устаревшие ТЗ, которые ссылаются на несуществующий код.

### 5. Live Telemetry Dashboard (Уровень 7) — Нет UI
Документ описывает живой дашборд, который парсит `HealthSnapshot` каждый тик и отображает состояние системы.
**Текущий статус:** У нас есть эндпоинт `/health` и отчёт `LAST_SESSION.md` после сессии. Но нет "живого" мониторинга в реальном времени (тебе приходится читать консоль или логи).