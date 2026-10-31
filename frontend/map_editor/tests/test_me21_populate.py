"""ME-2.1 Step A: Migration completeness test.

Verifies all OBJECT_PRESETS types are extracted to Blueprint JSON
without data loss. Each field is compared against the original preset.
"""

import ast
import json
import sys
from pathlib import Path

frontend_root = Path(__file__).resolve().parents[2]
map_editor_root = frontend_root / "map_editor"
for p in [str(frontend_root), str(map_editor_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Parse OBJECT_PRESETS from source (no pygame import needed)
dm_source = (map_editor_root / "data_manager.py").read_text(encoding="utf-8")
tree = ast.parse(dm_source)
ORIGINAL_PRESETS = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "OBJECT_PRESETS":
                ORIGINAL_PRESETS = ast.literal_eval(node.value)
                break
    if ORIGINAL_PRESETS is not None:
        break

BLUEPRINTS_DIR = frontend_root / "map_editor" / "assets" / "catalogs" / "base" / "blueprints"


def _load_blueprint(type_name):
    path = BLUEPRINTS_DIR / f"{type_name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class TestMigrationCompleteness:
    """Every OBJECT_PRESETS type must have a corresponding Blueprint JSON."""

    def test_all_types_extracted(self):
        """All 30 types from OBJECT_PRESETS have Blueprint JSON files."""
        for type_name in ORIGINAL_PRESETS:
            bp = _load_blueprint(type_name)
            assert bp is not None, f"Missing blueprint: {type_name}.json"

    def test_blueprint_count_matches(self):
        """Number of Blueprint files == number of OBJECT_PRESETS types."""
        bp_files = list(BLUEPRINTS_DIR.glob("*.json"))
        assert len(bp_files) == len(ORIGINAL_PRESETS), (
            f"Blueprint count {len(bp_files)} != preset count {len(ORIGINAL_PRESETS)}"
        )


class TestFieldPreservation:
    """Every field from OBJECT_PRESETS must be preserved in Blueprint JSON."""

    def test_label_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            assert bp["metadata"]["label"] == preset["label"], f"{type_name}: label mismatch"

    def test_icon_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            assert bp["metadata"]["icon"] == preset.get("icon", ""), f"{type_name}: icon mismatch"

    def test_passability_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            orig_pass = preset["passability"]
            bp_pass = bp["physics"]["passability"]
            for key in ("walk", "jump_over", "crawl_under", "climb_on", "walk_around"):
                assert bp_pass[key] == orig_pass[key], (
                    f"{type_name}: passability.{key} mismatch: {bp_pass[key]} != {orig_pass[key]}"
                )

    def test_cover_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            assert bp["physics"]["cover"] == preset["cover"], f"{type_name}: cover mismatch"

    def test_height_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            assert bp["physics"]["height"] == preset["height"], f"{type_name}: height mismatch"

    def test_color_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            assert bp["appearance"]["color"] == preset["color"], f"{type_name}: color mismatch"

    def test_default_size_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            orig_size = preset.get("default_size", {})
            bp_size = bp["metadata"]["default_size"]
            assert bp_size == orig_size, f"{type_name}: default_size mismatch: {bp_size} != {orig_size}"

    def test_sprite_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            orig_sprite = preset.get("sprite")
            bp_sprite = bp["appearance"]["sprite"]
            if orig_sprite is None:
                assert bp_sprite is None, f"{type_name}: sprite should be null"
            else:
                assert bp_sprite == list(orig_sprite), (
                    f"{type_name}: sprite mismatch: {bp_sprite} != {list(orig_sprite)}"
                )

    def test_default_properties_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            orig_props = preset.get("default_properties", {})
            bp_props = bp["metadata"]["default_properties"]
            assert bp_props == orig_props, f"{type_name}: default_properties mismatch: {bp_props} != {orig_props}"

    def test_rotation_mode_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            assert bp["geometry"]["rotation_mode"] == preset.get("rotation_mode", "free"), (
                f"{type_name}: rotation_mode mismatch"
            )

    def test_requires_wall_preserved(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            orig_rw = preset.get("requires_wall", False)
            bp_rw = bp["geometry"].get("requires_wall", False)
            assert bp_rw == orig_rw, f"{type_name}: requires_wall mismatch: {bp_rw} != {orig_rw}"

    def test_durability_in_physics(self):
        """durability from default_properties also in physics.durability."""
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            orig_props = preset.get("default_properties", {})
            if "durability" in orig_props:
                assert bp["physics"].get("durability") == orig_props["durability"], (
                    f"{type_name}: physics.durability mismatch"
                )


class TestBlueprintStructure:
    """Blueprint JSON files must have valid structure."""

    def test_required_fields(self):
        for type_name in ORIGINAL_PRESETS:
            bp = _load_blueprint(type_name)
            for field in ("blueprint_id", "version", "compat", "type"):
                assert field in bp, f"{type_name}: missing required field {field}"
            assert bp["blueprint_id"] == type_name, f"{type_name}: blueprint_id mismatch"
            assert bp["version"] == 1, f"{type_name}: version != 1"
            assert bp["compat"] == 1, f"{type_name}: compat != 1"

    def test_six_layers_present(self):
        for type_name in ORIGINAL_PRESETS:
            bp = _load_blueprint(type_name)
            for layer in ("geometry", "appearance", "physics", "function", "semantics"):
                assert layer in bp, f"{type_name}: missing layer {layer}"

    def test_geometry_size_has_3d(self):
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            size = bp["geometry"]["size"]
            assert "w" in size and "h" in size and "d" in size, f"{type_name}: geometry.size missing w/h/d"
            assert size["d"] == preset["height"], f"{type_name}: size.d != height"

    def test_tags_present(self):
        for type_name in ORIGINAL_PRESETS:
            bp = _load_blueprint(type_name)
            assert "tags" in bp and isinstance(bp["tags"], list), f"{type_name}: tags missing or not list"
            assert len(bp["tags"]) > 0, f"{type_name}: tags empty"

    def test_category_present(self):
        for type_name in ORIGINAL_PRESETS:
            bp = _load_blueprint(type_name)
            assert "category" in bp and isinstance(bp["category"], str), f"{type_name}: category missing"

    def test_metadata_present(self):
        for type_name in ORIGINAL_PRESETS:
            bp = _load_blueprint(type_name)
            assert "metadata" in bp, f"{type_name}: metadata missing"
            for field in ("label", "icon", "default_properties", "default_size"):
                assert field in bp["metadata"], f"{type_name}: metadata.{field} missing"

    def test_function_components_empty(self):
        """function.components is empty list (no unproven projection)."""
        for type_name in ORIGINAL_PRESETS:
            bp = _load_blueprint(type_name)
            assert bp["function"]["components"] == [], f"{type_name}: function.components should be empty"


class TestSpriteValidity:
    """Sprite references must point to existing files."""

    def test_sprite_files_exist(self):
        pixels_dir = frontend_root / "map_editor" / "pixels"
        for type_name, preset in ORIGINAL_PRESETS.items():
            bp = _load_blueprint(type_name)
            sprite = bp["appearance"]["sprite"]
            if sprite is None:
                continue  # fallback sprite, skip
            sheet_key = sprite[0]
            path_png = pixels_dir / f"{sheet_key}.png"
            path_noext = pixels_dir / sheet_key
            assert path_png.exists() or path_noext.exists(), f"{type_name}: sprite file not found: {sheet_key}"
