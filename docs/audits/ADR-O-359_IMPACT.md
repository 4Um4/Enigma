# ADR-O-359 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Input & Intent Compression (DOM-01)
- Player Cognition / Legacy Bridge

## Downstream Consumers
- `DecisionHub` (через `IntentParametersDTO`)
- `EpistemicStore` / `ClaimEventSubscriber` (через `Proposition`)

## Runtime Impact
- RAM: +2KB (статический текст промпта).
- Latency: LLM inference time увеличено на ~100мс из-за длины промпта (26 examples), но точность выросла с 55% до 88%.

## Sandbox Tests
- `backend/tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.py` (S203 Passed: Intent Preservation 88.0%, Causal Class Equivalence 86.9%)

## Rollback
- Удалить блок `# Few-Shot Examples` из `llm_compressor_client.py`.
- Вернуть `causal_class` к возврату `intent.action.value` без группировки.