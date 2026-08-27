# -*- coding: utf-8 -*-
"""ARCH-PROBE R3B :: сигнатуры для интеграций 7/8/9, клавиши 12, пресет 14c, yaml 6."""
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
        print("!! НЕТ:", relpath)
        return
    ls = p.read_text(encoding="utf-8", errors="replace").splitlines()
    for i in range(a, b + 1):
        if 1 <= i <= len(ls):
            print(f"{i:>5}| {ls[i - 1]}")


show("B1 keybindings целиком", "frontend/keybindings.py", 1, 130)
show("B2 front_applicator целиком", "backend/app/services/character/front_applicator.py", 1, 96)
show("B3 front_engine каркас", "backend/app/services/character/front_engine.py", 1, 80)
show("B4 role_transition каркас", "backend/app/services/npc/role_transition.py", 1, 100)
show("B5 linguistic calc целиком", "backend/app/services/memetic/linguistic_integrity_calculator.py", 1, 66)
show("B6 npc_profile поле", "backend/app/models/npc_profile.py", 40, 60)
show("B7 economy.yaml", "architecture/economy.yaml", 1, 120)
show("B8 ctx/shared_context поля фаз", "backend/app/services/phases/integration.py", 20, 60)

hr("GREP :: _WASD_KEYS все употребления")
p = ROOT / "frontend/game_screen.py"
ls = p.read_text(encoding="utf-8", errors="replace").splitlines()
for i, ln in enumerate(ls, 1):
    if "_WASD_KEYS" in ln:
        print(f"{i}| {ln.rstrip()}")

hr("GREP :: потребители front_description/world_pressure")
import re
rx = re.compile(r"front_description|world_pressure")
n = 0
for f in sorted((ROOT / "backend/app").rglob("*.py")):
    try:
        tls = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        continue
    rp = str(f.relative_to(ROOT))
    for i, ln in enumerate(tls, 1):
        if rx.search(ln):
            print(f"{rp}:{i}| {ln.rstrip()}")
            n += 1
            if n >= 30:
                break
    if n >= 30:
        break

hr("GREP :: контент-пресет во фронтовых настройках")
for i, ln in enumerate(p.parent.joinpath("settings_screen.py").read_text(encoding="utf-8", errors="replace").splitlines(), 1):
    if re.search(r"_apply_|пресет|preset|reload_content", ln, re.I):
        print(f"{i}| {ln.rstrip()}")

hr("КОНЕЦ ПРОБЫ R3B")