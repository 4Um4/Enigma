# ADR-SHI-IMPACT Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-SHI-IMPACT` [STANDARD] **IMPACT**

﻿# ADR-SHI-IMPACT Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-SHI-IMPACT` [STANDARD] ****
# ADR-SHI-IMPACT
## Changed Domains
- DOM-08 (Observability): Восстановлена труба логирования DecisionHub
- DOM-04 (Spatial & Locomotion): Устранены пустые транзиты и потеря позиций

## Downstream Consumers
- **CausalObserver**: Теперь успешно парсит `[DECISION_HUB]` с отрицательными score.
- **DNAComputer**: SHI (Simulation Health Index) корректно вычисляется (>0%).
- **SceneStateManager**: Избавлен от обработки `BUG_V_GUARD` и "зомби"-транзитов от LifeEngine.
- **MovementEngine**: Избавлен от кривых `MovementIntent` с `dict` в качестве `target_node_id`.

## Runtime Impact
- RAM: 0
- Latency: Уменьшение нагрузки на SSM (меньше холостых применений `SceneChange`).

## Sandbox Tests
- `DriftLaboratory` (200 тиков): `comparisons=347 rate=1.735/tick`, 0 крашей.

## Rollback
- Revert changes in `diagnostics/pattern_registry.py`, `backend/app/services/npc/npc_tick_pipeline.py`, `backend/app/services/npc/life_engine.py`.


Files: N/A
