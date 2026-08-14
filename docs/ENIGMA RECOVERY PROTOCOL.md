# ENIGMA RECOVERY PROTOCOL

## Version 2.0

Status: MANDATORY ARCHITECTURAL RESET — EPISTEMIC CORE PARTIALLY PROVEN

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

## Текущий статус (S188)

Эпистемическое ядро (Epistemic Core) частично доказано экспериментами
SUPERBOX-001 — SUPERBOX-013. Доказана причинная цепь:

    Communication → ClaimEvent → Proposition → BeliefRevisionEngine
        → EpistemicStore → EpistemicContextResolver → EpistemicContext
        → DecisionContext → DecisionHub → Intent

Доказан Modifier Contract v1: модификаторы аддитивны, детерминированы,
коммутативны и не мутируют исходный score-space.

НЕ доказано: production-интеграция (EpistemicStore не подключён к
NpcTickPipeline.run()), persistence (save/load), replay determinism,
контрольный прогон (control vs treatment) через полный GameLoop.

Следующий шаг: Фаза 8 — Production Integration.

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

## 4.1. Эксперименты EPISTEMIC (S186-S188)

Проведено 13 экспериментов, доказывающих эпистемическую причинность:

| SUPERBOX | Статус | Доказано |
|----------|--------|----------|
| 001 | PASS | Causal baseline (terminal MVP): каузальная труба жива, L1 работает |
| 002 | PASS | Proposition → Belief (pure unit test): детерминированная ревизия убеждений |
| 003 | PASS | EventBus → ClaimSubscriber → Belief: реальная шина доставляет ClaimEvent |
| 004 | RED | Belief → Decision: EpistemicStore не влияет на DecisionHub (разрыв локализован) |
| 005 | RED | DecisionHub contract absent: в сигнатуре compute() нет epistemic-входа |
| 006 | PASS | EpistemicContext DTO: семантический контракт (threats, allies, violations) |
| 007 | PASS | DecisionContext composition: EpistemicContext встроен композиционно (frozen) |
| 008 | PASS | EpistemicContextResolver: Store → Context (детерминированная проекция, read-only) |
| 009 | RED | Context → DecisionHub: DecisionHub проигнорировал EpistemicContext (RED последнего разрыва) |
| 010 | PASS | Epistemic causality: EpistemicContext → epistemic_modifiers → DecisionHub → Δscore |
| 011 | PASS | Modifier composition: социальные + эпистемические модификаторы складываются |
| 012 | PASS | Isolation/Additivity: Δ(E) = E, Δ(S) = S, Δ(E+S) = E+S, coupling_error = 0 |
| 013 | PASS | Commutativity + purity: apply(E,S) == apply(S,E), apply_modifiers — pure function |

## 4.2. Доказанные Epistemic Primitives

Следующие примитивы являются ПРОДОЛЖЕННЫМИ и ДОКАЗАННЫМИ:

| Primitive | Файл | Статус |
|-----------|------|--------|
| Proposition | `app/domain/epistemology.py` | 🟢 Доказан (S002) |
| SpeechAct | `app/domain/epistemology.py` | 🟢 Доказан (S002) |
| ClaimEvent | `app/domain/epistemology.py` | 🟢 Доказан (S002, S003) |
| EpistemicRecord | `app/domain/epistemology.py` | 🟢 Доказан (S002) |
| EpistemicContext | `app/domain/epistemology.py` | 🟢 Доказан (S006, S007) |
| BeliefRevisionEngine | `app/services/npc/belief_revision_engine.py` | 🟢 Доказан (S002) |
| EpistemicStore | `app/services/npc/epistemic_store.py` | 🟢 Доказан (S002, S008) |
| ClaimEventSubscriber | `app/services/events/claim_event_subscriber.py` | 🟢 Доказан (S003) |
| EpistemicContextResolver | `app/services/npc/epistemic_context_resolver.py` | 🟢 Доказан (S008) |
| SourceReliabilityProvider | Protocol в `belief_revision_engine.py` | 🟢 Доказан (S002) |
| COMMUNICATION_CLAIM | `app/services/events/event_types.py` | 🟢 Доказан (S003) |
| epistemic_modifiers | `app/services/npc/decision_hub.py` | 🟢 Доказан (S010-S013) |
| apply_modifiers (pure) | `app/services/npc/decision_hub.py` | 🟢 Доказан (S013) |

## 4.3. Modifier Contract v1

> DecisionHub принимает независимые числовые деформации пространства
> intent scores. Модификаторы аддитивны, детерминированы, коммутативны
> и не мутируют исходный score-space.

Доказано: S011 (аддитивность), S012 (изоляция), S013 (коммутативность + purity).

## 4.4. Архитектурные инварианты Epistemic Layer

1. **Claim ≠ Truth** — ClaimEvent никогда не является World Truth.
2. **Belief ≠ Truth** — EpistemicRecord хранит субъективное состояние, не факт.
3. **Proposition не мутирует RelationshipStore напрямую** — только через DecisionHub modifiers.
4. **SUPERBOX может инъецировать ClaimEvent, но никогда не инъецирует Belief/Relationship/Decision.**
5. **L1 Chronicle не хранит субъективные убеждения** — только provenance событий.
6. **confidence ≠ truth probability** — это детерминированное числовое состояние epistemic revision.
7. **EpistemicContext не содержит World Truth** — только perceived_* поля.
8. **DecisionHub не знает об EpistemicStore** — только о Dict[str, float] модификаторах.

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

[x] objective truth exists independently — доказано S002 (world_truth != c_belief)

[x] beliefs differ — доказано S002, S003 (EpistemicRecord хранит субъективное состояние)

[x] belief divergence affects DecisionHub — доказано S010 (score 0.19 → 0.79)

[x] no LLM is required — доказано S002, S003 (детерминированная инъекция ClaimEvent)

[ ] observations differ — НЕ ДОКАЗАНО (требует multi-agent наблюдаемости)

[ ] belief divergence is persistent — НЕ ДОКАЗАНО (требует save/load)

[ ] decisions produce different actions — ЧАСТИЧНО (доказано изменение score, но не intent)

[ ] actions create new world events — НЕ ДОКАЗАНО (требует production-интеграции)

[ ] another NPC can observe those events — НЕ ДОКАЗАНО (требует multi-agent пайплайна)

[ ] the observer can update its model — НЕ ДОКАЗАНО

[ ] save/load preserves epistemic state — НЕ ДОКАЗАНО

[ ] deterministic replay reproduces the trace — НЕ ДОКАЗАНО

[ ] control run produces different behavior — НЕ ДОКАЗАНО (требует full GameLoop control vs treatment)

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

# 19. NEXT STEPS (после S188)

## Фаза 8: Production Integration (S189)

Следующий шаг — внедрить EpistemicStore в production tick pipeline:

1. EpistemicStore инъецируется в TickState (через NpcTickPipeline.run).
2. EpistemicContextResolver.resolve() вызывается в NpcTickPipeline.run()
   перед DecisionHub.compute().
3. EpistemicContextResolver.to_modifiers() передаётся как epistemic_modifiers
   в DecisionHub.compute().
4. ClaimEventSubscriber регистрируется в GameLoop (как NpcDialogueSubscriber).
5. SourceReliabilityProvider реализуется через RelationshipStore.trust().

## После Phase 8:

    EPISTEMIC-002
    multi-source belief formation

    EPISTEMIC-003
    trust-weighted information propagation

    EPISTEMIC-004
    belief revision (contradictory evidence)

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