# vLLM Backend Roadmap — ENIGMA LLM Backend Abstraction

> Created: 2026-11-10
> Priority: #1 — make GigaChat work
> Goal: Remove llama-server hardcode; support multiple inference backends

## Problem

GigaChat models fail with llama-server:
- GigaChat-20B-A3B: SCORE 0.0 (VRAM OOM + chat template)
- GigaChat3.1-10B-A1.8B: SCORE 0.0 (API error — chat template incompatibility)

Root cause: llama-server --jinja + response_format incompatible with GigaChat chat template.
Also: llama-server lacks MoE expert offloading (layer-level only).

## Solution: Backend Adapter Pattern

Consumer -> ensure_llm -> Host Broker (:8182) -> LLMBackend Protocol -> LLM Server (:8181)

Backends:
- LlamaServerBackend (current, GGUF, --jinja)
- VLLMBackend (new, HF format, automatic chat template, expert offload)

Both expose OpenAI API on :8181 — consumers unchanged.

## Why vLLM

- Automatic chat template (from tokenizer_config.json) — GigaChat should work
- MoE expert offloading — partial VRAM for large MoE models
- PagedAttention — 2-4x throughput
- Continuous batching — better concurrency

## Steps

1. ADR-O-4XX — LLM Backend Abstraction (document why, what, rollback)
2. LLMBackend Protocol — backend/app/services/llm/runtime/backend.py
3. LlamaServerBackend — extract from host.py (no behavior change)
4. VLLMBackend — new, pip install vllm, spawn vllm server
5. Broker refactor — select backend by LLM_BACKEND env (default=llama_server)
6. probe_v2 refactor — add --backend flag, use LLMBackend protocol
7. Test Hermes on both backends — no regression
8. Test GigaChat on vLLM — goal: json_valid_rate > 0.5, SCORE >= 70

## Config

LLM_BACKEND=llama_server (default, current)
LLM_BACKEND=vllm (for GigaChat + MoE models)

## Timeline

~10 hours / 2-3 sessions:
- Steps 1-3: ~3h (ADR + protocol + extract)
- Steps 4-5: ~3h (vLLM backend + broker)
- Steps 6-7: ~2h (probe + test Hermes)
- Step 8: ~2h (test GigaChat)

## Risks

- vLLM VRAM overhead ~1-2 GB (less headroom)
- vLLM GGUF experimental — may need HF format (re-download models)
- vLLM startup ~30-60s (vs llama-server ~5s)
- pip install vllm ~5 GB disk
- Compute capability >= 7.0 required (RTX 3070 Ti = 8.6 OK)

## Success criteria

- GigaChat3.1-10B valid JSON on vLLM (json_valid_rate > 0.5)
- GigaChat SCORE >= 70 on vLLM
- Hermes still works on llama_server (no regression)
- Both backends pass IPT

## Priority

PRIORITY #1 — GigaChat must work.
If Qwen3-8B SCORE >= 90: vLLM still implemented (architectural debt).
If Qwen3-8B SCORE < 90: vLLM is critical path.

---

> For implementing agent. Start with Step 1 (ADR), proceed sequentially.
> Context: ЗАВЕЩАНИЕ №16 (S418-S420), probe_v2 --gpu-layers mod (this session).