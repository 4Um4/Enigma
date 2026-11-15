# ТЗ для следующей сессии — P2 deterministic inference + P4 model migration

> Updated: 2026-11-15 v5
> PREV: v4 (2026-11-14) — multi-run methodology + benchmark
> CURRENT SESSION: S426 (ветвь Б, 2026-11-15)

## Контекст

S426 закрыл ТЗ-v4 P0, P1 (infra + A/B test), P3:
- P0: multi-run averaging (--runs N, mean+stddev, stddev >0.05 → INVALID). Commit 959ed5a5.
- P1 infra: --no-grammar flag. Commit 8aec2489.
- P1 A/B test: grammar = REAL effect (+31 composite, GATE_JSON flip). Non-determinism persists (ID/CMP). Reports f40401ed.
- P3: addressee wiring. dm_agent.py в cac69cb7, test в db9d41f4.

Главная находка: grammar necessary but not sufficient. ID/CMP content non-determinism — следующий фронт.

## Задачи

### ПРИОРИТЕТ 1 — P2 Deterministic inference
- --batch-size 1, --cont-batching off, --no-mmap, CPU fallback
- Файл: llama-server spawn (Host broker / ensure_llm)
- Контракт: 3 прогона → stddev <0.02 на ALL modules

### ПРИОРИТЕТ 2 — P4 Model migration
- Qwen3.5-9B: multi-run stddev, scores, VRAM, latency
- Только если P2 не помогает

### ПРИОРИТЕТ 3 — Foreign IPT violations на _Говори!_1
- decision_hub.py:2031 silent-failure
- causality_manifest.py orphan (claim_source_id, trigger_source_id)
- life_project_resolver.py setattr_unauthorized (10x)

### ПРИОРИТЕТ 4 — Cleanup
- HttpLlamaCppAdapter 3x duplicate if params.get("grammar")
- load_npcs_merged RecursionError

## Что НЕ делать
1. Не объявлять модель READY на single-run
2. Не сравнивать по single-run
3. Не trust ID/CMP без stddev
4. Не amend
5. Не трогай foreign WIP

## Ключевые файлы
- Benchmark: backend/tests/LLM Benchmark/ENIGMA_LLM_COMPREHENSIVE_BENCHMARK.py
- A/B reports: reports/benchmark_ab_{a,b}_*_multi.json
- LLM Runtime: docs/architecture/LLM_RUNTIME_UNIFICATION_PROPOSAL.md
- Это ТЗ: docs/Почти Актуальные TZ/ТЗ_NEXT_SESSION_LLM_v5.md

> Преемник. Grammar necessary but not sufficient. Multi-run methodology даёт signal. Non-determinism на content level (ID/CMP) — следующий фронт. P2 (deterministic inference) или P4 (model migration).
