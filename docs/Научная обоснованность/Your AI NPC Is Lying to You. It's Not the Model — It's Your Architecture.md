---
title: "Your AI NPC Is Lying to You. It's Not the Model — It's Your Architecture"
published: false
description: "LLMs hallucinate. The real engineering question is whether a hallucinated claim can become world truth. Inside ENIGMA's epistemic architecture: perception, memory, belief revision, runtime guards, and deterministic simulation."
tags: ai, gamedev, architecture, python
cover_image: https://raw.githubusercontent.com/4Um4/Enigma/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/article_cover.png
---

Everyone blames the model when an AI character contradicts its own past.

The model hallucinated. The prompt was too weak. We need a bigger context window. Maybe RAG will fix it.

But what if the actual problem is somewhere else?

While building **ENIGMA**, a deterministic causal simulation engine for RPG worlds, I kept returning to a different question:

**What prevents something an NPC merely heard from becoming something that actually happened in the world?**

That question led me to an architectural principle that is easy to state and surprisingly difficult to enforce:

**World truth, perception, memory, and belief are different things. They must never be treated as interchangeable.**

## The dangerous shortcut: treating generated text as memory

Consider a familiar implementation:

```python
messages.append({
    "role": "system",
    "content": f"You are Marta. Your life so far: {summary}"
})

reply = llm.chat(messages)
```

The summarizer reconstructs Marta's past from previous conversations.

Suppose it invents a detail: Marta's brother died.

The summary is saved. Later, another conversation uses that summary as context. Marta now mourns a brother who is actually alive.

The next summary preserves the mistake.

The model didn't need to be consistently wrong. The architecture made its first mistake persistent.

This is the distinction that matters:

- A model can generate an incorrect statement.
- A character can believe an incorrect statement.
- A character can remember receiving incorrect information.
- None of these events should silently rewrite objective world history.

An LLM can hallucinate. The architecture decides what happens next.

## A claim is not a fact

ENIGMA implements a distinction that is particularly important for social simulation.

Someone saying that an event happened is itself an objective event.

The content of what they said is a separate proposition.

And what another character believes about that proposition is yet another object.

These are represented separately in ENIGMA's epistemic model.

The relevant data structures are `Proposition`, `ClaimEvent`, and `EpistemicRecord`.

A simplified view of their actual contracts:

```python
@dataclass(frozen=True)
class Proposition:
    subject_id: str
    predicate: Predicate
    object_id: str
    polarity: bool = True


@dataclass(frozen=True)
class ClaimEvent:
    event_id: str
    claim_id: str
    speaker_id: str
    listener_id: str
    proposition: Proposition
    speech_act: SpeechAct = SpeechAct.ASSERT
    tick: int = 0
```

A proposition describes what is being asserted. It does not contain an objective truth value.

A ClaimEvent records the communication: who said something, to whom, and when.

The listener's EpistemicRecord stores a different set of information:

- Which agent holds the belief.
- Which proposition they believe.
- Their confidence.
- Who supplied the information.
- Which claim introduced it.
- When it was first observed and last updated.
- Whether the information came from direct observation or testimony.
- The original source in a chain of retold information.

Notice the consequence.

If Goran tells Tornin that someone stole a ring, the engine can record that Tornin received this claim without declaring that the theft actually happened.

Tornin may believe it. He may distrust Goran. Someone else may contradict him.

The world does not need to change just because a sentence was spoken.

This is not a prompt convention. These are separate data structures with separate responsibilities.

Sources: [epistemology.py](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/app/domain/epistemology.py), [claim_event_subscriber.py](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/app/services/events/claim_event_subscriber.py).

## Belief revision: who told you matters

Storing beliefs is not enough.

A character needs a mechanism for updating them.

ENIGMA uses `BeliefRevisionEngine` to process claims and produce updated epistemic records.

The engine delegates source reliability to a separate provider.

Its current policy distinguishes between repeated information from the same source and independent confirmation.

For example:

- A new claim establishes an initial confidence based on source reliability.
- Repetition from the same source provides a smaller confidence increase.
- Confirmation from another source provides a larger increase.

The implementation uses a same-source boost of `0.2` against the incoming confidence contribution.

This is deliberately deterministic and does not require an LLM to decide whether the listener should believe someone.

There is another important detail: the resulting epistemic context is resolved separately before the decision system consumes it.

`EpistemicContextResolver` projects stored records into cognitively relevant information. `DecisionHub` receives that context rather than directly treating the entire epistemic store as its decision interface.

The result is a causal path:

```text
NPC_SPOKE / COMMUNICATION_CLAIM
              |
              v
      ClaimEventSubscriber
              |
              v
      BeliefRevisionEngine
              |
              v
         EpistemicStore
              |
              v
    EpistemicContextResolver
              |
              v
          DecisionHub
```

This is a foundation for NPCs that act on what they know, rather than on everything the game engine knows.

An important distinction: ENIGMA also has a separate `BeliefCrystallizationEngine`. It transforms aggregated `EvidenceOfPersistence` into persistent psychological beliefs. It is not the same mechanism as the claim-based epistemic revision system.

I consider this separation important because not every kind of belief should be produced by the same process.

Sources: [BeliefRevisionEngine](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/app/services/npc/belief_revision_engine.py), [EpistemicContextResolver](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/app/services/npc/epistemic_context_resolver.py), [BeliefCrystallizationEngine](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/app/services/npc/belief_crystallization_engine.py).

## Memory is not a conversation transcript

Another architectural mistake is assuming that everything an NPC has encountered should be stored as one growing dialogue history.

In ENIGMA, memory has its own lifecycle.

`MemoryManager` coordinates several memory mechanisms, including:

- Layered memory.
- Working memory.
- EventMemory.
- Dialogue sessions and consolidation.
- Persistent storage.

Memory processing also has a defined position in the simulation pipeline.

The documented tick sequence places memory processing before NPC decision-making.

That matters because a character should not make a decision using information that only becomes available after that decision.

It also means that memory is not simply a text summary injected into an LLM context window.

The character's memory is part of the simulation state, with its own processing and persistence mechanisms.

There is still substantial development work in this area. ENIGMA's memory architecture is an active development track, not a finished universal memory solution.

Source: [MemoryManager](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/app/services/memory/memory_manager.py).

## Architecture should fail loudly

Here is where the design becomes enforceable.

It is easy to write:

> Only StateApplicator may modify NPCState.

It is harder to prevent another module from violating that rule.

ENIGMA implements a caller-based write guard in `NPCState.__setattr__`.

Unauthorized writes to guarded fields raise `ArchitecturalViolationError` before the assignment is applied.

For example, beliefs have an explicit write permission boundary.

The corresponding test attempts a direct assignment:

```python
with pytest.raises(ArchitecturalViolationError):
    state.beliefs = {}
```

The test verifies that the exception identifies the protected field and the unauthorized calling module.

This is more meaningful than a comment in an architecture document: the rule is exercised by executable code.

There is an important qualification. The allowlist still contains temporary permissions for several legacy modules. This is a concrete enforcement mechanism for guarded writes, not a claim that every mutable object in the entire application is universally protected.

Source: [NPCState](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/app/models/npc_state.py), [test_belief_single_writer.py](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/tests/test_belief_single_writer.py).

## The LLM does not belong in the causal decision loop

Another rule in ENIGMA is that the simulation kernel must not depend on LLM generation to determine its causal decisions.

The project contains an AST-based checker, `lint_llm_exile.py`.

It examines five designated kernel modules:

- `tick_orchestrator`
- `npc_tick_pipeline`
- `decision_hub`
- `life_engine`
- `phases/decision.py`

It looks for specified generation methods such as `invoke`, `complete`, `chat`, and `generate` on recognized LLM-related receivers.

The intention is straightforward:

The simulation determines what an NPC decides and what happens in the world.

The LLM can participate in language-related work, but its generated text is not automatically authorized to mutate canonical simulation state.

This checker is intentionally scoped. It is not a universal proof that no possible LLM call exists anywhere in the repository.

The broader architectural contract is that interpretation and state mutation are separated. For example, `StateDeltaProposal` explicitly describes a proposal as input to validation, not as a command that can directly mutate NPC state.

Source: [lint_llm_exile.py](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/scripts/lint_llm_exile.py), [state_delta_proposal.py](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/app/domain/state_delta_proposal.py).

## Randomness is another source of architectural lies

A simulation that cannot reproduce its own random decisions is difficult to debug.

Consider:

```python
if random.random() < 0.4:
    ...
```

The result depends on hidden process-level RNG state and the order in which random calls occur.

ENIGMA instead uses `KernelRNG`.

```python
rng = KernelRNG(
    tick=42,
    npc_id="maid_lusya"
)

if rng.random() < 0.4:
    ...
```

Its seed is derived from:

```python
seed_raw = f"{tick}:{npc_id}:{salt}".encode("utf-8")
seed = int(hashlib.sha256(seed_raw).hexdigest(), 16)
```

The important contract is:

Same `(tick, npc_id, salt)` → same seed → same initial random sequence.

Different NPC identifiers or salts produce different seeds.

There are focused tests for repeated sequences, different NPCs, different ticks, invalid inputs, and deterministic selection.

ENIGMA also has an AST checker that rejects direct `random.*` calls in its designated simulation modules. The RNG and wall-clock checks are registered in the project's pre-commit configuration.

This does not make every conceivable execution path deterministic. It does make a critical source of hidden nondeterminism an explicit architectural concern with executable checks.

Sources: [KernelRNG](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/app/services/npc/kernel_rng.py), [RNG tests](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/backend/tests/test_kernel_rng.py), [RNG linter](https://github.com/4Um4/Enigma/blob/V.0.5.4.6.2_%D0%9B%D0%9B%D0%9C_2/scripts/lint_kernel_rng.py).

## What is actually finished?

ENIGMA is not a finished RPG.

It is an engine under active development.

Its README describes a 12-layer canonical construction and 18 architectural laws. Several development tracks remain active, including memory architecture, belief-to-expectation work, and narrative grounding.

I don't want to confuse an architectural foundation with a finished simulation.

What already exists is a set of distinct mechanisms and executable contracts:

- Objective events are not equivalent to claims.
- Claims are not equivalent to beliefs.
- Memory and epistemic state have separate representations.
- Belief revision has an explicit policy and source provenance.
- Protected state has runtime write guards.
- Selected kernel modules are checked for forbidden LLM calls.
- Simulation randomness has an explicit deterministic source.
- Architectural checks are part of the development workflow.

The remaining work is substantial. The system is not presented as a solved theory of cognition or a finished autonomous society.

But the direction is deliberate.

## The question worth asking about your own AI agents

When an NPC says something false, ask three questions:

1. Did the world actually change?
2. Did the NPC receive information that was false or incomplete?
3. Did the NPC form an incorrect belief from that information?

These are three different causal situations.

If your architecture cannot distinguish them, debugging an NPC's behavior becomes an exercise in interpreting generated text.

If it can distinguish them, you can inspect the chain of events, identify the source of the belief, and determine where the contradiction originated.

That is the engineering principle behind ENIGMA:

**The world has its own truth. Every character has their own access to it. And the difference between the two must be represented in code.**

---

**ENIGMA — Deterministic Causal Simulation Engine**

- Source code: https://github.com/4Um4/Enigma
- Architecture overview and interactive presentation: https://huggingface.co/spaces/Um44/ENIGMA
- Research citation: https://doi.org/10.5281/zenodo.22831764

The next challenge is not making NPCs sound more human.

It is making their knowledge, mistakes, decisions, and consequences form a coherent life.