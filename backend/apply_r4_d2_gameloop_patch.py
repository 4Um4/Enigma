"""
R4/GATE-9A D2 — patch game_loop.py
3 edits:
  Edit 1: skip_time — add except before finally (1 replacement)
  Edit 2: idle_tick — wrap body [1228..1478] in try/except/finally (line-range indent +4)
  Edit 3: run_turn  — wrap body [1518..1825] in try/except/finally (line-range indent +4)
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


def apply_text_replace(src: str, name: str, before: str, after: str) -> str:
    count = src.count(before)
    if count != 1:
        print(f"[FAIL] {name}: expected 1 occurrence, found {count}")
        sys.exit(2)
    print(f"[OK] {name}: 1 replacement applied")
    return src.replace(before, after, 1)


def apply_line_range_wrap(lines_list, name, start_1based, end_1based,
                          wrap_indent_str, except_body, finally_body):
    """Wrap lines [start..end] (1-based, inclusive) in try:/except/finally.
    Adds wrap_indent_str + 'try:' before start;
    indents each line in [start..end] by +4 spaces;
    adds except_body (with proper indent) after end;
    adds finally_body (with proper indent) after except.

    start_1based points to the FIRST line to be wrapped (will get +4 indent).
    end_1based points to the LAST line to be wrapped (will get +4 indent).
    """
    # Convert to 0-based
    start = start_1based - 1
    end = end_1based - 1
    if start < 0 or end >= len(lines_list) or start > end:
        print(f"[FAIL] {name}: bad range {start_1based}..{end_1based}")
        sys.exit(3)

    before_block = lines_list[:start]
    wrapped = lines_list[start:end+1]
    after_block = lines_list[end+1:]

    # Indent wrapped lines by +4 spaces (preserve empty lines as empty)
    new_wrapped = []
    for ln in wrapped:
        if ln.strip() == "":
            new_wrapped.append(ln)  # keep empty line as-is
        else:
            new_wrapped.append("    " + ln)

    # Build new lines
    new_lines = []
    new_lines.extend(before_block)
    new_lines.append(wrap_indent_str + "try:\n")
    new_lines.extend(new_wrapped)
    new_lines.append(wrap_indent_str + "except Exception:\n")
    for el in except_body:
        new_lines.append(wrap_indent_str + "    " + el + "\n")
    new_lines.append(wrap_indent_str + "finally:\n")
    for fl in finally_body:
        new_lines.append(wrap_indent_str + "    " + fl + "\n")
    new_lines.extend(after_block)

    print(f"[OK] {name}: wrapped lines {start_1based}..{end_1based} ({end - start + 1} lines)")
    return new_lines


# Reconstruct full source for text replacement (Edit 1)
src_text = "".join(lines)


# ─── Edit 1: skip_time — add except before finally ──────────────────────
# Текущая структура:
#   1057:             return {
#   ...
#   1063:             }
#   1064:         finally:
#   1065:             # BUG-FB-002 FIX: Снимаем блокировку...
#   1066:             self.scene_manager.unlock_tick(campaign_id)
#   1067:             lock.release()
#
# Минимальная правка: вставить `except Exception:` перед `finally:` @1064.
# В except вызвать mark_tick_aborted (затем finally снимет блокировку как обычно,
# но т.к. маркер установлен, persist будет пропущен).
#
# Точное совпадение для замены:
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


# ─── Edit 2: idle_tick — wrap body [1228..1478] in try/except/finally ───
# 1227: self.scene_manager.lock_all_for_tick(campaign_id, _location_ids)  — НЕ трогаем (acquire)
# 1228..1477: тело между acquire и unlock — wrap в try (indent +4)
# 1478: self.scene_manager.unlock_tick(campaign_id) — заменяем на finally (НЕ indent, переносим в finally body)
# 1479..1493: код после unlock (project_idle_events и т.д.) — НЕ трогаем
# 1494: return {...} — НЕ трогаем
#
# Стратегия: применяем line-range wrap к диапазону 1228..1477 (только тело).
# В finally_body кладём unlock_tick. except_body кладём mark_tick_aborted + raise.
#
# Но apply_line_range_wrap работает с lines_list, а Edit 1 уже изменил src_text.
# Поэтому: перечитываем lines из src_text, применяем Edit 2 (line-range), затем
# для Edit 3 снова перечитываем.

lines = src_text.splitlines(keepends=True)

# Find current line numbers after Edit 1 (Edit 1 added 6 lines: except + 4 comment/code + raise + finally moved)
# Edit 1 added: "        except Exception:\n" + 3 comment lines + "            self.scene_manager.mark_tick_aborted(campaign_id)\n" + "            raise\n"
# That's 6 new lines inserted before "        finally:" (which was line 1064).
# Original idle_tick lock_all_for_tick @ 1227 → now 1227 + 6 = 1233.
# Original unlock_tick @ 1478 → now 1478 + 6 = 1484.
# Range to wrap: 1234..1483 (1-based, inclusive) — that's body between lock_all and unlock.
# Then 1484 is the unlock line (will go into finally_body).

# Find lock_all_for_tick line dynamically
lock_all_line_idx = None
for i, ln in enumerate(lines):
    if "self.scene_manager.lock_all_for_tick(campaign_id, _location_ids)" in ln:
        lock_all_line_idx = i  # 0-based
        break
if lock_all_line_idx is None:
    print("[FAIL] Edit 2: lock_all_for_tick not found"); sys.exit(4)

# Find unlock_tick line in idle_tick (the one after lock_all, before "return {" with "status")
unlock_line_idx = None
for i in range(lock_all_line_idx + 1, len(lines)):
    ln = lines[i]
    if "self.scene_manager.unlock_tick(campaign_id)" in ln:
        # Check it's the idle_tick one (followed by ADR-O-420 comment later)
        unlock_line_idx = i  # 0-based
        break
if unlock_line_idx is None:
    print("[FAIL] Edit 2: unlock_tick not found"); sys.exit(5)

# Wrap range: from lock_all_line_idx+1 to unlock_line_idx-1 (0-based inclusive)
# That's body between lock and unlock.
wrap_start_1based = lock_all_line_idx + 2  # line after lock_all (1-based)
wrap_end_1based = unlock_line_idx         # unlock line itself (1-based), will be replaced by finally_body

# We'll wrap body [lock_all+1 .. unlock-1] and put unlock in finally_body.
wrap_start_0 = lock_all_line_idx + 1  # first body line
wrap_end_0 = unlock_line_idx - 1      # last body line before unlock

before_block = lines[:lock_all_line_idx + 1]  # up to and including lock_all line
wrapped = lines[wrap_start_0:wrap_end_0 + 1]
after_block = lines[unlock_line_idx + 1:]  # after unlock line

# Indent wrapped by +4
new_wrapped = []
for ln in wrapped:
    if ln.strip() == "":
        new_wrapped.append(ln)
    else:
        new_wrapped.append("    " + ln)

# Build new lines
new_lines = []
new_lines.extend(before_block)
new_lines.append("        try:\n")  # 8-space indent (method body level)
new_lines.extend(new_wrapped)
new_lines.append("        except Exception:\n")
new_lines.append("            # R4/GATE-9A D2: mark tick as aborted; unlock_tick in finally\n")
new_lines.append("            # will skip atomic_commit_all — persistence stays in pre-tick.\n")
new_lines.append("            self.scene_manager.mark_tick_aborted(campaign_id)\n")
new_lines.append("            raise\n")
new_lines.append("        finally:\n")
new_lines.append("            # S83.1: UNLOCK — единственная точка persist для idle_tick.\n")
new_lines.append("            # commit_tick_result() уже обновил _tick_scene результатом тика.\n")
new_lines.append("            # unlock_tick сохраняет его на диск (если тик НЕ помечен aborted).\n")
new_lines.append("            self.scene_manager.unlock_tick(campaign_id)\n")
new_lines.extend(after_block)

print(f"[OK] Edit 2: idle_tick wrapped body lines {wrap_start_1based}..{wrap_end_1based} ({wrap_end_0 - wrap_start_0 + 1} lines), unlock moved to finally")

lines = new_lines


# ─── Edit 3: run_turn — wrap body [execute+1 .. unlock] in try/except/finally ───
# Structure:
#   1518: state = await self._turn_pipeline.execute(...)
#   1519..1824: body (early return @1531 is INSIDE this range — but it's a normal return, not exception)
#   1825: self.scene_manager.unlock_tick(req.campaign_id)
#
# We wrap body AFTER execute returns (so early-return @1531 stays inside try, which is fine —
# try/finally executes finally on return too).
# Range: from line AFTER execute (1519) to line BEFORE unlock (1824).
# Unlock goes into finally_body.

# Find execute line (the first await self._turn_pipeline.execute)
execute_line_idx = None
for i, ln in enumerate(lines):
    if "state = await self._turn_pipeline.execute(" in ln:
        execute_line_idx = i  # 0-based
        break
if execute_line_idx is None:
    print("[FAIL] Edit 3: execute line not found"); sys.exit(6)

# Find unlock_tick(req.campaign_id) in run_turn (after execute)
unlock_rt_idx = None
for i in range(execute_line_idx + 1, len(lines)):
    ln = lines[i]
    if "self.scene_manager.unlock_tick(req.campaign_id)" in ln:
        unlock_rt_idx = i
        break
if unlock_rt_idx is None:
    print("[FAIL] Edit 3: run_turn unlock_tick not found"); sys.exit(7)

# Wrap body [execute_line_idx+1 .. unlock_rt_idx-1] (0-based inclusive)
before_rt = lines[:execute_line_idx + 1]
wrapped_rt = lines[execute_line_idx + 1:unlock_rt_idx]
after_rt = lines[unlock_rt_idx + 1:]

new_wrapped_rt = []
for ln in wrapped_rt:
    if ln.strip() == "":
        new_wrapped_rt.append(ln)
    else:
        new_wrapped_rt.append("    " + ln)

new_lines_rt = []
new_lines_rt.extend(before_rt)
new_lines_rt.append("        try:\n")
new_lines_rt.extend(new_wrapped_rt)
new_lines_rt.append("        except Exception:\n")
new_lines_rt.append("            # R4/GATE-9A D2: mark tick as aborted; unlock_tick in finally\n")
new_lines_rt.append("            # will skip atomic_commit_all — persistence stays in pre-tick.\n")
new_lines_rt.append("            self.scene_manager.mark_tick_aborted(req.campaign_id)\n")
new_lines_rt.append("            raise\n")
new_lines_rt.append("        finally:\n")
new_lines_rt.append("            # ADR-SCENE-LOCK: Разблокируем тик — финальный персист кэша\n")
new_lines_rt.append("            # (если тик НЕ помечен aborted).\n")
new_lines_rt.append("            self.scene_manager.unlock_tick(req.campaign_id)\n")
new_lines_rt.extend(after_rt)

print(f"[OK] Edit 3: run_turn wrapped body lines {execute_line_idx + 2}..{unlock_rt_idx} ({unlock_rt_idx - execute_line_idx - 1} lines), unlock moved to finally")

lines = new_lines_rt


# ─── Write result ───────────────────────────────────────────────────────
GL_PATH.write_text("".join(lines), encoding="utf-8")
new_count = len(lines)
print()
print(f"[DONE] {GL_PATH} patched: {original_count} -> {new_count} lines (+{new_count - original_count})")
print("[DONE] Backup at:", BACKUP_PATH)
print()
print("Next: re-run tests with: python -m pytest tests/test_r4_d2_ssm.py -v --tb=short")
