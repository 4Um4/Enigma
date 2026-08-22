"""
path: backend/tests/calibration_lab/test_m0_materializer.py
Назначение: M0-5a — приёмочные тесты материализатора: редирект+патч+restore
    на РЕАЛЬНОМ config/npc (maid_lusya/guard_borko из кампании Open_road),
    приоритет точечного оверрайда над wildcard, замена drives целиком,
    громкие отказы (нет root / неизвестный NPC / вложенность), обратный
    скан late-биндингов, restore при исключении в теле.
Зависимости: pytest, app.services.calibration.preset_io,
    app.services.calibration.preset_materializer, app.services.npc.npc_loader.
Основные сущности: TestMaterializePreset.

Запуск: cd backend; python -m pytest tests/calibration_lab/ -q --tb=line; cd ..
"""
import sys
import types
from pathlib import Path

import pytest

from app.services.calibration.preset_io import NpcOverride, Preset, load_preset
from app.services.calibration.preset_materializer import (
    MaterializationError,
    materialize_preset,
)
from app.services.npc import npc_loader
from app.services.npc.npc_loader import load_npcs_merged

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRESETS_DIR = _REPO_ROOT / "config" / "calibration" / "test_presets"


def _golden() -> Preset:
    return load_preset(_PRESETS_DIR / "enigma_golden.yaml")


def _find(npcs: list, npc_id: str) -> dict:
    return next(n for n in npcs if n.get("id") == npc_id)


class TestMaterializePreset:
    def test_redirect_patch_and_restore_with_real_config(self) -> None:
        original_root = npc_loader._CONFIG_NPC_ROOT
        with materialize_preset(_golden()) as mat:
            assert npc_loader._CONFIG_NPC_ROOT == mat.temp_root
            npcs = load_npcs_merged()
            assert npcs, "загрузчик вернул пустой список"
            lusya = _find(npcs, "maid_lusya")
            assert lusya["psyche"]["identity_rigidity"] == 0.42
            assert "maid_lusya" in mat.patched_npc_ids
            assert mat.files_patched >= 1
            temp_root = mat.temp_root
        assert npc_loader._CONFIG_NPC_ROOT == original_root
        assert not temp_root.exists()

    def test_specific_npc_overrides_wildcard(self) -> None:
        preset = Preset(
            preset_id="spec",
            npc_overrides={
                "*": NpcOverride(psyche={"identity_rigidity": 0.5}),
                "maid_lusya": NpcOverride(psyche={"identity_rigidity": 0.9}),
            },
        )
        with materialize_preset(preset):
            npcs = load_npcs_merged()
            assert _find(npcs, "maid_lusya")["psyche"]["identity_rigidity"] == 0.9
            assert _find(npcs, "guard_borko")["psyche"]["identity_rigidity"] == 0.5

    def test_drives_replaced_whole(self) -> None:
        drives = {"control": 0.25, "significance": 0.25, "fear": 0.25, "desire": 0.25}
        preset = Preset(
            preset_id="drv", npc_overrides={"*": NpcOverride(drives=drives)}
        )
        with materialize_preset(preset):
            npcs = load_npcs_merged()
            assert _find(npcs, "maid_lusya")["drives"] == drives

    def test_constants_only_preset_still_redirects(self) -> None:
        original_root = npc_loader._CONFIG_NPC_ROOT
        preset = Preset(preset_id="const", constants={"THETA_UP": 0.55})
        with materialize_preset(preset) as mat:
            assert npc_loader._CONFIG_NPC_ROOT == mat.temp_root
            assert load_npcs_merged()
            assert mat.patched_npc_ids == ()
        assert npc_loader._CONFIG_NPC_ROOT == original_root

    def test_restore_on_body_exception(self) -> None:
        original_root = npc_loader._CONFIG_NPC_ROOT
        with pytest.raises(RuntimeError, match="boom"):
            with materialize_preset(_golden()):
                raise RuntimeError("boom")
        assert npc_loader._CONFIG_NPC_ROOT == original_root

    def test_nested_materialization_forbidden(self) -> None:
        with pytest.raises(MaterializationError, match="Вложенная"):
            with materialize_preset(_golden()):
                with materialize_preset(_golden()):
                    pass

    def test_missing_base_root_loud_fail(self, tmp_path: Path) -> None:
        with pytest.raises(MaterializationError, match="config/npc не найден"):
            with materialize_preset(_golden(), base_npc_root=tmp_path / "missing"):
                pass

    def test_unknown_npc_in_overrides_loud_fail(self) -> None:
        preset = Preset(
            preset_id="ghost",
            npc_overrides={
                "npc_ghost": NpcOverride(psyche={"identity_rigidity": 0.5})
            },
        )
        with pytest.raises(MaterializationError, match="npc_ghost"):
            with materialize_preset(preset):
                pass

    def test_restore_fixes_late_importer_bindings(self) -> None:
        """Модуль, связавший temp-корень ВО ВРЕМЯ эксперимента (from-import
        читает уже патченный атрибут), восстанавливается обратным сканом."""
        original_root = npc_loader._CONFIG_NPC_ROOT
        late = types.ModuleType("calib_test_late_binding")
        sys.modules["calib_test_late_binding"] = late
        try:
            with materialize_preset(_golden()) as mat:
                late.ROOT = mat.temp_root
            assert late.ROOT is original_root
        finally:
            sys.modules.pop("calib_test_late_binding", None)