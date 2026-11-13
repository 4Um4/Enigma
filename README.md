# ENIGMA — Deterministic Causal Simulation Engine

> Executable epistemic contracts for agent simulation: world truth, perception, memory, belief, narration — each layer causally traced, never conflated.

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.22831764-blue)](https://doi.org/10.5281/zenodo.22831764)
[![HuggingFace Space](https://img.shields.io/badge/%F0%9F%A4%97%20Space-ENIGMA-yellow)](https://huggingface.co/spaces/Um44/ENIGMA)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Version](https://img.shields.io/badge/version-0.5.4.6.5-orange)](https://github.com/4Um4/Enigma/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Commits](https://img.shields.io/github/commit-activity/y/4Um4/Enigma)](https://github.com/4Um4/Enigma/commits/main)

## Live architectural overview

A visual overview of the architecture — 12-layer canonical order, enforced laws, causal trace, and the "Goran? Yes..." memory reconstruction scenario — is hosted on HuggingFace Spaces:

**→ https://huggingface.co/spaces/Um44/ENIGMA**

This GitHub repository contains the source code, full documentation, and reproducible build. The Space is a static presentation layer for the same artifact.

---

## What is this?

ENIGMA is an RPG engine where replayability approaches infinity.

Traditional RPGs offer branching paths — finite states, finite outcomes. ENIGMA's NPCs have genuine causal subjectivity: they remember what they perceived, form beliefs from experience, and decide based on their own lived history — not scripts. Every playthrough is unique because every NPC's internal state evolves causally from the player's specific actions.

**Why does replayability approach infinity?** Because the game state is not a tree of branches — it's a causal graph. Every NPC has memory that decays, beliefs that crystallize from experience, relationships that shift from real events, and a will that can be masked by social pressure. When you meet an NPC for the second time, they remember the first. When you betray them, they fear you. When someone tells them about your betrayal, they believe based on their trust in the teller — or they don't, if they don't trust the source. No two playthroughs share the same causal history — therefore no two playthroughs produce the same NPC behavior.

The foundation is a deterministic causal simulation: `WORLD TRUTH ≠ NPC MEMORY ≠ NPC BELIEF`. Agents act on incomplete, potentially erroneous models of the world. The 12-layer canonical construction ensures that memory, belief, relationship, and decision are causally traced — never conflated, never faked.

**A game engine, not yet a game.** The simulation infrastructure is in active development — 12 canonical layers, 18 enforced architectural laws, 400+ session iterations. The RPG experience — quests, world, player agency, emotional arcs — will be built on top of this foundation.

**Solo-maintained.** No support SLAs, no roadmap commitments to external stakeholders. Architectural documentation for researchers and engineers working on agent systems, epistemic logic, deterministic simulation, or LLM-assisted engineering.

What it is: a 12-layer canonical construction enforced by 18 architectural laws that raise `ArchitecturalViolationError` at runtime when violated.

## Key architectural principles

- **Epistemic grounding** — LLM is never a source of canonical truth; Python = causal authority (`INV-LLM-NOT-SSOT`)
- **Deterministic replay** — KernelRNG-protocol, no `random.*` or wall-clock in simulation layer (§15)
- **Causal layering** — 12-layer canonical construction order; upper layers must use the causal work of lower layers, never imitate it
- **Anti-Bond** — no parallel truth-stores, no decorative state — every entity must prove causal work no other entity performs
- **Belief non-mutation** — beliefs are lenses (weight modifiers), not genes (scalars); personality drift via interpretation is forbidden (§16)
- **Epistemological orthogonality** — `Reality` and `Observer Knowledge` are orthogonal axes; consumers receive only epistemic representations (§17)

## The 12-layer canonical construction order

| # | Layer | What is built |
|---|-------|---------------|
| 0 | **Authoring → Compiler** | Human description → semantic reconstruction → structured dossier → validation → materialization in stores. LLM translates, Python validates and writes. |
| 1 | **Identity / History** | `origin_events` → canonical NPC history → EventMemory / Chronicle / role history / relationship history |
| 2 | **Body → Need** | Body state, needs, sleep, hunger — and their real consumers |
| 3 | **Desire → Object → Activity** | Desire / Activity / Object mechanisms unified into a single circuit |
| 4 | **Decision → Action → Outcome** | `CAN ≠ WANT ≠ INTEND ≠ ATTEMPT ≠ SUCCESS`; TAKE/USE/MOVE/GIVE/FOLLOW and consequences |
| 5 | **Perception → Experience → Memory** | Perception membrane, personal experience, chronology, event_id, bounded recall, provenance |
| 6 | **Salience → Consolidation** | Event significance for a specific NPC → decay → consolidation → compression → deterministic distortion |
| 7 | **Relationships as History** | RelationshipEvent → repeated interactions → relationship changes → social consequences |
| 8 | **Belief → Expectation → Decision** | BC-2…BC-7: experience/testimony → belief → conclusion → expectation → decision |
| 9 | **NPC as Interface** | Targeted recall, biography, provenance, epistemic divergence, investigation loop, grounding, ignorance |
| 10 | **Self-Interpretation** | `WHAT HAPPENED ≠ WHAT REMEMBERS ≠ WHAT BELIEVES ≠ HOW EXPLAINS` |
| 11 | **Appraisal / Prediction / Humor** | Expectation → prediction error → appraisal → individual reactions / humor |
| 12 | **Deception** | `KNOWLEDGE → INTENTION TO DECEIVE → FALSE CLAIM → NARRATION` |

**Cross-cutting law:** each upper layer must use the causal work of the layer below, not imitate it.

`Dialogue ≠ Memory` · `Memory ≠ Causality` · `Belief ≠ Decision` · `Relationship scalar ≠ History` · `Self-interpretation ≠ Motivation` · `LLM ≠ Canonical Truth`

## Documentation

- **[Architectural Roadmap v4.12](docs/ENIGMA_ROADMAP_v4_12_WPS.md)** — operational map of all tracks (RE-01, AG1, NL-01, CCH, MEM, COV, EPI, MOT)
- **[Architectural Charter](docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md)** — 18 enforced laws (§ENIGMA-001..018)
- **[Working Mode](РЕЖИМ%20РАБОТЫ.md)** — meta code architect protocol for LLM-assisted development
- **[Citation file](CITATION.cff)** — BibTeX / APA / Chicago formats
- **[MUTATIONS archive](MUTATIONS.md)** — closed changes history (S1–S376+)

## Status

**Closed tracks:** RE-01 M2/D + G/H · AG1 BC-1 · CCH-0..5 · COV-0..2 · LC-IMPL-1..2

**Active fronts:** BC-2 (Conclusion → Expectation) · MOT (Motive & Decision Trace) · MEM (Memory Architecture) · NL-01 фаза 1 (Narrative Grounding)

**Planned:** NL-12 (active deception) · EPI (information lifecycle) · WPS (world process simulation) · MAG (somatico-resonance magic, deferred)

## Release build

The release script builds one game entry-point, `Bloodloom.exe`. The loading
screen is embedded in that executable and is started internally with `--splash`.
The default command performs a local build and creates a portable ZIP without
publishing or installing system drivers:

```powershell
.\publish_release.ps1 -CheckOnly
```

Use `-Publish` only when the build is ready to publish on GitHub. On first run,
open Settings → LLM Models and download the recommended `Lumimaid-v0.2-8B
Q4_K_M` model. At every launch the updater checks the latest GitHub release and
shows a separate Yes/No confirmation before downloading it.

## Repository structure

```
.
├── architecture/          # YAML topology (architecture-as-code)
├── backend/                # Python simulation engine
│   ├── app/
│   │   ├── domain/         # Pure dataclasses (no dependencies)
│   │   ├── models/         # Domain models
│   │   ├── services/       # Business logic (RE, AG1, MEM, NL, ...)
│   │   └── api/            # REST API layer
│   └── tests/              # IPT + gameplay + canary
├── frontend/               # Pygame UI (no backend imports, Law 1.1)
├── docs/                   # ADRs, charter, roadmap
├── diagnostics/            # Read-only observation (never mutates state)
├── scripts/                # Lint, session patches, probes
├── config/                 # NPC configs, calibration presets
└── reports/                # Session artifacts, audits
```

## Citation

```bibtex
@software{gritsaenko_2026_enigma,
  author       = {Gritsaenko, M.},
  title        = {ENIGMA: Executable Epistemic Contracts in Deterministic Agent Simulation},
  version      = {0.5.4.6.5},
  year         = {2026},
  url          = {https://github.com/4Um4/Enigma},
  doi          = {10.5281/zenodo.22831764},
  license      = {AGPL-3.0}
}
```

**APA:**

> Gritsaenko, M. (2026). ENIGMA: Executable Epistemic Contracts in Deterministic Agent Simulation (Version 0.5.4.6.5) [Computer software]. https://doi.org/10.5281/zenodo.22831764

## Acknowledgments

This project was developed through multi-model LLM-assisted engineering (GLM, GPT, Claude, Gemini, Kimi, DeepSeek) over free-tier web access. The architectural discipline — archaeological protocol, ADR-PRE-FLIGHT, executable invariants — emerged as a defense against model drift across versions.

The working methodology is documented in [`РЕЖИМ РАБОТЫ.md`](РЕЖИМ%20РАБОТЫ.md) and may be of independent interest to researchers studying LLM-assisted software engineering workflows.

## License

GNU AGPL v3.0 — use it, modify it, but if you serve it over network, share the source.

```
ENIGMA — Deterministic Causal Simulation Engine
Copyright (C) 2026  Gritsaenko, M.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
```
