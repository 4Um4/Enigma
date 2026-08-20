# ADR-157 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-157` [STANDARD] **IMPACT**
# ADR-157 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- LLM Infrastructure (Network Layer)
- Intent Compression (Slow-Path)

## Downstream Consumers
- `LlamaCppCompressorClient` (Semantic Parser)
- `LlamaCppProvider` (DM / NPC Verbalization)
- `health.py` (LLM Server Health Check)

## Runtime Impact
- Устранён `502 Bad Gateway` и `ReadError` при запросах к локальному `llama-server` через прокси `Throne`.
- LLM-запросы теперь выполняются через `urllib.request` с `ProxyHandler({})` в отдельном потоке (`asyncio.to_thread`), что предотвращает блокировку event-loop и обходит системный прокси.
- `httpx.Client` во всём бэкенде переведён на `trust_env=False`.

## Sandbox Tests
- `scripts/test_llm_parser.py` (вручную验证 Qwen2.5 extraction)

## Rollback
- Убрать `trust_env=False` из `httpx.Client` в `health.py`.
- Вернуть `httpx.AsyncClient` в `LlamaCppCompressorClient` (но это вернёт баг с прокси).
- Убрать `ProxyHandler({})` из `llama_cpp_provider.py`.


Files: N/A
