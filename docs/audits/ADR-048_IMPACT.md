# ADR-048 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-048` [STANDARD] **IMPACT**
### Итоги промежуточного фикса: "Проклятие Входной Двери"

**ROOT CAUSE:** Нарушение ADR-048. `SpatialQueryService` читал `npc_positions["player"]["position"]`, который инициализировался как `"entrance"` при загрузке сцены и **никогда не обновлялся** при перемещении игрока. Все NPC, решившие подойти к игроку, получали целевой узел `entrance` и послушно шли ко входу.

**FIX:** Внедрена динамическая синхронизация в `npc_orchestration.py`: перед созданием `SpatialQueryService` система читает актуальные координаты из `player_spatial`, резолвит макро-узел через `SpatialService.get_nearest()` и обновляет `npc_positions["player"]`. Теперь цель `"player"` — это живая пространственная истина, а не статичный спавн.

Файл: docs/audits/ADR-048_IMPACT_PLAYER_SYNC.md

```markdown
# ADR-048 Impact Audit: Player Spatial Sync
## Changed Domains
- Spatial (Player Position Authority)

## Downstream Consumers
- SpatialQueryService
- _resolve_reactive_movement (APPROACH intent)
- DecisionHub (distance scoring)

## Runtime Impact
- RAM: 0 (обновляет существующий dict)
- Latency: +1 вызов SpatialService.get_nearest() на ход игрока (O(1) для малого графа)

## Sandbox Tests
- 48 passed (регрессия отсутствует)

## Rollback
Удалить блок `_ps = _scene_state.get("player_spatial", {})...` в npc_orchestration.py


Files: N/A
