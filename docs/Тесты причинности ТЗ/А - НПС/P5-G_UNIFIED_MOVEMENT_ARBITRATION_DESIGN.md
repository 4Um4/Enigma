# P5-G — UNIFIED MOVEMENT ARBITRATION DESIGN & REGRESSION PROOF

**Forensic Milestone** — архитектурный дизайн + regression proof.

**Baseline:** `72cf47b0658ffe8cae6351213ddbfb3b48f2e6d2`
**Вердикт:** **Design Ready** — с одним CRITICAL finding (FLEE BLOCKED).

---

## Executive Verdict

**FLEE BLOCKED — PROVEN.** NPC не может физически отреагировать на угрозу (FLEE) при активном schedule traversal. Это **более серьёзный дефект**, чем SEEK_ALLY: реактивная защита NPC парализована.

### Краткие результаты по 7 трекам:

| Track | Вердикт | Главная находка |
|-------|---------|----------------|
| A — FLEE Runtime | **FLEE BLOCKED** | CommitmentArbiter возвращает PASS (LOG_ONLY), не прерывает traversal, B1.5 отклоняет FLEE |
| B — CommitmentArbiter Contract | **Partial authority** | Priority-based, но MacroMovementGoal не имеет intent_type → получает PRIORITY_ROUTINE |
| C — Unified Feasibility | **EXTEND** | CommitmentArbiter можно расширить, но требует intent_type в MacroMovementGoal |
| D — RCB Protection | **PROVEN** | B1.5 защищает от RCB, но блокирует ВСЕ non-interrupt intents |
| E — Transient Intent Fate | **DROP** | SEEK_ALLY и FLEE оба теряются без следа |
| F — Minimal Fix Options | **Option B+C** | Structured intent_type + B1.5 делегирует CommitmentArbiter |
| G — Regression Matrix | **12 scenarios** | G-05 (FLEE) = CRITICAL, G-04 (SEEK_ALLY) = KNOWN |

---

## Track A — FLEE Runtime Forensics

### Вердикт: FLEE BLOCKED

**PROVEN через runtime spy:**

```
FLEE intent (maid_lusya, reason="reactive:flee", priority=0.8, domain=ROUTINE)
    ↓
CommitmentArbiter.enforce_for_intent:
    candidate_priority = 2 (PRIORITY_ROUTINE — MacroMovementGoal lacks intent_type)
    incumbent = {status: EXECUTING, executor: traversal, priority: 0}
    2 > 0 + 3 = False → NOT VERDICT_INTERRUPT
    VERDICT_REJECT, but ARBITER_ENFORCEMENT=False → return True (LOG_ONLY PASS)
    traversal_changed = False ← traversal NOT interrupted
    ↓
MovementEngine.process_intents (B1.5):
    active_traversals[maid_lusya].status = "MOVING"
    reason="reactive:flee" — не содержит "interrupt" или "+relocation"
    → continue (REJECTED)
    ↓
spatial_changes for maid_lusya = 0
```

### Контрольные случаи:

| Случай | Результат | Доказательство |
|--------|----------|----------------|
| FLEE без active traversal | PASS (spatial_changes created) | Tick 1: maid_lusya SEEK_ALLY passes (no traversal yet) |
| FLEE с active schedule traversal | **BLOCKED** (0 spatial_changes) | Tick 2-3: maid_lusya FLEE, traversal MOVING → 0 changes |
| FLEE с traversal от другого источника | BLOCKED (same mechanism) | Tick 2: guard_borko also blocked (traversal from proactive_spread_rumor) |

### Root cause chain:

1. **MacroMovementGoal lacks `intent_type` field** → `resolve_candidate_priority(intent_type="", domain=ROUTINE)` returns PRIORITY_ROUTINE (2)
2. **PRIORITY_ROUTINE < threshold** (need > incumbent_priority + 3) → VERDICT_REJECT
3. **ARBITER_ENFORCEMENT=False** (default, LOG_ONLY) → REJECT becomes PASS (return True)
4. **Traversal NOT interrupted** → B1.5 sees MOVING traversal → REJECT

**Три уровня отказа:**
- Level 1: intent_type missing → wrong priority
- Level 2: ARBITER_ENFORCEMENT=False → REJECT becomes PASS
- Level 3: B1.5 → traversal still MOVING → silent continue

---

## Track B — CommitmentArbiter Contract

### Вердикт: C — механизм с частичными полномочиями

CommitmentArbiter — это **priority-based arbitrage mechanism** с частичными полномочиями:

| Аспект | Реальность | Доказательство |
|--------|-----------|----------------|
| Verdicts | PASS, REJECT, INTERRUPT | `commitment_arbiter.py:61-63` |
| Priority system | `resolve_candidate_priority(intent_type, intent_domain)` → int | `action_priority.py:57-90` |
| Enforcement | `enforce_for_intent` → если INTERRUPT: `interrupt_traversal()` | `commitment_arbiter.py:283-294` |
| LOG_ONLY mode | REJECT → return True (pass without interrupt) | `commitment_arbiter.py:298-300` |
| ENFORCEMENT mode | REJECT → return False (block) | `commitment_arbiter.py:298-299` |
| Priority resolution | Domain-based: SURVIVAL > SOCIAL > ROUTINE; Windowed > Sleep > Domain > ROUTINE | `action_priority.py:72-90` |

**Проблема:** MacroMovementGoal не имеет `intent_type` field → `getattr(intent, "intent_type", "")` = "" → `resolve_candidate_priority("", ROUTINE)` = PRIORITY_ROUTINE (2).

**CommitmentArbiter НЕ видит:**
- Что intent — это FLEE (reactive)
- Что intent — это SEEK_ALLY (social)
- Что intent — это SPREAD_RUMOR (social)

Все MacroMovementGoals получают PRIORITY_ROUTINE, независимо от их реального типа.

---

## Track C — Unified Arbitration Feasibility

### Вердикт: EXTEND

CommitmentArbiter можно использовать как центральную точку, но требует **минимального расширения**:

1. **Добавить `intent_type` в MacroMovementGoal** (или использовать `reason` для вывода типа)
2. **Включить ARBITER_ENFORCEMENT** (или хотя бы ENFORCEMENT для REACTIVE domain)
3. **Делегировать B1.5 решение CommitmentArbiter'у** — если VERDICT_INTERRUPT, traversal уже прерван; если PASS, B1.5 пропускает; если REJECT, B1.5 отклоняет

**Не нужно:** новый арбитр, новый store, новая очередь.

---

## Track D — RCB Protection Proof

### Вердикт: PROVEN — RCB защищён, но чрезмерно

| Scenario | B1.5 effect | RCB protection | Game damage |
|----------|------------|----------------|-------------|
| RCB-1: Schedule completion | ✅ Protected | ✅ Traversal reaches boundary | None |
| RCB-2: Repeated proactive | ✅ Blocked | ✅ No infinite restart | Social intents lost |
| RCB-3: Repeated need | ✅ Blocked | ✅ No infinite restart | Need intents lost |
| RCB-4: Valid interruption | ❌ Only "+relocation" | ⚠️ Too restrictive | FLEE blocked |
| RCB-5: No false interruption | ✅ Social blocked | ✅ Correct | But ALL social blocked |
| RCB-6: Completion boundary | ✅ Works | ✅ | None |
| RCB-7: Deterministic replay | ✅ Reproducible | ✅ | None |

**RCB protected, но over-protected:** B1.5 блокирует не только proactive/need intents (RCB threat), но и reactive (FLEE) и social (SEEK_ALLY) — которые НЕ вызывают RCB.

---

## Track E — Transient Intent Fate

| Intent | Причина отклонения | Что дальше | Существующий механизм | Вердикт |
|--------|-------------------|------------|----------------------|---------|
| SEEK_ALLY | B1.5 (traversal MOVING) | DecisionHub выбирает FLEE на следующем тике | REASSESS (new decision) | **REASSESS** — но оригинальный intent потерян |
| FLEE | B1.5 (traversal MOVING) | DecisionHub выбирает FLEE снова | REASSESS (repeats) | **RETRY** — FLEE повторяется, но всегда blocked |
| SPREAD_RUMOR | B1.5 (traversal MOVING) | DecisionHub выбирает снова | REASSESS | **RETRY** — пересоздаётся каждый тик |
| Schedule | Stage 1 (first-seen wins) | Если incumbent — сохраняется | PERSIST (traversal lifecycle) | **PERSIST** |
| +relocation | B1.5 supersede | Прерывает traversal | SUPERSEDE | **SUPERSEDE** |

**SEEK_ALLY: REASSESS** — новый decision на каждом тике, но оригинальное решение потеряно.
**FLEE: RETRY (но всегда BLOCKED)** — повторяется, но не может исполниться из-за traversal.

---

## Track F — Minimal Fix Options

### Recommended: Option B+C (Structured intent_type + B1.5 delegates to CommitmentArbiter)

**Изменения:**
1. **MacroMovementGoal**: добавить `intent_type: str = ""` field (backward compatible)
2. **npc_tick_pipeline**: при создании MacroMovementGoal, заполнить `intent_type` из DecisionHub decision
3. **B1.5**: заменить string-based check на CommitmentArbiter verdict
4. **ARBITER_ENFORCEMENT**: enable для REACTIVE domain (FLEE must interrupt)

**Затрагиваемые файлы:**
- `backend/app/domain/movement.py` — добавить field
- `backend/app/services/npc/npc_tick_pipeline.py` — заполнить intent_type
- `backend/app/services/spatial/movement_engine.py` — B1.5 delegate to CommitmentArbiter
- `backend/app/services/action/commitment_arbiter.py` — возможно, priority threshold tuning

**RCB protection preserved:** CommitmentArbiter уже имеет priority system — ROUTINE (social) не прервёт ROUTINE (schedule), но SURVIVAL (FLEE) прервёт.

---

## Track G — Regression Matrix

| ID | Сценарий | Текущий результат | После fix (ожидаемый) | Статус |
|---|---------|------------------|----------------------|--------|
| G-01 | Schedule без конфликтов | ✅ Completes | ✅ Unchanged | PASS |
| G-02 | Repeated proactive | ✅ Blocked | ✅ Blocked (priority insufficient) | PASS |
| G-03 | Repeated need | ✅ Blocked | ✅ Blocked | PASS |
| G-04 | SEEK_ALLY vs schedule | ❌ Blocked | ⚠️ Depends on priority policy | DESIGN DECISION |
| G-05 | FLEE vs schedule | ❌ **BLOCKED** | ✅ INTERRUPT (SURVIVAL > ROUTINE) | **CRITICAL FIX** |
| G-06 | Social vs schedule | ✅ Blocked | ✅ Blocked (unless priority sufficient) | PASS |
| G-07 | +relocation | ✅ Supersede | ✅ Unchanged | PASS |
| G-08 | "interrupt" string | ❌ String authority | ✅ Priority-based | FIX |
| G-09 | Completed traversal | ✅ No block | ✅ Unchanged | PASS |
| G-10 | Rejected transient | ❌ DROP | ⚠️ REASSESS (existing) | DESIGN DECISION |
| G-11 | Deterministic replay | ✅ Reproducible | ✅ Unchanged | PASS |
| G-12 | Enforcement off/on | ❌ Divergent semantics | ✅ Consistent | FIX |

---

## Required Game Design Decisions

Master/Геймдизайнер должен решить:

1. **FLEE priority:** Should FLEE (SURVIVAL domain) always interrupt schedule traversal?
   - Technical: Yes — SURVIVAL > ROUTINE in `resolve_candidate_priority`
   - Game design: Yes — NPC must be able to flee from danger

2. **SEEK_ALLY priority:** Should SEEK_ALLY (SOCIAL domain) interrupt schedule traversal?
   - Technical: Depends on `resolve_candidate_priority` — SOCIAL currently gets PRIORITY_ROUTINE
   - Game design: **Decision needed** — under what conditions?

3. **ARBITER_ENFORCEMENT:** Should ENFORCEMENT mode be ON by default?
   - Currently OFF (LOG_ONLY) — REJECT becomes PASS
   - If ON: REJECT actually blocks (return False)
   - Risk: may block legitimate movements that currently pass

4. **Transient intent fate:** Should rejected SEEK_ALLY be retried after traversal completion?
   - Currently: REASSESS (new decision each tick) — original intent lost
   - Option: DEFER (retry after traversal) — requires new mechanism
   - Game design: **Decision needed**

---

## Production Change Scope (description only, no implementation)

### Phase 1 — Critical Fix (FLEE)
1. Add `intent_type` field to MacroMovementGoal
2. Fill `intent_type` in npc_tick_pipeline when creating movement intents
3. Enable ARBITER_ENFORCEMENT for SURVIVAL domain intents
4. B1.5: delegate to CommitmentArbiter instead of string matching

### Phase 2 — Policy Tuning (SEEK_ALLY)
1. Define priority policy for SOCIAL domain intents
2. Decide: should SEEK_ALLY interrupt schedule? Under what conditions?
3. Implement priority threshold for SOCIAL interrupts

### Phase 3 — Intent Fate (optional)
1. If DEFER is needed: add minimal deferral mechanism
2. Re-evaluate rejected intents after traversal completion

---

## Финальная формула

> FLEE BLOCKED — это не просто потеря intent.
> Это паралич реактивной защиты NPC.
>
> NPC может решить бежать, но не может бежать.
> Потому что MacroMovementGoal не знает, что он — FLEE.
> А CommitmentArbiter не знает, что кандидат — реактивный.
> А B1.5 не знает ничего, кроме строки reason.
>
> Три механизма, три незнания, одна блокировка.
>
> Исправление — не новая подсистема.
> Это — дать существующему арбитру знать, что он арбитрит.

---

*P5-G Design Ready. Жду вердикта Master по Phase 1 (Critical Fix) и Game Design Decisions.*
