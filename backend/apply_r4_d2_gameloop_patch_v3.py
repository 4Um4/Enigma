"""
R4/GATE-9A D2 — patch game_loop.py v3 (corrected run_turn wrap to include execute).

v3 vs v2: Edit 3 wrap range = [execute .. unlock-1] (includes execute call).
This ensures exception inside execute (which acquires lock via _prepare_and_lock_scene)
is caught by except block, mark_tick_aborted is called, unlock_tick in finally.

Ранний return @1531 остаётся внутри try (OK — try/finally executes on return).
Вложенный async def _dm_unavailable_response @1588 остаётся внутри try (OK —
Python allows def inside try).
"""
import sys
import shutil
from pathlib import Path

GL_PATH = Path("app/services/game_loop/game_loop.py")
BACKUP_PATH = Path("app/services/game_loop/game_loop.py.r4_backup")

if not GL_PATH.exists():
    print(f"ERROR: {GL_PATH} not found"); sys.exit(1)

if not BACKUP_PATH.exists():
    shutil.copy2(GL_PATH, BACKUP_PATH)
    print(f"[OK] backup: {BACKUP_PATH}")
else:
    print(f"[skip] backup exists: {BACKUP_PATH}")

lines = GL_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
original_count = len(lines)


def apply_text_replace(src, name, before, after):
    count = src.count(before)
    if count != 1:
        print(f"[FAIL] {name}: expected 1 occurrence, found {count}")
        sys.exit(2)
    print(f"[OK] {name}: 1 replacement applied")
    return src.replace(before, after, 1)


def wrap_range(lines_list, name, start_0, end_0, except_body_lines, finally_body_lines):
    before = lines_list[:start_0]
    wrapped = lines_list[start_0:end_0 + 1]
    after = lines_list[end_0 + 1:]
    new_wrapped = []
    for ln in wrapped:
        if ln.strip() == "":
            new_wrapped.append(ln)
        else:
            new_wrapped.append("    " + ln)
    out = list(before)
    out.append("        try:\n")
    out.extend(new_wrapped)
    out.append("        except Exception:\n")
    for el in except_body_lines:
        out.append("            " + el + "\n")
    out.append("        finally:\n")
    for fl in finally_body_lines:
        out.append("            " + fl + "\n")
    out.extend(after)
    print(f"[OK] {name}: wrapped lines {start_0+1}..{end_0+1} ({end_0 - start_0 + 1} lines)")
    return out


# Edit 1: skip_time — add except before finally
src_text = "".join(lines)
EDIT1_BEFORE = """            }
        finally:
            # BUG-FB-002 FIX: Снимаем блокировку scene_manager, иначе ядро зависнет навсегда.
            self.scene_manager.unlock_tick(campaign_id)
            lock.release()"""
EDIT1_AFTER = """            }
        except Exception:
            # R4/GATE-9A D2: помечаем тик как аварийный (legitimate owner)
            # перед тем, как finally снимет блокировку. unlock_tick пропустит
            # atomic_commit_all — persistence остаётся в pre-tick.
            self.scene_manager.mark_tick_aborted(campaign_id)
            raise
        finally:
            # BUG-FB-002 FIX: Снимаем блокировку scene_manager, иначе ядро зависнет навсегда.
            self.scene_manager.unlock_tick(campaign_id)
            lock.release()"""
src_text = apply_text_replace(src_text, "Edit 1: skip_time except before finally", EDIT1_BEFORE, EDIT1_AFTER)
lines = src_text.splitlines(keepends=True)


# Edit 2: idle_tick — wrap body [lock_all+1 .. unlock-1]
lock_all_idx = None
for i, ln in enumerate(lines):
    if "self.scene_manager.lock_all_for_tick(campaign_id, _location_ids)" in ln:
        lock_all_idx = i
        break
if lock_all_idx is None:
    print("[FAIL] Edit 2: lock_all_for_tick not found"); sys.exit(4)

unlock_idle_idx = None
for i in range(lock_all_idx + 1, len(lines)):
    if "self.scene_manager.unlock_tick(campaign_id)" in lines[i]:
        unlock_idle_idx = i
        break
if unlock_idle_idx is None:
    print("[FAIL] Edit 2: idle_tick unlock not found"); sys.exit(5)

except_idle = [
    "# R4/GATE-9A D2: mark tick as aborted; unlock_tick in finally",
    "# will skip atomic_commit_all — persistence stays in pre-tick.",
    "self.scene_manager.mark_tick_aborted(campaign_id)",
    "raise",
]
finally_idle = [
    "# S83.1: UNLOCK — единственная точка persist для idle_tick.",
    "# commit_tick_result() уже обновил _tick_scene результатом тика.",
    "# unlock_tick сохраняет его на диск (если тик НЕ помечен aborted).",
    "self.scene_manager.unlock_tick(campaign_id)",
]
lines = wrap_range(lines, "Edit 2: idle_tick",
                  start_0=lock_all_idx + 1, end_0=unlock_idle_idx - 1,
                  except_body_lines=except_idle, finally_body_lines=finally_idle)


# Edit 3 v3: run_turn — wrap [execute .. unlock-1] (INCLUDES execute call)
# v2 wrapped [early_return+1 .. unlock-1], but acquisition happens INSIDE execute
# (via _prepare_and_lock_scene @773 → lock_for_tick @545). If execute raises,
# lock is acquired but finally @unlock_tick doesn't fire.
# v3 wraps from execute line itself, so exception in execute is caught.
execute_idx = None
for i, ln in enumerate(lines):
    if "state = await self._turn_pipeline.execute(" in ln:
        execute_idx = i
        break
if execute_idx is None:
    print("[FAIL] Edit 3: execute line not found"); sys.exit(6)

unlock_rt_idx = None
for i in range(execute_idx + 1, len(lines)):
    if "self.scene_manager.unlock_tick(req.campaign_id)" in lines[i]:
        unlock_rt_idx = i
        break
if unlock_rt_idx is None:
    print("[FAIL] Edit 3: run_turn unlock not found"); sys.exit(7)

except_rt = [
    "# R4/GATE-9A D2: mark tick as aborted; unlock_tick in finally",
    "# will skip atomic_commit_all — persistence stays in pre-tick.",
    "self.scene_manager.mark_tick_aborted(req.campaign_id)",
    "raise",
]
finally_rt = [
    "# ADR-SCENE-LOCK: Разблокируем тик — финальный персист кэша",
    "# (если тик НЕ помечен aborted).",
    "self.scene_manager.unlock_tick(req.campaign_id)",
]
lines = wrap_range(lines, "Edit 3 v3: run_turn (includes execute)",
                  start_0=execute_idx, end_0=unlock_rt_idx - 1,
                  except_body_lines=except_rt, finally_body_lines=finally_rt)


GL_PATH.write_text("".join(lines), encoding="utf-8")
new_count = len(lines)
print()
print(f"[DONE] {GL_PATH} patched: {original_count} -> {new_count} lines (+{new_count - original_count})")
print("[DONE] Backup at:", BACKUP_PATH)
