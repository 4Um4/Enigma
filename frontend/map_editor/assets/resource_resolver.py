"""path: /frontend/map_editor/assets/resource_resolver.py

ME-2.1-H-1: ResourceResolver — единая точка разрешения resource_id → файл.

Назначение:
    Разделение ответственностей (контракт Master H-1):
    - AssetStore владеет зарегистрированными ресурсами (ResourceRecord.path).
    - ResourceResolver определяет, какой физический файл соответствует
      логическому resource_id.
    - SpriteRegistry превращает файл в визуальное представление.

    Ни один из трёх не присваивает себе чужую ответственность.

Порядок разрешения (контракт Master §3):
    1. AssetStore.get_resource(resource_id) — campaign override если есть,
       иначе global. Возвращает ResourceRecord.path (не конструирует путь).
    2. LegacyDirResolver — только если canonical не найден. Read-only,
       воспроизводит прежнюю семантику SpriteRegistry._load_sheet.
    3. None — если ничего не найдено.

R1 (cache invalidation): SpriteRegistry.set_resolver() вызывает clear_cache().
    При смене AssetStore (campaign lifecycle) editor_core создаёт новый
    ResourceResolver и передаёт его через set_resolver — кэш инвалидируется,
    SpriteRegistry начинает использовать новый store. Контракт не привязан
    к вечному существованию одного экземпляра store.

R2 (path traversal): любой компонент ".." запрещён. Абсолютные пути
    запрещены. Нормализация разделителей. Проверка canonical path внутри
    root. Кириллица поддерживается (Path.resolve корректен на UTF-8).

R3 (legacy semantic): LegacyDirResolver воспроизводит точную семантику
    прежнего SpriteRegistry._load_sheet:
    1. Проверить файл без расширения (resource_id как путь).
    2. Проверить тот же путь с добавленным ".png" (не with_suffix, а + ".png").
    3. None.
    with_suffix заменяет расширение — это другая семантика, запрещена.

Зависимости: только стандартная библиотека + AssetStore (duck-typed).
    НЕ импортирует sprite_registry (иначе цикл).
    НЕ импортирует pygame (frontend boundary, Закон 1.1 Устава).

Основные сущности: LegacyDirResolver, ResourceResolver.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["LegacyDirResolver", "ResourceResolver"]


class LegacyDirResolver:
    """Read-only resolver для pixels/ (legacy fallback).

    Воспроизводит точную семантику прежнего SpriteRegistry._load_sheet
    (sprite_registry.py:36-58 до H-1):

    1. candidate = root / resource_id (нормализованный)
    2. Если candidate.is_file() → вернуть candidate
    3. Если (candidate + ".png").is_file() → вернуть candidate + ".png"
    4. None

    R2: path traversal защита. resource_id поступает из данных Blueprint
    (appearance.sprite[0]) — не доверенный. Любой компонент ".." запрещён.
    Абсолютные пути запрещены. Проверка canonical path внутри root.

    Read-only: не регистрирует, не изменяет, не создаёт файлов.
    """

    def __init__(self, root_dir: Path | str) -> None:
        self._root = Path(root_dir)

    @property
    def root_dir(self) -> Path:
        """Корневая директория (pixels/). Только для чтения."""
        return self._root

    def resolve(self, resource_id: str) -> Path | None:
        """Вернуть Path к физическому файлу или None.

        R2 контракт:
        - пустой/нечстроковый resource_id → None
        - абсолютный путь (Unix /, Windows X:) → None
        - любой компонент ".." → None
        - нормализация: \\ → /
        - canonical check: candidate.resolve() внутри self._root.resolve()

        R3 контракт (точная legacy-семантика):
        1. candidate = root / parts
        2. candidate.is_file() → candidate
        3. (str(candidate) + ".png") is_file() → Path(str(candidate) + ".png")
        4. None

        Args:
            resource_id: логический ID ресурса (path без расширения, posix).
                         Может содержать кириллицу.

        Returns:
            Path к существующему файлу, или None.
        """
        # 1. Базовая валидация
        if not isinstance(resource_id, str) or not resource_id:
            return None

        # 2. Запрет абсолютных путей
        #    Unix: начинается с "/"
        #    Windows: "C:\..." или "C:/..." (drive letter + colon)
        if resource_id.startswith(("/", "\\")):
            return None
        if len(resource_id) >= 2 and resource_id[1] == ":":
            return None

        # 3. Нормализация разделителей и разбор на компоненты
        parts = resource_id.replace("\\", "/").strip("/").split("/")
        #    strip("/") убирает ведущие/завершающие слэши (после нормализации)
        #    пустые parts (resource_id == "" или "//") → [] после strip

        # 4. R2: запрет любого компонента ".." (контракт Master — любой, не
        #    только выход за корень). "Deadbeat/../Deadbeat/x" → None.
        if any(part == ".." for part in parts):
            return None

        # 5. Пустой resource_id после нормализации (например, был только "/")
        if not parts:
            return None

        # 6. Конструирование candidate. joinpath корректно обрабатывает
        #    кириллицу (UTF-8 на уровне str → Path).
        candidate = self._root.joinpath(*parts)

        # 7. R2 canonical check: candidate.resolve() должен быть внутри root.
        #    Защита от symlink-атак и непредвиденных нормализаций.
        #    Если root не существует (папки pixels/ нет) — resolve() вернёт
        #    несуществующий путь, relative_to выбросит ValueError → None.
        try:
            root_resolved = self._root.resolve()
            candidate_resolved = candidate.resolve()
            # relative_to: если candidate_resolved вне root_resolved → ValueError
            candidate_resolved.relative_to(root_resolved)
        except (ValueError, OSError):
            return None

        # 8. R3: точная legacy-семантика (НЕ with_suffix).
        #    Шаг 1: файл без расширения (resource_id как полный путь к файлу).
        if candidate.is_file():
            return candidate

        # 9. R3: Шаг 2 — добавить ".png" (не заменить расширение).
        #    Семантика: str(candidate) + ".png".
        #    "textures/v1.sheet" → "textures/v1.sheet.png" (не "textures/v1.png").
        #    "Deadbeat/deadbeat_b" → "Deadbeat/deadbeat_b.png".
        candidate_png = Path(str(candidate) + ".png")
        if candidate_png.is_file():
            return candidate_png

        # 10. Не найден
        return None


class ResourceResolver:
    """Канонический resolver: AssetStore → ResourceRecord.path.

    Порядок разрешения (контракт Master §3):
    1. AssetStore.get_resource(resource_id) — campaign override если есть,
       иначе global. Возвращает ResourceRecord.path.
    2. LegacyDirResolver — только если canonical не найден.
    3. None.

    Возвращает ResourceRecord.path, не конструирует путь самостоятельно
    (нет второго механизма знания о физической структуре AssetStore).

    R1 (campaign lifecycle): при смене AssetStore editor_core создаёт
    НОВЫЙ ResourceResolver(new_store, legacy) и передаёт его в
    SpriteRegistry.set_resolver(). Старый resolver более не используется.
    Контракт не привязан к вечному существованию одного экземпляра store.
    """

    def __init__(
        self,
        asset_store: Any,
        legacy_resolver: LegacyDirResolver,
    ) -> None:
        """
        Args:
            asset_store: AssetStore (duck-typed). Должен иметь метод
                get_resource(resource_id) -> ResourceRecord | None.
                ResourceRecord должен иметь атрибут path (Path).
                AssetStore НЕ импортируется здесь (layering, Закон 1.2) —
                duck-typing, как в save_blueprint_atomic (asset_store.py:268).
            legacy_resolver: LegacyDirResolver для fallback в pixels/.
                Обязателен (не None) — без него legacy-ссылки на
                Deadbeat/deadbeat_b перестанут работать.
        """
        if legacy_resolver is None:
            raise ValueError("legacy_resolver обязательна (не None)")
        self._store = asset_store
        self._legacy = legacy_resolver

    def resolve(self, resource_id: str) -> Path | None:
        """Вернуть Path к физическому файлу или None.

        1. AssetStore.get_resource(resource_id) → ResourceRecord.path
           (campaign override если есть, иначе global — логика внутри store).
        2. Legacy fallback (R2 защищён внутри LegacyDirResolver).
        3. None.
        """
        # 1. Canonical: AssetStore владеет зарегистрированными ресурсами.
        #    Не конструируем путь самостоятельно — берём record.path.
        if self._store is not None:
            record = self._store.get_resource(resource_id)
            if record is not None and hasattr(record, "path") and record.path is not None:
                return record.path

        # 2. Legacy fallback (read-only, R2 защищён)
        return self._legacy.resolve(resource_id)
