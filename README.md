# ENIGMA — Deterministic Causal Simulation Engine

> Executable epistemic contracts for agent simulation: world truth, perception, memory, belief, narration — each layer causally traced, never conflated.

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.22831764-blue)](https://doi.org/10.5281/zenodo.22831764)
[![HuggingFace Space](https://img.shields.io/badge/%F0%9F%A4%97%20Space-ENIGMA-yellow)](https://huggingface.co/spaces/Um44/ENIGMA)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Version](https://img.shields.io/badge/version-0.5.4.4.8-orange)](https://github.com/4Um4/Enigma/releases)
[![Python](https://img.shields.io/badge/python-3.12+-blue)](https://www.python.org/)
[![Commits](https://img.shields.io/badge/commits-729-brightgreen)](https://github.com/4Um4/Enigma/commits/main)

## Live architectural overview

A visual overview of the architecture — 12-layer canonical order, enforced laws, causal trace, and the "Goran? Yes..." memory reconstruction scenario — is hosted on HuggingFace Spaces:

**→ https://huggingface.co/spaces/Um44/ENIGMA**

This GitHub repository contains the source code, full documentation, and reproducible build. The Space is a static presentation layer for the same artifact.

---

## What is this?

ENIGMA is a research project exploring whether a deterministic game simulation can generate meaningful emergent behavior when agents act based on their own incomplete and potentially erroneous models of the world — `WORLD TRUTH ≠ NPC MEMORY ≠ NPC BELIEF`.

**Not a game.** A scientific software artifact in active development.

**Not a tutorial.** Architectural documentation for researchers and engineers working on agent systems, epistemic logic, deterministic simulation, or LLM-assisted engineering.

**Not a product.** Solo-maintained research project, no support SLAs, no roadmap commitments to external stakeholders.

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
  version      = {0.5.4.4.8},
  year         = {2026},
  url          = {https://github.com/4Um4/Enigma},
  doi          = {10.5281/zenodo.22831764},
  license      = {AGPL-3.0}
}
```

**APA:**

> Gritsaenko, M. (2026). ENIGMA: Executable Epistemic Contracts in Deterministic Agent Simulation (Version 0.5.4.4.8) [Computer software]. https://doi.org/10.5281/zenodo.22831764

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
