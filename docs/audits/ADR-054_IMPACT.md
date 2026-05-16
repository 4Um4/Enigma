# ADR-054 Impact Audit: Test Suite Synchronization & ADR-052 Alignment
## Changed Domains
- testing (stress, sandbox)

## Downstream Consumers
- CI/CD Pipeline (тесты больше не падают на легаси-сигнатурах)

## Runtime Impact
- Нулевое влияние на runtime. Изменения коснулись только тестового контура.

## Sandbox Tests
- backend/tests/sandbox/test_schedule_locomotion.py (2 passed)
- backend/tests/sandbox/stress/test_schedule_override.py (1 passed - fixed signature)

## Rollback
- Вернуть `threat_gradient` в тестовых фикстурах вместо `initiative_suppression`.
- Вернуть `current_tick=1` в вызовах `_simulate_minor`.
