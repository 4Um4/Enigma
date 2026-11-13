# ADR-O-439 Impact Audit

> Детальный аудит ОДНОГО ADR. Атлас: `docs/ADR (Architecture Decision Records).md`.
> Связанные: ADR-O-381 (BC-1, dormant), ADR-O-414 (INV-CONSUMER-GAP), ADR-O-208 (L3-P1).

## Changed Domains

- **StateDeltas** (`state_delta.py:151`) — новое спец-поле `pressure_accumulator_update: Optional[Dict[Tuple[str,str], float]]` (по образцу `intent`/`intent_tick`).
- **DecisionHub** (`decision_hub.py`) — `compute()` больше не мутирует `state.pressure_accumulator`; собирает `_pressure_updates` локально и возвращает дельту в `DecisionResult.deltas`.
- **StateApplicator._apply_deltas** — применяет `deltas.pressure_accumulator_update` в `state.pressure_accumulator` (место — рядом с intent-блоком).
- **NPCState WARA §12.2** — `to_persistence_dict:1013` пишет `pressure_accumulator` (tuple-key → `"from|to"`); `from_legacy:1333` читает симметрично.
- **causality_manifest** — объявлен `state_delta.pressure_accumulator_update` (DEBT, organ=relationship, terminal=decision, authority=CG-D-B1).

## Downstream Consumers

- **StateApplicator.apply_batch** → `_apply_delta_to_raw` → `apply_deltas_and_commit` → `to_persistence_dict` — WARA-канал исполнения.
- **TickOrchestrator Phase 5** → `TickMutation.npc_deltas` → Phase 8 `apply_batch` — провод давления от decision к state.
- **GameLoop** (restore) — `from_legacy` восстанавливает `pressure_accumulator` из `npc_dict`.
- **Replay** — состояние pressure теперь детерминировано между тиками (T6 determinism).

## Runtime Impact

- **RAM**: +0 к размеру NPCState (поле уже существовало); `_pressure_updates` — локальный dict на тик, O(N²) на пары intent.
- **Latency**: +1 dict-lookup в `_apply_deltas` (микро); +1 dict-serialization в `to_persistence_dict` (микро, раз в тик на NPC).
- **Persistence**: `npc_dict["pressure_accumulator"]` в runtime-JSON — размер растёт пропорционально накопленным парам (обычно ≤ 10 на NPC).
- **Обратная совместимость**: старые сейвы без `pressure_accumulator` — `from_legacy` вернёт `{}` (пустой dict, дефолт), поведение эквивалентно прежнему, но гистерезис теперь начнёт накапливаться корректно.

## Sandbox Tests

- `backend/tests/test_d_a02_read_only_and_roundtrip.py` (6 тестов):
  - T1: WARA round-trip (`to_persistence_dict` ↔ `from_legacy`).
  - T2: `apply_batch` применяет `pressure_accumulator_update`.
  - T3: `None` pressure → no write.
  - T4: `StateDeltas.pressure_accumulator_update` — optional.
  - T5: `compute()` не мутирует `state.pressure_accumulator` (READ ONLY).
  - T6: replay-determinism (`compute()` дважды → идентичный результат).
- Регресс: `test_intent_roundtrip.py` (10), `test_intent_tick_guard.py` (8), `test_contracts_stage6.py` (11), `test_decision_calibration.py` (10), `test_decision_hub_goal_boost.py` (1) — **40/40 passed**.
- IPT: **54/54 · 0 CRITICAL**.

## Rollback

Полный revert в 4 файлах:
1. `state_delta.py` — удалить поле `pressure_accumulator_update`.
2. `decision_hub.py` — вернуть `state.pressure_accumulator[acc_key] = accumulated` (2 точки).
3. `state_applicator.py` — удалить pressure-блок в `_apply_deltas`.
4. `npc_state.py` — удалить writer/reader `pressure_accumulator`.
5. `causality_manifest.py` — удалить запись `state_delta.pressure_accumulator_update`.

**Совместимость с сейвами**: revert возвращает к «не читается»; старые сейвы с `npc_dict["pressure_accumulator"]` — поле игнорируется, поведение как до S423. **Не критично** — WARA-разрыв был мёртвым каналом.

**Критерий успеха**: после revert IPT 54/54 (тест `test_d_a02_read_only_and_roundtrip.py` откатить вместе с кодом — он проверяет существование фикса).