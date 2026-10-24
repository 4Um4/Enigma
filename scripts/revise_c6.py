"""GC-01 Block 68 — Revise c6 contract: absolute stability -> identity+location.

Justification (ADR citations):
- ADR-O-377 (ACTIVE) rule 3: "деградация без интеллекта — отсутствие LLM-ответа
  не останавливает быстрые следствия" — npc movement during degraded player
  turn is architecturally MANDATED, not a bug.
- ADR-O-407 Status: "реализация — отдельная сессия" — time gate NOT yet
  implemented by design; premature gate broke d2 (world_snapshot dependency).
- ADR-O-201: movement only via MovementEngine (E10 teleport check, E18
  boundary traversal) — the assertable anti-teleport invariants are
  identity stability + location stability.
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

p = ROOT / "backend/tests/gameplay/test_negative_paths.py"
src = p.read_text(encoding="utf-8")

# 1. Module docstring line
old1 = "  npc_positions стабильны (REST не тик и не телепортирует).\n"
new1 = "  npc_positions: identity+location инварианты (ADR-O-201/377; см. c6).\n"
if old1 in src:
    src = src.replace(old1, new1, 1)
    ok("c6-docstring-module", "updated")
else:
    warn("c6-docstring-module", "not found")

# 2. Class docstring line (updated in Block 64, now stale re D2)
old2 = (
    "    Контракты проверяются напрямую; xfail-маркеры сняты (Блок №58).\n"
    "    D1/D2 fixed в Блоке №64 (game_loop.py:1930 guard + npc_tick_pipeline gate).\n"
)
new2 = (
    "    Контракты проверяются напрямую; xfail-маркеры сняты (Блок №58).\n"
    "    D1 fixed в Блоке №64 (game_loop.py:1930 guard). D2: абсолютная\n"
    "    стабильность позиций противоречила ADR-O-377 (3) — c6 ревизован\n"
    "    на identity+location инварианты (Блок №68), гейты откатаны.\n"
)
if old2 in src:
    src = src.replace(old2, new2, 1)
    ok("c6-docstring-class", "updated")
else:
    warn("c6-docstring-class", "not found")

# 3. c6 docstring
old3 = '        """REST не тик и не телепортирует: npc_positions стабильны."""\n'
new3 = '''        """REST не телепортирует: identity + location инварианты NPC.

        ADR-O-377 (3): LLM-деградация не останавливает быстрые следствия —
        npc_positions МОГУТ меняться в ходе player_action (исполнение
        запланированных задач, traversal interpolation). Абсолютная
        стабильность — ошибочное ожидание (снято в Блоке №68).

        Инварианты (ADR-O-201):
          1. Identity: множество NPC стабильно (спавн/деспавн вне
             initialize_scene запрещён).
          2. Location: ни один NPC не меняет location_id за один ход
             (межлокационный переход требует boundary traversal, E18).
        Внутрилокационные смены graph-узла легальны (movement engine —
        единственный writer позиций, MotionPlan + E10 teleport check).
        """
'''
if old3 in src:
    src = src.replace(old3, new3, 1)
    ok("c6-docstring-test", "updated")
else:
    warn("c6-docstring-test", "not found")

# 4. c6 assertion — replace absolute equality with two invariants
old4 = """            assert before == after, (
                f"positions changed: before={before}, after={after}"
            )
"""
new4 = """            # Инвариант 1: identity (ADR-O-201 — спавн/деспавн вне
            # initialize_scene запрещён)
            assert set(before.keys()) == set(after.keys()), (
                f"npc identity changed: before={sorted(before.keys())}, "
                f"after={sorted(after.keys())}"
            )
            # Инвариант 2: location (ADR-O-201 E18 — межлокационный переход
            # требует boundary traversal, не мгновенный телепорт)
            _teleported = {
                nid: (before[nid].get("location_id"), after[nid].get("location_id"))
                for nid in before
                if before[nid].get("location_id") != after[nid].get("location_id")
            }
            assert not _teleported, (
                f"cross-location teleport detected: {_teleported}"
            )
"""
if old4 in src:
    src = src.replace(old4, new4, 1)
    ok("c6-assert", "replaced with identity+location invariants")
else:
    warn("c6-assert", "not found")

p.write_text(src, encoding="utf-8")
print()
for name, status, msg in results:
    print(f"  [{status:4}] {name}: {msg}")
sys.exit(0)