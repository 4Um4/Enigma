# C:\DDD\Codex\VSC_Enigma\Enigma\Now.md
# NOW.md - Technical Audit of Enigma
Audit date: 2026-03-28
Workspace: `C:\DDD\Codex\VSC_Enigma\Enigma`

## 1) Audit Method (Step by Step)
1. Identified real entrypoints and boot chain from scripts and backend startup files.
2. Read documentation sources as potentially stale references:
   - `README.md`
   - `ROADMAP_v5.2.md`
   - `ENIGMA_ROADMAP_v8.1.md`
3. Built static import graph from runtime root `backend/app/main.py`.
4. Split modules into `Active`, `Orphan`, `Partial` based on real reachability and call-path usage.
5. Verified critical references by direct grep (imports, endpoint usage, script chaining).
6. Checked model config vs actual files in `Models LLM`.
7. Attempted test execution; recorded environment blockers and inferred test drift.

## 2) Documentation vs Reality (Drift Map)
`Roadmap.md` file does not exist as a single file. Actual roadmap sources are `ROADMAP_v5.2.md` and `ENIGMA_ROADMAP_v8.1.md`.

| Documentation Claim | Reality in Codebase | Status |
|---|---|---|
| Core runtime is `orchestrator.py` | Runtime core is `backend/app/services/game_loop.py` + `game_loop_factory.py`; `orchestrator.py` is absent | Drift |
| `reload_enigma.bat` exists | File absent; existing utility is `restart_all.bat` | Drift |
| `launcher.py` exists/used | File absent | Drift |
| Layered architecture folders (`services/core`, `input`, `engines`, `systems`, `ai`, `output`) are active | These folders are mostly absent in actual tree; current structure is flatter (`services/*`) | Drift |
| `intent_parser.py` fallback exists | File absent in repository | Drift |
| EventBus integrated through processor | `events/event_bus.py` exists but is not imported from runtime path | Drift |
| `memory_manager_agent.py` active | File exists but is not referenced by runtime graph | Drift |

## 3) Runtime Call Map (Actual)
Boot path:
1. `start_enigma.bat`
2. `backend/start_llm.bat`
3. `backend/start_backend.bat`
4. `uvicorn app.main:app`
5. `backend/app/main.py`
6. `app.api.routes` + `app.api.routes_stream` + `app.api.routes_debug`
7. `game_loop_factory.game_loop` singleton
8. `game_loop.run_turn()` (REST) or `game_loop.stream_turn()` (SSE)
9. `ActionProcessor` -> `PythonEngines` -> `RulesAgent` -> `NpcAgent` -> `DmAgent`

Frontend runtime path:
- `frontend/ui/index.html` calls `/api/game/action/stream` (primary) and `/api/game/action` (fallback).

## 4) Current Tree and State
Legend:
- `Ready` = implemented and wired in runtime.
- `In Progress` = wired/implemented partially, or has runtime defects/drift.
- `Stub` = placeholder or minimal skeleton.

```text
Enigma/
|- start_enigma.bat                         [Ready]
|- restart_all.bat                          [Ready]
|- test_gemma.bat                           [Ready, utility/orphan]
|- backend/
|  |- start_backend.bat                     [Ready]
|  |- start_llm.bat                         [Ready]
|  |- run_terminal_dm.py                    [In Progress, orphan, broken imports]
|  |- app/
|  |  |- main.py                            [Ready]
|  |  |- api/                               [In Progress]
|  |  |- agents/                            [Ready]
|  |  |- core/                              [Ready]
|  |  |- models/                            [Ready]
|  |  |- services/                          [Ready/In Progress mixed]
|  |- data/                                 [Ready/In Progress mixed]
|  |- tests/                                [In Progress]
|  |- AppAgent/                             [Ready, orphan external project]
|- frontend/
|  |- ui/index.html                         [Ready]
|  |- chat/.gitkeep                         [Stub]
|  |- map/.gitkeep                          [Stub]
|- Models LLM/                              [Ready/In Progress mixed]
|- docs/                                    [Stub]
|- pdf drop/                                [Ready, source assets]
```

## 5) Module Classification

### 5.1 Active (runtime-reachable)

#### API and entry
- `backend/app/main.py` - `Ready`
- `backend/app/api/routes.py` - `Ready`
- `backend/app/api/routes_stream.py` - `Ready`
- `backend/app/api/routes_debug.py` - `In Progress` (`time` used without import in `/debug/health/agents`)

#### Core and schemas
- `backend/app/core/config.py` - `Ready`
- `backend/app/core/runtime_config.py` - `Ready`
- `backend/app/core/settings_dm.py` - `Ready`
- `backend/app/core/settings_npc.py` - `Ready`
- `backend/app/core/settings_rules.py` - `Ready`
- `backend/app/core/settings_world.py` - `Ready`
- `backend/app/models/schemas.py` - `Ready`

#### Agents
- `backend/app/agents/dm_agent.py` - `Ready`
- `backend/app/agents/npc_agent.py` - `Ready`
- `backend/app/agents/rules_agent.py` - `Ready`
- `backend/app/agents/world_sim_agent.py` - `Ready`

#### Services: action and game loop
- `backend/app/services/game_loop.py` - `Ready`
- `backend/app/services/game_loop_factory.py` - `Ready`
- `backend/app/services/action/processor.py` - `Ready`
- `backend/app/services/action/player_target_extractor.py` - `Ready`
- `backend/app/services/action/python_engines.py` - `In Progress` (contains stale fallback import to removed `app.services.orchestrator`)
- `backend/app/services/action_classifier.py` - `Ready`

#### Services: game mechanics
- `backend/app/services/game/combat_math.py` - `Ready`
- `backend/app/services/game/physics_validator.py` - `Ready`
- `backend/app/services/game/sandbox_handler.py` - `Ready`
- `backend/app/services/combat_service.py` - `Ready`
- `backend/app/services/character_service.py` - `Ready`

#### Services: NPC and scene
- `backend/app/services/npc/npc_cognition.py` - `Ready`
- `backend/app/services/npc/psyche_engine.py` - `Ready`
- `backend/app/services/npc/perception_engine.py` - `Ready`
- `backend/app/services/npc/reaction_priority.py` - `Ready`
- `backend/app/services/npc/threat_assessor.py` - `Ready`
- `backend/app/services/npc/life_engine.py` - `Ready`
- `backend/app/services/scene_state_manager.py` - `Ready`
- `backend/app/services/scene_change.py` - `Ready`

#### Services: LLM and infra
- `backend/app/services/llm/router.py` - `Ready`
- `backend/app/services/llm/provider.py` - `Ready`
- `backend/app/services/llm/provider_manager.py` - `Ready`
- `backend/app/services/llm/factory.py` - `Ready`
- `backend/app/services/llm/llama_cpp_provider.py` - `Ready`
- `backend/app/services/model_router.py` - `Ready`
- `backend/app/services/llm_service.py` - `Ready`
- `backend/app/services/vram_monitor.py` - `Ready`
- `backend/app/services/error_interpreter.py` - `Ready`
- `backend/app/services/logging_tools.py` - `Ready`
- `backend/app/services/prompt_loader.py` - `Ready`

#### Services: state and persistence
- `backend/app/services/memory.py` - `Ready`
- `backend/app/services/campaign_state_service.py` - `Ready`
- `backend/app/services/player_session_service.py` - `Ready`
- `backend/app/services/knowledge_ingest.py` - `Ready`
- `backend/app/services/adventure_loader.py` - `Ready`
- `backend/app/services/readiness.py` - `Ready`
- `backend/app/services/world_scheduler.py` - `Ready`
- `backend/app/services/state/context_builder.py` - `Ready`
- `backend/app/services/simulation/world_state.py` - `In Progress` (context slice is wired; event ingestion path `record_event()` is not wired)
- `backend/app/services/system_requirements.py` - `Ready`

### 5.2 Orphan (Dead Code or disconnected from main call tree)
- `backend/app/agents/memory_manager_agent.py` - `Stub` (minimal wrapper, no runtime usage)
- `backend/app/core/error_logger.py` - `Ready` (legacy logger, not referenced by runtime)
- `backend/app/services/events/event_bus.py` - `In Progress` (implemented but not wired)
- `backend/app/services/events/event_types.py` - `In Progress` (implemented but not wired)
- `backend/app/services/llama_cpp.py` - `Ready` (legacy adapter path, not wired)
- `backend/app/services/npc/perception_filter.py` - `Ready` (implemented, not wired)
- `backend/app/services/pdf_drop_importer.py` - `Ready` (not connected to active API/runtime path)
- `backend/run_terminal_dm.py` - `In Progress` (imports removed modules: `app.services.orchestrator`, `app.services.context_builder`)
- `backend/AppAgent/*` - `Ready` external subsystem, isolated and not integrated with Enigma runtime

### 5.3 Partial (Declared/placeholder, not implemented as active behavior)
- `backend/app/__init__.py` - `Stub`
- `backend/app/agents/__init__.py` - `Stub`
- `backend/app/api/__init__.py` - `Stub`
- `backend/app/core/__init__.py` - `Stub`
- `backend/app/models/__init__.py` - `Stub`
- `backend/app/services/__init__.py` - `Stub`
- `backend/app/services/events/__init__.py` - `Stub`
- `backend/app/services/game/__init__.py` - `Stub`
- `backend/app/services/npc/__init__.py` - `Stub`
- `backend/app/services/simulation/__init__.py` - `Stub`
- `frontend/chat/.gitkeep` - `Stub`
- `frontend/map/.gitkeep` - `Stub`
- `frontend/ui/.gitkeep` - `Stub`
- `backend/data/assets/.gitkeep` - `Stub`
- `backend/data/campaigns/.gitkeep` - `Stub`
- `backend/data/pdf_drop/.gitkeep` - `Stub`
- `backend/data/worlds/.gitkeep` - `Stub`
- `backend/data/npc_major.gguf` - `Stub` (0-byte placeholder)
- `backend/data/npc_mass.gguf` - `Stub` (0-byte placeholder)
- Root `docs/` directory - `Stub` (empty)

## 6) Technical Findings

### Critical
1. `routes_debug` has runtime bug: `time.time()` without `import time`.
2. `run_terminal_dm.py` and some tests depend on removed `orchestrator` module; current state is incompatible with live architecture.

### High
1. Fallback model config drift:
   - Config references files that do not exist locally (`qwen2.5-7b-instruct-q4_k_m.gguf`, `saiga_mistral_7b_model-q4_K.gguf`, `mistral-pygmalion-7b.Q4_K_M.gguf`).
   - If fallback routing is triggered, model load may fail.
2. `world_state.record_event()` is never called, so planned event-context compression path is incomplete.
3. Event subsystem (`event_bus`, `event_types`, `perception_filter`) is implemented but disconnected from active processor/game loop path.

### Medium
1. Startup/config drift: `backend/start_llm.bat` hardcodes generation/runtime params (`NGPU`, `CTX`, `THREADS`, `NPRED`) separately from `config.py` values.
2. Documentation drift is significant and can mislead implementation decisions.

### Testability
- Test run could not be executed in this environment:
  - `pytest` unavailable in active interpreter.
  - Local `.venv` launcher points to missing Python path.
- Static inspection shows additional likely failures from stale imports in tests.

## 7) Next Steps (New Roadmap from Real Code)
Priority order is based on risk to runtime correctness and future refactoring safety.

### P0 - Runtime correctness (immediate)
1. Fix `backend/app/api/routes_debug.py`: add `import time`.
2. Remove/replace stale fallback import in `backend/app/services/action/python_engines.py` (`app.services.orchestrator`).
3. Decide terminal mode strategy:
   - Option A: migrate `run_terminal_dm.py` to `game_loop` architecture.
   - Option B: archive/remove script to avoid false expectations.

### P1 - Architecture consistency
1. Make one authoritative architecture doc (update `README.md` + one roadmap file).
2. Replace all references to `orchestrator.py` with `game_loop.py` where appropriate.
3. Mark speculative folders/phases explicitly as planned, not implemented.

### P2 - Dead code strategy
1. For each orphan module (`event_bus`, `perception_filter`, `pdf_drop_importer`, legacy `llama_cpp`):
   - either wire into runtime,
   - or move into `legacy/` with explicit deprecation marker,
   - or remove.
2. Normalize startup scripts and remove contradictory launch paths.

### P3 - Quality gate restoration
1. Repair Python environment pinning (`.venv` integrity) and test runner availability.
2. Update tests to current architecture (`game_loop` instead of removed `orchestrator`).
3. Add smoke tests for:
   - `/api/game/action/stream`
   - `/api/game/action`
   - `/api/debug/*`
   - model fallback behavior when files are missing.

## 8) Context for LLM
This section is optimized so another model can immediately continue implementation.

1. Runtime architecture is backend-centric FastAPI with frontend SSE transport.
2. Real execution root is `game_loop.py` (not `orchestrator.py`).
3. Pattern: Python computes state and mechanics first, LLM narrates after structured context is prepared.
4. Dependency flow is explicit and mostly constructor-injected in `game_loop_factory.py`.
5. `routes.py` and `routes_stream.py` are transport adapters; business logic is in services and agents.
6. State storage is file-based (`backend/data/*.jsonl` + campaign JSON files), no DB layer yet.
7. Model management pattern is singleton pool + router (`provider_manager`, `model_router`, `llm/router`).
8. Current refactor frontier is around event-driven simulation (`event_bus`, `world_state`, perception pipeline) which exists but is not fully connected.
9. Main technical debt is architecture drift between docs/scripts/tests and actual runtime graph.

## 9) Assumptions and Confidence
- This audit is static and filesystem-based; no live server startup was performed.
- Confidence is high for reachability classification (`Active/Orphan/Partial`) because it is grounded in import graph + direct reference search.
- Confidence is medium for runtime behavior claims that require live execution (LLM/fallback behavior under load).
