from __future__ import annotations

# backend/tests/micro/test_det2_state_checksum.py
"""
path: backend/tests/micro/test_det2_state_checksum.py
Назначение: DET-2 (§17.8; вердикт Мастера — четыре обязательных теста):
детект изменения, эквивалентность порядка вставки, стабильность дайджеста
между процессами с разными PYTHONHASHSEED, фактическое исполнение probe
на каждом тике (счётчик _state_hash_ticks на production-пути).
Зависимости: pytest, subprocess, json, hashlib; app-прод-путь (idle_tick).
Основные сущности: test_det2_*.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.tick_orchestrator import TickOrchestrator  # noqa: E402


def _digest(v) -> str:
    return TickOrchestrator._DET2_DIGEST_PUBLIC(v)


def _snapshot(seed: str) -> dict:
    return {"npcs": [{"id": f"npc-{seed}", "psyche": {"stress": 1.5}, "tags": ["a", "b"]}]}


def test_det2_field_change_changes_digest():
    """Тест 1 (вердикт): изменение одного поля состояния меняет дайджест."""
    before = _digest(_snapshot("x"))
    changed = _snapshot("x")
    changed["npcs"][0]["psyche"]["stress"] = 9.9
    assert _digest(changed) != before


def test_det2_key_insertion_order_equivalence():
    """Тест 2 (вердикт): эквивалентные структуры с разным порядком вставки
    ключей дают одинаковый дайджест (замок sort_keys)."""
    a = {"npcs": {"x": 1, "y": 2}, "meta": {"p": 1.5, "q": None}}
    b = {}
    for k in reversed(list(a.keys())):
        b[k] = a[k]
    bb = {}
    for k in ["meta", "npcs"]:
        bb[k] = a[k]
    assert _digest(a) == _digest(b) == _digest(bb)
    # вложенный порядок тоже не влияет
    c = {"y": 2, "x": 1}
    d = {"x": 1, "y": 2}
    assert _digest(c) == _digest(d)


def test_det2_stable_across_processes_and_hashseed():
    """Тест 3 (вердикт): одинаковый логический снимок — одинаковый дайджест
    в отдельных процессах с РАЗНЫМИ PYTHONHASHSEED (builtin hash() это
    не проходит; sha256 — да)."""
    payload = json.dumps(_snapshot("stable"))
    code = (
        "import sys, json, hashlib;"
        "sys.path.insert(0, r'%s');"
        "from app.services.tick_orchestrator import TickOrchestrator as T;"
        "print(T._DET2_DIGEST_PUBLIC(json.loads(%r)))"
        % (str(Path(__file__).resolve().parents[2]), payload)
    )
    digests = []
    for seed in ("0", "12345", "999"):
        env = {"PYTHONHASHSEED": seed, "PATH": "", "SYSTEMROOT": ""}
        import os

        env = {**os.environ, "PYTHONHASHSEED": seed}
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, env=env
        )
        assert proc.returncode == 0, proc.stderr[-500:]
        digests.append(proc.stdout.strip())
    assert digests[0] == digests[1] == digests[2], digests


def test_det2_probe_runs_every_tick_on_production_path():
    """Тест 4 (вердикт): probe ФАКТИЧЕСКИ исполняется на каждом тике —
    счётчик _state_hash_ticks растёт на каждый idle_tick (свидетельство
    1/1 для закрытия DET-2; артефакт живого прогона)."""
    from app.core.config import settings
    from app.services.game_loop_builder import build_game_loop

    loop = build_game_loop(Path(settings.data_dir))
    orch = loop._tick_orch  # game_loop.py:193 — единственный инстанс TickOrchestrator
    before = getattr(orch, "_state_hash_ticks", 0)
    loop.idle_tick("tavern_silver_wolf")
    loop.idle_tick("tavern_silver_wolf")
    after = getattr(orch, "_state_hash_ticks", 0)
    assert after - before == 2, f"probe не на каждом тике: {before}->{after}"