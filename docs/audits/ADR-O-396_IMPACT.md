# Impact Audit — ADR-O-396 [ONTO] SOCIAL Vertical Slice — «потребность в другом → изменившиеся отношения»
`ADR-O-396` [ONTO] **SOCIAL Vertical Slice — «потребность в другом → изменившиеся отношения»**
Files: backend/app/services/game_loop/__init__.py, backend/app/services/game_loop/task_scheduler.py, backend/tests/sandbox/superbox_social_deterministic.py
> Детальный аудит ОДНОГО ADR. Единый атлас: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- social/game_loop pipeline: idle execute_pending, PACING-continue, enqueue-дедуп+CANCELLED, broadcast-валидатор

## Downstream Consumers
- backend/app/services/game_loop/__init__.py, backend/app/services/game_loop/task_scheduler.py, backend/app/models/npc_state.py (broadcast-исключения)

## Runtime Impact
- trust-мутации живого контура (5 NPC, +0.998…+2.475), ×3 детерминированно

## Sandbox Tests
- backend/tests/sandbox/superbox_social_deterministic.py (D1–D4 ×3)

## Rollback
- revert 4 фиксов (полная хроника — архив: git show b59dac3f:docs/MUTATIONS.md, S264); гейт — D1–D4 вернутся в красный