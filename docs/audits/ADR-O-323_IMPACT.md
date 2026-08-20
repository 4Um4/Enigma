# ADR-O-323 Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: `docs/ADR (Architecture Decision Records).md`

`ADR-O-323` [STANDARD] **IMPACT**
# ADR-O-323 Impact Audit: Atomic Fact Extraction
> Этот файл — детальный аудит онтологического сдвига.

## Changed Domains
- PERCEPTION & PHENOMENOLOGY

## Ontological Shift
`ObservedFact` теперь строго атомарен. 
Составные выводы (например, `hand_on_weapon`) запрещены на уровне FactExtractor.
FactExtractor извлекает только атомарные сущности: `hand_position`, `weapon_visible`, `distance_to_observer`.
Сложные выводы и гипотезы выносятся в слой `Inference`.

## Rationale
Чем атомарнее FactExtractor, тем мощнее Inference. Составные факты ломают гибкость системы и заставляют FactExtractor делать предположения, что нарушает инвариант невозрастания истины.

# ADR-O-323 Impact Audit: MovementPlanner Authoring
> Архитектурный аудит внедрения единого автора TraversalProposal.

## Changed Domains
- `movement` (Фаза 5: `MovementEngine` → `MovementPlanner`)
- `scene_state` (Фаза 8: `SceneStateManager.apply_change`)
- `shadow_compiler` (Фаза 9: `EventCompiler._compile_full_movement`)
- `validation` (Фаза 9: `EquivalenceValidator.validate_traversal`)

## Downstream Consumers
- `EquivalenceValidator` (сравнивает материализованное состояние Legacy с Shadow-проекцией)
- `WorldSnapshotBuilder` (читает `active_traversals` для DTO)
- `TraversalExecutionSystem` (Фаза 0.5: двигает `local_position` по `path_waypoints`)

## Runtime Impact
- **RAM:** negligible additional allocation; proposal replaces duplicated traversal computation.
- **Tick Latency:** expected reduction from elimination of duplicate path computation; exact delta requires benchmark.

## Sandbox Tests
- `tests/sandbox/movement/test_movement_planner_contract.py` (9/9 passed)
- `IPT.py` (5/5 passed, 0 CRITICAL)

## Rollback
- Вернуть безусловный вызов `build_traversal_dict` в `SceneStateManager` (строка ~1492) и `EventCompiler` (строка ~530).
- Удалить чтение `traversal_proposal` из `SceneChange`.
- Удалить класс `MovementPlanner` из `movement_engine.py`.

## Principle Enforced
**Single Author + Independent Verifier + Shared Materialization Contract**


Files: N/A
