"""Tests for ТЗ-6 Cleanup.

Запуск: cd backend; python -m pytest tests/test_tz6_cleanup.py -v; cd ..
"""
import pytest
from pathlib import Path
from importlib import import_module

# parents[1] = backend/
BACKEND_ROOT = Path(__file__).resolve().parents[1]
# parents[2] = корень проекта
PROJECT_ROOT = Path(__file__).resolve().parents[2]

class TestPatchA_DeadCode:
    # test_world_sim_agent_removed удалён, так как модуль жив (TЗ-6 некорректно посчитал его мёртвым)
    
    def test_parser_removed(self):
        assert not (BACKEND_ROOT / "app" / "services" / "llm" / "parser.py").exists()
        
    def test_npc_response_validator_removed(self):
        assert not (BACKEND_ROOT / "app" / "services" / "verbalization" / "npc_response_validator.py").exists()

    def test_no_dead_methods(self):
        from app.services.verbalization.dm_contract_builder import DMContractBuilder
        assert not hasattr(DMContractBuilder, "add_npc_author_notes")

class TestPatchB_ProductionHygiene:
    def test_no_print_in_movement_engine(self):
        path = BACKEND_ROOT / "app" / "services" / "spatial" / "movement_engine.py"
        source = path.read_text(encoding="utf-8-sig")
        lines = [l for l in source.split('\n') if 'print(' in l and not l.strip().startswith('#')]
        assert len(lines) == 0, f"print() found in movement_engine: {lines}"

    def test_willstate_single_definition(self):
        path = BACKEND_ROOT / "app" / "models" / "will.py"
        source = path.read_text(encoding="utf-8-sig")
        assert "class WillState" not in source or "from app.models.npc_state import WillState" in source, \
            "WillState still duplicated (B9 not applied)"

    def test_compute_continuous_drift_returns_list(self):
        from app.services.npc.break_progress_engine import compute_continuous_drift
        import inspect
        source = inspect.getsource(compute_continuous_drift)
        assert "return {}" not in source, "compute_continuous_drift still returns dict"

    def test_no_silent_failures_in_tick_orchestrator(self):
        path = BACKEND_ROOT / "app" / "services" / "tick_orchestrator.py"
        source = path.read_text(encoding="utf-8-sig")
        assert "except Exception:\n                    pass" not in source, "Silent failure found"

class TestPatchC_Constants:
    def test_constants_has_spatial(self):
        path = BACKEND_ROOT / "app" / "core" / "constants.py"
        source = path.read_text(encoding="utf-8-sig")
        assert "VISIBILITY_RADIUS_M" in source
        assert "LOS_THRESHOLD" in source
        
    def test_constants_has_dm_messages(self):
        path = BACKEND_ROOT / "app" / "core" / "constants.py"
        source = path.read_text(encoding="utf-8-sig")
        assert "MSG_MAX_REPLIES" in source
        assert "MSG_NOTHING_HAPPENED" in source

    def test_i18n_has_menu_keys(self):
        path = PROJECT_ROOT / "frontend" / "i18n.py"
        source = path.read_text(encoding="utf-8-sig")
        assert "ui:menu_new_game" in source
        assert "ui:menu_exit" in source