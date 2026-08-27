# -*- coding: utf-8 -*-
"""
ARCH-PROBE R1 :: сверка реестра аудита v0.5.3.9.0 с фактическим кодом.
Покрывает дефекты: №1, №2, №3, №4, №5 (критич.) + №11 (VRAM), №15 (SCALE).
Запуск из КОРНЯ репозитория:  python -X utf8 scripts/arch_probe_r1.py
Вывод целиком отправляется в чат.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def hr(title):
    print("=" * 79)
    print("### " + title)


def show(tag, relpath, a, b):
    hr(f"{tag}  [{relpath}:{a}-{b}]")
    p = ROOT / relpath
    if not p.exists():
        print("!! ФАЙЛ НЕ НАЙДЕН:", relpath)
        return
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    n_bad = 0
    for i in range(a, b + 1):
        if i < 1 or i > len(lines):
            continue
        ln = lines[i - 1]
        if any("\ufffd" == ch for ch in ln[:5]):
            n_bad += 1
        print(f"{i:>5}| {ln}")


def py_files(rel_dirs):
    seen = set()
    for d in rel_dirs:
        base = ROOT / d
        if base.is_file():
            yield base
            continue
        if not base.exists():
            continue
        for f in sorted(base.rglob("*.py")):
            rp = str(f.relative_to(ROOT))
            if rp in seen:
                continue
            seen.add(rp)
            yield f


def grep(tag, pattern, rel_dirs, flags_no_case=True, limit=60):
    import re
    hr("GREP :: " + tag + f"  /{pattern}/")
    rx = re.compile(pattern, re.IGNORECASE if flags_no_case else 0)
    hits = 0
    for f in py_files(rel_dirs):
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print("READ-ERR:", f, e)
            continue
        rp = str(f.relative_to(ROOT))
        for i, ln in enumerate(txt.splitlines(), 1):
            if rx.search(ln):
                print(f"{rp}:{i}| {ln.rstrip()}")
                hits += 1
                if hits >= limit:
                    print("... (обрезано по лимиту)")
                    return
    if hits == 0:
        print("(пусто)")


# ---------- F1: битый импорт в routes_debug ----------
show("F1-a импорт и вызов аксессора", "backend/app/api/routes_debug.py", 66, 112)
show("F1-b", "backend/app/core/game_loop.py", 1, 10)  # должен отсутствовать
grep("get_game_loop во всех источниках", r"get_game_loop", ["backend/app"])

# ---------- F2: crystallized_belief_store -> DecisionHub ----------
show("F2-a чтение в decision", "backend/app/services/phases/decision.py", 298, 320)
show("F2-b контракт NpcTickServices", "backend/app/services/npc/npc_tick_contracts.py", 60, 100)
show("F2-c сборка сервисов", "backend/app/services/game_loop/npc_orchestration.py", 110, 145)
grep("crystallized_belief_store везде", r"crystallized_belief_store|CrystallizedBeliefStore",
     ["backend/app"])
grep("CrystallizedBeliefModifierResolver вызовы", r"CrystallizedBeliefModifierResolver",
     ["backend/app"])

# ---------- F3: idle_tick / skip_time без npc_services ----------
show("F3-a idle_tick у оркестратора", "backend/app/services/game_loop/__init__.py", 900, 945)
show("F3-b второй путь (skip_time/promote)", "backend/app/services/game_loop/__init__.py", 1095, 1140)
grep("конструкции NpcTickServices(", r"NpcTickServices\s*\(", ["backend/app"], limit=80)
grep("execute\(.*npc_services|npc_services=", r"npc_services", ["backend/app/services"],
     limit=120)
grep("TimeSkipExecutor", r"class\s+TimeSkipExecutor|def\s+skip\s*\(", ["backend/app"])

# ---------- F4: set_continuity_mode разорван ----------
show("F4-a HTTPGateway delegate", "frontend/api_client.py", 368, 385)
grep("set_continuity_mode везде", r"set_continuity_mode", ["frontend", "backend/app"])
grep("Класс BackendContract", r"class\s+BackendContract\b", ["frontend"])
grep("Маршруты с continuity", r"continuity", ["backend/app/api"], limit=30)

# ---------- F5: молчаливый экран + Direct без scene_state ----------
show("F5-a ранний возврат экрана", "frontend/game_screen.py", 575, 600)
show("F5-b Direct get_session_state", "frontend/api_client.py", 540, 556)
grep("create_game_gateway вызовы", r"create_game_gateway\s*\(", ["frontend", "."], limit=30)

# ---------- F11: VRAM-заглушка ----------
show("V-a vram_monitor шапка", "backend/app/services/vram_monitor.py", 1, 45)
show("V-b стартовый рапорт main", "backend/main.py", 118, 142)
grep("vram упоминания в debug-роутах", r"vram", ["backend/app/api"], limit=25)

# ---------- F15: двойной масштаб редактора ----------
show("S-a редактор SCALE", "frontend/map_editor/editor_core.py", 55, 70)
show("S-b дубликат в обработчике", "frontend/map_editor/core/event_handler.py", 15, 30)
show("S-c зоны пересчёта драгов", "frontend/map_editor/core/event_handler.py", 380, 445)

hr("КОНЕЦ ПРОБЫ R1")