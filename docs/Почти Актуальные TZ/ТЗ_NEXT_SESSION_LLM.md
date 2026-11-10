# ТЗ для следующей сессии — LLM verification

> Created: 2026-11-10
> Previous: S-LLM-VERIFY-01 (Этапы 0-7 ТЗ_ЛЛМ_и_мозг_НПС.md)

## Что сделано

- Этапы 0-3: археология, аудит контракта, golden corpus (4 документа)
- Этапы 4-5: 35 моделей протестировано через probe v2
- Этап 7: Scenario A — Hermes-3 остаётся production
- probe_v2: 5 новых флагов (--gpu-layers, --no-jinja, --no-response-format, --ctx-size, --no-thinking-suppress)
- GigaChat3.1 заработала: SCORE 49.08, latency 0.89s (fastest!)
- GigaChat-20B НЕ viable на 8GB VRAM

## Текущее состояние

Production: Hermes-3-Llama-3.1-8B Q4_K_M (SCORE 89.62)
Production server: ОСТАНОВЛЕН (broker убит для VRAM)
IPT: 51/3 (3 CRITICAL — foreign WIP)

## Где документы

| Что | Путь |
|---|---|
| Финальный отчёт | docs/Почти Актуальные TZ/LLM_MODELS_2026_CCH_TEST.md |
| Inventory | docs/research/LLM_PREVIOUS_TESTS_INVENTORY.md |
| Contract matrix | docs/research/ENIGMA_LLM_CONTRACT_MATRIX.md |
| Golden corpus | docs/research/ENIGMA_LLM_GOLDEN_CORPUS.md |
| vLLM roadmap | docs/vllm_backend_roadmap.md |
| Leaderboard (35) | reports/probe_v2/leaderboard.md |
| probe_v2 (modified) | scripts/probe_v2_cch_canonize.py |
| ТЗ (этот файл) | docs/Почти Актуальные TZ/ТЗ_NEXT_SESSION_LLM.md |

## Приоритеты

### 1. ПЕРЕЗАПУСТИТЬ production
game_launcher → ensure_llm(label="backend") → Hermes-3 на :8181
Проверить: localhost:8181/health + python backend/tests/IPT.py

### 2. Few-shot Hermes (опционально)
Создать chronicle_decompose_system_fewshot.txt (копия + примеры)
Добавить --system-prompt-file в probe_v2
Цель: SCORE 90+ (сейчас 89.62, gap 0.38)

### 3. GigaChat3.1 улучшение (опционально)
SCORE 49.08, weak: valid_items 0.83 (почти ничего не извлекает)
Изучить raw_response в reports/probe_v2/ — почему?
Оптимальные флаги: --no-jinja --ctx-size 16384

### 4. vLLM backend (опционально, долгосрочно)
Roadmap: docs/vllm_backend_roadmap.md
Не критичен — llama-server работает с правильными флагами

## Ключевые находки

1. System prompt = 9170 tokens для GigaChat > 8192 context → --ctx-size 16384
2. --jinja ломает GigaChat chat template → --no-jinja
3. GigaChat3.1 fastest: 0.89s (1.8B MoE active vs Hermes 8B)
4. Hermes tokenizer компактнее (system prompt fits 8192)
5. response_format НЕ влияет на GigaChat3.1

## Модели

Production: Models LLM\Hermes-3-Llama-3.1-8B.Q4_K_M.gguf
D:\LLM: 14 GGUF (87.66 GB) — см. inventory
GigaChat3.1: D:\LLM\GigaChat3.1-10B-A1.8B-bf16.Q4_K_S.gguf (5.69 GB)