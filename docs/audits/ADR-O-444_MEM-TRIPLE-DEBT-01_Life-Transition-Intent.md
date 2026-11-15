# ADR-O-444 — MEM-TRIPLE-DEBT-01: Life Transition Intent (вычисление vs запись)

> **Статус:** PROPOSED (архитектурное направление APPROVED, реализация pending)
> **Дата:** 2026-11-15 · **База:** HEAD `333cb89e` · **Автор:** ветвь А
> **Основание:** Master 2026-11-15 — направление 2 принято, код закрыт до отдельного GO
> **Не является:** разрешением на код. Это архитектурный контракт для будущей реализации.

---

## 1. Контекст

`MEM-TRIPLE-DEBT-01` — 10 CRIT `INV-MEM-TRIPLE` в `life_project_resolver.py`. Нарушение SSOT-записи в `NPCState`: `LifeProjectResolver.resolve()` обходит writer-guard `NPCState.__setattr__` через `object.__setattr__`.

Линтер документирует этот факт (`scripts/lint_mem_triple.py`, docstring):

> `MEM-TRIPLE-DEBT-01: life_project_resolver bypasses NPCState writer guard (10 CRIT in baseline). Debt tracked separately, NOT allowlisted.`

Baseline 10 CRIT принят (не P0 user-facing; **критический архитектурный долг** — классификация Master 2026-11-15). Порча игрового состояния **не доказана** отдельно.

## 2. Проблема

`LifeProjectResolver.resolve(state, identity_pressure, tick)`:

- вызывается каждый тик из `phases/decision.py:132` — прод-путь;
- для 6 состояний FSM (`ACTIVE`, `COMPLETED`, `COLLAPSING`, `LOST`, `SEARCHING`, `COMMITTED`) делает **10** `object.__setattr__` на 3 поля:
  - `life_project_state` — **7** записей (строки 43, 49, 55, 59, 66, 72, 76);
  - `life_project` — **1** запись (строка 71);
  - `stress` — **2** записи (строки 53, 63 — внутри `min(100, +5)` и `min(100, +10)`);
- `object.__setattr__` обходит `NPCState.__setattr__` (guard).

`_ALLOWED_WRITERS` (`npc_state.py:649-682`) содержит:

- `app.services.npc.state_applicator: {"*"}` — постоянный контракт;
- `app.services.phases.decision: {"*"}` — **TODO: убрать после Task 0.9** (временная поблажка);
- прочие модули — TODO или test-исключения.

`life_project_resolver` **не в whitelist** — и **не должен** туда попасть (направление 1 отвергнуто: легализация обхода вместо устранения причины).

## 3. Решение (архитектура)

**Принцип: вычисление ≠ запись.**

- `LifeProjectResolver` **сохраняет** FSM-логику (переходы, условия, последствия) — **владелец вычисления**.
- `LifeProjectResolver` **не изменяет** `NPCState`. Возвращает **`LifeTransitionIntent`** — frozen dataclass.
- `StateApplicator.apply_life_transition(state, intent)` — **единая авторизованная точка записи**. `state_applicator` уже в `_ALLOWED_WRITERS` с `{"*"}`, без TODO.
- `phases/decision.py` **не меняет** call site (строка 132); меняется только форма возврата + один вызов `StateApplicator.apply_life_transition`.

Отдельный mutation gateway **не создаётся**: `StateApplicator` — по контракту (docstring) «единственный модуль с правом записи в NPCState», уже покрывает `relationships`, `needs`, `physiology`, `emotion`, `stress`. `life_transition` — **шестая категория того же класса**, не новый класс.

## 4. Контракт

### 4.1. `LifeTransitionIntent` (frozen dataclass)

**Расположение:** нейтральный **доменный** модуль, доступный обоим компонентам (`LifeProjectResolver` возвращает, `StateApplicator` принимает). **Не размещать в `state_applicator.py`**: это связало бы доменную логику с механизмом записи. Конкретный путь файла — при реализации, после проверки существующей структуры моделей (`app/models/`, `app/domain/`). Открытый вопрос §12.4.

Поля:

```python
@dataclass(frozen=True)
class LifeTransitionIntent:
    new_life_project_state: str          # ACTIVE | COLLAPSING | LOST | SEARCHING | COMMITTED | COMPLETED
    new_life_project: str | None = None  # None = не менять
    stress_delta: float = 0.0            # применяется через saturation-pipeline
    reason: str = ""                     # "pressure>60x3", "vitality_decay", ...
```

### 4.2. `LifeProjectResolver.resolve` (новый контракт)

```python
@staticmethod
def resolve(state: NPCState, identity_pressure: float, tick: int = 0) -> LifeTransitionIntent | None
```

- Возвращает `None`, если перехода нет (state не тронут).
- Возвращает `LifeTransitionIntent`, если нужен переход.
- **Никаких** `object.__setattr__` в resolver.

### 4.3. `StateApplicator.apply_life_transition`

```python
def apply_life_transition(self, state: NPCState, intent: LifeTransitionIntent) -> None
```

- Пишет `life_project_state` / `life_project` (если `new_life_project is not None`).
- Применяет `stress_delta` через существующий `apply_saturation`-pipeline (`state_applicator.py:884-895`).
- **Требование согласованного применения:** при исключении посередине операции `state` не должен остаться частично-мутированным. Механизм rollback (snapshot / copy-on-write / отложенная сборка нового state / иное) — определить при реализации. Тест отказа посередине операции **обязателен**. Нельзя называть несколько последовательных `object.__setattr__` атомарной операцией только потому, что они в одном методе.
- `object.__setattr__` **внутри** `state_applicator` — легально, whitelist `{"*"}` покрывает.

### 4.4. `phases/decision.py` (изменяется)

```python
# было:
LifeProjectResolver.resolve(_npc_state, _break_deltas.identity_pressure, tick=tick_number)

# станет:
_intent = LifeProjectResolver.resolve(_npc_state, _break_deltas.identity_pressure, tick=tick_number)
if _intent is not None:
    _svc.state_applicator.apply_life_transition(_npc_state, _intent)
# _old_state / log — после применения, без изменений
```

`_svc.state_applicator` — проверить наличие при реализации (вероятно, доступен через `NpcServices`; открытый вопрос §12.1).

## 5. Владение полями

| Поле | Владелец переходов | Допустимые причины изменения |
|---|---|---|
| `life_project_state` | `LifeProjectResolver` (FSM) | FSM-переходы — 6 состояний |
| `life_project` | `LifeProjectResolver` (FSM, `SEARCHING→COMMITTED`) | `_CRISIS_TRANSITIONS` lookup |
| `stress` | единый механизм записи (`StateApplicator`) | **несколько** причин (FSM `vitality_decay`, tick_recovery, combat, и т.д.) |

**Единый writer ≠ единственная причина изменения.** `StateApplicator` — единая точка записи, но причин по-прежнему много.

## 6. Сохранение поведения (golden master)

Обязателен **golden master до и после** для:

- 6 FSM-состояний: `ACTIVE`, `COMPLETED`, `COLLAPSING`, `LOST`, `SEARCHING`, `COMMITTED`;
- `stress`-дельта на переходах `COMPLETED→LOST` (+5) и `LOST→SEARCHING` (+10);
- `life_project` lookup на `SEARCHING→COMMITTED`;
- tick-sequencing: `phases/decision.py:132` вызывается **каждый тик**, переходы из разных состояний **не должны меняться**.

Golden master фиксирует **state_before + inputs → state_after**. Если поведение меняется — STOP, не коммит.

## 7. Детерминизм

Тест: `(input_state, identity_pressure, tick) → LifeTransitionIntent` — детерминирован.
`LifeTransitionIntent` — frozen dataclass, `hashable`. Одинаковый вход → одинаковый intent (по полям).

## 8. Линтер

- `scripts/lint_mem_triple.py` — **не ослабляется**.
- `_ALLOWED_WRITERS` — **не меняется** (`state_applicator: {"*"}` уже покрывает `life_project_state` / `life_project` / `stress`).
- `test_lint_mem_triple.py::test_baseline_10_crit_in_life_project_resolver` — **снимается по факту** (10 → 0), но не через allowlist и не через исключения.
- После устранения десяти нарушений `INV-MEM-TRIPLE` повторно запускается полный IPT. Новый общий baseline фиксируется исключительно по фактическому результату проверки. Ожидаемое количество CRIT заранее не устанавливается.

## 9. Rollback

- `LifeProjectResolver` с `object.__setattr__` — восстанавливается одним revert.
- `LifeTransitionIntent` — удаляется.
- `StateApplicator.apply_life_transition` — удаляется.
- `phases/decision.py` call site — восстанавливается.
- Baseline 10 CRIT — восстанавливается в `test_lint_mem_triple.py` и IPT.
- **Риск:** если в промежутке появился новый тест, требующий 0 CRIT — конфликт, разбор отдельно.

## 10. Тесты (план)

| Тест | Что проверяет |
|---|---|
| `test_life_transition_intent` | frozen, hashable, все поля |
| `test_resolver_returns_intent_not_mutation` | `resolve()` не мутирует `state`, возвращает intent |
| `test_resolver_determinism` | одинаковый вход → одинаковый intent (100 прогонов) |
| `test_state_applicator_apply_life_transition` | 3 поля записываются, `stress_delta` через saturation |
| `test_state_applicator_failure_rollback` | исключение посередине → `state` не частично-мутирован (механизм — при реализации) |
| `test_golden_master_6_states` | 6 FSM-состояний + stress → state_after идентичен |
| `test_baseline_zero_crit` | `lint_mem_triple` = 0 CRIT в `life_project_resolver` |
| `test_existing_crisis_flow` | `tests/sandbox/system/test_life_direction_crisis.py` — без регрессий |

## 11. Не входит в scope

- `P0-3` (`_pending_dialogue_memories`) — deferred.
- `phases/decision.py:126` `object.__setattr__(_npc_state, "will_state", ...)` — **отдельный** debt (TODO в whitelist, «убрать после Task 0.9»).
- `app.services.phases.memory`, `life_engine`, `npc_loader` TODO-whitelist — **отдельные** задачи.
- Расширение `_ALLOWED_WRITERS` — **не делаем**.
- §3-protected, A19.5, S426 — **не касаемся**.

## 12. Открытые вопросы (для реализации)

1. `_svc.state_applicator` — доступен ли в `phases/decision.py` через `NpcServices`? Проверить при реализации.
2. Golden master: синтетический (`NPCState` + параметры) или снятый из прод-прогона? Для детерминизма — синтетика достаточна.
3. Механизм rollback в `apply_life_transition` — snapshot / copy-on-write / отложенная сборка нового state. Определить при реализации.
4. Расположение `LifeTransitionIntent` — `app/models/` vs `app/domain/` vs новый модуль. Определить при реализации после инвентаризации существующей структуры.

## 13. Ссылки

- `backend/app/services/npc/life_project_resolver.py` (10 CRIT)
- `backend/app/services/npc/state_applicator.py` (target gateway)
- `backend/app/models/npc_state.py:649-682` (`_ALLOWED_WRITERS`)
- `backend/app/services/phases/decision.py:128-134` (call site)
- `scripts/lint_mem_triple.py` (A-3 правило)
- `backend/tests/micro/test_lint_mem_triple.py:381-393` (baseline 10)
- `backend/tests/IPT.py:2811` (`MEM-TRIPLE-DEBT-01`)

---

**Классификация:** критический архитектурный долг, **не P0 user-facing**. SSOT-нарушение **доказано**; порча игрового состояния **не доказана**.
**Статус:** PROPOSED. Архитектурное направление APPROVED. Реализация — после отдельного GO.
**База:** `333cb89e`.
