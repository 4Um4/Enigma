# Enigma Backend - Current Project State (2026-03-14)

## Overview
FastAPI backend for **Enigma** - multi-agent LLM-powered RPG system. Features:
- **Agents**: DM (narrative), NPC (dialog), Rules (d20 checks), World (simulation).
- **LLM Router**: Llama.cpp providers, dynamic ports, health checks, capability mapping.
- **Memory**: Layered JSONL (world/campaign/session).
- **Services**: Orchestrator pipeline, error interpreter (5 types: timeout/OOM/context/JSON/model), VRAM monitor, combat, knowledge ingest, PDF drops.
- **API**: /api/routes, /api/debug/health/agents, frontend UI mount (/ui).
- **Monitoring**: JSONL logs (data/logs/enigma_*.jsonl), startup checks (resources/ports/files).

### Structure
```
backend/
├── app/                # FastAPI app (main.py)
│   ├── agents/         # DM/NPC/Rules/World agents
│   ├── api/            # Routes, debug
│   ├── core/           # Config, settings_*.py, TODO.md
│   ├── models/         # Pydantic schemas
│   └── services/       # LLM, memory, orchestrator, error_interpreter, vram_monitor
├── data/               # runtime_ports.json, campaigns/, logs/
├── tests/              # Unittests (services, startup, llm, error_interpreter), TODO.md
├── requirements.txt    # FastAPI 0.115, uvicorn, pydantic, psutil, pytest
├── start_backend.bat   # uvicorn app.main:app
├── start_llm.bat       # llama-server.exe qwen2.5-7b
└── run_test_llm.bat    # tests/test_llm.py
```

## Current Status
| Component | Status | Details |
|-----------|--------|---------|
| Core App | ✅ 90% | main.py startup (router init, loggers, health). |
| LLM Router/Provider | ✅ 80% | Llama.cpp, singleton pool, capability prefs. Server often down. |
| Agents/Orchestrator | ✅ 70% | Pipeline DM→Rules→NPC→DM; error wrapping partial. |
| Memory/Services | ✅ 85% | JSONL layered, combat, ingest; tests pass basics. |
| Error/VRAM | ✅ Partial | Interpreter (5 types), VRAM monitor; integration TODO. |
| Tests | ⚠️ 65% | Unittests pass mocks/memory; FAIL LLM health/imports. |
| Startup | ⚠️ 60% | Resources OK (15GB RAM, NVIDIA); FAIL LLM/app imports. |
| **Overall Phase 1** | **65-80%** | Stability focus; ready for Phase 2 (SSE streaming). |

**Progress Source:** Multiple TODO.md (core/data/tests/TODO_fix_tests), logs (19 recent startups).

## Known Issues & Errors
1. **LLM Server Down** (most common): `[ERROR] LLaMA Server NOT running at 127.0.0.1:8080/8081`. Fix: `backend/start_llm.bat`.
2. **Import Errors**: `No module named 'app'` in test_llm.py/logs. Fix: `cd backend` before run.
3. **Test Fails**: 
   - test_services.py: 4 API mismatches.
   - test_llm.py: Indentation/imports.
   - Skips: LLM deps, manual health.
4. **Startup Warnings**: Low RAM (15GB), wmic deprecated (Win11) → replace PowerShell.
5. **Logs Example** (startup_20260314__00544.log): Resources OK, Smoke Tests OK, but app import FAIL.

Recent startup summary: Ports dynamic (8080/8001/3000), model 4.4GB OK, Python 3.11 OK, pytest smoke OK.

## Setup & Run
1. **Venv**: `cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt`
2. **Model**: Download `qwen2.5-7b-instruct-q4_k_m.gguf` (~5GB) to `Models LLM/`.
3. **Ports**: Auto-dynamic `backend/data/runtime_ports.json`.
4. **Start**:
   ```
   backend/start_llm.bat          # LLM server (port 8080+)
   backend/start_backend.bat      # FastAPI (8001+)
   # Or all: start_enigma.bat
   ```
5. **Access**: http://localhost:8001/ui/index.html | /api/health

## Tests
```
cd backend
python -m pytest tests/ -v --tb=short   # All (expect ~65% pass, LLM skips)
python tests/test_llm.py               # Multimodel health
python tests/test_services.py          # Services/memory/agents
python tests/test_startup_checks.py    # Smoke/resources
python tests/test_error_interpreter.py # Errors (passes)
backend/run_test_llm.bat              # Quick LLM check
```
**Expected**: Memory/combat/ingest OK; LLM/health FAIL if server down.

## Logs & Monitoring
- **JSONL**: `data/logs/enigma_YYYYMMDD.jsonl` {timestamp,level,agent,model,error_code,duration_ms}.
- **Startup**: `logs/startup_*.log`.
- **Endpoints**: /api/health, /debug/agents (VRAM/errors), /debug/vram.
- **Tail**: `tail -f data/logs/enigma_*.jsonl`

## TODO Summary (Consolidated)
- **Immediate**:
  | Priority | Task | Status |
  |----------|------|--------|
  | P0 | Fix startup wmic→PowerShell (start_enigma.bat) | Pending |
  | P0 | Stabilize LLM server (auto-retry) | Partial |
  | P1 | Fix test imports/cwd (test_llm.py) | Partial (run_test_llm.bat OK) |
  | P1 | Resolve test_services mismatches | Pending |
- **Phase 1 Remainder** (Stability): Agent dashboard, structlog full, VRAM alerts.
- **Phase 2**: Token streaming SSE, full test coverage.

**Generated:** Analyzed 20+ files/logs/tests/TODOs. Last update: 2026-03-14. Run `git diff backend/README.md` for changes.

