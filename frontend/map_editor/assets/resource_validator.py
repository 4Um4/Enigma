"""ME-2.1 Step D: ResourceValidator — multi-level Blueprint validation.

Validation levels (NOT a single boolean):
- L1 Structural: required fields, types, geometry
- L2 Resource: sprite file exists in pixels/
- L3 Editor compat: type known to OBJECT_PRESETS
- L4 Runtime compat: archetype known to backend FSMs (info only)

Errors block placement. Warnings allow placement but flag issues.
Info is informational only.

Does NOT duplicate SpriteRegistry internal logic — uses file existence check only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from assets.resource_resolver import LegacyDirResolver


@dataclass
class ValidationIssue:
    """Single validation finding."""

    level: str  # "error", "warning", "info"
    category: str  # "structural", "resource", "editor", "runtime"
    message: str
    field: str | None = None


@dataclass
class ValidationResult:
    """Validation result for a single blueprint."""

    blueprint_id: str
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def can_place(self) -> bool:
        """True if no error-level issues (placement allowed)."""
        return not any(i.level == "error" for i in self.issues)

    @property
    def fully_supported(self) -> bool:
        """True if no error AND no warning (fully game-ready)."""
        return not any(i.level in ("error", "warning") for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def infos(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "info"]


class ResourceValidator:
    """Multi-level Blueprint and resource validation."""

    # Known backend archetypes (from test_object_fsms.py / build_world_object)
    # Extension = mini-ADR (same pattern as AffordanceResolver precondition registry)
    _KNOWN_ARCHETYPES = frozenset(
        {
            "door",
            "chair",
            "container",
            "bed",
            "lever",
            "weapon",
        }
    )

    def __init__(
        self,
        pixels_dir: Path | str,
        *,
        resolver: LegacyDirResolver | None = None,
    ) -> None:
        """ME-2.1-H-1: L2 использует единый resolver.resolve().

        Контракт Master §4: единый механизм, без if/else ветки.
        - Если resolver передан — используется он.
        - Если не передан — создаётся LegacyDirResolver(pixels_dir).
        L2 _check_resources всегда вызывает resolve().
        Backward compat: ResourceValidator(pixels_dir) — прежняя семантика.
        """
        self._pixels_dir = Path(pixels_dir)
        self._resolver = resolver if resolver is not None else LegacyDirResolver(self._pixels_dir)

    def validate_blueprint(self, bp_data: dict[str, Any]) -> ValidationResult:
        """Full validation: structural + resource + editor + runtime.

        Args:
            bp_data: Blueprint JSON data dict.

        Returns ValidationResult with all issues found.
        """
        bp_id = str(bp_data.get("blueprint_id", "<unknown>"))
        result = ValidationResult(blueprint_id=bp_id)

        self._check_structural(bp_data, result)
        self._check_resources(bp_data, result)
        self._check_editor_compat(bp_data, result)
        self._check_runtime_compat(bp_data, result)

        return result

    def validate_all(self, asset_store: Any) -> dict[str, ValidationResult]:
        """Validate all blueprints in AssetStore.

        Returns dict of {blueprint_id: ValidationResult}.
        """
        results: dict[str, ValidationResult] = {}
        for bp_id in asset_store.list_blueprints():
            record = asset_store.get_blueprint(bp_id)
            if record and record.data:
                results[bp_id] = self.validate_blueprint(record.data)
        return results

    def _check_structural(self, data: dict, result: ValidationResult) -> None:
        """L1: Required fields and structure."""
        for key in ("blueprint_id", "version", "compat"):
            if key not in data:
                result.issues.append(
                    ValidationIssue(
                        level="error",
                        category="structural",
                        message=f"Missing required field: {key}",
                        field=key,
                    )
                )

        for layer in ("geometry", "appearance", "physics"):
            if layer not in data:
                result.issues.append(
                    ValidationIssue(
                        level="error",
                        category="structural",
                        message=f"Missing layer: {layer}",
                        field=layer,
                    )
                )

        # Geometry size
        geom = data.get("geometry", {})
        size = geom.get("size", {})
        for dim in ("w", "h", "d"):
            val = size.get(dim, 0)
            if not isinstance(val, int | float) or val <= 0:
                result.issues.append(
                    ValidationIssue(
                        level="error",
                        category="structural",
                        message=f"geometry.size.{dim} must be > 0",
                        field=f"geometry.size.{dim}",
                    )
                )

        # Passability
        physics = data.get("physics", {})
        passability = physics.get("passability", {})
        for key in ("walk", "jump_over", "crawl_under", "climb_on", "walk_around"):
            if key not in passability:
                result.issues.append(
                    ValidationIssue(
                        level="error",
                        category="structural",
                        message=f"physics.passability.{key} missing",
                        field=f"physics.passability.{key}",
                    )
                )

    def _check_resources(self, data: dict, result: ValidationResult) -> None:
        """L2: Sprite file exists in pixels/."""
        appearance = data.get("appearance", {})
        sprite = appearance.get("sprite")

        if sprite is None:
            result.issues.append(
                ValidationIssue(
                    level="warning",
                    category="resource",
                    message="No sprite — uses fallback (may not render correctly)",
                    field="appearance.sprite",
                )
            )
            return

        if not isinstance(sprite, list) or len(sprite) not in (3, 7):
            length = len(sprite) if isinstance(sprite, list) else type(sprite).__name__
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Invalid sprite format: expected 3 or 7 elements, got {length}",
                    field="appearance.sprite",
                )
            )
            return

        sheet_key = sprite[0]
        if not isinstance(sheet_key, str) or not sheet_key:
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message="Sprite sheet_key must be non-empty string",
                    field="appearance.sprite[0]",
                )
            )
            return

        # ME-2.1-H-1: единый механизм разрешения через self._resolver.resolve().
        # Backward compat: default resolver = LegacyDirResolver(pixels_dir),
        # что воспроизводит прежнюю семантику (sheet_key.png или sheet_key без ext).
        # R2 (path traversal) и R3 (.png semantic) — внутри resolver.
        path = self._resolver.resolve(sheet_key)
        if path is None:
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Sprite file not found: {sheet_key}",
                    field="appearance.sprite",
                )
            )

    def _check_editor_compat(self, data: dict, result: ValidationResult) -> None:
        """L3: Type known to editor (OBJECT_PRESETS or new)."""
        from data_manager import OBJECT_PRESETS

        bp_type = data.get("type", "")
        if not bp_type:
            result.issues.append(
                ValidationIssue(
                    level="warning",
                    category="editor",
                    message="No type field — type will be inferred from blueprint_id",
                )
            )
        elif bp_type not in OBJECT_PRESETS:
            result.issues.append(
                ValidationIssue(
                    level="warning",
                    category="editor",
                    message=f"Unknown type '{bp_type}' — not in OBJECT_PRESETS (new type)",
                )
            )

    def _check_runtime_compat(self, data: dict, result: ValidationResult) -> None:
        """L4: Runtime archetype known to backend (info only).

        Cannot fully check from frontend — backend FSMs are separate.
        This is informational only, does not block placement.
        """
        bp_type = data.get("type", data.get("blueprint_id", ""))
        if bp_type not in self._KNOWN_ARCHETYPES:
            result.issues.append(
                ValidationIssue(
                    level="info",
                    category="runtime",
                    message=(
                        f"Archetype '{bp_type}' may not have backend FSM — object is decorative only (no game actions)"
                    ),
                )
            )
