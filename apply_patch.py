import sys
from pathlib import Path

target = Path("backend/app/services/spatial/movement_engine.py")
content = target.read_text(encoding="utf-8")

# Точное соответствие — boundary_arrival ветка
old_block = """                    return [
                        SceneChange(
                            type=ChangeType.NPC_POSITION, target=intent.actor_id,
                            field="position", value=next_node.node_id,
                            cause=f"boundary_arrival:{intent.reason}", tick=tick,
                            traversal_proposal=None,
                        ),
                        SceneChange(
                            type=ChangeType.NPC_POSITION, target=intent.actor_id,
                            field="local_position",
                            value={"x": next_node.x, "y": next_node.y},
                            cause=f"boundary_arrival:{intent.reason}", tick=tick,
                            traversal_proposal=None,
                        ),
                    ]"""

new_block = """                    # ADR-O-323 FIX-01: boundary_arrival завершает traversal (NPC
                    # дошёл до boundary-узла), не начинает новый. Cause =
                    # traversal_complete (whitelist SSM), корректно снимает
                    # требование proposal для snap-позиции. MovementPlanner
                    # остаётся единственным автором proposal для macro
                    # relocation; boundary_arrival им не является.
                    return [
                        SceneChange(
                            type=ChangeType.NPC_POSITION, target=intent.actor_id,
                            field="position", value=next_node.node_id,
                            cause="traversal_complete", tick=tick,
                            traversal_proposal=None,
                        ),
                        SceneChange(
                            type=ChangeType.NPC_POSITION, target=intent.actor_id,
                            field="local_position",
                            value={"x": next_node.x, "y": next_node.y},
                            cause="traversal_complete", tick=tick,
                            traversal_proposal=None,
                        ),
                    ]"""

if old_block not in content:
    print("FAIL: old_block not found in movement_engine.py")
    # Покажем что есть в файле вокруг boundary_arrival
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        if "boundary_arrival" in line:
            print(f"--- line {i}: {line}")
            for j in range(max(1, i-3), min(len(lines), i+5)):
                print(f"  {j}: {lines[j-1]}")
            break
    sys.exit(1)

new_content = content.replace(old_block, new_block)
target.write_text(new_content, encoding="utf-8")
print("PATCH APPLIED: ADR-O-323 FIX-01")
print(f"Lines: {len(new_content.splitlines())} (was {len(content.splitlines())})")
