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

from assets.resource_formats import MAGIC_BYTES, is_supported_format
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


@dataclass
class ResourceValidationResult:
    """ME-2.1-H-2: Результат валидации самостоятельного ресурса (не Blueprint).

    Используется ResourceValidator.validate_resource() и AssetStore.save_new_resource_atomic().
    """

    path: Path
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def can_register(self) -> bool:
        """True если нет error-level issues."""
        return not any(i.level == "error" for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]


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

    # ===== ME-2.1-H-2: validate_resource (L1-L4 для самостоятельных ресурсов) =====

    def validate_resource(self, image_path: Path) -> "ResourceValidationResult":
        """ME-2.1-H-2: Валидация самостоятельного ресурса (не Blueprint).

        4 уровня (L4 — error, не warning, по решению Master G8):
        - L1 Existence: обычный файл, размер > 0.
        - L2 Format: path.suffix.lower() в SUPPORTED_RESOURCE_FORMATS.
        - L3 Magic: сигнатура содержимого соответствует расширению.
        - L4 Loadable: pygame.image.load() декодирует без ошибки.

        L4 НЕ вызывает pygame.init() или display.set_mode() — pygame.image.load
        работает без них на pygame 2.6.1 (подтверждено тестом).

        Args:
            image_path: путь к файлу изображения.

        Returns:
            ResourceValidationResult с issues (error/warning/info).
        """
        result = ResourceValidationResult(path=Path(image_path))
        self._check_resource_existence(image_path, result)
        # L2-L4 только если файл существует (иначе бессмысленно)
        if not result.errors:
            self._check_resource_format(image_path, result)
        if not result.errors:
            self._check_resource_magic(image_path, result)
        if not result.errors:
            self._check_resource_loadable(image_path, result)
        return result

    def _check_resource_existence(self, image_path: Path, result: "ResourceValidationResult") -> None:
        """L1: файл существует, обычный файл, размер > 0."""
        if not image_path.exists():
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Файл не существует: {image_path}",
                    field="path",
                )
            )
            return
        if not image_path.is_file():
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Не файл (возможно директория): {image_path}",
                    field="path",
                )
            )
            return
        try:
            size = image_path.stat().st_size
        except OSError as exc:
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Не удалось получить размер: {exc}",
                    field="path",
                )
            )
            return
        if size == 0:
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Файл пустой (0 байт): {image_path}",
                    field="path",
                )
            )

    def _check_resource_format(self, image_path: Path, result: "ResourceValidationResult") -> None:
        """L2: расширение в SUPPORTED_RESOURCE_FORMATS (PNG/JPG/JPEG)."""
        suffix = image_path.suffix.lower()
        if not is_supported_format(suffix):
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Неподдерживаемый формат '{suffix}' — только PNG/JPG/JPEG",
                    field="format",
                )
            )

    def _check_resource_magic(self, image_path: Path, result: "ResourceValidationResult") -> None:
        """L3: сигнатура содержимого соответствует расширению."""
        suffix = image_path.suffix.lower()
        expected_magic = MAGIC_BYTES.get(suffix)
        if expected_magic is None:
            # L2 уже должен был провалиться, но на всякий случай
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Нет magic bytes для формата '{suffix}'",
                    field="format",
                )
            )
            return
        try:
            with open(image_path, "rb") as f:
                actual_magic = f.read(len(expected_magic))
        except OSError as exc:
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Не удалось прочитать для magic check: {exc}",
                    field="path",
                )
            )
            return
        if actual_magic != expected_magic:
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=(
                        f"Magic bytes не соответствуют расширению '{suffix}': "
                        f"ожидалось {expected_magic!r}, получено {actual_magic!r}"
                    ),
                    field="format",
                )
            )

    def _check_resource_loadable(self, image_path: Path, result: "ResourceValidationResult") -> None:
        """L4: pygame.image.load() декодирует изображение (error, не warning).

        Контракт Master G8: ошибка загрузки — error, не warning.
        Не вызывает pygame.init() или display.set_mode() — pygame.image.load
        работает без них на pygame 2.6.1 (подтверждено тестом).
        """
        try:
            import pygame

            surf = pygame.image.load(str(image_path))
            if surf is None:
                result.issues.append(
                    ValidationIssue(
                        level="error",
                        category="resource",
                        message=f"pygame.image.load вернул None: {image_path}",
                        field="loadable",
                    )
                )
        except pygame.error as exc:
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Изображение не декодируется (pygame.error): {exc}",
                    field="loadable",
                )
            )
        except Exception as exc:
            result.issues.append(
                ValidationIssue(
                    level="error",
                    category="resource",
                    message=f"Неожиданная ошибка при загрузке: {type(exc).__name__}: {exc}",
                    field="loadable",
                )
            )
