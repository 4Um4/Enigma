# ADR-150 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-150` [STANDARD] **IMPACT**
# ADR-150 Impact Audit: Need-Driven Semantic Spatial Binding

## Changed Domains
- LifeEngine (_check_need_driven_movement)
- SpatialService (resolve_node usage for needs)

## Downstream Consumers
- MovementEngine (receives intents with spatially-resolved targets)
- NPC positions (NPC move to semantically-correct locations for needs)
- Activity map system (now has fallback path)

## Runtime Impact
- RAM: No change (_NEED_ROLE_MAP is a static dict)
- Tick Latency: +1 SpatialService.resolve_node() call per critical need NPC per tick
- Rate: 0.27 → 0.40/tick (from semantic fallback alone)

## Sandbox Tests
- DriftLaboratory mass_traversal (50 ticks): verified socializing→BAR resolution

## Rollback
1. Remove _NEED_ROLE_MAP and semantic fallback block in _check_need_driven_movement
2. Return to None when activity_map entry missing (previous behavior)

## Key Files Changed
- backend/app/services/npc/life_engine.py (_check_need_driven_movement)

