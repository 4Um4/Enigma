"""
path: backend/tests/test_tz4_spatial_authority.py
Назначение: Интеграционные тесты ТЗ-04 (Spatial Authority & Physics Repair).
Проверяют, что зомби-ридеры удалены, мёртвый код вырезан, и мутации идут через SceneChange.
Зависимости: pytest, pathlib
Основные сущности: TestPatchA_ZombieReaders, TestPatchA_Removals, TestPatchB_NoSilentFailure, TestPatchB_SpatialFactory

Запуск: cd backend; python -m pytest tests/test_tz4_spatial_authority.py -v; cd ..
"""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "app"
FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"


class TestPatchA_ZombieReaders:
    """A1-A3: zombie readers → SpatialQueryService."""

    def test_no_player_distances_in_combat_subscriber(self):
        path = BACKEND_ROOT / "services" / "combat" / "combat_subscriber.py"
        source = path.read_text(encoding="utf-8")
        assert 'scene_state.get("player_distances"' not in source, "zombie reader in combat_subscriber (A1 not applied)"

    def test_no_player_distances_in_r3_direct_builder(self):
        path = BACKEND_ROOT / "services" / "scene" / "r3_direct_builder.py"
        source = path.read_text(encoding="utf-8")
        assert 'scene_state.get("player_distances"' not in source, "zombie reader in r3_direct_builder (A2 not applied)"

    def test_no_player_distances_in_world_state(self):
        path = BACKEND_ROOT / "services" / "simulation" / "world_state.py"
        source = path.read_text(encoding="utf-8")
        assert '"player_distances":' not in source, "zombie reader in world_state (A3 not applied)"


class TestPatchA_RNGIsolation:
    """A4: RNG → KernelRNG in physics layer."""

    def test_no_random_uniform_in_apply_change(self):
        path = BACKEND_ROOT / "services" / "scene_state_manager.py"
        source = path.read_text(encoding="utf-8")
        # Извлекаем метод apply_change
        start = source.find("def apply_change(")
        end = source.find("def apply_changes(", start)
        apply_change_src = source[start:end]
        assert "random.uniform(" not in apply_change_src, "random.uniform() call found in apply_change (A4 not applied)"


class TestPatchA_Removals:
    """A5-A6: dead modules removed."""

    def test_transit_tracker_removed(self):
        path = BACKEND_ROOT / "services" / "spatial" / "transit_tracker.py"
        assert not path.exists(), "transit_tracker.py should be removed (A5)"

    def test_location_graph_removed(self):
        path = BACKEND_ROOT / "services" / "spatial" / "location_graph.py"
        assert not path.exists(), "location_graph.py should be removed (A5)"


class TestPatchB_NoSilentFailure:
    """B1: Spatial Oracle no-silent-failure."""

    def test_no_silent_pass_in_bridge(self):
        path = FRONTEND_ROOT / "game_loop_bridge.py"
        source = path.read_text(encoding="utf-8")
        assert "except Exception:\n pass" not in source, "Silent pass in game_loop_bridge (B1 not applied)"


class TestPatchB_SpatialFactory:
    """B3: single SpatialService entry."""

    def test_spatial_factory_exists(self):
        path = BACKEND_ROOT / "services" / "spatial" / "spatial_factory.py"
        assert path.exists(), "spatial_factory.py should exist (B3)"

    def test_no_direct_build_in_orchestration(self):
        path = BACKEND_ROOT / "services" / "game_loop" / "npc_orchestration.py"
        source = path.read_text(encoding="utf-8")
        assert "SpatialService.build_for_location" not in source, "Direct build in npc_orchestration (B3 not applied)"

    def test_no_direct_build_in_tick_orchestrator(self):
        path = BACKEND_ROOT / "services" / "tick_orchestrator.py"
        source = path.read_text(encoding="utf-8")
        assert "SpatialService.build_for_location" not in source, "Direct build in tick_orchestrator (B3 not applied)"


class TestPatchB_SceneChangeRouting:
    """B4-B5: mutations → SceneChange."""

    def test_no_direct_activity_mutation_in_orchestration(self):
        path = BACKEND_ROOT / "services" / "game_loop" / "npc_orchestration.py"
        source = path.read_text(encoding="utf-8")
        assert 'scene_state["npc_positions"][_nid]["activity"]' not in source, (
            "Direct activity mutation in npc_orchestration (B4 not applied)"
        )

    def test_no_direct_los_mutation_in_dm_phase(self):
        path = BACKEND_ROOT / "services" / "game_loop" / "dm_phase.py"
        source = path.read_text(encoding="utf-8")
        assert 'scene_state["line_of_sight"]' not in source, "Direct LoS mutation in dm_phase (B5 not applied)"
