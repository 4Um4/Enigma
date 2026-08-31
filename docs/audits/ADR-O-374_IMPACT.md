# ADR-O-374 Impact Audit
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- Сон: coupling-семантика канонизирована (is_sleep_coupling); сон-физиология ×3 и sleep-зеркало впервые достижимы в production.
- Диагностика: инверсия двух снов квантифицирована (до/после, 2400 сэмплов).

## Downstream Consumers
- BodyEngine (×3-ветки) — теперь сверяются с предикатом.
- CommitmentRegistry.reconcile_sleep_ownership — предикат (флаги зеркал OFF по-прежнему).
- Future S2B6-B/D — B1/Y6-ветки SUPERBOX-гейта оживлены как вход.
- SleepLifecycleService — без изменений (писатель coupling_profile).
- Потребители множителей (integration.py) — без изменений (непрersивные оси не тронуты).

## Runtime Impact
- O(1)-вызов функции-предиката вместо tuple-membership — пренебрежимо; поведение тика неизменно при FULL_WAKE-pinned NPC (доказано drift A–E=0/0).

## Sandbox Tests
- TestS2B6CanonicalCoupling (3 гварда).
- Диагностические прогоны: reports/DIAG_S2B6_sleep_baseline.txt / _after.txt / drift_before.md (зонды отреверсированы).

## Rollback
- Revert патчей возвращает фантомные литералы; гварды (truth-table/membership/grep) упадут первыми — их назначение.
- Данные диагностики сохранены в reports/ — не зависят от отката кода.