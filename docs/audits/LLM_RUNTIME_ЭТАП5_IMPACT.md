# LLM Runtime Unification - Stage 5 (Production Integration) Impact Audit

> Base: PROPOSAL Section 7 Stage 5
> Status: GREEN. game_launcher + main.py migrated. d61 deferred.

## Commits
| Commit | File | Summary |
|---|---|---|
| 0cc44230 | game_launcher.py | ensure_llm(pinned=True) + port-scan LLM excluded + release_lease before os._exit |
| e54b74ce | main.py | ensure_llm(label=backend) + shutdown release_lease |

## Changes
### game_launcher.py
1. _ensure_llm_running: acquire_lock + Popen -> ensure_llm(pinned=True). exe/model checks KEPT.
2. Port-scan: llama_cpp_port EXCLUDED (broker owns server, Ustav 19).
3. os._exit: release_lease() BEFORE os._exit (bypasses atexit).

### main.py
1. _background_llm_startup: acquire_lock + start -> ensure_llm(label=backend).
2. Shutdown: _llama_state proc.terminate -> release_lease().

### readiness.py - NO changes (passive consumer, D70/S358)
### d61 - DEFERRED (broker /restart endpoint, Stage 4 PROPOSAL not done)

## Tests
- IPT 52/2 (0 new regressions; INV-RE-CACHE-ALLOWLIST + INV-FLAG-REGISTRY foreign)
- [LLM_SDK] lease released confirmed
- py_compile OK

## Rollback
git revert e54b74ce 0cc44230