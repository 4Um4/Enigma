# ADR-O-311 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-311` [STANDARD] **IMPACT**
# ADR-O-311 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Will & Decision (`ExposureLevel` определяет радиус слышимости `CommunicationIntent`)
- Perception (radius пробрасывается в `EventDTO.visibility` через `IntentEventAdapter`)

## Downstream Consumers
- `domain/communication.py` — `ExposureLevel` класс + `_EXPOSURE_DEFAULT_RADIUS` маппинг (semantic → float radius). Единственный источник радиуса
- `services/events/intent_event_adapter.py:52` — `radius=intent.exposure_level.physical_radius` — проброс в EventDTO
- `services/npc/decision_hub.py:315` — создаёт `CommunicationIntent` с `ExposureLevel.from_semantic("normal")`
- `services/npc/npc_tick_pipeline.py:288,967` — создаёт `CommunicationIntent` с `ExposureLevel.from_semantic("shout")` для атак

## Runtime Impact
- **RAM:** Нулевой — `_EXPOSURE_DEFAULT_RADIUS` это модульный dict (6 записей), `ExposureLevel` это enum-обёртка
- **Latency:** Нулевой — словарь-lookup O(1)
- **Determinism:** Чистая функция (semantic string → float), детерминирована

## Sandbox Tests
- Фаза 0 — документальная гигиена, runtime-тесты не требуются
- Будущий тест: `test_exposure_level_from_semantic_rejects_unknown` (верификация ValueError при неизвестном semantic)

## Rollback
1. Заменить `intent.exposure_level.physical_radius` на хардкод `radius=5.0` в `intent_event_adapter.py:52`
2. Удалить `ExposureLevel` из `CommunicationIntent` (поле становится optional с дефолтом)
3. Удалить `_EXPOSURE_DEFAULT_RADIUS` и `ExposureLevel` из `communication.py



Files: N/A
