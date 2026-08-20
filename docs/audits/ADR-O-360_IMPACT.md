# ADR-O-360 Impact Audit: Source-Weighted Reliability & Observation Channel
> Единый атлас: `docs/ADR (Architecture Decision Records).md` (L14.4). Сессия: S207.
> Номер ADR-O-359 занят (LLM Few-Shot Intent Grounding, anti-race protocol).

## Changed Domains
- **DOM-EPISTEMIC:** `get_reliability(context["source_type"])`; второй канал убеждений (observation); `BeliefRevisionEngine.revise()` + опциональный `reliability_context` (проброс, не логика).
- **DOM-SPATIAL:** мембрана наблюдения = `SpatialQueryService.visibility` (стены/препятствия) + дистанция `_OBSERVATION_SIGHT_RADIUS=10.0` (компенсация: `visibility()` не проверяет дальность, `line_of_sight()` — проверяет; унификация — ревизия).

## Downstream Consumers
- `ClaimEventSubscriber` / testimony-путь — не затронуты (context=None → прежнее поведение).
- `INV-EPISTEMIC-TRUST-MONOTONICITY` — не затронут (без context).
- `DecisionHub` — по-прежнему только `Dict[str, float]` модификаторы.

## Runtime Impact
- ~50 строк нового кода; +1 подписчик на THEFT; latency ~0.1ms/событие.
- Калибруемые параметры: `DIRECT_OBSERVATION_RELIABILITY=0.9`, `_OBSERVATION_SIGHT_RADIUS=10.0`.

## Sandbox Tests
- `SUPERBOX-OBSERVATION` (T1–T5, 5/5; T2b — стенной контроль): observation создаёт убеждение 0.9; no-telepathy (дистанция и стена); truth-immutability; same-source буст; вражеское cross-confirm точной формулой.
- Гейты: IPT 44/44; S206 baseline AFTER — байт-в-байт (context-ветка не активируется в testimony-прогонах).

## Rollback
Удалить: ObservationSubscriber + регистрация в `_register_epistemic_core` + context-ветка провайдера + параметр `reliability_context` движка. Атомарно.

## Known Debts
- DEBT-R1 (event.radius=999.0), DEBT-R3 (NPC-кража не порождает THEFT — блокер Phase G), DEBT-R5 (try/except регистрации; живой инцидент S207: ImportError → тихая смерть ядра → поймано IPT), DEBT-R6 (изоляция SUPERBOX).