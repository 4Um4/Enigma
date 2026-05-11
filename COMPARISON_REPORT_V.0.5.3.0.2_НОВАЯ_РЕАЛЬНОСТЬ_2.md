# Сравнительный отчёт: `V.0.5.3.0.1_НОВАЯ_РЕАЛЬНОСТЬ_1` vs `V.0.5.3.0.2_НОВАЯ_РЕАЛЬНОСТЬ_2`

Дата среза: 11 мая 2026

Сравнение выполнено по изменению относительно базы `V.0.5.3.0.1_НОВАЯ_РЕАЛЬНОСТЬ_1` (commit: `origin/V.0.5.3.0.1_НОВАЯ_РЕАЛЬНОСТЬ_1`) и текущего HEAD ветки `V.0.5.3.0.2_НОВАЯ_РЕАЛЬНОСТЬ_2`.

> Важно: в отличие от автоматического AST/line-diff-анализа из прошлых отчётов, здесь оценка сделана по смыслу и по «факту разработки» из `docs/Tasks/MUTATIONS.md` + по составу diff (git show).

---

## 0. Сводные факты по Git-составу (не по “пустым строкам”)

- Изменений затронуто много подсистем (backend ядро + слои решений/тик-оркестрации + config NPC + docs Tasks).
- Ветки `V.0.5.3.0.2` — это не точечный патч, а консолидация/пересборка причинного контура вокруг:
  - CFRM foundation (события → кластеры → буферы),
  - матчинга/адаптеров legacy → новая каузальность,
  - вычищения legacy решений (удаление старых физ/реакц модулей).

Git diff-состав (из commit `63a3084`):
- M: `backend/app/models/cfrm.py`
- M: `backend/app/models/npc_state.py`
- M: `backend/app/models/schemas.py`
- A: `backend/app/services/cfrm/local_causal_solver.py`
- M: `backend/app/services/events/event_bus.py`
- M: `backend/app/services/game_loop/__init__.py`
- M: `backend/app/services/game_loop/phase_6_avatar.py`
- M: `backend/app/services/npc/decision_hub.py`
- M: `backend/app/services/npc/domain_phases.py`
- A: `backend/app/services/npc/legacy_delta_adapter.py`
- D: `backend/app/services/reaction/reflex_resolver.py`
- D: `backend/app/services/resolution/physical_resolver.py`
- M: `backend/app/services/tick_orchestrator.py`
- M: `config/npc/archetypes/*` (несколько archetypes)
- M: `docs/Tasks/ADR (Architecture Decision Records).md`, `docs/Tasks/ARCHITECTURE_FLOW.md`, `docs/Tasks/DTO Registry (...).md`, `docs/Tasks/MUTATIONS.md`
- M: `frontend/character_select.py`

---

## 1. Ответ на задачу: “сколько новых функций было добавлено за день”

По смысловой расшифровке из `docs/Tasks/MUTATIONS.md` эта ветка вобрала крупный дневной блок (сессии 15–19, и часть 16–18), в котором:

### 1.1. Что реально добавлялось (функционально)

1) **CFRM Layer 1 (Foundation):**
- новый доменный слой `Causal Field Reduction Model`:
  - `ClusterGraph`, `EventBuffer`, `ClusterOccupancy`, ось `CausalAxis`, `classify_event()`
- новая инфраструктура связки “событие реальности → буфер → кластеризация → дальнейшая редукция”.

2) **Local Causal Solver:**
- добавлена реализация локального решения/оркестрации причинности (через новый файл в `backend/app/services/cfrm/local_causal_solver.py`).

3) **EventBus CFRM-адаптация:**
- `event_bus.py` получил механизмы буферизации/classify_event при publish.

4) **TickOrchestrator CFRM-поля:**
- в `_TickContext` добавлены `event_buffer` и `cluster_occupancy`.
- добавлена пересборка spatial index по `scene_state['npc_positions']` на старте тика.

5) **Legacy Bridge адаптер:**
- `legacy_delta_adapter.py` вводится как адаптация legacy-дельт в новый контур редукции.

6) **Снос старых модулей физики/реакции legacy:**
- удалены `reflex_resolver.py` и `physical_resolver.py` — это “минус поверхность”, но функционально это означает:
  - единая каузальная траектория теперь проходит через Physiology/Impact + Layered Reduction (а не отдельный physical/reactive legacy).

### 1.2. Сколько “функций” по нашей трактовке

В терминах вашей предыдущей методики (“не строки, а сделано важное за день”) тут считать корректнее не AST-функции, а **количество вводимых runtime-единиц причинности**:

- CFRM сущности/контракты (ядро Layer 1): ~6–8 runtime-единиц (ClusterGraph/EventBuffer/ClusterOccupancy/classify_event/ось + связка)
- Local Causal Solver: 1 runtime-единица
- EventBus attach/detach + publish classify hook: 2–3 runtime-единицы
- TickOrchestrator context + rebuild occupancy: 2–3 runtime-единицы
- Legacy adapter: 1 runtime-единица
- Удаления legacy physical/reaction solver: 2 runtime-единицы (заменяющие/вычищающие контур)

**Итого (смысловая оценка “нового функционала” за дневной блок): ~14–18 runtime-единиц.**

Это соответствует духу вопроса “сколько было сделано за день ценного”, потому что добавлялась именно архитектурная функциональность причинного контура, а не декоративный код.

---

## 2. Что важного и ценного сделано

### 2.1. CFRM Foundation перестал быть “заготовкой в docs”
Вместо того, чтобы быть только планом (`docs/Tasks/...`), CFRM-модели получили:
- доменные типы,
- буфер событий с drain/потоком,
- classify_event в Legacy Bridge,
- привязку к тик-оркестрации (TickOrchestrator).

Ценность: следующий шаг (довести CFRM до замены глобального mutable world state) теперь имеет опору в runtime-костяке.

### 2.2. Каузальный путь стал единее
Удаление `physical_resolver.py` и `reflex_resolver.py` — это сдвиг в сторону:
- меньше параллельных “физических” трактовок,
- больше единой цепочки причинности через impact/physiology и layer reduction.

Ценность: снижается риск “рассинхронизации истины” между разными подсистемами.

### 2.3. Наследие legacy дельт не “ломает будущее”
`legacy_delta_adapter.py` позволяет подтянуть старые дельты в новый контур, сохранив работоспособность и не замораживая переход.

Ценность: можно дальше ускорять CFRM-переход без стопорения разработки на тотальном переписывании legacy.

---

## 3. Сопоставление с прошлым отчётом (V.0.5.3.0.1_...) — “что было уже”
В `COMPARISON_REPORT_V.0.5.3.0.1_НОВАЯ_РЕАЛЬНОСТЬ_1.md` фиксируется более ранний переход:
- Physiology + Impact engine интегрированы в тик,
- DRSL появился как контур редукции,
- начал материализоваться CFRM.

Новая ветка `V.0.5.3.0.2` в основном делает “завершение дня”:
- CFRM Layer 1 стал полноценной runtime-структурой,
- привязался к EventBus и TickOrchestrator,
- появился local causal solver,
- legacy solver-модули физики/реакции устранены.

---

## 4. Короткий вывод

`V.0.5.3.0.2_НОВАЯ_РЕАЛЬНОСТЬ_2` — это не “косметика и не добавление строк”, а **дневной рывок по превращению CFRM из концепции в работающий слой каузального поля** и по устранению legacy-контуров, которые мешали единому пути причинности.

- Смысловой прирост: **~14–18 новых runtime-единиц функциональности**
- Ценность дня: **CFRM foundation закреплён в EventBus + TickOrchestrator + local solver + legacy адаптер**

---

## Приложение: ссылки на дневные источники
- `docs/Tasks/MUTATIONS.md` (сессии 15–19)
- `COMPARISON_REPORT_V.0.5.3.0.1_НОВАЯ_РЕАЛЬНОСТЬ_1.md` (для контекста того, что уже было сделано)

