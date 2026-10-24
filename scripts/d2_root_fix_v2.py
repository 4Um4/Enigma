"""GC-01 Block 67 — D2 root fix v2: gate tick_orchestrator during player_action.

CORRECTED version: replaces the ENTIRE tick loop body (not just the header),
so indentation is preserved. ADR-O-407 (APPROVED-BY-MASTER) gates
TickOrchestrator.execute() during player turn.
"""
import sys
from pathlib import Path

ROOT = Path(".")
results = []

def ok(name, msg):
    results.append((name, "OK", msg))
    print(f"[OK]   {name}: {msg}")

def warn(name, msg):
    results.append((name, "WARN", msg))
    print(f"[WARN] {name}: {msg}")

def fail(name, msg):
    results.append((name, "FAIL", msg))
    print(f"[FAIL] {name}: {msg}")


def fix_d2_root():
    p = ROOT / "backend/app/services/game_loop/npc_orchestration.py"
    src = p.read_text(encoding="utf-8")

    # Replace the ENTIRE block from comment header to end-of-for body
    # (preserving exact content, just wrapping in `if not ctx.hub_event:`)
    old = """    # Дополнение Б: Глобальный цикл тика для хода игрока
    for _loc_id in _location_ids:
        # Активная локация использует shared_context.scene_state, остальные грузим из менеджера
        if _loc_id == _active_loc:
            _current_scene = shared_context.scene_state
        else:
            _current_scene = _scene_manager.get_scene_state(campaign_id, _loc_id) if _scene_manager else None  # noqa: ENIGMA001

        if _current_scene is None:
            continue

        # Инъекция SpatialService для каждой локации
        _loc_spatial_svc = None
        try:
            from app.services.spatial.spatial_factory import SpatialFactory
            _loc_spatial_svc = SpatialFactory.build_for_campaign(campaign_id=campaign_id, location_id=_loc_id, scene_state=_current_scene)
        except Exception as e:
            logger.warning(f"SpatialFactory failed for loc={_loc_id}: {e}")

        # Передаем interventions только для активной локации
        _current_interventions = [_intervention] if _loc_id == _active_loc else []

        # BUG-NO-RETRO-SIM FIX: Линтер ошибочно принимает проход по локациям за ретро-симуляцию.
        _execute_tick = tick_orchestrator.execute
        _loc_result = _execute_tick(
            campaign_id=campaign_id,
            scene_state=_current_scene,
            tick_number=shared_context.current_tick or 0,
            interventions=_current_interventions,
            npc_services=_npc_svc,
            spatial_service=_loc_spatial_svc,
            all_npcs_raw=ctx.all_npcs_raw,
            shared_context=shared_context if _loc_id == _active_loc else None,  # noqa: ENIGMA001
            active_location_id=_active_loc,
            location_ids=_location_ids,
            hub_event=ctx.hub_event if _loc_id == _active_loc else None,  # BUG-CORE-003 FIX  # noqa: ENIGMA001
            task_scheduler=deps.task_scheduler_getter(),  # REGRESSION-CORE-001 FIX: Проброс task_scheduler в ядро
        )
        # BUG-FB-031 FIX: Сохраняем world_snapshot из ядра в shared_context, чтобы не пересобирать его с нуля в GameLoop
        if hasattr(_loc_result, "world_snapshot") and _loc_result.world_snapshot is not None:
            shared_context.world_snapshot = _loc_result.world_snapshot

        # Коммитим результат тика для каждой локации
        if _loc_result is not None and _loc_result.final_scene_state is not None and _scene_manager:
            if _scene_manager.is_tick_locked_for(campaign_id):
                _scene_manager.commit_tick_result(campaign_id, _loc_result.final_scene_state)

        # Сохраняем результат активной локации
        if _loc_id == _active_loc:
            _tick_result = _loc_result
            shared_context.scene_state = _loc_result.final_scene_state
"""
    new = """    # D2 root fix (GC-01 / ADR-O-407): player turn pauses world time —
    # idle-контур НЕ вызывает TickOrchestrator.execute() во время player_action.
    # NPC dialogue reactions приходят из dm_result, не из tick_orchestrator.
    # Существующие in-flight traversals НЕ интерполируются (no tick advancement).
    if not getattr(ctx, "hub_event", None):
        # Дополнение Б: Глобальный цикл тика для idle-хода (не player_action)
        for _loc_id in _location_ids:
            # Активная локация использует shared_context.scene_state, остальные грузим из менеджера
            if _loc_id == _active_loc:
                _current_scene = shared_context.scene_state
            else:
                _current_scene = _scene_manager.get_scene_state(campaign_id, _loc_id) if _scene_manager else None  # noqa: ENIGMA001

            if _current_scene is None:
                continue

            # Инъекция SpatialService для каждой локации
            _loc_spatial_svc = None
            try:
                from app.services.spatial.spatial_factory import SpatialFactory
                _loc_spatial_svc = SpatialFactory.build_for_campaign(campaign_id=campaign_id, location_id=_loc_id, scene_state=_current_scene)
            except Exception as e:
                logger.warning(f"SpatialFactory failed for loc={_loc_id}: {e}")

            # Передаем interventions только для активной локации
            _current_interventions = [_intervention] if _loc_id == _active_loc else []

            # BUG-NO-RETRO-SIM FIX: Линтер ошибочно принимает проход по локациям за ретро-симуляцию.
            _execute_tick = tick_orchestrator.execute
            _loc_result = _execute_tick(
                campaign_id=campaign_id,
                scene_state=_current_scene,
                tick_number=shared_context.current_tick or 0,
                interventions=_current_interventions,
                npc_services=_npc_svc,
                spatial_service=_loc_spatial_svc,
                all_npcs_raw=ctx.all_npcs_raw,
                shared_context=shared_context if _loc_id == _active_loc else None,  # noqa: ENIGMA001
                active_location_id=_active_loc,
                location_ids=_location_ids,
                hub_event=ctx.hub_event if _loc_id == _active_loc else None,  # BUG-CORE-003 FIX  # noqa: ENIGMA001
                task_scheduler=deps.task_scheduler_getter(),  # REGRESSION-CORE-001 FIX: Проброс task_scheduler в ядро
            )
            # BUG-FB-031 FIX: Сохраняем world_snapshot из ядра в shared_context
            if hasattr(_loc_result, "world_snapshot") and _loc_result.world_snapshot is not None:
                shared_context.world_snapshot = _loc_result.world_snapshot

            # Коммитим результат тика для каждой локации
            if _loc_result is not None and _loc_result.final_scene_state is not None and _scene_manager:
                if _scene_manager.is_tick_locked_for(campaign_id):
                    _scene_manager.commit_tick_result(campaign_id, _loc_result.final_scene_state)

            # Сохраняем результат активной локации
            if _loc_id == _active_loc:
                _tick_result = _loc_result
                shared_context.scene_state = _loc_result.final_scene_state
    else:
        # D2 fix: player_action path — NPC state НЕ продвигается.
        # shared_context.scene_state остаётся как был (set в _sync_shared_context_with_scene).
        # world_snapshot остаётся None (заполняется из dm_result отдельно).
        # _tick_result остаётся None — commit_tick_result ниже (@273-282) тоже пропускается.
        pass
"""
    if old in src:
        src = src.replace(old, new, 1)
        p.write_text(src, encoding="utf-8")
        ok("D2-root-v2", f"gate added with full body re-indent in {p.name}")
    else:
        warn("D2-root-v2", "full body block not matched")


if __name__ == "__main__":
    print("=" * 70)
    print("GC-01 Block 67 — D2 root fix v2")
    print("=" * 70)
    fix_d2_root()
    for name, status, msg in results:
        print(f"  [{status:4}] {name}: {msg}")
    fails = [r for r in results if r[1] == "FAIL"]
    sys.exit(0 if not fails else 1)