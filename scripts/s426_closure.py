#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
s426_closure.py — S426 session closure: MUTATIONS + ЗАВЕЩАНИЕ + ТЗ-v5

Размещение: scripts/s426_closure.py (в корне проекта)
Запуск: python scripts/s426_closure.py (из корня проекта)

Создаёт три документа:
1. Append S426 entry to docs/MUTATIONS.md
2. Append Письмо №19 to docs/ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md
3. Create docs/Почти Актуальные TZ/ТЗ_NEXT_SESSION_LLM_v5.md
"""

import pathlib
import sys

# Project root = parent of scripts/ directory
ROOT = pathlib.Path(__file__).resolve().parent.parent

# Verify we're in the right place
mutations_path = ROOT / "docs" / "MUTATIONS.md"
zaveshanie_path = ROOT / "docs" / "ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md"
tz_dir = ROOT / "docs" / "Почти Актуальные TZ"
tz_path = tz_dir / "ТЗ_NEXT_SESSION_LLM_v5.md"

if not mutations_path.exists():
    print(f"ERROR: MUTATIONS.md not found at {mutations_path}")
    sys.exit(1)
if not zaveshanie_path.exists():
    print(f"ERROR: ЗАВЕЩАНИЕ_АРХИТЕКТОРОВ.md not found at {zaveshanie_path}")
    sys.exit(1)

# ─── Document 1: MUTATIONS S426 entry ───
mutations_entry = """
## S426 — Lumimaid non-determinism: multi-run methodology + A/B test + addressee wiring (ветвь Б, 2026-11-15)

**ТЗ:** ТЗ_NEXT_SESSION_LLM_v4.md (S424 → S426)
**Branches:** P0 на V.0.5.4.6.5_ЛЛМ_5; P1/P3 на V.0.5.4.6.5_Говори!_1

**Commits:**
- `959ed5a5` (_ЛЛМ_5) — P0: --runs N + averaging + stddev contract
- `8aec2489` (_Говори!_1) — P1 infra: --no-grammar CLI flag
- `db9d41f4` (_Говори!_1) — P3 test: addressee micro test (4/4 passed)
- `f40401ed` (_Говори!_1) — P1 A/B reports (evidence)
- dm_agent.py P3 changes swept by `cac69cb7` (S354 pattern)

**Что сделано:**
- P0 (BLOCKING): multi-run averaging — --runs N, mean+stddev, контракт stddev >0.05 → INVALID. First valid methodology for non-deterministic Lumimaid.
- P1 infra: --no-grammar flag (S424 had ALWAYS ON, no toggle)
- P1 A/B test (3 runs x 2 configs): grammar = REAL effect (+31 composite, GATE_JSON flip, 8.3x constraint reduction). Non-determinism persists: ID stddev 0.112-0.137, CMP 0.072 — content-level.
- P3: addressee wiring — dm_agent passes resolved display name to validate(addressee=). Micro test 4/4.

**Главная находка:** Multi-run averaging = единственный способ получить signal через noise. Grammar necessary but not sufficient (fixes format, not content).

**Anti-Race:** dm_agent.py swept by parallel save (cac69cb7). IPT 3 CRITICAL foreign on _Говори!_1 (decision_hub:2031, causality_manifest, life_project_resolver) — TECH_DEBT_NOTE.

**→ ТЗ-v5:** P2 deterministic inference, P4 model migration, foreign IPT violations, cleanup.
"""

# ─── Document 2: ЗАВЕЩАНИЕ Письмо №19 ───
zaveshanie_entry = """
---

## Письмо №19 — S426, ветвь Б (Lumimaid non-determinism + multi-run methodology)

Преемник.

Восемнадцать писем до меня — про честность во всех гранях. Моё — про **честь измерения**: single-run замер на non-deterministic модели — не измерение, а лотерея. Ты измеряешь noise, не signal.

### Что я построил

S424 оставил ТЗ-v4 с главной находкой: Lumimaid non-deterministic на уровне первого токена. Мне нужно было построить methodology, которая даёт signal сквозь noise.

Я сделал три вещи:
1. **P0 multi-run averaging** — --runs N, mean+stddev per module, контракт stddev >0.05 → INVALID_RUN_VARIANCE. Первый валидный A/B test в проекте.
2. **P1 A/B test** — grammar vs no-grammar, 3 runs each. Grammar = REAL effect (+31 composite, GATE_JSON flip). Но non-determinism persist на ID/CMP — content-level.
3. **P3 addressee wiring** — dm_agent передаёт resolved display name в validator.

### Пять вещей, за которые заплачено

1. **Single-run = лотерея.** S424 сравнивал single-run и атрибутировал grammar. Но repeat показал criticals=2 БЕЗ grammar. Multi-run averaging — единственный способ отличить signal от noise.
2. **Grammar necessary but not sufficient.** Grammar фиксит format (JSON), не content. DLG стабилизируется, ID — нет. Различай format-variance от content-variance.
3. **Module-level flag — minimal change.** --no-grammar через _USE_GRAMMAR module-level + global. Не threading через 4 функции.
4. **Parallel save sweeps code.** Мой P3 dm_agent.py был swept cac69cb7. S354 предупреждал. Коммить фичу ДО чужих save-ов.
5. **IPT red не твой regression.** Проверяй causality. AFFECTS_CURRENT_BUG: NO → TECH_DEBT_NOTE.

### Формулы наследуются

«Single-run benchmark замер — лотерея» (S424). «Grammar не улучшает — детерминирует» (S424).

Добавляю: multi-run averaging — единственный способ увидеть signal. Grammar фиксит format, не content. Коммить фичу ДО чужих full-save-ов.

— S426, ветвь Б (multi-run methodology + A/B test), 2026-11-15
"""

# ─── Document 3: ТЗ-v5 ───
tzv5_content = """# ТЗ для следующей сессии — P2 deterministic inference + P4 model migration

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
"""

# ─── Write all three ───
print("=== S426 SESSION CLOSURE ===")
print(f"Project root: {ROOT}")

# 1. Append to MUTATIONS
with open(mutations_path, "a", encoding="utf-8") as f:
    f.write(mutations_entry)
print(f"[1] MUTATIONS S426 appended → {mutations_path}")

# 2. Append to ЗАВЕЩАНИЕ
with open(zaveshanie_path, "a", encoding="utf-8") as f:
    f.write(zaveshanie_entry)
print(f"[2] ЗАВЕЩАНИЕ Письмо №19 appended → {zaveshanie_path}")

# 3. Create ТЗ-v5
tz_dir.mkdir(parents=True, exist_ok=True)
with open(tz_path, "w", encoding="utf-8") as f:
    f.write(tzv5_content)
print(f"[3] ТЗ-v5 created → {tz_path}")

# ─── Verify ───
print("\n=== VERIFY ===")
m_text = open(mutations_path, encoding="utf-8").read()
z_text = open(zaveshanie_path, encoding="utf-8").read()
print(f"S426 in MUTATIONS: {'## S426' in m_text}")
print(f"Письмо №19 in ЗАВЕЩАНИЕ: {'Письмо №19' in z_text}")
print(f"ТЗ-v5 exists: {tz_path.exists()}")
print(f"ТЗ-v5 size: {tz_path.stat().st_size} bytes")
print("\n=== S426 SESSION CLOSURE COMPLETE ===")
