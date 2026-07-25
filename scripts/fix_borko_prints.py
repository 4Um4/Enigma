import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
file_path = ROOT / "backend/app/services/spatial/movement_engine.py"

if not file_path.exists():
    print(f"[ERROR] File not found: {file_path}")
    exit(1)

content = file_path.read_text(encoding="utf-8")

replacements = [
    ('                print(f"[BORKO_TRACE] tick={tick} type={type(intent).__name__} reason={getattr(intent, \'reason\', \'\')} target={getattr(intent, \'target_node_id\', getattr(intent, \'local_target_xy\', \'?\'))}")',
     '                logger.debug(f"[BORKO_TRACE] tick={tick} type={type(intent).__name__} reason={getattr(intent, \'reason\', \'\')} target={getattr(intent, \'target_node_id\', getattr(intent, \'local_target_xy\', \'?\'))}")'),
    ('                    print(f"[BORKO_CROSS] tick={tick} target_node={intent.target_node_id} intent_loc={getattr(intent, \'location_id\', \'N/A\')} cur_loc={current_loc} target_loc={target_loc} scene_state={_ss}")',
     '                    logger.debug(f"[BORKO_CROSS] tick={tick} target_node={intent.target_node_id} intent_loc={getattr(intent, \'location_id\', \'N/A\')} cur_loc={current_loc} target_loc={target_loc} scene_state={_ss}")'),
    ('                    print(f"[BORKO_CROSS_IN] tick={tick} ENTERED CROSS_LOC_INTERCEPT block")',
     '                    logger.debug(f"[BORKO_CROSS_IN] tick={tick} ENTERED CROSS_LOC_INTERCEPT block")'),
    ('                        print(f"[BORKO_CROSS_BOUNDARY] tick={tick} boundary_node={boundary_node}")',
     '                        logger.debug(f"[BORKO_CROSS_BOUNDARY] tick={tick} boundary_node={boundary_node}")'),
    ('                                print(f"[BORKO_DIST] tick={tick} cur_xy=({_cur_x:.1f}, {_cur_y:.1f}) boundary_xy=({boundary_node.x:.1f}, {boundary_node.y:.1f}) dist={_dist_to_boundary:.2f}")',
     '                                logger.debug(f"[BORKO_DIST] tick={tick} cur_xy=({_cur_x:.1f}, {_cur_y:.1f}) boundary_xy=({boundary_node.x:.1f}, {boundary_node.y:.1f}) dist={_dist_to_boundary:.2f}")'),
    ('                    print(f"[BORKO_RELOC] tick={tick} loc={location_id} target={intent.target_node_id} cur_pos={_current_pos} cur_xy={_current_xy}")',
     '                    logger.debug(f"[BORKO_RELOC] tick={tick} loc={location_id} target={intent.target_node_id} cur_pos={_current_pos} cur_xy={_current_xy}")'),
    ('                print(f"[BORKO_ASTAR_FAIL] target={target_node_obj.node_id} path_nodes={path_nodes}")',
     '                logger.debug(f"[BORKO_ASTAR_FAIL] target={target_node_obj.node_id} path_nodes={path_nodes}")'),
    ('            print(f"[BORKO_ASTAR] current_pos={current_pos} source_xy={source_xy} target={target_node_obj.node_id} path={[n.node_id for n in path_nodes]}")',
     '            logger.debug(f"[BORKO_ASTAR] current_pos={current_pos} source_xy={source_xy} target={target_node_obj.node_id} path={[n.node_id for n in path_nodes]}")'),
    ('                print(f"[BORKO_PLAN_REJECT] tick={tick} target={intent.target_node_id} reason={plan_result.reason}")',
     '                logger.debug(f"[BORKO_PLAN_REJECT] tick={tick} target={intent.target_node_id} reason={plan_result.reason}")'),
]

changed = False
for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        changed = True

if changed:
    file_path.write_text(content, encoding="utf-8")
    print("[FIXED] movement_engine.py prints replaced with logger.debug")
else:
    print("[SKIP] No prints found to replace")