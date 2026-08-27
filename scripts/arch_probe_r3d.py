# -*- coding: utf-8 -*-
"""ARCH-PROBE R3D :: добор: движение-потребление, импорты настроек, endpooint-поиск,
голосовой реестр, возраст, identity_attachment источники, выжившие economy."""
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


def show(tag, rel, a, b):
    hr(f"{tag} [{rel}:{a}-{b}]")
    p = ROOT / rel
    if not p.is_file():
        print("!! НЕ ФАЙЛ:", rel)
        return
    L = p.read_text(encoding="utf-8", errors="replace").splitlines()
    for i in range(a, b + 1):
        if 1 <= i <= len(L):
            print(f"{i:>5}| {L[i - 1]}")


def rgrep(tag, pat, base_rel, lim=25):
    hr(f"{tag} /{pat}/ @ {base_rel}")
    import re
    rx = re.compile(pat)
    base = ROOT / base_rel
    files = [base] if base.is_file() else sorted(base.rglob("*.py"))
    n = 0
    for f in files:
        if not f.is_file():
            continue
        rp = str(f.relative_to(ROOT))
        try:
            L = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            print(f"READ-ERR {rp}: {e}")
            continue
        for i, ln in enumerate(L, 1):
            if rx.search(ln):
                print(f"{rp}:{i}| {ln.rstrip()}")
                n += 1
                if n >= lim:
                    print("(лимит)")
                    return
    if n == 0:
        print("(пусто)")


show("D1 движение-потребление", "frontend/game_screen.py", 688, 758)
show("D2 импорты настроек", "frontend/settings_screen.py", 1, 42)
rgrep("D3 def save_content_policy", r"def\s+save_content_policy", ".")
rgrep("D4 контент-роуты бэкенда", r"content[_-]policy", "backend/app/api")
rgrep("D5 голосовой реестр", r"voice_archetype", "backend/app/services", lim=15)
rgrep("D6 yaml голосов", r"voice_archetypes", "backend", lim=10)
show("D7 профиль: хвост L0/возраст", "backend/app/models/npc_profile.py", 112, 175)
rgrep("D8 age у NPC", r"\bage\b", "backend/app/models/npc_state.py", lim=10)
rgrep("D9 identity_attachment источники", r"identity_attachment", "backend/app/services", lim=15)
hr("D10 economy выжившие")
edir = ROOT / "backend/app/services/economy"
print("\n".join(sorted(f.name for f in edir.iterdir())) if edir.exists() else "(нет каталога)")
hr("КОНЕЦ ПРОБЫ R3D")