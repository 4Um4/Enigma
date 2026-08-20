# ADR-S202 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-S202` [STANDARD] **IMPACT**
# ADR-S202 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- `DOM-03`: Perception & Phenomenology (CFRM)
- `DOM-06`: Social, Memory & Affective
- `DOM-08`: Observability & Enforcement

## Downstream Consumers
- `backend/app/services/events/claim_event_subscriber.py`: `ClaimEventSubscriber.on_claim_event()`
- `backend/app/services/input/intent_compressor.py`: `IntentCompressor._fast_path_parse()`
- `backend/app/services/game_loop/__init__.py`: `GameLoop._execute_dm_and_intent_resolution()`

## Runtime Impact
- RAM: Нет значительных изменений.
- Latency: Нет значительных изменений (вычисление дистанций уже кэшировано в SpatialQueryService).

## Sandbox Tests
- `backend/tests/sandbox/micro/test_observer_causality.py`

## Rollback
- В `ClaimEventSubscriber` вернуть `_origin_id = event.source` вместо `payload.get("target_id", event.source)`.
- Удалить генерацию `Proposition` для `ATTACK` в `IntentCompressor._fast_path_parse()`.
- Удалить публикацию `SOCIAL_ACTION` из `GameLoop._execute_dm_and_intent_resolution()`.


Files: N/A
