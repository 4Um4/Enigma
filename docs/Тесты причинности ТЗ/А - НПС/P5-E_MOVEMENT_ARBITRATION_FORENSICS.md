# P5-E — MOVEMENT ARBITRATION FORENSICS: COMPLETED

**Forensic Milestone** — аналитический отчёт о завершении эксперимента P5-E.

**Baseline:** `72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2`
**Branch:** `main`
**Probe:** `backend/tests/sandbox/p5e_movement_arbitration_probe.py`
**Вердикт:** **GREEN — CLOSED**. Причина отсутствия spatial_changes для maid_lusya установлена с предсказанием и подтверждением.

---

## Итоговый вопрос Master

**Почему `MovementEngine` получает intent `SEEK_ALLY` от `maid_lusya`, но не создаёт для неё `spatial_changes`?**

### Ответ: GATE B1.5 — Traversal Pre-emption Guard

`backend/app/services/spatial/movement_engine.py:202-229`

```python
if scene_state:
    _active_travs_pre = scene_state.get("active_traversals", {})
    if isinstance(_active_travs_pre, dict) and _active_travs_pre:
        _filtered: list = []
        for _it in intents:
            if not isinstance(_it, MacroMovementGoal):
                _filtered.append(_it)
                continue
            _trav = _active_travs_pre.get(_it.actor_id)
            if (
                isinstance(_trav, dict)
                and _trav.get("status") == "MOVING"
                and "interrupt" not in getattr(_it, "reason", "")
                and "+relocation" not in getattr(_it, "reason", "")
            ):
                logger.debug(
                    f"[GATE_B1_5] npc={_it.actor_id} traversal MOVING "
                    f"(target={_trav.get('target_node')}) — intent "
                    f"'{getattr(_it, 'reason', '')}' отклонён (no-interrupt)"
                )
                continue  # ← INTENT ОТКЛОНЁН ЗДЕСЬ
```

**Точная причина:** maid_lusya имеет active_traversal со status="MOVING" (созданный Phase 0 LifeEngine schedule в том же idle_tick, первым вызовом process_intents). Когда Phase 5 (DecisionHub) создаёт SEEK_ALLY MacroMovementGoal с reason="proactive_seek_ally" (не содержит "interrupt" или "+relocation"), GATE B1.5 отклоняет его через `continue`.

---

## И отдельно: сохраняется ли намерение Люси для повторного исполнения?

**Ответ: НЕТ — intent ТЕРЯЕТСЯ (REJECTED).**

Судьба SEEK_ALLY intent: **REJECTED** (категория 1 из P5-E.3).

- Intent не откладывается (нет DEFERRED queue)
- Intent не заменяется (нет SUPERSEDED mechanism)
- Intent не сохраняется для повторного рассмотрения (нет RETRY mechanism)
- `continue` в line 229 просто пропускает intent → он удаляется из `_filtered` list
- На следующем тике maid_lusya выбирает FLEE (не SEEK_ALLY) — intent не повторяется

**SEEK_ALLY умирает в GATE B1.5 без следа.**

---

## Доказательство: PREDICTED_REJECT → ACTUAL_REJECT

### Сценарий A, idle_tick=1, ВТОРОЙ вызов process_intents (Phase 5):

```
STAGE0.pre_process_intents:
  maid_lusya_active_traversal: {
    status: "MOVING",
    target_node: "tavern:node_16"
  }

STAGE3.B1_5_PREDICTION maid_lusya:
  ml_is_moving: true                    ← active traversal EXISTS
  ml_intent_reason: "proactive_seek_ally"
  ml_has_interrupt: false               ← reason не содержит "interrupt"
  ml_has_relocation: false              ← reason не содержит "+relocation"
  PREDICTED_REJECT: true                ← ПРЕДСКАЗАНИЕ: будет отклонён

STAGE2._spatial_intent_gate:
  ml_current_pos: "tavern:node_16"
  ml_target: "tavern:behind_bar"
  ml_collapsed: false                   ← Stage 2 пройден (не collapsed)

STAGE_FINAL.process_intents:EXIT:
  maid_lusya_changes_count: 0          ← spatial_changes НЕ созданы
  ACTUAL_REJECT: true                   ← ПОДТВЕРЖДЕНИЕ: отклонён
```

**PREDICTED_REJECT=True → ACTUAL_REJECT=True.** Причинный механизм доказан.

---

## Два вызова process_intents в одном idle_tick

| Вызов | Фаза | Intents | maid_lusya reason | Active traversal ПЕРЕД | PREDICTED_REJECT | ACTUAL_REJECT | spatial_changes для maid_lusya |
|-------|------|---------|-------------------|----------------------|-----------------|---------------|-------------------------------|
| 1-й | Phase 0 (LifeEngine schedule) | 6 | "schedule:working" | {} (пусто) | False | False | **2** (position=node_16, heading) |
| 2-й | Phase 5 (DecisionHub SEEK_ALLY) | 5 | "proactive_seek_ally" | {status:MOVING, target:node_16} | **True** | **True** | **0** |

**Последовательность:**
1. Phase 0: LifeEngine создаёт schedule intent для maid_lusya → process_intents вызывается → spatial_changes созданы → active_traversal(status=MOVING) установлен
2. Phase 5: DecisionHub создаёт SEEK_ALLY intent → process_intents вызывается → GATE B1.5 видит active_traversal(MOVING) → intent отклонён

---

## Состояние maid_lusya перед SEEK_ALLY обработкой

### A. Actor state
- position: "tavern:node_16" (изменён Phase 0)
- activity: "serving_tables" (из Phase 0 schedule)

### B. Traversal state
- active_traversal: EXISTS
- status: "MOVING"
- target_node: "tavern:node_16"
- reason: "" (пусто — schedule traversal не содержит reason field)
- origin_node: "" (пусто)

### C. Movement ownership
- Владелец: Phase 0 LifeEngine schedule (reason="schedule:working")
- Commitment: активный (status=MOVING)
- Конфликт: Phase 5 SEEK_ALLY (reason="proactive_seek_ally") пытается заменить

### D. Incoming intent (SEEK_ALLY)
- actor_id: maid_lusya
- type: MacroMovementGoal
- reason: "proactive_seek_ally"
- target_node_id: "tavern:behind_bar" (где был tavern_keeper_tornin)
- priority: 0.5 (default, PRIORITY_NEEDS)
- has_interrupt: false
- has_relocation: false

---

## A/B Comparison

| Параметр | A (с PLAYER_INSULTS) | B (control) |
|---------|----------------------|-------------|
| 1-й process_intents (Phase 0) | maid_lusya: 2 changes (schedule) | maid_lusya: 2 changes (schedule) |
| Active traversal перед 2-м call | {MOVING, target:node_16} | {MOVING, target:node_16} |
| 2-й process_intents (Phase 5) maid_lusya reason | "proactive_seek_ally" | "proactive_seek_ally" |
| PREDICTED_REJECT | True | True |
| ACTUAL_REJECT | True | True |
| spatial_changes for maid_lusya (Phase 5) | 0 | 0 |

**A/B идентичны** — traversal конфликт возникает в обоих случаях. PLAYER_INSULTS не влияет на movement arbitration; он влияет только на cognitive decision (SEEK_ALLY vs FLEE).

---

## Five-Intent Arbitration (2-й process_intents, Phase 5)

| # | Actor | Reason | Target | Stage 2 (spatial_gate) | Stage 3 (B1.5) | Stage 4 (_process_single) | spatial_changes |
|---|-------|--------|--------|----------------------|-----------------|--------------------------|-----------------|
| 1 | guard_borko | proactive_spread_rumor | tavern:node_17 | PASS | PASS (no active traversal) | ENTER → EXIT | 2 (position, heading) |
| 2 | merchant_goran | proactive_change_role | tavern:fireplace | PASS | **REJECT** (MOVING traversal) | NOT CALLED | 0 |
| 3 | maid_lusya | proactive_seek_ally | tavern:behind_bar | PASS | **REJECT** (MOVING traversal) | NOT CALLED | 0 |
| 4 | blacksmith_orm | proactive_change_role | tavern:behind_bar | PASS | **REJECT** (MOVING traversal) | NOT CALLED | 0 |
| 5 | tavern_keeper_tornin | proactive_seek_ally | tavern:node_17 | PASS | **REJECT** (MOVING traversal) | NOT CALLED | 0 |

**Из 5 intents:**
- 1 PASSED B1.5 (guard_borko — нет active traversal) → 2 spatial_changes
- 4 REJECTED by B1.5 (merchant_goran, maid_lusya, blacksmith_orm, tavern_keeper_tornin — все имеют active traversal MOVING)

**guard_borko — единственный без active traversal** на момент 2-го вызова process_intents. Причина: его Phase 0 traversal уже завершился (достиг цели к этому моменту), или его schedule не создал traversal в этом тике.

---

## Call Graph MovementEngine.process_intents

```
process_intents(intents, tick, npc_positions, campaign_id, scene_state)
  │
  ├── Stage 1: Total Intent Arbitration (lines 156-192)
  │   └── Per-actor: select best MacroMovementGoal (Reactive > Schedule > Social)
  │   └── Filter LocalSteeringGoal if actor has winning MacroMovementGoal
  │
  ├── Stage 2: _spatial_intent_gate (lines 91-138, called at line 197)
  │   └── For each MacroMovementGoal:
  │       └── if current_pos == target_pos → COLLAPSE (continue, intent dropped)
  │       └── else → ACCEPT (append to validated)
  │
  ├── Stage 3: GATE B1.5 — Traversal Pre-emption Guard (lines 202-261) ← ПРИЧИНА
  │   └── For each MacroMovementGoal:
  │       └── if active_traversal.status == "MOVING"
  │           AND "interrupt" NOT in reason
  │           AND "+relocation" NOT in reason
  │           → REJECT (continue, intent dropped) ← maid_lusya отклонён ЗДЕСЬ
  │       └── elif "+relocation" in reason
  │           → SUPERSEDE (interrupt existing traversal)
  │       └── else → PASS (append to _filtered)
  │
  └── Stage 4: _process_single_intent (lines 662+, called per-intent)
      └── Resolve target_node_id → {x, y} via SpatialService
      └── Generate SceneChange(field="position", value="location:node_id")
      └── Generate SceneChange(field="body_heading", value=angle)
```

---

## Таблица условий обработки intents

| Условие | Файл:строки | Проверка | При PASS | При FAIL | Применимо к maid_lusya? |
|---------|-------------|----------|----------|----------|--------------------------|
| Stage 1: Intent Arbitration | movement_engine.py:161-181 | Per-actor priority (Reactive > Schedule > Social) | Best intent selected | Lower-priority intent dropped | maid_lusya имеет 1 intent → нет конфликта → PASS |
| Stage 2: Spatial Gate (collapse) | movement_engine.py:115-123 | current_pos == target_pos? | Intent accepted | Intent dropped (continue) | ml_pos="node_16" ≠ target="behind_bar" → PASS |
| **Stage 3: GATE B1.5** | **movement_engine.py:218-229** | **active_traversal.status == "MOVING" AND "interrupt" NOT in reason AND "+relocation" NOT in reason?** | **Intent passed to _filtered** | **Intent REJECTED (continue)** | **ml_traversal={MOVING}, reason="proactive_seek_ally" (no interrupt/relocation) → FAIL → REJECT** |
| Stage 4: _process_single_intent | movement_engine.py:662+ | Target node resolution + SceneChange generation | SceneChange created | Warning logged, intent skipped | maid_lusya NEVER REACHED this stage |

---

## Подтверждённые факты (PROVEN)

1. **PROVEN**: maid_lusya имеет active_traversal со status="MOVING" ПЕРЕД обработкой SEEK_ALLY (spy: `maid_lusya_active_traversal: {status: "MOVING", target_node: "tavern:node_16"}`)
2. **PROVEN**: active_traversal создан Phase 0 LifeEngine schedule (1-й вызов process_intents, reason="schedule:working")
3. **PROVEN**: SEEK_ALLY intent имеет reason="proactive_seek_ally" (не содержит "interrupt" или "+relocation")
4. **PROVEN**: GATE B1.5 (movement_engine.py:218-229) проверяет `_trav.get("status") == "MOVING" AND "interrupt" not in reason AND "+relocation" not in reason`
5. **PROVEN**: PREDICTED_REJECT=True (spy предсказал отклонение на основе код-анализа B1.5)
6. **PROVEN**: ACTUAL_REJECT=True (spy подтвердил: maid_lusya_changes_count=0)
7. **PROVEN**: PREDICTED_REJECT → ACTUAL_REJECT (причинный механизм доказан)
8. **PROVEN**: maid_lusya не доходит до _process_single_intent (Stage 4 NEVER CALLED for maid_lusya)
9. **PROVEN**: 4 из 5 intents отклонены B1.5 (merchant_goran, maid_lusya, blacksmith_orm, tavern_keeper_tornin)
10. **PROVEN**: guard_borko — единственный, чей intent прошёл B1.5 (нет active traversal)
11. **PROVEN**: SEEK_ALLY intent ТЕРЯЕТСЯ — нет DEFERRED queue, нет RETRY mechanism, нет повторного рассмотрения
12. **PROVEN**: На следующем тике maid_lusya выбирает FLEE (не SEEK_ALLY) — intent не повторяется

## Гипотезы (SUPPORTED/HYPOTHESIS)

- **SUPPORTED**: Если бы maid_lusya не имела active traversal, SEEK_ALLY прошёл бы B1.5 и создал spatial_changes. (Косвенно доказано тем, что guard_borko без traversal прошёл и получил spatial_changes.)
- **HYPOTHESIS**: Если бы SEEK_ALLY reason содержал "interrupt" или "+relocation", он прошёл бы B1.5 (не проверено экспериментом, но следует из кода).

## Неизвестные (UNKNOWN)

- Точное условие, при котором guard_borko не имеет active_traversal, когда 4 других NPC имеют. (Возможно: его Phase 0 traversal завершился в том же тике, или его schedule не создал traversal.)
- Что произошло бы, если бы SEEK_ALLY был создан с reason="proactive_seek_ally+relocation" — прошёл бы B1.5? (Не проверено.)
- Поведение при TRAVERSAL_OWNERSHIP_ENFORCEMENT=true (env flag OFF по умолчанию, legacy mode).

---

## Рекомендация Master по следующему техническому шагу

**P5-E завершён с доказанной причиной.** Теперь Master должен решить:

1. **Является ли GATE B1.5 дефектом или штатным правилом арбитража?**
   - Если **штатное правило**: SEEK_ALLY правильно отклоняется при активном schedule traversal. NPC не может прервать движение по расписанию ради социального намерения. Это архитектурное решение — body следует schedule, а не desire.
   - Если **дефект**: SEEK_ALLY должен иметь возможность прервать schedule traversal (как это делает "+relocation"). Возможно, reason="proactive_seek_ally" должен содержать маркер прерывания.

2. **Если дефект — какой минимальный fix?**
   - **Вариант A**: Добавить "seek_ally" в список interrupt-capable reasons (movement_engine.py:221-222). Минимальное изменение: расширить условие пропуска.
   - **Вариант B**: Изменить reason в npc_tick_pipeline.py при создании SEEK_ALLY movement_intent на "proactive_seek_ally+relocation" (использовать существующий supersede mechanism).
   - **Вариант C**: Добавить DEFERRED queue для отклонённых intents (architecture change — не минимальный fix).

3. **Если штатное правило — что делать с "потерянным" SEEK_ALLY?**
   - Зафиксировать как известное ограничение: NPC не может искать союзника, пока движется по расписанию.
   - Открыть отдельный трек для "social intent deferral" (если Master хочет, чтобы SEEK_ALLY повторялся после завершения traversal).

**Моя рекомендация:** Вариант A — минимальное изменение, добавляющее "seek_ally" в interrupt-capable reasons. Но это решение Master, не исполнителя.

---

## Финальная формула

> Намерение Люси не потерялось в пустоте.
> Оно было отклонено — честно, по правилу, записанному в коде.
>
> Правило говорит: тело, уже идущее по расписанию,
> не может быть повёрнуто социальным желанием —
> если только желание не несёт маркер прерывания.
>
> SEEK_ALLY не несёт этого маркера.
> Поэтому оно умирает в GATE B1.5 —
> не от бага, а от контракта.
>
> Вопрос в том, правильный ли это контракт.

---

## Status P5-E

**GREEN — CLOSED.** Причина установлена с предсказанием и подтверждением.
Production fixes не выполнялись. Жду вердикта Master.

---

## Status всех треков P5

| Трек | Вердикт | Причина |
|------|---------|---------|
| P5-A: Belief Propagation | CLOSED | Belief меняет адресат коммуникации |
| P5-B: SQLite Persistence | PASS | Belief переживает reload |
| P5-C: Real LLM Verification | PASS* | NPC_SPOKE опубликован через real LLM |
| P5-D: SEEK_ALLY Execution | PARTIAL | Movement path существует, но 0 spatial_changes |
| **P5-E: Movement Arbitration** | **GREEN** | **GATE B1.5 отклоняет SEEK_ALLY из-за active traversal (status=MOVING)** |

---

*Forensic milestone зафиксирован. Baseline `72cf47b0` не тронут. Все 5 треков P5 (A/B/C/D/E) завершены.*
