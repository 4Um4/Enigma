# ADR-O-321 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- L2.7: LifeProject FSM (`life_project_resolver.py`)
- L2.6: BreakProgress (`break_progress_engine.py`, `phases/decision.py`)
- L2.2: NPCState (`npc_state.py`)

## Downstream Consumers
- `DecisionHub` (читает `life_project` и `life_project_state` для модуляции utility)
- `BehaviorMaskEngine` (читает `will_state` и `identity_integrity`)

## Runtime Impact
- RAM: +8 байт на NPC (новое поле `recent_failures: int`).
- Latency: 0 (вычисления остаются O(1) внутри `BreakProgressEngine`).

## Sandbox Tests
- `tests/test_break_progress_engine_r64.py` (22 passed)
- `tests/sandbox/system/test_life_direction_crisis.py` (1 passed)
- `backend/tests/IPT.py` (5/5 passed)

## Rollback
- Удалить поле `recent_failures` из `NPCState` и адаптеров.
- Откатить `LifeProjectResolver.resolve()` к сигнатуре с `identity_crisis: bool`.
- Вернуть хардкод `gold >= 1000` в `phases/decision.py`.