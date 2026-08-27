# -*- coding: utf-8 -*-
"""ARCH-PROBE R3 :: средняя группа реестра (N6-10, 12-14, 16-17). Запуск из корня."""
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


def src(relpath):
    p = ROOT / relpath
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8", errors="replace").splitlines()


def show(tag, relpath, a, b):
    hr(f"{tag} [{relpath}:{a}-{b}]")
    ls = src(relpath)
    if ls is None:
        print("!! НЕТ ФАЙЛА:", relpath)
        return
    for i in range(a, b + 1):
        if 1 <= i <= len(ls):
            print(f"{i:>5}| {ls[i - 1]}")


def hits(tag, relpath, pattern, radius=5, limit=12):
    import re
    hr(f"{tag} :: /{pattern}/ в {relpath}")
    ls = src(relpath)
    if ls is None:
        print("!! НЕТ ФАЙЛА:", relpath)
        return
    rx = re.compile(pattern)
    n = 0
    for i, ln in enumerate(ls, 1):
        if rx.search(ln):
            lo, hi = max(1, i - radius), min(len(ls), i + radius)
            print("-" * 60)
            for j in range(lo, hi + 1):
                mark = ">>" if j == i else "  "
                print(f"{mark}{j:>4}| {ls[j - 1]}")
            n += 1
            if n >= limit:
                print("(лимит)")
                return


def grep_all(tag, pattern, dirs=("backend/app", "backend/main.py"), limit=40):
    import re
    hr(f"{tag} :: /{pattern}/")
    rx = re.compile(pattern)
    n = 0
    for d in dirs:
        p = ROOT / d
        files = [p] if p.is_file() else sorted(p.rglob("*.py")) if p.exists() else []
        for f in files:
            rp = str(f.relative_to(ROOT))
            try:
                ls = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            for i, ln in enumerate(ls, 1):
                if rx.search(ln):
                    print(f"{rp}:{i}| {ln.rstrip()}")
                    n += 1
                    if n >= limit:
                        print("(лимит)")
                        return
    if n == 0:
        print("(пусто)")


# N17: дублированный ключ mvp_health
show("R3-A1 /health", "backend/app/api/routes.py", 268, 300)

# N13: пять хардкодов localhost:8000 в LLM-вкладке
hits("R3-B1", "frontend/settings_screen.py", r"http://localhost:8000", radius=4)
grep_all("R3-B2 кто вычисляет BACKEND_URL", r"_BACKEND_URL\s*=", dirs=("game_launcher.py",))

# N14: сетка вкладок на 3 кнопки при четырёх + Apply зовёт не то
show("R3-C1 сетка вкладок", "frontend/settings_screen.py", 138, 168)
hits("R3-C2 обработчики Apply", "frontend/settings_screen.py", r"_apply_\w+", radius=2, limit=15)
hits("R3-C3 списки вкладок", "frontend/settings_screen.py", r"TABS?\s*=|tab_names|вкладок", radius=3, limit=6)

# N12: ремап клавиш пишется, но не читается
hits("R3-D1 запись биндов", "frontend/settings_screen.py", r"keybinds|_rebind_key|json\.dump", radius=3, limit=10)
hits("R3-D2 чтение биндов игрой", "frontend/game_screen.py", r"dialogue_open|keybinds", radius=3, limit=8)
show("R3-D3 захардоженный ввод WASD", "frontend/game_screen.py", 650, 680)
show("R3-D4 клавиши journal/pause/console", "frontend/game_screen.py", 760, 800)

# N16: reload_content_policy никем не вызывается
grep_all("R3-E1 reload_content_policy все упоминания", r"reload_content_policy")

# N6/7/8: TODO-кладбище оркестратора
show("R3-F1 TODO-блоки тика", "backend/app/services/tick_orchestrator.py", 832, 875)

# N9: меметический калькулятор
show("R3-G1 integration TODO", "backend/app/services/phases/integration.py", 420, 452)

# N10: Shadow Causality в никуда
show("R3-H1 проекция мира", "backend/app/services/scene_state_manager.py", 1583, 1615)
grep_all("R3-H2 потребители WorldProjectionEvent", r"WorldProjectionEvent|shared_context.*projection", limit=20)

# Подтверждение мёртвости N6/7/8 модулей
grep_all("R3-I1 импорты экономики", r"trade_resolver|MarketState\b|transaction_engine|traveller\b", limit=20)
grep_all("R3-I2 импорты front/profession", r"front_applicator|front_engine|role_transition", limit=20)

hr("КОНЕЦ ПРОБЫ R3")