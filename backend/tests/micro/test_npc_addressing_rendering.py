"""
path: /project/backend/tests/micro/test_npc_addressing_rendering.py
Назначение: C3-A2-UI-1 regression — rendering NPC addressing indicators.
    Source-inspection + structural tests for draw_addressing_indicators.
Зависимости: frontend.focus_renderer, frontend.game_screen
Основные сущности: тесты battery 1-8
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _read_focus_renderer_source() -> str:
    test_dir = Path(__file__).resolve().parent
    fr_path = test_dir.parent.parent.parent / "frontend" / "focus_renderer.py"
    if not fr_path.exists():
        pytest.skip("focus_renderer.py not found")
    return fr_path.read_text(encoding="utf-8-sig")


def _read_game_screen_source() -> str:
    test_dir = Path(__file__).resolve().parent
    gs_path = test_dir.parent.parent.parent / "frontend" / "game_screen.py"
    if not gs_path.exists():
        pytest.skip("game_screen.py not found")
    return gs_path.read_text(encoding="utf-8-sig")


def test_1_draw_addressing_indicators_exists():
    src = _read_focus_renderer_source()
    assert "def draw_addressing_indicators" in src


def test_1b_draw_addressing_indicators_called_in_game_screen():
    src = _read_game_screen_source()
    assert "draw_addressing_indicators(" in src


def test_2_method_accepts_npc_coords_and_indicators():
    src = _read_focus_renderer_source()
    assert "npc_coords" in src and "addressing_indicators" in src


def test_3_iterates_npc_coords():
    src = _read_focus_renderer_source()
    idx = src.index("def draw_addressing_indicators")
    method_end = src.index("def ", idx + 10)
    method_src = src[idx:method_end]
    assert "for" in method_src and "npc_coords" in method_src


def test_4_multiple_events_per_npc():
    src = _read_focus_renderer_source()
    idx = src.index("def draw_addressing_indicators")
    method_end = src.index("def ", idx + 10)
    method_src = src[idx:method_end]
    assert "setdefault" in method_src or "append" in method_src


def test_5_dedup_by_event_id():
    src = _read_game_screen_source()
    assert "_addr_eid not in self.npc_addressing_indicators" in src


def test_6_missing_npc_no_data_loss():
    src = _read_focus_renderer_source()
    idx = src.index("def draw_addressing_indicators")
    method_end = src.index("def ", idx + 10)
    method_src = src[idx:method_end]
    assert "del " not in method_src and ".pop(" not in method_src and ".clear()" not in method_src
    assert "continue" in method_src


def test_7_separate_from_manifestations():
    src = _read_focus_renderer_source()
    assert "def draw_manifestations" in src
    assert "def draw_addressing_indicators" in src
    manif_idx = src.index("def draw_manifestations")
    manif_end = src.index("def ", manif_idx + 10)
    manif_src = src[manif_idx:manif_end]
    assert "addressing_indicators" not in manif_src


def test_8_existing_methods_intact():
    src = _read_focus_renderer_source()
    assert "def draw_manifestations" in src
    assert "def draw_action_markers" in src
    assert "def draw_bubbles" in src
    assert src.count("def draw_") >= 3


def test_8b_game_screen_calls_all_three():
    src = _read_game_screen_source()
    assert "draw_manifestations(" in src
    assert "draw_addressing_indicators(" in src
    assert "draw_action_markers(" in src