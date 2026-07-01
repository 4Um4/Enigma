# ENIGMA

ENIGMA is a causal simulation engine. The Fool is the first game and runtime proving ground.

README is a living sprint document: map, not territory. It must stay short, machine-readable, and useful to an architect opening the repository for the first time.

## Build Status

| Field | Value |
|---|---|
| project | ENIGMA / The Fool |
| version | V.0.5.3.2.7_Не_хватает_соединительной_ткани |
| branch | V.0.5.3.2.7_Не_хватает_соединительной_ткани |
| previous_snapshot | V.0.5.3.2.6_Всё_вижу_и_создаю |
| sprint_state_source | reports/LAST_SESSION.md |
| snapshot_datetime | 2026-06-28 14:43 Asia/Krasnoyarsk |
| campaign | Open_road |
| player | Венус |
| SHI | 100% |
| NPI | 100% |
| SCF | 1.0 |
| PFI | 0% |
| runtime_status | simulation_alive |
| primary_audience | architect_first_open |

## Quick Start

Prerequisite: Python 3.x on Windows PowerShell.

1. Open the repository root.
2. Install dependencies from the backend requirement files if present: `python -m pip install -r backend/requirements.txt`.
3. Start the game from root: `python game_launcher.py`.
4. If running backend directly, use the backend entry point after checking `backend/app/main.py` and local environment variables.
5. Read runtime state in `reports/LAST_SESSION.md`.
6. Read backend logs in `backend/logs/` when present.
7. Read DNA history in `reports/dna_history.jsonl`.

Do not diagnose from UI text alone. Diagnose from pipeline traces, session report, logs, and source contracts.

## Repository Anchors (source-of-truth files)

### Архитектура (закон)
- `docs/00_CAUSAL_CONTRACT_v2.0.md` (v2.0, текущий)
- `docs/ARCHIVE/2026-06-19/CAUSAL_CONTRACT_v1.0.md` (v1.0, для истории)
- `docs/АРХИТЕКТУРНЫЙ_УСТАВ_ENIGMA.md` (навигация)

### ADR (Architecture Decision Records)
- `docs/ADR (Architecture Decision Records).md` (полный список)
- `docs/audits/ADR_STATUS_MATRIX.md` (статусы реализации — C1-FIX)

### Технические задания (TЗ)
- `docs/Диаграммы игры/` (актуальные ТЗ и инструкции)
- `docs/Tasks/ТЗ/03_KNOWN_ISSUES_AND_BUGS.md` (регистр известных багов)

### Прочее
- `docs/DTO Registry (Реестр контрактов).md` (контракты)
- `docs/MUTATIONS.md` (история изменений)
- `docs/ARCHITECTURE_FLOW_GENERATED.md` (топология, генерируется из YAML)

## Architecture Summary

Core pipeline object: world tick.

Pipeline shape: CREATE -> READ -> TRANSFORM -> APPLY -> COMMIT -> PROJECT.

Current ownership:

| Area | Owner | Boundary |
|---|---|---|
| phase order | TickOrchestrator | execution follows pipeline |
| state mutation | DeltaBuffer / StateApplicator | no direct state bypass |
| scene commit | SceneStateManager | commit boundary stays explicit |
| NPC decision | DecisionHub and domain resolvers | evaluates, does not govern world |
| spatial truth | SpatialService / spatial runtime | UI and narrative are not spatial SSOT |
| projection | snapshot/projection services | reads committed reality |
| voice | LLM/verbalization | describes, does not decide facts |

## Architectural Prohibitions

- Execution must not make architectural decisions.
- Projection must not change reality.
- DecisionHub evaluates options; it does not manage world state.
- LLM is voice, not source of truth.
- Frontend displays snapshots and sends intents; it does not own state.
- New DTOs, services, states, ADRs, or layers require evidence that existing structures are insufficient.
- Fallback without root cause is forbidden.
- Mermaid in `docs/ARCHITECTURE_FLOW_GENERATED.md` is generated output; edit `architecture/*.yaml` and regenerate instead.
- Minimal local fix has priority over broad refactor.

## Active Bugs And Debt

| Priority | Item | Status |
|---|---|---|
| P0 | BUG-001 DirectiveInterpretationSubscriber state desync | listed in full register |
| P0 | BUG-002 TICK_CATCHUP breaks TraversalState | listed in full register |
| P1 | BUG-003 SHI=0% counter split risk | historical risk; latest SHI is 100% |
| P1 | BUG-004 NPC route resolves to entrance instead of target | listed in full register |
| P1 | Stale Cognition: DecisionHub reads state T-1 | active architectural debt |
| P1 | Cognitive Overlay Layer | separate sprint debt |

Source of truth for the list: `docs/Tasks/ТЗ/03_KNOWN_ISSUES_AND_BUGS.md` and `reports/LAST_SESSION.md`.

## Change Workflow

1. Define PIPELINE_OBJECT.
2. Define OWNER.
3. Reconstruct CREATE -> READ -> TRANSFORM -> APPLY -> COMMIT -> PROJECT.
4. Check Single Source of Truth.
5. Check ownership boundaries.
6. Check DTO and runtime contracts.
7. Identify FAIL_STAGE before proposing a fix.
8. Build H1/H2/H3 with confidence.
9. Choose minimal FIX_SCOPE.
10. Update docs required by the sprint close instruction.
11. Run the most local meaningful tests or sandbox checks.
12. Commit and push a named branch.

Required session-close documents are described in `docs/ИНСТРУКЦИЯ ПО ОКОНЧАНИЮ СЕССИИ.md`.

## What Not To Do

- Do not treat a symptom as root cause.
- Do not introduce a fallback to hide an unknown failure.
- Do not move responsibility between layers without evidence.
- Do not make projection, UI, or LLM mutate committed state.
- Do not create a second source of truth for spatial, memory, body, or scene state.
- Do not edit generated architecture maps by hand.
- Do not add new abstractions for aesthetic symmetry.
- Do not promise future features in README.

## External Auditor Contract

| Field | Value |
|---|---|
| archive_version | V.0.5.3.2.7_Не_хватает_соединительной_ткани |
| cut_datetime | 2026-06-28 14:43 Asia/Krasnoyarsk |
| audit_entry | README.md |
| session_state | reports/LAST_SESSION.md |
| architectural_index | docs/ADR (Architecture Decision Records).md |
| contract_index | docs/DTO Registry (Реестр контрактов).md |
| bug_register | docs/Tasks/ТЗ/03_KNOWN_ISSUES_AND_BUGS.md |
| expected_reader | external architect / LLM auditor |

Auditor rule: README gives entry points and current boundaries only. Final authority remains in source code, ADR, DTO registry, architecture YAML, and current session reports.

## Contact

Repository owner: `4Um4`.

Primary project address: `https://github.com/4Um4/Enigma`.
