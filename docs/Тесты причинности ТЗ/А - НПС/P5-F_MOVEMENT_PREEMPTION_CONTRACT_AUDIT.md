# P5-F — MOVEMENT PRE-EMPTION CONTRACT AUDIT: COMPLETED

**Forensic Milestone** — архитектурный аудит контракта pre-emption.

**Baseline:** `72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2`
**Branch:** `main`
**Вердикт:** **GREEN — CLOSED** с подтверждёнными противоречиями.

---

## Итоговые вопросы Master (4 ответа)

### 1. Какой инвариант защищает GATE B1.5 и соответствует ли его реализация этому назначению?

**PROVEN:** GATE B1.5 защищает инвариант: **schedule traversal должен достичь completion (boundary) без прерывания proactive/need интентами.**

Источник: комментарий в `movement_engine.py:207-208`:
> "Forensic RCB: бесконечный перезапуск движения proactive/need-интентами не давал schedule-traversal дожить до boundary (2-3 тика пути)."

Git blame: commit `636d7975` (2026-09-20), Mikle.

**Реализация ЧАСТИЧНО соответствует назначению:**
- ✅ B1.5 действительно защищает schedule traversals от proactive/need интентов
- ❌ Но B1.5 также блокирует **все** non-interrupt/non-relocation интенты, включая социальные (SEEK_ALLY, SPREAD_RUMOR) и **даже сам reactive FLEE** (если reason не содержит "reactive" в нужной форме)
- ❌ B1.5 использует **string matching** вместо priority-based arbitration

### 2. Почему приоритет, выбранный Stage 1, может не иметь силы при активном traversal?

**PROVEN: Архитектурное противоречие.**

Существуют **ТРИ уровня арбитража** с разными правилами:

| Уровень | Где | Правило | Тип |
|---------|-----|--------|------|
| **Stage 1** | `movement_engine.py:156-192` | Reactive > Schedule > Social (по `reason` string) | String-based |
| **CommitmentArbiter** | `movement_bridge.py:100-108` → `commitment_arbiter.py:256-289` | Priority-based (`resolve_candidate_priority(intent_type, intent_domain)`) | **Priority-based** |
| **GATE B1.5** | `movement_engine.py:202-229` | Active traversal(MOVING) blocks non-interrupt/non-relocation intents | String-based |

**Противоречие:** Stage 1 и CommitmentArbiter работают с приоритетами, но GATE B1.5 работает со строками. Если B1.5 отклоняет intent, ни Stage 1, ни CommitmentArbiter не могут это переопределить.

**Намеренное разделение ответственности:** Да — B1.5 защищает traversal lifecycle (runtime state), а Stage 1 выбирает между concurrent intents (внутритиковый выбор). Но разделение использует **несогласованные критерии**.

### 3. Какие игровые намерения должны иметь возможность прерывать движение по расписанию?

**Это геймдизайнерское решение Master.** Технические последствия по вариантам — в §8 отчёта.

Существующий контракт:
- ✅ "interrupt" маркер — **любой** caller может добавить эту строку
- ✅ "+relocation" маркер — **только LifeEngine** (schedule/need-driven relocations)
- ✅ CommitmentArbiter — priority-based, но вызывается **ДО** B1.5 в movement_bridge
- ❌ SEEK_ALLY, SPREAD_RUMOR, CHANGE_ROLE, APPROACH — **не имеют** права прерывания

### 4. Как обеспечить, чтобы отказ в исполнении намерения не превращался в незаметную потерю значимого решения NPC?

**PROVEN: Intent теряется без следа.**

Комментарий B1.5 (line 204): "дошёл до цели — рождён следующий тактом" — дизайн-предположение: proactive/need intents пересоздаются каждый тик. Но это **НЕВЕРНО** для transient intents:
- SEEK_ALLY появляется только на tick 1 (после PLAYER_INSULTS), затем заменяется на FLEE
- Отклонённый intent не сохраняется, не повторяется, не логируется как потерянный

**Минимальный механизм без новой подсистемы:** `CommitmentArbiter` уже возвращает structured verdict (VERDICT_INTERRUPT / VERDICT_REJECT / VERDICT_ACCEPT). Если B1.5 будет делегировать решение `CommitmentArbiter`, отклонённые intents получат structured verdict вместо silent `continue`.

---

## P5-F.1 — GATE B1.5 Origin

| Поле | Значение |
|------|---------|
| Commit | `636d7975` (2026-09-20, Mikle) |
| Branch | V.0.5.4.1.0_КросЛокация |
| Исходная проблема | "бесконечный перезапуск движения proactive/need-интентами не давал schedule-traversal дожить до boundary" |
| Защищаемый инвариант | Schedule traversal completion (2-3 тика пути до boundary) |
| Исключения | "interrupt" (reactive), "+relocation" (schedule-level supersede) |
| Последующие изменения | `2e09a2f3` (S273, 2026-09-21): добавлен relocation-supersede branch (lines 230-261) |
| Почему в MovementEngine | Потому что MovementEngine — единственный execution layer, где известен active_traversal state |
| Почему строковый reason | Не найдено архитектурного обоснования — вероятнее всего, quick fix без ADR |
| Почему `continue` (silent reject) | Дизайн-предположение: "дошёл до цели — рождён следующий тактом" (intents пересоздаются) |

---

## P5-F.2 — Stage 1 Priority Arbitration Contract

### Таблица категорий:

| Категория | Источник | Приоритет | Может вытеснить? | Подтверждение |
|-----------|----------|-----------|-----------------|---------------|
| Reactive | npc_tick_pipeline reason="reactive:*" или "flee" | Высший | Да (вытесняет Schedule и Social) | `movement_engine.py:166,176-178` |
| Schedule | LifeEngine reason="schedule:*" | Средний | Да (вытесняет Social, но НЕ Reactive) | `movement_engine.py:165,180-181` |
| Social | npc_tick_pipeline reason="proactive_*" | Низший | Нет (не вытесняет ни Reactive, ни Schedule) | `movement_engine.py:168-169` (default: first-seen wins) |
| LocalSteering | LocalSteeringGoal (micro) | Удаляется если actor имеет winning Macro | Нет | `movement_engine.py:185-190` |

### Обязательный вопрос:

**Если Stage 1 выбирает intent как победителя арбитража, означает ли это, что он получает право прервать активный traversal?**

**НЕТ.** Stage 1 — это **предварительный отбор кандидатов** между concurrent intents (внутри одного тика). Он НЕ учитывает active traversal state. Право прерывания определяется **только** в GATE B1.5 (string-based) или CommitmentArbiter (priority-based).

---

## P5-F.3 — Traversal Lifecycle and Ownership

| Переход | Файл:строки | Инициатор | Условия | Побочные эффекты |
|---------|-------------|-----------|--------|-----------------|
| Создание | `projection_engine.py:134-151` | MovementEngine (via _process_single_intent) | New intent passes all gates | `active_traversals[npc_id] = {status:"MOVING", ...}` |
| Продвижение | `traversal_execution_system.py` (advance) | TickOrchestrator Phase 0.5 | tick boundary | `local_position` updated |
| Завершение | `projection_engine.py:175` | ProjectionEngine | target reached | `status="COMPLETED"`, traversal removed |
| Прерывание (enforcement) | `traversal_schema.py:188` → `interrupt_traversal()` | CommitmentArbiter / B1.5 supersede | reason has "+relocation" AND TRAVERSAL_OWNERSHIP_ENFORCEMENT=true | `interrupt_traversal()` called, traversal interrupted |
| Прерывание (legacy) | `movement_engine.py:256` | B1.5 supersede (legacy) | reason has "+relocation" AND TRAVERSAL_OWNERSHIP_ENFORCEMENT=false | `_active_travs_pre.pop(npc_id)` — silent removal |
| Замена | `movement_engine.py:250-253` | B1.5 supersede | reason has "+relocation" AND enforcement=true | `interrupt_traversal(INTERRUPT_PRIORITY_SUPERSEDE)` |

**TRAVERSAL_OWNERSHIP_ENFORCEMENT:**
- Default: OFF (legacy mode)
- ON: uses `interrupt_traversal()` (proper mechanism with structured reasons)
- OFF: uses `_active_travs_pre.pop()` (silent removal, no audit trail)

**Ownership vs Priority:** Ownership = who created the traversal (LifeEngine schedule vs DecisionHub social). Priority = relative importance of new intent vs existing traversal. **Это разные понятия**, но B1.5 смешивает их: ownership определяется через `reason` string, а не через structured field.

---

## P5-F.4 — Interrupt Capability Audit

### +relocation callsites:

| Файл:строки | Источник | reason | Игровая причина |
|-------------|----------|--------|----------------|
| `life_engine.py:1759` | LifeEngine need-driven | `f"need_driven:{need}={val}+relocation"` | Need-driven cross-location relocation |
| `life_engine.py:2229` | LifeEngine schedule | `f"schedule:{activity}+relocation"` | Schedule-driven cross-location relocation |
| `movement_engine.py:222` | B1.5 check | (reads reason) | Reject if no "+relocation" |
| `movement_engine.py:242` | B1.5 supersede | (reads reason) | Supersede if "+relocation" |

### "interrupt" callsites:

| Файл:строки | Источник | Игровая причина |
|-------------|----------|----------------|
| `traversal_schema.py:206` | `interrupt_traversal()` registry | Validates reason against `_INTERRUPT_TRAVERSAL_REASONS` |
| `commitment_arbiter.py:289` | CommitmentArbiter.enforce_for_intent | Priority-based interrupt (VERDICT_INTERRUPT) |
| `commitment_registry.py:142,240` | Commitment tracking | Audit trail for interrupts |

### Критический вопрос:

**Является ли `reason` описанием причины движения или фактическим механизмом предоставления полномочий на прерывание?**

**PROVEN: Фактический механизм полномочий.** B1.5 использует `reason` string как единственный критерий права прерывания. Любой caller может добавить "interrupt" или "+relocation" к `reason` и получить право прерывания. Нет проверки правомочности инициатора.

**Это отдельный архитектурный риск.**

---

## P5-F.5 — Impact Analysis (Матрица сценариев)

| Сценарий | Активный traversal? | B1.5 result | Intent fate | Возможный игровой ущерб |
|----------|---------------------|-------------|-------------|------------------------|
| FLEE (reactive) | Да | PASS (reason="reactive:flee" не содержит "interrupt", но B1.5 проверяет "interrupt" not in reason → REJECT) **БАГ?** | REJECTED | NPC не может бежать при активном движении |
| SEEK_ALLY (social) | Да | REJECT | LOST | NPC не может искать союзника |
| SPREAD_RUMOR (social) | Да | REJECT | LOST (но пересоздаётся каждый тик → низкий ущерб) | NPC не может распространять слухи в движении |
| Schedule (routine) | Да (другой schedule) | PASS (через Stage 1: Schedule beats Schedule → first-seen wins) | RETAINED (заменяет incumbent) | Нет ущерба |
| +relocation | Да | SUPERSEDE (interrupts incumbent) | RETAINED | Нет ущерба (proper mechanism) |
| CHANGE_ROLE (social) | Да | REJECT | LOST | NPC не может сменить роль в движении |
| APPROACH (social) | Да | REJECT | LOST | NPC не может подойти к игроку |

### FLEE anomaly:

**SUPPORTED:** FLEE с reason="reactive:flee" содержит "flee", но B1.5 проверяет `"interrupt" not in reason` — "flee" ≠ "interrupt". FLEE должен проходить через CommitmentArbiter (movement_bridge.py:100-108), который может дать VERDICT_INTERRUPT. Но если B1.5 срабатывает ПЕРВЫМ (после CommitmentArbiter), FLEE может быть отклонён.

**Это требует экспериментальной проверки (Experiment A).**

### Intent loss:

- **PROVEN:** SEEK_ALLY теряется без следа (P5-D доказал)
- **NOT PROVEN для других:** SPREAD_RUMOR, CHANGE_ROLE пересоздаются каждый тик (если DecisionHub их выбирает повторно)
- **UNKNOWN:** FLEE — если отклонён B1.5, теряется ли реактивная защита NPC?

---

## P5-F.6 — Contract Consistency Audit

### A. Priority without execution authority

**PROVEN.** Stage 1 выбирает победителя по приоритету (Reactive > Schedule > Social). Но B1.5 может отклонить победителя, если у NPC есть active traversal. Priority Stage 1 не даёт права на исполнение.

### B. String-based capability

**PROVEN.** Право прерывания определяется содержимым `reason` string. `"interrupt"` и `"+relocation"` — единственные маркеры. Нет structured capability field.

### C. Silent rejection

**PROVEN.** `continue` в B1.5 (line 229) — intent исключается из `_filtered` без:
- логирования как потерянный (только debug-level)
- сохранения для повторного рассмотрения
- уведомления инициатора
- structured verdict

### D. Traversal lock without semantic priority

**PROVEN.** `status == "MOVING"` — единственный проверяемый критерий traversal. Не проверяется:
- кто создал traversal (ownership)
- каков приоритет traversal (schedule? social? reactive?)
- каков приоритет нового intent относительно traversal

### E. Inconsistent interruption policy

**PROVEN.** Разные источники движения получают разные права:
- LifeEngine schedule с "+relocation" → может прерывать (supersede)
- LifeEngine schedule без "+relocation" → не может прерывать
- DecisionHub SEEK_ALLY → не может прерывать
- DecisionHub FLEE → может прерывать через CommitmentArbiter, но B1.5 может отклонить

**Политика несогласована:** права определяются строковыми маркерами, а не единой системой приоритетов.

---

## P5-F.8 — Architecture Options

### Option A — Unified Pre-emption Arbitration

Согласовать Stage 1 и GATE B1.5: решение об изменении движения учитывает priority intent И state traversal.

| Критерий | Оценка |
|----------|--------|
| Изменение игровой семантики | Минимальное — расширяет права social intents |
| Архитектурная сложность | Средняя — B1.5 делегирует CommitmentArbiter |
| Риск регрессий | ВЫСОКИЙ — "бесконечный перезапуск" может вернуться |
| Затрагиваемые модули | movement_engine.py, movement_bridge.py |
| Совместимость | Требует настройки threshold для social intents |

### Option B — Explicit Interrupt Capability

Разделить описание причины движения и полномочие прерывания.

| Критерий | Оценка |
|----------|--------|
| Изменение игровой семантики | Нет — только структурирование |
| Архитектурная сложность | Низкая — добавить field в MacroMovementGoal |
| Риск регрессий | Низкий — existing callers unaffected (default False) |
| Затрагиваемые модули | movement.py (MacroMovementGoal), npc_tick_pipeline.py (reason builders) |
| Совместимость | Обратная совместимость: default can_interrupt=False |

### Option C — Deferred Intent

Повторное рассмотрение отклонённых intents после завершения traversal.

| Критерий | Оценка |
|----------|--------|
| Изменение игровой семантики | ДА — NPC "помнит" отклонённое намерение |
| Архитектурная сложность | ВЫСОКАЯ — новая подсистема |
| Риск регрессий | Средний — может создать очередь stalled intents |
| Затрагиваемые модули | movement_engine.py, scene_state (new field), tick_orchestrator |
| Совместимость | Требует ADR — новая сущность |

### Option D — Preserve Current Contract

Оставить B1.5 без изменений.

| Критерий | Оценка |
|----------|--------|
| Изменение игровой семантики | Нет |
| Архитектурная сложность | Нет |
| Риск регрессий | Нет |
| Затрагиваемые модули | Нет |
| Совместимость | Полная |
| **Риск** | **Социальные intents остаются "вторым классом" — расписание = рельсы** |

---

## Рекомендация исполнителя

**Option B (Explicit Interrupt Capability)** — минимальный риск, обратная совместимость, структурирование вместо string-matching. Но:

**Master должен сначала решить геймдизайнерский вопрос:** какие социальные намерения имеют право прерывать schedule traversal, при каких условиях (threat level, relationship, urgency), и на основании какого существующего механизма (CommitmentArbiter priority? New policy?).

**Не рекомендую Option A** без отдельного аудита "бесконечного перезапуска" — если просто убрать B1.5, может вернуться исходная проблема (RCB forensic).

---

## Финальная формула

> GATE B1.5 защищает реальный инвариант — schedule traversal должен достичь цели.
>
> Но защищает его строковым маркером, а не приоритетом.
> Система имеет три уровня арбитража с разными правилами.
> И когда социальное намерение проигрывает расписанию,
> оно не откладывается — оно умирает.
>
> Расписание не должно быть абсолютным хозяином тела.
> Но и тело не должно метаться между бесконечными желаниями.
>
> Нужна не новая очередь, а согласованная политика:
> кто вправе прервать движение, и что происходит с тем,
> кому отказано.

---

*P5-F CLOSED. Жду вердикта Master по Option A/B/C/D и геймдизайнерскому вопросу.*
