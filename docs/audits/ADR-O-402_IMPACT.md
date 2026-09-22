# ADR-O-402 Impact Audit — Turn Pipeline Ownership (Phase 3A)
> Атлас: docs/ADR (Architecture Decision Records).md | Ветка: V.0.5.4.1.2_Чистка_истоков
> Коммиты: f35a9d72 (SeamA), 56fcecfe (B1), d301b87b (SeamB+B2), 73e1f528/ac433c33 (каркас), 5026d02d (final)

## Changed Domains
- game_loop: новый владелец turn_pipeline.py (фазовая машина player-turn: execute + 6 фаз, 17 DI-полей)
- game_loop: dm_phase/npc_orchestration де-связаны от поверхности GameLoop (DmPhaseDeps 7 полей / NpcOrchDeps 13 полей, frozen, принадлежат фазам)
- scene_state_manager: публичный tick-API (adopt_scene_for_tick, is_tick_locked_for) — internals больше не читаются/пишутся извне

## Downstream Consumers
- Поверхность пакета сохранена: __init__.py = шим (GameLoop, _PipelineState); 22 файла-потребителя не тронуты
- Wiring-лямбды подписчиков читают GameLoop._current_tick через setter — владение сохранено

## Ownership Decisions (карта 3A.1)
- TurnServices-контейнер ЭЛИМИНИРОВАН (red-flag 25-полевой тест + 32 обратных доступа dm_phase/npc_orchestration)
- NpcTickServices — канонический NPC-контракт переиспользуется; lifetime экземпляра = turn (не application)
- B-состояния: _prev_player_distances/_scene_continuities/_current_tick/_background_tasks — GameLoop-owned, доступ через accessors/setter/provider
- C-зависимости: _load_npcs_with_runtime (DEFERRED trio), _get_task_scheduler (lazy identity) — callables
- D: memory_manager._relationships → rel_store (identity 159b), 2 приватных seam к MemoryManager умерли

## Runtime Impact
- Поведение неизменно: IPT 45/45 на каждой итерации; этапный реплей fedafcca MATCH; pytest r4+pipeline 16+1
- game_loop.py: 2902 → 2224 (−23%); turn_pipeline.py ~736 — отвечает на один вопрос: «как выполняется player turn»

## Sandbox Tests
- tests/test_game_loop_pipeline.py, tests/test_spatial_runtime_r4.py, tests/IPT.py, DriftLab replay_determinism

## Rollback
- git revert 5026d02d + восстановление региона из 73e1f528~1; re-export-точки не трогаются

## Taboo
- ❌ Передача game_loop-объекта в фазовые модули (god-reference); ❌ новый TurnServices-контейнер; ❌ lifetime=NpcTickServices(application); ❌ третий путь зеркала материализации; ❌ Campaign Lifecycle extraction без отдельного ownership-design (HOLD)