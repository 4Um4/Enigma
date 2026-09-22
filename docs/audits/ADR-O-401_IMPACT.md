# ADR-O-401 Impact Audit — De-godification SSM: extraction в пакет scene_state/
> Единый атлас: docs/ADR (Architecture Decision Records).md | Серия: DEGOD ITER1–4c, 2026-09-22
> Ветка: V.0.5.4.1.2_Чистка_истоков | Коммиты: 95bf50a8, 0eff3fc1, 87aa1e8b, ff0a751a, 75dbb62f (+ITER4c)

## Changed Domains
- scene_state (новый пакет: environment_modifiers, change_validator, npc_display_name, editor_locator, dm_presentation, scene_factory + технический __init__)
- scene_state_manager.py: 2427 → ~1660 строк (−31%); класс/сигнатуры/call-sites неизменны (фасад = тот же объект)

## Downstream Consumers (grep-верифицировано)
- import-поверхность сохранена re-export'ами: _derive_environment_modifiers (test_spatial_runtime_r4), ChangeValidator, _npc_id_to_display (dm_agent, recognition_layer, diagnose_spatial), _find_editor_location и др. (методы-делегаты), _select_time_variant (time_advance.py:98 — делегат)
- get_scene_state_manager (singleton): world_routes, event_compiler — не тронут

## Runtime Impact
- Поведение: IPT 45/45 на каждой итерации; DriftLab E MATCH на каждой; passport env#1 b971b767 (x5) → env#3 fedafcca (смена среды между паспортами зафиксирована в досье; дым-тест фабрики: канонические 22 ключа, env-mod точен, SC-1 жив)
- mypy delta=0 (baseline 4 диагностики), ruff delta→0 (2×F841 + 1×I001 pre-existing остаются)

## Sandbox Tests
- tests/test_spatial_runtime_r4.py (16 passed, внешний re-export), tests/IPT.py, DriftLab replay_determinism

## Rollback
- git revert цепочки ff0a751a..HEAD по scene_state/; re-export-точки не трогаются

## Запреты (сохранены)
- EPOCH-FINAL commit (:1658-историч.), GAP12, RE-зона M1b.4.2, apply_change-ядро (ATOMIC-GUARD/зеркало S203.1), gc_traversals Ц1, несущий deepcopy S266 — НЕ ТРОНУТЫ (STOP-зоны карты DEGOD_PHASE0_MAP_SSM)