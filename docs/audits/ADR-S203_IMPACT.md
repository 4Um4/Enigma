# ADR-S203 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-S203` [STANDARD] **IMPACT**
# ADR-S203 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- `DOM-07`: Frontend, Presentation & Input

## Downstream Consumers
- `backend/tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.py`

## Runtime Impact
- RAM: Нет изменений.
- Latency: Нет изменений (тестовый скрипт).

## Sandbox Tests
- `backend/tests/sandbox/SUPERBOX/scenarios/semantic_torture_test.py`

## Rollback
- Удалить файл `semantic_torture_test.py`.
- Убрать few-shot examples из промпта в `llm_compressor_client.py`.
