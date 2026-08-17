# ENIGMA

> A deterministic causal simulation engine for agents, world state, memory,
> perception, belief, decision and emergent narrative.

**Status: Experimental / Research Prototype**

ENIGMA is not currently a finished autonomous-world simulator.

It is an evolving simulation architecture whose central research question is:

> Can a deterministic game simulation produce meaningful emergent behavior
> when agents act not directly on objective world truth, but on their own
> incomplete and potentially incorrect models of that world?

This distinction is the core of the project.

---

# 1. What ENIGMA actually is

ENIGMA is a Python-based simulation/game engine built around a causal tick loop.

The currently implemented system contains real infrastructure for:

- deterministic world ticks;
- NPC state;
- needs and drives;
- decision scoring;
- movement;
- spatial state;
- relationships;
- trust / attraction;
- memory;
- identity events;
- L1 chronicle persistence;
- belief-related state;
- state mutation;
- recovery / decay;
- economic simulation;
- combat;
- player actions;
- LLM-assisted dialogue;
- replay / drift experiments;
- causal validation;
- long-horizon sandbox simulation.

The project does **not** currently claim that all planned epistemic or predictive systems are implemented.

---

# 2. The central hypothesis

Traditional game AI generally follows:

    WORLD STATE
        ↓
    NPC PERCEPTION
        ↓
    NPC DECISION
        ↓
    ACTION
        ↓
    WORLD CHANGE

ENIGMA is investigating a deeper model:

    WORLD TRUTH
        ↓
    PERCEPTION
        ↓
    OBSERVATION
        ↓
    MEMORY
        ↓
    BELIEF
        ↓
    EXPECTATION
        ↓
    MOTIVATION
        ↓
    DECISION
        ↓
    ACTION
        ↓
    WORLD CHANGE

The critical property is:

    WORLD TRUTH ≠ AGENT BELIEF

and, more importantly:

    AGENT A BELIEF ≠ AGENT B BELIEF

if their observations, memories, trust relationships or inference histories
differ.

This property is not considered implemented merely because a class called
"Belief" exists.

It must be demonstrated experimentally.

---

# 3. Objective truth vs subjective model

The intended long-term architecture distinguishes at least three categories:

## World truth

What actually happened in the simulation.

Example:

    A stole the ring from B.

## Agent observation

What an agent actually had access to.

Example:

    B saw A near the ring.

    C was not present.

## Agent belief

What the agent currently considers true.

Example:

    B believes A stole the ring.

    C believes B stole the ring.

The engine must never silently collapse these into one state.

---

# 4. Current implementation

The current codebase contains a functioning causal simulation substrate.

The strongest currently demonstrated areas are:

- tick orchestration;
- state mutation;
- NPC decision scoring;
- needs;
- drives;
- relationships;
- spatial behavior;
- combat effects;
- stress / affect;
- identity pressure;
- persistence;
- economic modifiers;
- long-horizon sandbox execution;
- causal validation;
- **epistemic divergence** (three-agent «Double Truth» scenario);
- **epistemic causal chain** (Belief → Decision);
- **observation divergence** (different agents observe different events);
- **decision divergence** (different beliefs produce different decisions);
- **second-order observation** (NPC_A's action cascades to NPC_B's belief);
- **second-order Theory of Mind attribution** (NPC_B believes NPC_A asserts P);
- **epistemic persistence** (beliefs survive save/load and GameLoop restart);
- **perception membrane hardening** (agents cannot bypass the perception layer);
- **modifier composition** (additive, layer-stacked decision deformation);
- **modifier commutativity** (order-independent scoring);
- **action / world-event causation** (Belief → Task → Scheduled World Event).

The `backend/tests/sandbox/SUPERBOX` directory contains dedicated research
tools for NPC simulation, causal validation, drift analysis, behavior
experiments and stress testing.

The `backend/tests/sandbox/SUPERBOX/scenarios` directory holds the executable
evidence scenarios for the epistemic architecture. Each `SUPERBOX-NNN` scenario
proves one causal contract of the belief→decision→action→world-change chain.
These scenarios are part of the project's evidence layer and double as the
acceptance gate for epistemic claims.

---

# 5. What is NOT currently claimed as implemented

The following are research targets unless directly backed by executable code
and a passing validation scenario:

- predictive perception kernel;
- information-theoretic surprise;
- full predictive-processing loop;
- 4D belief representation;
- BELIEVES predicates;
- prophecy causality;
- self-fulfilling prophecy;
- semantic LLM cache;
- BGE / FAISS semantic retrieval;
- formal Dialogue Response Integrity;
- neural ADR classifier;
- Active Inference integration;
- full self-model;
- counterfactual reasoning.

> Note: Second-order Theory of Mind is no longer in this list — it has been
> proven by `SUPERBOX-014` (Second-Order Attribution). First-order epistemic
> divergence, observation divergence, decision divergence, persistence and
> the full Belief → Decision → Action → World-Event causal chain are likewise
> proven by the `SUPERBOX-NNN` scenarios under
> `backend/tests/sandbox/SUPERBOX/scenarios`.

A roadmap entry is not evidence of implementation.

A class name is not evidence of semantics.

A metric is not evidence unless its computation is traceable to the claimed
property.

---

# 6. Evidence standard

ENIGMA follows a strict rule:

> A system is implemented only when its behavior is observable and
> reproducibly testable.

For every architectural claim there must eventually exist:

    CLAIM
      ↓
    CODE
      ↓
    CALL PATH
      ↓
    TEST
      ↓
    OBSERVABLE RESULT

For example:

Bad:

    "Belief Layer implemented."

Good:

    "NPC A and NPC B receive different observations of the same event.
     Their persisted beliefs diverge.
     Their subsequent decisions diverge because of those beliefs.
     The divergence survives at least N ticks and survives save/load."

---

# 7. Current architectural layers

The currently implemented architecture should be understood approximately as:

    WORLD / SNAPSHOT
          ↓
    PERCEPTION / EVENT PROCESSING
          ↓
    NPC STATE
          ↓
    NEEDS / DRIVES
          ↓
    DECISION HUB
          ↓
    ACTION / MOVEMENT
          ↓
    STATE MUTATION
          ↓
    PERSISTENCE / CHRONICLE

Additional systems attach to this pipeline:

    relationships
    economy
    combat
    identity
    recovery
    memory
    LLM dialogue
    replay / drift analysis

This architecture is real.

The deeper epistemic architecture is no longer purely proposed — its
foundational layer has been proven by the `SUPERBOX-NNN` scenarios
(epistemic divergence, observation divergence, decision divergence,
second-order attribution, persistence, perception membrane, modifier
composition/commutativity, and the full Belief → Decision → Action →
World-Event causal chain). The research frontier now is to deepen and
harden that epistemic layer, not to build it from scratch.

---

# 8. The research frontier

The decisive question was never:

    "Can ENIGMA have more systems?"

It was:

    "Can ENIGMA produce causal behavior from different internal models
     of the same objective world?"

That minimum experiment — a three-agent epistemic divergence scenario —
has now been performed and passed by the `SUPERBOX` scenarios.

The canonical form:

    WORLD TRUTH:

        A stole X from B.

    A:
        knows that A stole X.

    B:
        witnessed the theft.

    C:
        did not witness the theft.

    A tells C:
        "B stole X."

    C trusts A.

Result (proven, not expected):

    Truth:
        A stole X.

    B belief:
        A stole X.

    C belief:
        B stole X.

B and C then produce different behavior from the same objective world
because their beliefs diverge. C acts against B because of the false
belief; B treats A as the culprit. The simulation has demonstrated the
essential property ENIGMA was designed to investigate.

The research frontier is therefore no longer to prove the core thesis.
It is to harden it: longer horizons, larger agent populations, richer
belief sources (testimony, inference, memory decay), and resistance to
collapse under save/load and long-horizon drift.

---

# 9. What would constitute failure

The following are failures:

- all agents access the same objective truth;
- beliefs are merely aliases for world state;
- beliefs are overwritten globally;
- dialogue text says an agent believes something but the decision engine
  does not use it;
- belief differences do not affect behavior;
- belief differences disappear on the next tick without causal reason;
- save/load destroys the divergence;
- the LLM invents the belief while deterministic simulation remains unaware
  of it;
- the test passes only because assertions inspect strings instead of state.

The goal is not to generate convincing text.

The goal is to generate different causal futures.

---

# 10. LLM's role

The LLM is not the intelligence substrate of ENIGMA.

The deterministic engine owns:

- state;
- time;
- causality;
- perception;
- memory;
- belief;
- decision;
- action;
- persistence.

The LLM may provide:

- language interpretation;
- dialogue realization;
- narrative expression.

A generated sentence cannot create a world fact unless a deterministic
simulation pathway accepts and validates the corresponding mutation.

---

# 11. Determinism

Determinism is an engineering requirement for the simulation core.

The system should allow:

    initial state
        +
    seed
        +
    player actions
        +
    tick sequence
        ↓
    reproducible simulation

Cosmetic randomness must not be confused with causal nondeterminism.

Replay validation must distinguish:

- structural state divergence;
- causal divergence;
- numerical drift;
- cosmetic movement jitter.

A replay metric must never report "zero drift" merely because the comparison
was skipped after an upstream failure.

---

# 12. Documentation policy

ENIGMA documentation uses three statuses.

## IMPLEMENTED

Executable code exists and a validation scenario demonstrates the claimed
behavior.

## PARTIAL

Some infrastructure exists, but the complete semantic contract is not
demonstrated.

## PROPOSED

The architecture is designed or hypothesized but is not implemented.

Roadmap items are not implementation evidence.

---

# 13. Current project position

ENIGMA is a causal NPC/world simulation prototype with a proven foundational
epistemic layer.

The first major milestone — the central architectural thesis — has been met:

    DIFFERENT BELIEFS → DIFFERENT DECISIONS → DIFFERENT FUTURES

This is demonstrated, not hypothesized. The `SUPERBOX-NNN` scenarios under
`backend/tests/sandbox/SUPERBOX/scenarios` are the executable evidence:
epistemic divergence, observation divergence, decision divergence,
second-order attribution, persistence across save/load, perception membrane
hardening, modifier composition/commutativity, and the full
Belief → Decision → Action → World-Event causal chain.

ENIGMA is not yet a completed epistemic simulation engine. The remaining
work is to harden and broaden the proven layer (longer horizons, richer
belief sources, larger populations, drift resistance) before stacking
additional predictive or counterfactual systems on top of it.

---

# 14. Development principle

Do not build the next abstraction because it is intellectually attractive.

Build it because the previous experiment proves that the simulation requires it.

The project therefore proceeds from:

    observable behavior
        ↓
    causal requirement
        ↓
    minimal architecture
        ↓
    implementation
        ↓
    validation

not:

    theory
        ↓
    roadmap
        ↓
    names
        ↓
    presumed implementation

---

# 15. License

See repository license.