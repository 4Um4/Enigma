"""path: /frontend/map_editor/assets/asset_store.py

Назначение: Склад чертежей и ресурсов (ME-1.2, Этап 01). Читает общие каталоги
    (assets/catalogs/<имя>/) и собственный каталог кампании (assets/<кампания>/),
    ведёт список имён и версий. Если у предмета с одинаковым именем есть своя
    версия в кампании — главнее она (решение Мастера 2026-10-14), и замена
    фиксируется в списке перекрытий. Если папки assets/ нет — склад пуст, это не
    ошибка, и на диск ничего не пишется (существующие кампании не ломаются).
    Битый чертёж — громкая ошибка с именем файла и поля.

Зависимости: только стандартная библиотека. Backend не импортируется
    (граница фронта, Закон 1.1 Устава ENIGMA).

Основные сущности: AssetStore, BlueprintRecord, ResourceRecord, AssetStoreError.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Устав §12.1: ключи сериализации — модульные константы, не inline-строки
_KEY_BLUEPRINT_ID = "blueprint_id"
_KEY_VERSION = "version"
_KEY_COMPAT = "compat"

_BLUEPRINTS_DIR = "blueprints"
_RESOURCES_DIR = "resources"
_GLOBAL_CATALOGS_DIR = "catalogs"

_SOURCE_GLOBAL = "global"
_SOURCE_CAMPAIGN = "campaign"


class AssetStoreError(RuntimeError):
    """Громкий отказ загрузки: перечень проблем с именем файла и поля.

    Загрузить половину и молча пропустить битое запрещено — это тихая потеря
    данных; поэтому все проблемы собираются в один пакет и поднимаются разом.
    """


@dataclass(frozen=True)
class BlueprintRecord:
    """Чертёж в реестре: данные + откуда прочитан."""

    data: dict
    version: int
    source: str  # "global:<каталог>" | "campaign:<кампания>"
    path: Path

    @property
    def blueprint_id(self) -> str:
        return str(self.data[_KEY_BLUEPRINT_ID])


@dataclass(frozen=True)
class ResourceRecord:
    """Ресурс (картинка): имя = путь внутри resources/ без расширения.

    Версия в v1 всегда 1: полноценный учёт версий картинок включается при
    переносе спрайтов (ME-1.6). Поле оставлено сейчас, чтобы форма записи
    реестра не менялась дважды.
    """

    resource_id: str
    version: int
    source: str
    path: Path


class AssetStore:
    """Склад чертежей поверх папки assets/ (ME-1.2).

    Порядок чтения: сначала общие каталоги, потом собственный каталог
    открытой кампании (campaign_id) — своя версия предмета перекрывает
    общую при одинаковом имени. Каталоги ДРУГИХ кампаний не загружаются:
    уникальные предметы кампании не видны остальным (спека §2).
    """

    def __init__(self, base_dir: Path | str, campaign_id: str | None = None) -> None:
        self._base = Path(base_dir)
        if campaign_id == _GLOBAL_CATALOGS_DIR:
            raise ValueError("campaign_id не может называться 'catalogs'")
        self._campaign_id = campaign_id
        self._blueprints: Dict[str, BlueprintRecord] = {}
        self._resources: Dict[str, ResourceRecord] = {}
        self._overrides: List[str] = []

    @property
    def base_dir(self) -> Path:
        return self._base

    @property
    def overrides(self) -> List[str]:
        """Список перекрытий вида 'имя: общий источник -> источник кампании'."""
        return list(self._overrides)

    def load(self) -> None:
        """Прочитать все каталоги. Нет папки — пустой склад, не ошибка."""
        self._blueprints.clear()
        self._resources.clear()
        self._overrides.clear()
        problems: List[str] = []
        if not self._base.is_dir():
            # Кампания без assets/ — законное состояние; чтение не создаёт папок
            logger.info("[ASSET_STORE] %s отсутствует — реестр пуст", self._base)
            return
        catalogs_dir = self._base / _GLOBAL_CATALOGS_DIR
        if catalogs_dir.is_dir():
            for catalog in sorted(catalogs_dir.iterdir()):
                if catalog.is_dir():
                    self._load_catalog(
                        catalog, f"{_SOURCE_GLOBAL}:{catalog.name}", problems
                    )
        # Приватность (спека §2): каталог кампании виден только самой кампании.
        # Склад строится в контексте ОДНОЙ открытой кампании; чужие каталоги
        # не загружаются — уникальные предметы не протекают наружу.
        if self._campaign_id is not None:
            own = self._base / self._campaign_id
            if own.is_dir():
                self._load_catalog(
                    own, f"{_SOURCE_CAMPAIGN}:{self._campaign_id}", problems
                )
        if problems:
            raise AssetStoreError(
                f"Битые чертежи/ресурсы в assets/ ({len(problems)}):\n  "
                + "\n  ".join(problems)
            )
        logger.info(
            "[ASSET_STORE] чертежей=%d, ресурсов=%d, перекрытий=%d",
            len(self._blueprints),
            len(self._resources),
            len(self._overrides),
        )

    def get_blueprint(self, blueprint_id: str) -> Optional[BlueprintRecord]:
        return self._blueprints.get(blueprint_id)

    def list_blueprints(self) -> List[str]:
        return sorted(self._blueprints.keys())

    def get_resource(self, resource_id: str) -> Optional[ResourceRecord]:
        return self._resources.get(resource_id)

    def list_resources(self) -> List[str]:
        return sorted(self._resources.keys())

    def stats(self) -> Tuple[int, int, int]:
        """(чертежей, ресурсов, перекрытий) — для проверок и отчёта."""
        return len(self._blueprints), len(self._resources), len(self._overrides)

    def _load_catalog(self, catalog_dir: Path, source: str, problems: List[str]) -> None:
        bp_dir = catalog_dir / _BLUEPRINTS_DIR
        if bp_dir.is_dir():
            for path in sorted(bp_dir.glob("*.json")):
                self._register_blueprint(path, source, problems)
        res_dir = catalog_dir / _RESOURCES_DIR
        if res_dir.is_dir():
            for path in sorted(res_dir.rglob("*")):
                if path.is_file() and path.suffix.lower() != ".json":
                    self._register_resource(path, res_dir, source, problems)

    def _register_blueprint(self, path: Path, source: str, problems: List[str]) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path}: не читается или битый JSON — {exc}")
            return
        if not isinstance(raw, dict):
            problems.append(
                f"{path}: чертёж обязан быть JSON-объектом, получен {type(raw).__name__}"
            )
            return
        for key in (_KEY_BLUEPRINT_ID, _KEY_VERSION, _KEY_COMPAT):
            if key not in raw:
                problems.append(f"{path}: нет обязательного поля '{key}'")
                return
        bid = raw[_KEY_BLUEPRINT_ID]
        if not isinstance(bid, str) or not bid:
            problems.append(f"{path}: поле 'blueprint_id' — непустая строка")
            return
        if bid != path.stem:
            # Реестровое правило: имя файла = blueprint_id (дополнение спеки §2)
            problems.append(
                f"{path}: blueprint_id '{bid}' не совпадает с именем файла '{path.stem}'"
            )
            return
        version = raw[_KEY_VERSION]
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            problems.append(f"{path}: поле 'version' — целое число >= 1")
            return
        compat = raw[_KEY_COMPAT]
        if not isinstance(compat, int) or isinstance(compat, bool) or compat < 1:
            problems.append(f"{path}: поле 'compat' — целое число >= 1")
            return
        record = BlueprintRecord(data=raw, version=version, source=source, path=path)
        self._put_blueprint(record, problems)

    def _put_blueprint(self, record: BlueprintRecord, problems: List[str]) -> None:
        existing = self._blueprints.get(record.blueprint_id)
        if existing is None:
            self._blueprints[record.blueprint_id] = record
            return
        new_is_campaign = record.source.startswith(_SOURCE_CAMPAIGN)
        old_is_campaign = existing.source.startswith(_SOURCE_CAMPAIGN)
        if new_is_campaign and not old_is_campaign:
            # Решение Мастера: своя версия предмета главнее общей
            self._overrides.append(
                f"{record.blueprint_id}: {existing.source} -> {record.source}"
            )
            self._blueprints[record.blueprint_id] = record
            return
        problems.append(
            f"{record.path}: два чертежа с именем '{record.blueprint_id}'"
            f" ({existing.source} и {record.source}) — переименуйте один"
        )

    def _register_resource(
        self, path: Path, res_root: Path, source: str, problems: List[str]
    ) -> None:
        rel = path.relative_to(res_root).with_suffix("")
        record = ResourceRecord(
            resource_id=rel.as_posix(), version=1, source=source, path=path
        )
        existing = self._resources.get(record.resource_id)
        if existing is None:
            self._resources[record.resource_id] = record
            return
        new_is_campaign = record.source.startswith(_SOURCE_CAMPAIGN)
        old_is_campaign = existing.source.startswith(_SOURCE_CAMPAIGN)
        if new_is_campaign and not old_is_campaign:
            self._overrides.append(
                f"ресурс {record.resource_id}: {existing.source} -> {record.source}"
            )
            self._resources[record.resource_id] = record
            return
        problems.append(
            f"{path}: два ресурса с именем '{record.resource_id}'"
            f" ({existing.source} и {record.source}) — переименуйте один"
        )

