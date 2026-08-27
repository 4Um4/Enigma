# -*- coding: utf-8 -*-
"""ARCH-PROBE R2 :: добивка для патчей P3/P4/P5/PV. Запуск из корня репозитория."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def hr(t):
    print("=" * 79)
    print("### " + t)


def show(tag, relpath, a, b):
    hr(f"{tag} [{relpath}:{a}-{b}]")
    p = ROOT / relpath
    if not p.exists():
        print("!! НЕТ ФАЙЛА:", relpath)
        return
    ls = p.read_text(encoding="utf-8", errors="replace").splitlines()
    for i in range(a, b + 1):
        if 1 <= i <= len(ls):
            print(f"{i:>5}| {ls[i - 1]}")


show("R2-1 импорты orchestration", "backend/app/services/game_loop/npc_orchestration.py", 1, 42)
show("R2-2 тело/границы orchestration", "backend/app/services/game_loop/npc_orchestration.py", 43, 250)
show("R2-3 TimeSkipExecutor.skip", "backend/app/services/world/time_skip_executor.py", 485, 590)
show("R2-4 Direct continuity", "frontend/api_client.py", 552, 585)
show("R2-5 Fallback continuity", "frontend/api_client.py", 786, 815)
show("R2-6 фабрика гейтвея", "frontend/api_client.py", 1080, 1150)
show("R2-7 launcher #1", "game_launcher.py", 470, 510)
show("R2-8 launcher #2", "game_launcher.py", 540, 570)
show("R2-9 Direct bridge/session", "frontend/api_client.py", 495, 552)
show("R2-10 game_screen контекст старта", "frontend/game_screen.py", 550, 592)

hr("GREP PV :: баннер VramMonitor/ErrorInterpreter в backend")
rx = re.compile(r"VramMonitor|VRAMMonitor|ErrorInterpreter\s*\+", re.I)
done = False
for f in sorted((ROOT / "backend").rglob("*.py")):
    if done:
        break
    try:
        txt = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    ls = txt.splitlines()
    rp = str(f.relative_to(ROOT))
    for i, ln in enumerate(ls, 1):
        if rx.search(ln):
            lo, hi = max(1, i - 6), min(len(ls), i + 6)
            hr(f"PANORAMA {rp}:{i}")
            for j in range(lo, hi + 1):
                mark = ">>" if j == i else "  "
                print(f"{mark}{j:>4}| {ls[j - 1]}")
            done = True
            break
if not done:
    print("(баннер не найден)")

hr("КОНЕЦ ПРОБЫ R2")