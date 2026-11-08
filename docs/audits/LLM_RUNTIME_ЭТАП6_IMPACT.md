# LLM Runtime Unification - Stage 6 (SSOT Port + Legacy Cleanup) Impact Audit

> Base: PROPOSAL Section 7 Stage 6
> Status: GREEN. SSOT port + legacy cleanup done. d61 deferred.

## Commit
| Commit | Files | Summary |
|---|---|---|
| 9145ead8 | 7 files (+21/-69) | direct_llm_client→settings, test_llm→settings, runtime_ports deprecated, spawn_prod_llama deleted, system tests→ensure_llm |

## Changes
1. direct_llm_client.py: hardcoded http://localhost:8181 → settings.llama_cpp_server_url
2. test_llm.py: runtime_ports.json (8080) → settings.llama_cpp_port
3. runtime_ports.py: DEPRECATED (redirect to settings)
4. runtime_config.py: get_llm_url() DEPRECATED
5. logs/spawn_prod_llama.py: DELETED (broker replaces)
6. test_epistemology_pipeline.py: _start_llama_server → ensure_llm(label="epistemology_pipeline")
7. test_homeostatic_dialogue_stability.py: _start_llama_server → ensure_llm(label="homeostatic_dialogue")

## Criterion
- taskkill /IM llama-server / Stop-Process: ZERO (met since Stage 0)
- Hardcoded 8181 in production code: REDUCED (direct_llm_client fixed)
- Scripts/tests hardcoded 8181: LOWER priority (follow-up)

## Tests
- IPT 52/2 (0 new regressions)
- py_compile 6/6 OK

## Follow-up
- s371_3_*.py scripts (6 files) — hardcoded URLs
- probe_*.py scripts — hardcoded port
- butterfly_l4_real_llm.py — hardcoded health URL
- d61 — broker /restart transport (Stage 4 PROPOSAL dependency)