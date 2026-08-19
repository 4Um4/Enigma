# ADR-S200 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-S200` [STANDARD] **IMPACT**
# ADR-S200 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- `DOM-06`: Social, Memory & Affective
- `DOM-07`: Frontend, Presentation & Input

## Downstream Consumers
- `backend/app/services/game_loop/__init__.py`: `GameLoop._execute_dm_and_intent_resolution()`
- `backend/app/services/input/intent_compressor.py`: `IntentCompressor.compress()`, `_fast_path_parse()`, `_slow_path_parse()`
- `backend/app/services/input/llm_compressor_client.py`: `LLMCompressorClient.compress_intent()`, `_build_prompts()`

## Runtime Impact
- RAM: Увеличение на ~1KB на тик (передача DialogueSession в IntentCompressor).
- Latency: Уменьшение времени LLM-вызова для коротких реплик (Fast Path CONTINUE срабатывает до LLM).

## Sandbox Tests
- `backend/tests/sandbox/phenomenology/test_dialogue_context_binding.py`
- `backend/tests/IPT.py:inv_dialogue_context_binding`

## Rollback
- Удалить параметр `dialogue_session` из `IntentCompressor.compress()` и `LLMCompressorClient.compress_intent()`.
- Удалить Fast Path проверку на `_continue_indicators` в `IntentCompressor._fast_path_parse()`.
