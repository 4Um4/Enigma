# ТЗ для следующей сессии — Lumimaid production + improvements

> Updated: 2026-11-10 v3
> MIGRATED: Lumimaid-v0.2-8B = production LLM

## Что сделано

- 44 модели CCH + 6 моделей NPC + comprehensive benchmark (78 задач, 11 модулей)
- Lumimaid выбрана: composite 29.26, WSI 0.80, GATE_JSON true, MUL 0.89
- Migrated from Hermes-3 → Lumimaid (config.py, user_settings.yaml)
- IPT: 52/2 (foreign WIP)
- Production: Lumimaid на :8181, health OK
- GBNF dm_response.gbnf создан (не в production pipeline)
- Benchmark: backend/tests/LLM Benchmark/ENIGMA_LLM_COMPREHENSIVE_BENCHMARK.py

## Production status

Model: Lumimaid-v0.2-8B-Q4_K_M-imat.gguf (4.58 GB)
Server: localhost:8181 (health OK)
ctx-size: 16384 (config.py:164)
IPT: 52/2 (foreign WIP: avatar_intent_record.py, player_avatar_service.py)

## Приоритеты следующей сессии

### 1. Few-shot Lumimaid для CCH BIO+CMP
- BIO: 0.45 → цель 0.70 (few-shot примеры в chronicle_decompose_system)
- CMP: 0.15 → цель 0.40 (complex scenarios)
- Создать chronicle_decompose_system_fewshot.txt
- Добавить --system-prompt-file в probe_v2
- Прогнать CCH probe + comprehensive benchmark

### 2. GBNF в production DM pipeline
- config/dm_response.gbnf → server_lifecycle или router
- Тест: production DM → всегда JSON {"dm_response":"..."}

### 3. World-State Integrity в ResponseValidator
- Проверять: модель не определяет результат действий игрока
- Проверять: правильный NPC отвечает
- Файл: backend/app/services/verbalization/response_validator.py

### 4. Constraint violations (7 в benchmark)
- Изучить какие constraints нарушаются
- Возможно: system prompt усиление

## Ключевые файлы

| Что | Путь |
|---|---|
| Production model | Models LLM\Lumimaid-v0.2-8B-Q4_K_M-imat.gguf |
| Config | backend/app/core/config.py (ctx_size=16384) |
| Benchmark | backend/tests/LLM Benchmark/ENIGMA_LLM_COMPREHENSIVE_BENCHMARK.py |
| Benchmark reports | backend/tests/LLM Benchmark/reports/ |
| CCH probe | backend/tests/LLM Benchmark/probe_v2_cch_canonize.py |
| NPC probe | backend/tests/LLM Benchmark/probe_npc_roleplay.py |
| GBNF DM | config/dm_response.gbnf |
| GBNF CCH | config/chronicle_decompose.gbnf |
| CCH prompt | backend/prompts/chronicle_decompose_system.txt |
| DM prompt | backend/prompts/dm_system.txt |
| Финальный отчёт | docs/Почти Актуальные TZ/LLM_MODELS_2026_CCH_TEST.md |

## Lumimaid profile (comprehensive benchmark)

composite: 29.26 | WSI: 0.80 | MEM: 0.82 | MUL: 0.89 | GATE_JSON: true
Weak: BIO 0.45, CMP 0.15, CONSTRAINT_VIOLATION 7