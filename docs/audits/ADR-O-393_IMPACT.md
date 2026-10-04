# Impact Audit — ADR-O-393 [ONTO] Determinism Foundation — кросс-процессный детерминизм (IRON RIVER)
`ADR-O-393` [ONTO] **Determinism Foundation — кросс-процессный детерминизм причинного контура**
Files: backend/app/services/game_loop/task_scheduler.py, backend/app/services/npc/life_engine.py, backend/tests/sandbox/iron_river_ab.py, backend/tests/sandbox/iron_river_diff.py, backend/tests/sandbox/iron_river_eatlog.py, backend/tests/sandbox/iron_river_lusya.py, backend/tests/sandbox/iron_river_trace.py
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- детерминизм: wall-clock/uuid4/admission изъяты из состояния (task_scheduler, speech_scheduler, combat_subscriber); изоляция лаборатории (settings.data_dir → sessions_dir)

## Downstream Consumers
- backend/app/services/game_loop/task_scheduler.py, backend/app/services/game_loop/speech_scheduler.py, backend/app/services/combat/combat_subscriber.py, backend/app/services/npc/activity_lifecycle_service.py, backend/app/services/npc/life_engine.py, backend/tests/IPT.py

## Runtime Impact
- нулевой функциональный: устранены скрытые причинные переменные; канон-хеш A/B 3×MATCH

## Sandbox Tests
- backend/tests/sandbox/iron_river_*.py (7 харнессов), backend/tests/sandbox/f3_combat_smoke.py

## Rollback
- по-фиксно (4 P0-брейкера независимы); гейт возврата — красный A/B 2×150 канон-хешем