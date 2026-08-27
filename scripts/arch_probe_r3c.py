# -*- coding: utf-8 -*-
"""ARCH-PROBE R3C :: движение/TextInput/12, wrapper 14c, входы 9, триггеры 8, economy-выжившие."""
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


def ls(rel):
    p = ROOT / rel
    if not p.exists():
        print(f"!! НЕТ: {rel}")
        return []
    return p.read_text(encoding="utf-8", errors="replace").splitlines()


def show(tag, rel, a, b):
    hr(f"{tag} [{rel}:{a}-{b}]")
    L = ls(rel)
    for i in range(a, b + 1):
        if 1 <= i <= len(L):
            print(f"{i:>5}| {L[i - 1]}")


def hits(tag, rel, pat, rad=3, lim=14):
    import re
    hr(f"{tag} /{pat}/ @ {rel}")
    L = ls(rel)
    rx = re.compile(pat)
    n = 0
    for i, ln in enumerate(L, 1):
        if rx.search(ln):
            lo, hi = max(1, i - rad), min(len(L), i + rad)
            print("-" * 55)
            for j in range(lo, hi + 1):
                print((">>" if j == i else "  ") + f"{j:>4}| {L[j - 1]}")
            n += 1
            if n >= lim:
                print("(лимит)")
                return


show("C1 TextInput ввод/ESC/RETURN", "frontend/text_input.py", 280, 330)
hits("C2 движение-поллинг", "frontend/game_screen.py", r"K_[wasd]\b|move_up|move_down|move_left|move_right")
show("C3 wrapper content_policy", "backend/app/core/content_policy.py", 170, 200)
hits("C4 роль-триггеры в решениях", "backend/app/services/phases/decision.py",
     r"role_change|profession|change_role|archetype", rad=2, lim=10)
hits("C5 голос-архетип", "backend/app/domain/memetic/voice_archetype.py", r"class\s+\w+|class_factor", rad=2, lim=8)
show("C6 профиль L0 состав", "backend/app/models/npc_profile.py", 56, 115)
hits("C7 identity_attachment источник", "backend/app", r"identity_attachment", lim=10)
hr("C8 economy выжившие файлы")
edir = ROOT / "backend/app/services/economy"
if edir.exists():
    for f in sorted(edir.iterdir()):
        print(("DIR " if f.is_dir() else "FILE") + f" {f.name}")
else:
    print("(каталог отсутствует)")
hr("КОНЕЦ ПРОБЫ R3C")