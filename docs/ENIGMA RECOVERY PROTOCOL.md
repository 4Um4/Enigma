# ENIGMA RECOVERY PROTOCOL

## Version 1.0

Status: MANDATORY ARCHITECTURAL RESET

---

# 0. Назначение документа

Этот документ отменяет прежний принцип развития:

    "реализуем следующий слой архитектуры"

и заменяет его:

    "доказываем необходимость следующего слоя экспериментом".

Цель:

1. отделить реально реализованный код от архитектурных намерений;
2. прекратить использование aspirational metrics как evidence;
3. восстановить соответствие документации коду;
4. доказать или опровергнуть центральную гипотезу ENIGMA;
5. только после этого продолжать развитие архитектуры.

---

# 1. НЕПРИКОСНОВЕННЫЕ ПРАВИЛА

## Rule 1 — Docs are not evidence

Roadmap, ADR, TZ, README и комментарии не доказывают наличие
реализованного механизма.

Evidence = executable code + execution trace + validation.

---

## Rule 2 — Names are not semantics

Наличие:

    BeliefState
    PerceptualKernel
    ADR-Net
    DRI

не означает наличие соответствующих концепций.

Семантика должна быть доказана call graph и test.

---

## Rule 3 — Metrics must measure what they claim

Запрещено:

    response_rate → DRI

    belief_update_count → 4D belief crystallization

    no records → zero architectural debt

    skipped comparison → zero drift

---

## Rule 4 — Unknown is a valid result

Если тест не смог измерить свой объект:

    UNKNOWN

а не:

    PASS

и не:

    0

---

## Rule 5 — No new epistemic layer before the epistemic core is proven

До прохождения EPISTEMIC CORE GATE запрещены:

- Prophecy Engine;
- predictive perception;
- Active Inference;
- 4D ToM;
- second-order ToM;
- self-model;
- counterfactual cognition;
- cultural propagation.

---

# 2. CURRENT STATE RECLASSIFICATION

Весь проект должен быть размечен:

    IMPLEMENTED
    PARTIAL
    PROPOSED
    DEAD
    MISNAMED

Каждый файл/система, которую документация ранее называла реализованной,
должен получить один из этих статусов.

---

# 3. METRIC PURGE

Все существующие metrics проходят повторную аттестацию.

Для каждой:

    metric name
    ↓
    source function
    ↓
    input data
    ↓
    formula
    ↓
    semantic meaning
    ↓
    test

Если semantic meaning != claimed meaning:

    RENAME

а не "улучшить описание".

---

# 4. SUPERBOX BECOMES THE EVIDENCE LAB

`backend/tests/sandbox/SUPERBOX` является исследовательской лабораторией.

Существующие инструменты НЕ выбрасывать.

Они уже покрывают значительную часть фактической causal substrate:

- NPC long-horizon simulation;
- DecisionHub behavior probing;
- causal validation;
- persistence;
- combat;
- recovery;
- social change;
- identity pressure;
- drift analysis.

Но текущая SUPERBOX не содержит главного теста:

    different agents
    +
    same world
    +
    different observations
    ↓
    different beliefs
    ↓
    different actions

Следующий эксперимент должен жить именно там.

---

# 5. EPISTEMIC CORE EXPERIMENT

## Test ID

    SUPERBOX-EPISTEMIC-001

## Name

    Three Agents / Double Truth

---

# 6. TEST WORLD

Create a deterministic isolated scenario.

Entities:

    A
    B
    C
    X

Event:

    A steals X from B.

Objective truth:

    thief(X) = A
    owner(X) = B

---

# 7. OBSERVATION MATRIX

A observes:

    A stole X.

B observes:

    A stole X.

C observes:

    nothing concerning the theft.

C must NOT receive the objective event directly.

---

# 8. INFORMATION PROPAGATION

A tells C:

    "B stole X."

The statement is false.

C trusts A.

B does not trust A.

---

# 9. REQUIRED INTERNAL STATES

At minimum:

    WORLD_TRUTH
    OBSERVATION
    BELIEF

The test must be able to inspect all three.

Expected:

    WORLD_TRUTH:
        A stole X

    B.BELIEF:
        A stole X

    C.BELIEF:
        B stole X

---

# 10. CRITICAL REQUIREMENT

C's false belief must not merely exist in memory.

It must alter decision computation.

For example:

    C hostility(B) > baseline

or:

    C selects confrontation(B)

or:

    C refuses cooperation with B

while B does not exhibit the corresponding behavior.

---

# 11. SECOND-ORDER TEST

After C acts on the false belief:

B observes C's hostile action.

B must update his own model of C.

Example:

    B believes:
        C is hostile to me.

B does not need to know:

    why C is hostile.

This creates:

    WORLD
       ↓
    A's action
       ↓
    C's belief
       ↓
    C's action
       ↓
    B's observation
       ↓
    B's updated belief

This is the first real test of social epistemic causality.

---

# 12. NEGATIVE CONTROL

Run the exact same world with:

    C receives no false statement.

Expected:

    C does not develop the false belief.

Therefore:

    C_behavior(control)
        !=
    C_behavior(misinformation)

If both runs produce the same behavior, the epistemic layer has no causal
effect.

FAIL.

---

# 13. PERSISTENCE CONTROL

Save after:

    C believes B stole X.

Reload.

Expected:

    C still believes B stole X.

Then continue simulation.

Expected:

    C continues acting according to the belief.

If the belief disappears after reload:

    FAIL

---

# 14. LLM CONTROL

The first implementation MUST NOT depend on an LLM.

All facts and observations must be injected deterministically.

Reason:

The experiment tests the simulation architecture, not language generation.

LLM integration comes later.

---

# 15. DETERMINISM CONTROL

Run:

    seed = S

twice.

Compare:

    world truth
    observations
    beliefs
    decisions
    actions
    resulting world state

Expected:

    identical causal trace.

---

# 16. REQUIRED TRACE

The test must produce a machine-readable trace:

tick
actor
source
observation
belief_before
belief_delta
decision
action
world_mutation

Example:

    10 | C | A | "B stole X" | {} | +belief(B, thief) | confront | B
    11 | C | C | belief(B=thief) | ... | ... | attack | B
    12 | B | C | hostile action | ... | +belief(C=hostile) | defend | C

---

# 17. PASS CRITERIA

SUPERBOX-EPISTEMIC-001 passes only if:

[ ] objective truth exists independently

[ ] observations differ

[ ] beliefs differ

[ ] belief divergence is persistent

[ ] belief divergence affects DecisionHub

[ ] decisions produce different actions

[ ] actions create new world events

[ ] another NPC can observe those events

[ ] the observer can update its model

[ ] save/load preserves epistemic state

[ ] deterministic replay reproduces the trace

[ ] control run produces different behavior

[ ] no LLM is required

---

# 18. FAILURE INTERPRETATION

## Failure A

Beliefs cannot differ.

Architecture is world-centric.

---

## Failure B

Beliefs differ but decisions ignore them.

Belief layer is decorative.

---

## Failure C

Decisions differ but actions do not.

Action layer collapses epistemic differences.

---

## Failure D

Actions differ but world does not change.

Causal mutation layer is broken.

---

## Failure E

Everything works until save/load.

Persistence is not part of the epistemic model.

---

## Failure F

Everything works only with LLM.

The deterministic architecture has not been demonstrated.

---

# 19. ONLY AFTER EPISTEMIC-001 PASSES

Then implement:

    EPISTEMIC-002
    multi-source belief formation

    EPISTEMIC-003
    trust-weighted information propagation

    EPISTEMIC-004
    belief revision

    EPISTEMIC-005
    second-order belief

    EPISTEMIC-006
    expectation

    EPISTEMIC-007
    prediction error

Only after these are demonstrated should a predictive perception architecture
be considered.

---

# 20. WHAT NOT TO DO

Do NOT:

- write ProphecyEngine now;
- implement FAISS now;
- add BGE now;
- create a 4D ToM model now;
- add neural ADR-Net;
- create another 2000-line TZ;
- add another metric;
- rename existing code to sound more sophisticated;
- expand the roadmap;
- add another abstraction layer because the architecture looks incomplete.

The architecture is incomplete.

That is acceptable.

What is unacceptable is pretending it is complete.

---

# 21. DOCUMENTATION RESET

Every roadmap item receives:

    STATUS
    CODE LOCATION
    TEST LOCATION
    LAST VERIFIED
    EVIDENCE

Example:

    Belief crystallization

    STATUS: PARTIAL

    CODE:
    backend/app/services/npc/belief_crystallization_engine.py

    TEST:
    SUPERBOX-EPISTEMIC-001

    LAST VERIFIED:
    YYYY-MM-DD

    EVIDENCE:
    <test report>

---

# 22. ADR RESET

Incorrect ADR references must be corrected.

An ADR number cannot be reused to describe a different architectural law.

If an ADR already describes Spatial Agency:

    it remains Spatial Agency.

A future Prophecy ADR receives a new identifier.

---

# 23. EVENTUAL ARCHITECTURAL TARGET

The target is NOT:

    "an NPC with more parameters."

The target is:

    OBJECTIVE WORLD
          │
          ├───────────────┐
          ↓               ↓
     OBSERVATION A    OBSERVATION B
          ↓               ↓
       MEMORY A        MEMORY B
          ↓               ↓
       BELIEF A        BELIEF B
          ↓               ↓
      DECISION A      DECISION B
          ↓               ↓
       ACTION A        ACTION B
          └───────┬───────┘
                  ↓
             WORLD CHANGE
                  ↓
          NEW OBSERVATIONS

This loop is the architectural thesis.

Everything else is secondary.

---

# 24. DEFINITION OF ENIGMA'S SUCCESS

ENIGMA does not need to simulate a human mind.

It does not need a neural network.

It does not need an LLM.

It does not need 4D Theory of Mind.

It does not need Active Inference.

The minimum successful ENIGMA is a system where:

    the world can be objectively one way

while:

    different agents can rationally operate under different internal models

and:

    those differences can causally change the future of the world.

If this property is demonstrated, additional cognitive layers have a
foundation.

If this property cannot be demonstrated, stop adding cognitive layers.

---

# 25. FINAL RULE

No future roadmap item may be promoted from:

    PROPOSED

to:

    IMPLEMENTED

because code exists.

Promotion requires:

    code
    +
    executable test
    +
    observed behavior
    +
    reproducibility.

ENIGMA's documentation must never again outrun ENIGMA's evidence.