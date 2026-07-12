"""Integration tests for ТЗ-03 Frontend ↔ Backend Contract Repair.
Фиксация результатов миграции: single causal authority, no silent failures, canonical DTO.

Запуск: cd backend; python -m pytest tests/test_tz3_contract_repair.py -v --tb=short; cd ..
"""

import sys
from pathlib import Path

# Добавить frontend в path для импорта api_client
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "frontend"))


class TestPatchA1_GameActionResponse:
    """A1: GameActionResponse expansion."""

    def test_scene_state_field_exists(self):
        from api_client import GameActionResponse

        response = GameActionResponse(
            dm_response="test",
            npc_reactions=[],
            world_changes=[],
            journal_entry_id=None,
            scene_state={"test": True},
            metadata={"meta": True},
        )
        assert response.scene_state == {"test": True}
        assert response.metadata == {"meta": True}


class TestPatchA2_WorldSnapshotDTO:
    """A2: npc_positions Dict canonicalization."""

    def test_npc_positions_is_dict(self):
        import typing

        from app.domain.snapshot import WorldSnapshotDTO

        hints = typing.get_type_hints(WorldSnapshotDTO)
        assert hints["npc_positions"].__origin__ == dict, "npc_positions must be Dict"

    def test_no_snapshot_npc_positions_to_dict(self):
        from app.domain import snapshot

        assert not hasattr(snapshot, "snapshot_npc_positions_to_dict"), (
            "snapshot_npc_positions_to_dict should be removed (A2-FIX)"
        )


class TestPatchA3_CueNormalization:
    """A3: cue_type → cue_key."""

    def test_peripheral_cue_dto_uses_cue_key(self):
        from app.domain.snapshot import PeripheralCueDTO

        cue = PeripheralCueDTO(npc_id="test", cue_key="FREEZE", hover_text="Замер")
        assert cue.cue_key == "FREEZE"

        from dataclasses import asdict

        d = asdict(cue)
        assert "cue_key" in d
        assert "cue_type" not in d


class TestPatchB1_FrontendAuthority:
    """B1: frontend = renderer, never state generator."""

    def test_no_game_time_mutation(self):
        import ast

        screen_path = Path(__file__).resolve().parents[2] / "frontend" / "game_screen.py"
        # utf-8-sig съедает BOM (U+FEFF), который ломает ast.parse
        source = screen_path.read_text(encoding="utf-8-sig")

        # Парсим AST, чтобы игнорировать комментарии и строки
        tree = ast.parse(source)
        mutations = []

        for node in ast.walk(tree):
            # Ищем AugAssign (+=, -=, и т.д.), где target является self.game_time_seconds
            if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
                if (
                    isinstance(node.target, ast.Attribute)
                    and isinstance(node.target.value, ast.Name)
                    and node.target.value.id == "self"
                    and node.target.attr == "game_time_seconds"
                ):
                    mutations.append(node.lineno)

        assert len(mutations) == 0, f"game_time_seconds mutation (+=) found in game_screen at lines: {mutations}"

    def test_no_avatar_state_override(self):
        screen_path = Path(__file__).resolve().parents[2] / "frontend" / "game_screen.py"
        source = screen_path.read_text(encoding="utf-8")
        assert 'avatar_state"]["perceptual_stability"] =' not in source, (
            "avatar_state override found (B1.2-FIX not applied)"
        )

    def test_no_dialog_journal_append(self):
        screen_path = Path(__file__).resolve().parents[2] / "frontend" / "game_screen.py"
        source = screen_path.read_text(encoding="utf-8")
        assert "dialog_journal.append" not in source, "dialog_journal local append found (B1.3-FIX not applied)"


class TestPatchB2_SpatialOracleNoSilentFailure:
    """B2: Spatial Oracle no-silent-failure."""

    def test_no_silent_pass_in_bridge(self):
        bridge_path = Path(__file__).resolve().parents[2] / "frontend" / "game_loop_bridge.py"
        source = bridge_path.read_text(encoding="utf-8")
        assert "except Exception:\n pass" not in source, "Silent pass found in game_loop_bridge (B2-FIX not applied)"

    def test_logger_warnings_present(self):
        bridge_path = Path(__file__).resolve().parents[2] / "frontend" / "game_loop_bridge.py"
        source = bridge_path.read_text(encoding="utf-8")
        assert "SPATIAL_ORACLE" in source, "SPATIAL_ORACLE logging not found (B2-FIX not applied)"


class TestPatchC1_NoSilentSuppress:
    """C1: no suppress(Exception)."""

    def test_no_suppress_exception_in_game_screen(self):
        screen_path = Path(__file__).resolve().parents[2] / "frontend" / "game_screen.py"
        source = screen_path.read_text(encoding="utf-8")
        # Игнорируем комментарии и initiative_suppression
        lines = [
            l for l in source.splitlines() if "contextlib.suppress(Exception)" in l and not l.strip().startswith("#")
        ]
        assert len(lines) == 0, f"suppress(Exception) found in game_screen: {lines}"


class TestPatchC2_NoDuplication:
    """C2: spatial duplication removed."""

    def test_minimal_registry_has_find_chunks(self):
        sco_path = Path(__file__).resolve().parents[2] / "frontend" / "spatial_compilation_orchestrator.py"
        source = sco_path.read_text(encoding="utf-8")
        assert "def find_chunks" in source, "_MinimalFrontendRegistry.find_chunks not found (C2-FIX not applied)"
