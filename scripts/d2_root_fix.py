"""GC-01 Block 66 — D2 root fix: gate tick_orchestrator during player_action.

ADR-O-407 (APPROVED-BY-MASTER): "пока не исполнено обязательство хода игрока,
мировое время не продвигается: idle-контур не вызывает TickOrchestrator.execute()".

Current code at npc_orchestration.py:218 explicitly runs a tick loop during
player_action ("Глобальный цикл тика для хода игрока"), violating ADR-O-407.

This fix gates the entire `for _loc_id in _location_ids:` tick loop when
ctx.hub_event is present (player_action). NPC dialogue reactions (from DM agent)
are unaffected — they come from dm_result, not from tick_orchestrator.

Side effect: _tick_result stays None for player_action → shared_context.scene_state
not re-assigned from final_scene_state. This is acceptable because:
  - DM agent already has scene_state (set by _sync_shared_context_with_scene @114)
  - world_changes from DM are applied separately (RCE commit phase)
  - npc_reactions from DM are returned in ChatTurnResponse
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

    # We need to gate the tick loop based on ctx.hub_event presence.
    # The loop starts with: "    # Дополнение Б: Глобальный цикл тика для хода игрока"
    # followed by: "    for _loc_id in _location_ids:"

    # Strategy: insert a guard before the for loop that skips it when ctx.hub_event
    # is present (player_action). We need to preserve the post-loop logic (lines 270+)
    # which handles commit_tick_result for the active location.

    # Look for the exact comment + for-loop start
    old = (
        "    # Дополнение Б: Глобальный цикл тика для хода игрока\n"
        "    for _loc_id in _location_ids:\n"
    )
    new = (
        "    # D2 root fix (GC-01 / ADR-O-407): player turn pauses world time —\n"
        "    # idle-контур НЕ вызывает TickOrchestrator.execute() во время player_action.\n"
        "    # Пропускаем глобальный цикл тика; NPC dialogue reactions приходят из dm_result,\n"
        "    # не из tick_orchestrator. Существующие in-flight traversals НЕ интерполируются\n"
        "    # (no tick advancement = no ghost interpolation per ADR-O-201 E5).\n"
        "    if not getattr(ctx, \"hub_event\", None):\n"
        "        # Дополнение Б: Глобальный цикл тика для idle-хода (не player_action)\n"
        "        for _loc_id in _location_ids:\n"
    )
    if old in src:
        src = src.replace(old, new, 1)
        # Now we need to indent the entire body of the for loop by 4 more spaces
        # Find the for loop and indent until we exit its body
        lines = src.split("\n")
        # Find the new for-loop line
        for i, line in enumerate(lines):
            if "for _loc_id in _location_ids:" in line and "idle-хода" in lines[i-1]:
                # Determine current indent of for line
                for_indent = len(line) - len(line.lstrip())
                # Indent all subsequent lines that are deeper than for_indent
                # until we hit a line with indent <= for_indent (end of for body)
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    if next_line.strip() == "":
                        j += 1
                        continue
                    next_indent = len(next_line) - len(next_line.lstrip())
                    if next_indent <= for_indent:
                        break
                    # Indent this line by 4 more spaces
                    lines[j] = "    " + next_line
                    j += 1
                break
        src = "\n".join(lines)
        p.write_text(src, encoding="utf-8")
        ok("D2-root", f"gate added in {p.name}")
    else:
        warn("D2-root", "tick loop start not found")


if __name__ == "__main__":
    print("=" * 70)
    print("GC-01 Block 66 — D2 root fix")
    print("=" * 70)
    fix_d2_root()
    for name, status, msg in results:
        print(f"  [{status:4}] {name}: {msg}")
    fails = [r for r in results if r[1] == "FAIL"]
    sys.exit(0 if not fails else 1)