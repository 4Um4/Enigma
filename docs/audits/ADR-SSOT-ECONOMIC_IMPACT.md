# ADR-SSOT-ECONOMIC Impact Audit
> Этот файл — детальный аудит ОДНОГО ADR. Единый атлас всех ADR: docs/ADR (Architecture Decision Records).md

## Changed Domains
- Economy (money / gold)
- Avatar Ownership
- Social (RelationshipStore API)

## Downstream Consumers
- state_applicator.py (обрабатывает игрока как NPC, update_relationships API)
- game_loop/__init__.py (применяет экономические дельты)
- phase_2_world_tick.py (упразднён bypass)

## Runtime Impact
- **RAM:** Нет изменений.
- **Latency:** Нет изменений. Унификация логики в pply_batch упрощает путь данных.

## Sandbox Tests
- 	ests/test_stage0_and_1_invariants.py::TestStage0Invariants::test_I0_10_no_avatar_body_state_mutation

## Rollback
- Вернуть прямую мутацию _avatar.body_state["money"] в game_loop/__init__.py (НЕ рекомендуется, нарушает SSOT Economic).
