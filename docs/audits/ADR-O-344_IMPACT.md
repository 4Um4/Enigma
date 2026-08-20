# ADR-O-344 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-344` [STANDARD] **IMPACT**
# ADR-O-344 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

## Changed Domains
- **Temporal Ownership**: `game_time_seconds` и `tick` теперь строго управляются `TickOrchestrator` (WorldTick). Слой приложения (`GameLoop`) лишается прав на мутацию этих полей.
- **Execution Topology**: Цикл обработки локаций перемещается из `GameLoop.idle_tick` внутрь `TickOrchestrator.execute`. Теперь один вызов `execute` обрабатывает все локации (WorldTick), выполняя ровно один temporal advance и один global commit.

## Downstream Consumers
- **GameLoop**: Теряет цикл `for _loc_id in _location_ids:`. Делегирует полный WorldTick оркестратору.
- **TickOrchestrator**: Получает список `location_ids` и итерируется по ним *внутри* себя. Вызывает `_advance_idle_time` ровно 1 раз (до цикла сцен). Вызывает `_phase_10_persistence` ровно 1 раз (после цикла сцен).
- **SceneStateManager**: `lock_all_for_tick` остаётся, но `atomic_commit` вызывается оркестратором один раз для всех сцен.

## Runtime Impact
- **Latency**: Устранение O(N²) выполнения фаз. Время тика больше не зависит от количества локаций квадратично.
- **Time Drift**: Полностью устраняется `70.0` секунд за тик. Возвращается `10.0` (`GAME_TICK_INTERVAL_SECONDS`).
- **Atomicity**: Устраняется риск разорванной реальности при падении между коммитами локаций.

## Sandbox Tests
- `backend/tests/IPT.py` → `INV-TICK-CARDINALITY` (должен перейти из RED в GREEN).
- `backend/tests/sandbox/SUPERBOX/drift_laboratory.py` → `quick_debug` (3 тика).

## Rollback
Вернуть цикл `for _loc_id in _location_ids:` в `GameLoop.idle_tick` и вернуть `+60.0` хардкод. Удалить глобальный цикл из `TickOrchestrator.execute`.



Files: N/A
