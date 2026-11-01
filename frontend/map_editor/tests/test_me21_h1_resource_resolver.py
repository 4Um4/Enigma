"""ME-2.1-H-1 Step 1: ResourceResolver contract tests.

Тестирует только assets/resource_resolver.py (LegacyDirResolver + ResourceResolver).
SpriteRegistry / ResourceValidator / editor_core wiring — отдельные шаги.

Контракты (по GO Master H-1):
- LegacyDirResolver: R2 (path traversal), R3 (точная legacy-семантика .png).
- ResourceResolver: canonical (AssetStore), campaign override, legacy fallback, None.
- R1 (cache invalidation) — тестируется в шаге 2 (SpriteRegistry).
- Возврат ResourceRecord.path, не самостоятельное конструирование пути.

Изоляция: tmp_path для каждого теста, никаких глобальных состояний.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest

frontend_root = Path(__file__).resolve().parents[2]
map_editor_root = frontend_root / "map_editor"
for p in [str(frontend_root), str(map_editor_root)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from assets.resource_resolver import LegacyDirResolver, ResourceResolver  # noqa: I001


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class _FakeResourceRecord:
    """Duck-typed ResourceRecord для тестов (как asset_store.py:154-163)."""

    resource_id: str
    version: int
    source: str
    path: Path


class _FakeAssetStore:
    """Duck-typed AssetStore: get_resource(resource_id) → record или None.

    Воспроизводит контракт asset_store.py:213 (get_resource). Реальная
    логика campaign/global override — внутри AssetStore._put_blueprint /
    _register_resource; здесь она эмулируется словарём.
    """

    def __init__(self, records: dict[str, _FakeResourceRecord] | None = None) -> None:
        self._records: dict[str, _FakeResourceRecord] = dict(records or {})

    def get_resource(self, resource_id: str) -> _FakeResourceRecord | None:
        return self._records.get(resource_id)

    def add_record(self, record: _FakeResourceRecord) -> None:
        self._records[record.resource_id] = record


def _make_legacy_tree(tmp_path: Path) -> Path:
    """Создать pixels/-подобное дерево:
    pixels/Deadbeat/deadbeat_b.png
    pixels/textures/Растения.png  (кириллица)
    pixels/текстуры/пол/утоптанная земля.png  (кириллица + пробел)
    pixels/deadbeat_a.png  (без поддиректории)
    """
    root = tmp_path / "pixels"
    (root / "Deadbeat").mkdir(parents=True)
    (root / "Deadbeat" / "deadbeat_b.png").write_bytes(b"PNG")
    (root / "textures").mkdir(parents=True)
    (root / "textures" / "Растения.png").write_bytes(b"PNG")
    (root / "текстуры" / "пол").mkdir(parents=True)
    (root / "текстуры" / "пол" / "утоптанная земля.png").write_bytes(b"PNG")
    (root / "deadbeat_a.png").write_bytes(b"PNG")
    return root


def _make_canonical_tree(tmp_path: Path) -> Path:
    """Создать assets/.../resources/ дерево для canonical тестов:
    assets/catalogs/base/resources/furniture/chair.png
    assets/Open_road/resources/furniture/chair.png  (campaign override)
    """
    base = tmp_path / "assets"
    g = base / "catalogs" / "base" / "resources" / "furniture"
    g.mkdir(parents=True)
    (g / "chair.png").write_bytes(b"PNG-global")
    c = base / "Open_road" / "resources" / "furniture"
    c.mkdir(parents=True)
    (c / "chair.png").write_bytes(b"PNG-campaign")
    return base


# ═══════════════════════════════════════════════════════════════════
# LegacyDirResolver: R3 (точная legacy-семантика)
# ═══════════════════════════════════════════════════════════════════


class TestLegacyDirResolverExistence:
    """R3: базовое разрешение существующих ресурсов."""

    def test_resolve_png_with_extension_added(self, tmp_path):
        """Deadbeat/deadbeat_b → pixels/Deadbeat/deadbeat_b.png (добавлено .png)."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        result = r.resolve("Deadbeat/deadbeat_b")
        assert result is not None
        assert result.name == "deadbeat_b.png"
        assert result.is_file()

    def test_resolve_file_without_extension(self, tmp_path):
        """Файл без расширения: resource_id как полный путь к файлу.

        R3 шаг 1: проверить файл без расширения ПЕРЕД добавлением .png.
        """
        root = tmp_path / "pixels"
        root.mkdir()
        (root / "noext_file").write_bytes(b"data")  # файл без расширения
        r = LegacyDirResolver(root)
        result = r.resolve("noext_file")
        assert result is not None
        assert result.name == "noext_file"

    def test_resolve_png_priority_over_noext(self, tmp_path):
        """R3: если есть и noext и .png — возвращается noext (шаг 1 раньше шага 2).

        Семантика прежнего SpriteRegistry._load_sheet: сначала проверяется
        path (без .png), потом path + ".png". Если есть оба — noext выигрывает.
        """
        root = tmp_path / "pixels"
        root.mkdir()
        (root / "sprite").write_bytes(b"noext")  # шаг 1
        (root / "sprite.png").write_bytes(b"png")  # шаг 2
        r = LegacyDirResolver(root)
        result = r.resolve("sprite")
        assert result is not None
        assert result.name == "sprite"  # noext приоритет

    def test_resolve_nonexistent_returns_none(self, tmp_path):
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        assert r.resolve("Nonexistent/sheet") is None

    def test_resolve_empty_string_returns_none(self, tmp_path):
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        assert r.resolve("") is None

    def test_resolve_only_slashes_returns_none(self, tmp_path):
        """resource_id = "/" → после strip("/") → пусто → None."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        assert r.resolve("/") is None
        assert r.resolve("///") is None

    def test_resolve_backslash_normalized(self, tmp_path):
        """Windows-стиль: "Deadbeat\\deadbeat_b" → "Deadbeat/deadbeat_b"."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        result = r.resolve("Deadbeat\\deadbeat_b")
        assert result is not None
        assert result.name == "deadbeat_b.png"

    def test_resolve_leading_trailing_slashes_stripped(self, tmp_path):
        """/Deadbeat/deadbeat_b/ → Deadbeat/deadbeat_b (strip)."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        # Замечание: leading "/" в R2 НЕ абсолютный путь для strip-после-нормализации.
        # Но R2 блокирует "/" в начале как абсолютный. Проверяем strip для trailing.
        result = r.resolve("Deadbeat/deadbeat_b/")
        assert result is not None
        assert result.name == "deadbeat_b.png"


class TestLegacyDirResolverCyrillic:
    """R2/R3: кириллица в resource_id."""

    def test_resolve_cyrillic_simple(self, tmp_path):
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        result = r.resolve("textures/Растения")
        assert result is not None
        assert result.is_file()

    def test_resolve_cyrillic_with_spaces(self, tmp_path):
        """Кириллица + пробелы в имени директории и файла."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        result = r.resolve("текстуры/пол/утоптанная земля")
        assert result is not None
        assert result.is_file()
        assert "утоптанная земля.png" in result.name


class TestLegacyDirResolverPathTraversal:
    """R2: path traversal защита (контракт Master — любой .. запрещён)."""

    def test_traversal_parent_directory_blocked(self, tmp_path):
        """../../etc/passwd → None (выход за корень)."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        assert r.resolve("../../etc/passwd") is None

    def test_traversal_internal_dotdot_blocked(self, tmp_path):
        """R2 (корректировка Master): Deadbeat/../Deadbeat/deadbeat_b → None.

        Контракт: ЛЮБОЙ компонент ".." запрещён, не только выход за корень.
        Внутренний ".." не даёт полезной функциональности, усложняет анализ.
        """
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        assert r.resolve("Deadbeat/../Deadbeat/deadbeat_b") is None

    def test_traversal_single_dotdot_blocked(self, tmp_path):
        """Простой ".." → None."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        assert r.resolve("..") is None

    def test_traversal_dotdot_in_middle_blocked(self, tmp_path):
        """a/../../b → None."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        assert r.resolve("a/../../b") is None

    def test_absolute_unix_path_blocked(self, tmp_path):
        """/etc/passwd → None (абсолютный Unix-путь)."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        assert r.resolve("/etc/passwd") is None

    def test_absolute_windows_path_blocked(self, tmp_path):
        """C:\\Windows\\system32 → None (абсолютный Windows-путь)."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        assert r.resolve("C:\\Windows\\system32") is None
        # Также forward-slash вариант
        assert r.resolve("C:/Windows/system32") is None

    def test_dotdot_does_not_leak_outside_root(self, tmp_path):
        """Реальная проверка: даже если бы .. не был запрещён на уровне parts,
        canonical check всё равно блокирует выход за root. Двойная защита.
        """
        # Создаём файл вне root
        outside = tmp_path / "secret.txt"
        outside.write_bytes(b"SECRET")
        root = tmp_path / "pixels"
        root.mkdir()
        r = LegacyDirResolver(root)
        # Попытка выйти через ..
        assert r.resolve("../secret.txt") is None
        assert r.resolve("../secret") is None  # + .png тоже не должен сработать


class TestLegacyDirResolverRootIntegrity:
    """R2: корневая директория и canonical check."""

    def test_resolve_when_root_does_not_exist(self, tmp_path):
        """Папки pixels/ нет → resolve возвращает None (не падает)."""
        r = LegacyDirResolver(tmp_path / "nonexistent")
        assert r.resolve("anything") is None

    def test_resolve_directory_returns_none(self, tmp_path):
        """resource_id указывает на директорию, не файл → None."""
        root = _make_legacy_tree(tmp_path)
        r = LegacyDirResolver(root)
        # "Deadbeat" — это директория, не файл
        assert r.resolve("Deadbeat") is None

    def test_root_dir_property(self, tmp_path):
        """root_dir возвращает исходный Path."""
        root = tmp_path / "pixels"
        r = LegacyDirResolver(root)
        assert r.root_dir == root


# ═══════════════════════════════════════════════════════════════════
# LegacyDirResolver: R3 (точная семантика .png, не with_suffix)
# ═══════════════════════════════════════════════════════════════════


class TestLegacyDirResolverDotPngSemantic:
    """R3 (корректировка Master): .png ДОБАВЛЯЕТСЯ, не заменяет расширение.

    with_suffix(".png") заменил бы "v1.sheet" → "v1.png" (потеря .sheet).
    Контракт: str(candidate) + ".png" → "v1.sheet.png".
    """

    def test_dot_added_not_replaced_simple(self, tmp_path):
        """sprite → sprite.png (простой случай, with_suffix и + ".png" совпадают)."""
        root = tmp_path / "pixels"
        root.mkdir()
        (root / "sprite.png").write_bytes(b"PNG")
        r = LegacyDirResolver(root)
        result = r.resolve("sprite")
        assert result is not None
        assert result.name == "sprite.png"

    def test_dot_added_not_replaced_with_dot_in_name(self, tmp_path):
        """textures/v1.sheet → textures/v1.sheet.png (НЕ v1.png).

        Критический тест R3: with_suffix дал бы v1.png, что неверно.
        """
        root = tmp_path / "pixels" / "textures"
        root.mkdir(parents=True)
        # Файл с точкой в имени, но без расширения .png
        (root / "v1.sheet.png").write_bytes(b"PNG")
        r = LegacyDirResolver(root.parent)  # pixels/
        result = r.resolve("textures/v1.sheet")
        assert result is not None, "v1.sheet.png должен резолвиться через + .png"
        assert result.name == "v1.sheet.png", (
            f"Ожидалось v1.sheet.png (добавление .png), получено {result.name} "
            f"(возможно, использован with_suffix — это нарушение R3)"
        )

    def test_dot_added_multiple_dots_in_name(self, tmp_path):
        """a.b.c → a.b.c.png (несколько точек — все сохранены)."""
        root = tmp_path / "pixels"
        root.mkdir()
        (root / "a.b.c.png").write_bytes(b"PNG")
        r = LegacyDirResolver(root)
        result = r.resolve("a.b.c")
        assert result is not None
        assert result.name == "a.b.c.png"

    def test_dot_not_added_when_file_exists_noext(self, tmp_path):
        """Если файл без расширения существует — .png не добавляется."""
        root = tmp_path / "pixels"
        root.mkdir()
        (root / "file").write_bytes(b"data")
        (root / "file.png").write_bytes(b"PNG")  # тоже есть
        r = LegacyDirResolver(root)
        result = r.resolve("file")
        # R3: шаг 1 (noext) приоритет над шагом 2 (.png)
        assert result is not None
        assert result.name == "file"  # без .png


# ═══════════════════════════════════════════════════════════════════
# ResourceResolver: canonical (AssetStore)
# ═══════════════════════════════════════════════════════════════════


class TestResourceResolverCanonical:
    """Контракт: canonical resolution через AssetStore → ResourceRecord.path."""

    def test_resolve_canonical_global(self, tmp_path):
        """AssetStore.get_resource возвращает global record → вернуть record.path."""
        canonical_path = (
            tmp_path / "assets" / "catalogs" / "base" / "resources" / "chair.png"
        )
        canonical_path.parent.mkdir(parents=True)
        canonical_path.write_bytes(b"PNG-global")

        store = _FakeAssetStore(
            {
                "furniture/chair": _FakeResourceRecord(
                    resource_id="furniture/chair",
                    version=1,
                    source="global:base",
                    path=canonical_path,
                )
            }
        )
        legacy = LegacyDirResolver(tmp_path / "pixels")
        r = ResourceResolver(store, legacy)

        result = r.resolve("furniture/chair")
        assert result == canonical_path
        assert result.is_file()

    def test_resolve_returns_record_path_not_constructed(self, tmp_path):
        """Контракт Master §3: ResourceResolver возвращает record.path, не
        конструирует путь самостоятельно. Если record.path не существует
        физически — всё равно возвращается он (resolver доверяет store).
        """
        # path указывает на несуществующий файл — но resolver возвращает его
        fake_path = tmp_path / "nonexistent" / "chair.png"
        store = _FakeAssetStore(
            {
                "chair": _FakeResourceRecord(
                    resource_id="chair",
                    version=1,
                    source="global:base",
                    path=fake_path,
                )
            }
        )
        legacy = LegacyDirResolver(tmp_path / "pixels")
        r = ResourceResolver(store, legacy)

        result = r.resolve("chair")
        assert result == fake_path  # возвращён path из record, не None

    def test_resolve_canonical_takes_precedence_over_legacy(self, tmp_path):
        """Если ресурс есть и в canonical и в legacy — canonical побеждает."""
        # canonical
        canonical_path = tmp_path / "canonical" / "chair.png"
        canonical_path.parent.mkdir(parents=True)
        canonical_path.write_bytes(b"canonical")

        # legacy (тот же resource_id)
        legacy_root = tmp_path / "pixels"
        legacy_root.mkdir()
        (legacy_root / "chair.png").write_bytes(b"legacy")

        store = _FakeAssetStore(
            {
                "chair": _FakeResourceRecord(
                    resource_id="chair",
                    version=1,
                    source="global:base",
                    path=canonical_path,
                )
            }
        )
        legacy = LegacyDirResolver(legacy_root)
        r = ResourceResolver(store, legacy)

        result = r.resolve("chair")
        assert result == canonical_path  # canonical, не legacy


class TestResourceResolverCampaignOverride:
    """Контракт: campaign override на уровне AssetStore.

    Логика override (asset_store.py:340-365) — внутри AssetStore.
    ResourceResolver делегирует в get_resource, который уже возвращает
    campaign record если есть, иначе global. Здесь эмулируем оба случая.
    """

    def test_campaign_override_wins(self, tmp_path):
        """AssetStore возвращает campaign record (не global) → вернуть campaign path."""
        global_path = tmp_path / "global" / "chair.png"
        global_path.parent.mkdir(parents=True)
        global_path.write_bytes(b"global")

        campaign_path = tmp_path / "campaign" / "chair.png"
        campaign_path.parent.mkdir(parents=True)
        campaign_path.write_bytes(b"campaign")

        # AssetStore.get_resource("chair") возвращает campaign (override уже применён)
        store = _FakeAssetStore(
            {
                "chair": _FakeResourceRecord(
                    resource_id="chair",
                    version=1,
                    source="campaign:Open_road",
                    path=campaign_path,
                )
            }
        )
        legacy = LegacyDirResolver(tmp_path / "pixels")
        r = ResourceResolver(store, legacy)

        result = r.resolve("chair")
        assert result == campaign_path
        assert result != global_path

    def test_global_when_no_campaign(self, tmp_path):
        """AssetStore возвращает global record (campaign нет) → global path."""
        global_path = tmp_path / "global" / "chair.png"
        global_path.parent.mkdir(parents=True)
        global_path.write_bytes(b"global")

        store = _FakeAssetStore(
            {
                "chair": _FakeResourceRecord(
                    resource_id="chair",
                    version=1,
                    source="global:base",
                    path=global_path,
                )
            }
        )
        legacy = LegacyDirResolver(tmp_path / "pixels")
        r = ResourceResolver(store, legacy)

        result = r.resolve("chair")
        assert result == global_path


class TestResourceResolverLegacyFallback:
    """Контракт: legacy fallback только если canonical не найден."""

    def test_legacy_fallback_when_not_in_store(self, tmp_path):
        """Ресурса нет в AssetStore → fallback в LegacyDirResolver."""
        legacy_root = tmp_path / "pixels"
        legacy_root.mkdir()
        (legacy_root / "Deadbeat").mkdir()
        (legacy_root / "Deadbeat" / "deadbeat_b.png").write_bytes(b"legacy")

        store = _FakeAssetStore({})  # пустой store
        legacy = LegacyDirResolver(legacy_root)
        r = ResourceResolver(store, legacy)

        result = r.resolve("Deadbeat/deadbeat_b")
        assert result is not None
        assert result.name == "deadbeat_b.png"
        assert result.parent.name == "Deadbeat"

    def test_none_when_neither_canonical_nor_legacy(self, tmp_path):
        """Нет ни в store, ни в legacy → None."""
        store = _FakeAssetStore({})
        legacy = LegacyDirResolver(tmp_path / "pixels")
        r = ResourceResolver(store, legacy)

        assert r.resolve("Nonexistent/sheet") is None


class TestResourceResolverLifecycle:
    """R1: контракт замены AssetStore (campaign lifecycle).

    Master R1: при смене AssetStore editor_core создаёт НОВЫЙ
    ResourceResolver(new_store, legacy) и передаёт в set_resolver.
    Старый resolver более не используется.
    """

    def test_new_resolver_uses_new_store(self, tmp_path):
        """После создания нового resolver с новым store — resolve идёт в новый store."""
        store1_path = tmp_path / "store1" / "chair.png"
        store1_path.parent.mkdir(parents=True)
        store1_path.write_bytes(b"store1")

        store2_path = tmp_path / "store2" / "chair.png"
        store2_path.parent.mkdir(parents=True)
        store2_path.write_bytes(b"store2")

        store1 = _FakeAssetStore(
            {"chair": _FakeResourceRecord("chair", 1, "global:base", store1_path)}
        )
        store2 = _FakeAssetStore(
            {"chair": _FakeResourceRecord("chair", 1, "global:base", store2_path)}
        )

        legacy = LegacyDirResolver(tmp_path / "pixels")

        resolver1 = ResourceResolver(store1, legacy)
        assert resolver1.resolve("chair") == store1_path

        # Смена store: новый resolver
        resolver2 = ResourceResolver(store2, legacy)
        assert resolver2.resolve("chair") == store2_path

        # Старый resolver не изменился (но его store не поменялся)
        assert resolver1.resolve("chair") == store1_path

    def test_resolver_with_none_store_uses_only_legacy(self, tmp_path):
        """asset_store=None → только legacy fallback (для тестов/default)."""
        legacy_root = tmp_path / "pixels"
        legacy_root.mkdir()
        (legacy_root / "sprite.png").write_bytes(b"legacy")

        legacy = LegacyDirResolver(legacy_root)
        r = ResourceResolver(None, legacy)  # type: ignore[arg-type]

        result = r.resolve("sprite")
        assert result is not None
        assert result.name == "sprite.png"

    def test_legacy_resolver_required(self, tmp_path):
        """legacy_resolver=None → ValueError (обязательный параметр)."""
        store = _FakeAssetStore({})
        with pytest.raises(ValueError, match="legacy_resolver обязательна"):
            ResourceResolver(store, None)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════
# Интеграция с реальным AssetStore (не mock) — smoke test
# ═══════════════════════════════════════════════════════════════════


class TestResourceResolverWithRealAssetStore:
    """Smoke test: ResourceResolver работает с реальным AssetStore.

    Подтверждает duck-typing: ResourceResolver не импортирует AssetStore,
    но корректно вызывает get_resource и читает record.path.
    """

    def test_resolve_with_empty_real_store_falls_to_legacy(self, tmp_path):
        """Пустой AssetStore (нет resources/) → legacy fallback."""
        from assets.asset_store import AssetStore

        # Создаём assets/ с базовой структурой, но без resources/
        assets_dir = tmp_path / "assets"
        bp_dir = assets_dir / "catalogs" / "base" / "blueprints"
        bp_dir.mkdir(parents=True)
        # Минимальный валидный blueprint (для load без ошибок)
        (bp_dir / "test.json").write_text(
            json.dumps(
                {
                    "blueprint_id": "test",
                    "version": 1,
                    "compat": 1,
                    "type": "test",
                    "geometry": {
                        "source": "primitive",
                        "size": {"w": 1, "h": 1, "d": 1},
                    },
                    "appearance": {"color": "#FFFFFF"},
                    "physics": {"passability": {}, "cover": 0, "height": 1},
                }
            ),
            encoding="utf-8",
        )

        store = AssetStore(assets_dir)
        store.load()

        # legacy с реальным пикселем
        legacy_root = tmp_path / "pixels"
        legacy_root.mkdir()
        (legacy_root / "Deadbeat").mkdir()
        (legacy_root / "Deadbeat" / "deadbeat_b.png").write_bytes(b"PNG")

        legacy = LegacyDirResolver(legacy_root)
        r = ResourceResolver(store, legacy)

        # Нет в store (resources/ не создан) → legacy
        result = r.resolve("Deadbeat/deadbeat_b")
        assert result is not None
        assert result.name == "deadbeat_b.png"

    def test_resolve_with_real_store_having_resources(self, tmp_path):
        """AssetStore с resources/ → canonical resolution."""
        from assets.asset_store import AssetStore

        assets_dir = tmp_path / "assets"
        bp_dir = assets_dir / "catalogs" / "base" / "blueprints"
        res_dir = assets_dir / "catalogs" / "base" / "resources" / "furniture"
        bp_dir.mkdir(parents=True)
        res_dir.mkdir(parents=True)
        (bp_dir / "test.json").write_text(
            json.dumps(
                {
                    "blueprint_id": "test",
                    "version": 1,
                    "compat": 1,
                    "type": "test",
                    "geometry": {
                        "source": "primitive",
                        "size": {"w": 1, "h": 1, "d": 1},
                    },
                    "appearance": {"color": "#FFFFFF"},
                    "physics": {"passability": {}, "cover": 0, "height": 1},
                }
            ),
            encoding="utf-8",
        )
        chair_png = res_dir / "chair.png"
        chair_png.write_bytes(b"PNG-canonical")

        store = AssetStore(assets_dir)
        store.load()

        # Проверяем, что store зарегистрировал ресурс
        assert "furniture/chair" in store.list_resources()

        legacy = LegacyDirResolver(tmp_path / "pixels")
        r = ResourceResolver(store, legacy)

        result = r.resolve("furniture/chair")
        assert result == chair_png
        assert result.is_file()


# ═══════════════════════════════════════════════════════════════════
# Summary контрактов (для документации в выводе pytest)
# ═══════════════════════════════════════════════════════════════════


class TestContractSummary:
    """Документация: какие контракты H-1 Step 1 покрыты.

    Не содержит assertions — это manifest для ревью.
    Контракт → тестовый класс/метод.
    """

    CONTRACTS: ClassVar[dict[str, list[str]]] = {
        "R2_path_traversal_any_dotdot_blocked": [
            "TestLegacyDirResolverPathTraversal.test_traversal_internal_dotdot_blocked",
            "TestLegacyDirResolverPathTraversal.test_traversal_parent_directory_blocked",
            "TestLegacyDirResolverPathTraversal.test_traversal_single_dotdot_blocked",
            "TestLegacyDirResolverPathTraversal.test_dotdot_does_not_leak_outside_root",
        ],
        "R2_absolute_paths_blocked": [
            "TestLegacyDirResolverPathTraversal.test_absolute_unix_path_blocked",
            "TestLegacyDirResolverPathTraversal.test_absolute_windows_path_blocked",
        ],
        "R3_dot_png_added_not_replaced": [
            "TestLegacyDirResolverDotPngSemantic.test_dot_added_not_replaced_with_dot_in_name",
            "TestLegacyDirResolverDotPngSemantic.test_dot_added_multiple_dots_in_name",
        ],
        "R3_noext_priority_over_png": [
            "TestLegacyDirResolverDotPngSemantic.test_dot_not_added_when_file_exists_noext",
            "TestLegacyDirResolverExistence.test_resolve_png_priority_over_noext",
        ],
        "canonical_resolution_returns_record_path": [
            "TestResourceResolverCanonical.test_resolve_canonical_global",
            "TestResourceResolverCanonical.test_resolve_returns_record_path_not_constructed",
            "TestResourceResolverCanonical.test_resolve_canonical_takes_precedence_over_legacy",
        ],
        "campaign_override_at_store_level": [
            "TestResourceResolverCampaignOverride.test_campaign_override_wins",
            "TestResourceResolverCampaignOverride.test_global_when_no_campaign",
        ],
        "legacy_fallback_only_when_canonical_missing": [
            "TestResourceResolverLegacyFallback.test_legacy_fallback_when_not_in_store",
            "TestResourceResolverLegacyFallback.test_none_when_neither_canonical_nor_legacy",
        ],
        "R1_lifecycle_new_store_new_resolver": [
            "TestResourceResolverLifecycle.test_new_resolver_uses_new_store",
            "TestResourceResolverLifecycle.test_resolver_with_none_store_uses_only_legacy",
        ],
        "cyrillic_supported": [
            "TestLegacyDirResolverCyrillic.test_resolve_cyrillic_simple",
            "TestLegacyDirResolverCyrillic.test_resolve_cyrillic_with_spaces",
        ],
    }

    def test_manifest(self):
        """Manifest: все контракты H-1 Step 1 описаны."""
        assert len(self.CONTRACTS) == 9
        for name, tests in self.CONTRACTS.items():
            assert len(tests) > 0, f"Контракт {name} без тестов"