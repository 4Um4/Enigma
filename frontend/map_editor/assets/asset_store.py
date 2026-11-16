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

import hashlib
import json
import logging
import os
import shutil
import time
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from assets.resource_formats import is_supported_format, normalize_format

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

# ME-2.1-H-2: Staging + lock константы
_STAGING_DIR = ".staging"
_STAGING_TMP_DIR = ".tmp"  # внутри _STAGING_DIR — для временных файлов регистрации
_STAGING_LOCKS_DIR = ".locks"  # внутри _STAGING_DIR — для lock-файлов


class AssetStoreError(RuntimeError):
    """Громкий отказ загрузки: перечень проблем с именем файла и поля.

    Загрузить половину и молча пропустить битое запрещено — это тихая потеря
    данных; поэтому все проблемы собираются в один пакет и поднимаются разом.
    """


@dataclass(frozen=True)
class BlueprintRecord:
    """Чертёж в реестре: данные + откуда прочитан.

    fingerprint — SHA256 байтов файла на момент load. Используется в
    save_blueprint_atomic (R2-уточнение Master) для ловли lost update:
    если внешний процесс изменил содержимое JSON, оставив version той же,
    fingerprint разойдётся → VersionConflict. Это дополняет memory
    version check (R5) и disk version check — последний ловит только
    изменение поля version, fingerprint ловит любое изменение байтов.
    """

    data: dict
    version: int
    source: str  # "global:<каталог>" | "campaign:<кампания>"
    path: Path
    fingerprint: str

    @property
    def blueprint_id(self) -> str:
        return str(self.data[_KEY_BLUEPRINT_ID])


class VersionConflict(Exception):
    """Файл чертежа изменён снаружи между открытием и сохранением (ME-2.1-G-1).

    Контракт: save_blueprint_atomic сравнивает (а) версию record с текущей в
    store (memory check, R5) и (б) fingerprint байтов файла на диске с
    record.fingerprint (disk check, R2-уточнение Master). Расхождение →
    VersionConflict. Master решает: reload или overwrite. Авто-overwrite
    запрещён (R5).

    R2-уточнение Master: version check ловит только инкремент version;
    fingerprint ловит любое изменение байтов (включая «version та же,
    содержимое другое» — lost update). Оба случая → VersionConflict с
    разным reason ('version' | 'fingerprint') для понятного сообщения.
    """

    def __init__(
        self,
        blueprint_id: str,
        expected_version: int,
        actual_version: int,
        *,
        reason: str = "version",
    ) -> None:
        self.blueprint_id = blueprint_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        self.reason = reason
        if reason == "fingerprint":
            msg = (
                f"Blueprint '{blueprint_id}' изменён снаружи (содержимое, "
                f"version та же v{expected_version}) — fingerprint разошёлся"
            )
        else:
            msg = (
                f"Blueprint '{blueprint_id}' изменён снаружи: ожидалась v{expected_version}, на диске v{actual_version}"
            )
        super().__init__(msg)


class SaveBlocked(Exception):
    """Сохранение заблокировано ошибками валидации (ME-2.1-G-1).

    Контракт: validator (передан извне, duck-typing) нашёл error-level issues.
    Save не выполняется, оригинал не трогается. issues — список объектов с
    атрибутом level (ValidationIssue из resource_validator.py).
    """

    def __init__(self, blueprint_id: str, issues: list) -> None:
        self.blueprint_id = blueprint_id
        self.issues = issues
        super().__init__(f"Save заблокирован для '{blueprint_id}': {len(issues)} error(s)")


@dataclass(frozen=True)
class SaveResult:
    """Результат атомарного сохранения чертежа (ME-2.1-G-1).

    Поля:
    - ok: True если файл записан и реестр пересобран
    - blueprint_id: какой чертёж сохранён
    - version: новая версия (int, из new_data после reload)
    - path: путь к файлу на диске
    - cache_stale: True если файл сохранён, реестр актуален, но внешний
      on_cache_refresh упал — производные кэши (CatalogIndex/OBJECT_PRESETS)
      устарели; реестр AssetStore актуален
    """

    ok: bool
    blueprint_id: str
    version: int
    path: Path
    cache_stale: bool = False


@dataclass(frozen=True)
class ResourceRecord:
    """Ресурс (визуальный): логический ID + физический файл.

    v2 (ME-2.1-H-2): добавлены format + fingerprint.
    - resource_id: логический путь без расширения (posix), "furniture/chair".
    - format: нормализованное расширение без точки, "png"/"jpg"/"jpeg" (lower).
    - fingerprint: SHA-256 байтов файла, вычисляется при load() и при save.
    """

    resource_id: str
    version: int  # всегда 1 в v1
    source: str  # "global:base" | "campaign:<id>"
    path: Path
    format: str  # НОВОЕ H-2: "png"/"jpg"/"jpeg"
    fingerprint: str  # НОВОЕ H-2: SHA-256 байтов файла


@dataclass(frozen=True)
class SaveResourceResult:
    """Результат атомарной регистрации ресурса (ME-2.1-H-2).

    Поля:
    - ok: True если файл опубликован и реестр пересобран.
    - resource_id: логический ID зарегистрированного ресурса.
    - path: путь к физическому файлу на диске.
    - format: нормализованный формат ("png"/"jpg"/"jpeg").
    - fingerprint: SHA-256 байтов файла (тот, что прошёл валидацию).
    - cache_stale: True если файл сохранён, реестр актуален, но внешний
      on_cache_refresh упал.
    """

    ok: bool
    resource_id: str
    path: Path
    format: str
    fingerprint: str
    cache_stale: bool = False


class ResourceRegistrationBusy(RuntimeError):
    """Lock на resource_id уже удерживается (другая регистрация, ME-2.1-H-2 C2).

    Контракт: OS-level advisory lock (fcntl.flock на POSIX, msvcrt.locking на
    Windows). Lock-файл остаётся на диске, но блокировка освобождается OS при
    завершении процесса. Stale-таймаута НЕТ — OS единственный арбитр.
    """

    def __init__(self, resource_id: str) -> None:
        self.resource_id = resource_id
        super().__init__(f"Регистрация '{resource_id}' уже выполняется (lock занят)")


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
        # ME-2.1-H-2: active staging paths (защита от cleanup_stale_staging)
        self._active_staging: set = set()

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
                    self._load_catalog(catalog, f"{_SOURCE_GLOBAL}:{catalog.name}", problems)
        # Приватность (спека §2): каталог кампании виден только самой кампании.
        # Склад строится в контексте ОДНОЙ открытой кампании; чужие каталоги
        # не загружаются — уникальные предметы не протекают наружу.
        if self._campaign_id is not None:
            own = self._base / self._campaign_id
            if own.is_dir():
                self._load_catalog(own, f"{_SOURCE_CAMPAIGN}:{self._campaign_id}", problems)
        if problems:
            raise AssetStoreError(f"Битые чертежи/ресурсы в assets/ ({len(problems)}):\n  " + "\n  ".join(problems))
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

    # ===== ME-2.1-G-1: Write-API =====
    #
    # Контракт ТЗ Master (G-1, п.1-6):
    # 1. Неизменность исходника — new_data не мутирует уже зарегистрированный record.
    # 2. Контроль версии — VersionConflict если файл изменён снаружи.
    # 3. Атомарность файловой записи — tmp → validate → test-load → rename.
    #    При ошибке исходный файл остаётся целым.
    # 4. Разделение файловой транзакции и обновления кэшей — AssetStore SSOT
    #    обновляется через load(); CatalogIndex/OBJECT_PRESETS — производные,
    #    обновляются через on_cache_refresh callback. ENTITY_SPRITE_MAP НЕ
    #    обновляется автоматически (по требованию Master: сначала доказать
    #    затрагивание).
    # 5. Не затрагивает экземпляры — сохранение Blueprint не меняет размещённые
    #    на карте объекты (R4 — дизайн).
    # 6. Не расширять G-1 — только фундамент записи, без UI/модалок/категорий.

    def save_blueprint_atomic(
        self,
        record: BlueprintRecord,
        new_data: dict,
        *,
        validator: Optional[Any] = None,
        on_cache_refresh: Optional[Callable[[], None]] = None,
    ) -> SaveResult:
        """Атомарное сохранение чертежа (ME-2.1-G-1).

        Args:
            record: BlueprintRecord, открытый через get_blueprint(). record.path
                определяет куда писать (source = global или campaign сохраняется).
            new_data: новый dict чертежа. НЕ мутирует record.data (deepcopy не нужна
                на стороне вызова — метод не трогает ни record, ни new_data после записи).
            validator: Optional, duck-typed объект с методом validate_blueprint(data)
                -> ValidationResult. Если передан и возвращает errors → SaveBlocked.
                AssetStore НЕ импортирует ResourceValidator (layering, Закон 1.2).
            on_cache_refresh: Optional callback, вызывается ПОСЛЕ успешного rename
                и self.load(). Внутри callback: CatalogIndex.refresh() +
                refresh_object_presets(store) (+ refresh_entity_sprite_map() если
                доказано затрагивание appearance.sprite). Если callback raises —
                файл уже сохранён, реестр актуален, но кэши устарели
                → SaveResult.cache_stale=True.

        Returns:
            SaveResult с ok=True и новой версией.

        Raises:
            VersionConflict: файл изменён снаружи (expected != actual version).
            SaveBlocked: validator нашёл error-level issues.
            AssetStoreError: test-load упал (битый JSON в tmp) — tmp удалён,
                оригинал цел.
        """
        bp_id = record.blueprint_id

        # 1. Валидация (если validator передан) — гейт перед файловой транзакцией
        if validator is not None:
            validation = validator.validate_blueprint(new_data)
            issues = getattr(validation, "issues", [])
            errors = [i for i in issues if getattr(i, "level", "") == "error"]
            if errors:
                raise SaveBlocked(bp_id, errors)

        # 2. Контроль версии (R5) — record.version должен совпадать с текущим store
        current = self._blueprints.get(bp_id)
        if current is None:
            raise AssetStoreError(f"Blueprint '{bp_id}' не найден в реестре — save невозможен")
        if current.version != record.version:
            raise VersionConflict(bp_id, record.version, current.version)

        # 2b. Проверка внешнего изменения файла (R2-уточнение Master).
        #    version check ловит только инкремент version; fingerprint ловит
        #    любое изменение байтов (включая «version та же, содержимое другое» —
        #    lost update). Считаем SHA256 байтов файла на диске и сравниваем
        #    с record.fingerprint (вычислен при load). Дополняет memory check (2).
        try:
            disk_bytes = record.path.read_bytes()
        except OSError as exc:
            raise AssetStoreError(f"Не удалось прочитать '{record.path}' для проверки fingerprint: {exc}") from exc
        disk_fingerprint = hashlib.sha256(disk_bytes).hexdigest()
        if disk_fingerprint != record.fingerprint:
            # Извлечь disk_version для понятного сообщения (best-effort)
            try:
                raw_on_disk = json.loads(disk_bytes.decode("utf-8-sig"))
                disk_version = raw_on_disk.get(_KEY_VERSION, record.version)
            except (json.JSONDecodeError, UnicodeDecodeError):
                disk_version = record.version
            raise VersionConflict(bp_id, record.version, disk_version, reason="fingerprint")

        # 3. Контракт реестра: имя файла = blueprint_id (rule спеки §2)
        #    Rename blueprint_id запрещён в v1 (ТЗ Master п.6 «не расширять G-1»)
        new_bp_id = new_data.get(_KEY_BLUEPRINT_ID)
        if new_bp_id != bp_id:
            raise AssetStoreError(
                f"blueprint_id изменён ('{bp_id}' -> '{new_bp_id}') — rename запрещён в v1 (ТЗ Master п.6)"
            )

        # 4. Запись в tmp (utf-8 без BOM; _register_blueprint читает utf-8-sig,
        #    толерантен к BOM и без BOM; стандарт JSON — без BOM).
        #    tmp_path.stem ДОЛЖЕН совпадать с target_path.stem — правило реестра
        #    «имя файла = blueprint_id» (asset_store.py:188, _register_blueprint).
        #    with_suffix(".tmp") даёт stem="door" из "door.json" → "door.tmp";
        #    with_suffix(".json.tmp") дало бы stem="door.json" → test-load упадёт.
        target_path = record.path
        tmp_path = target_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(
                json.dumps(new_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            raise AssetStoreError(f"Не удалось записать tmp-файл '{tmp_path}': {exc}") from exc

        # 5. Test-load tmp через изолированный _register_blueprint
        #    НЕ self.load() — чтобы чужой битый файл не блокировал save нашего
        problems: List[str] = []
        test_store = AssetStore.__new__(AssetStore)
        test_store._base = self._base
        test_store._campaign_id = self._campaign_id
        test_store._blueprints = {}
        test_store._resources = {}
        test_store._overrides = []
        test_store._register_blueprint(tmp_path, "test", problems)
        if problems:
            # tmp битый — удаляем, оригинал цел
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise AssetStoreError(f"Test-load tmp упал для '{bp_id}':\n  " + "\n  ".join(problems))

        # 6. .history/<id>.<old_version>.json — копия оригинала (best-effort)
        #    Не блокирует save; .history/ игнорируется при load (фильтр glob *.json
        #    в _load_catalog не заходит в подпапки)
        history_dir = target_path.parent / ".history"
        history_path = history_dir / f"{bp_id}.{record.version}.json"
        try:
            history_dir.mkdir(exist_ok=True)
            history_path.write_bytes(target_path.read_bytes())
        except OSError as exc:
            logger.warning("[ASSET_STORE] .history не записан для '%s': %s", bp_id, exc)

        # 7. Backup оригинала в памяти для recovery (R1 — Master контрольный вопрос).
        #    После replace() оригинал перезаписан; если load() упадёт — восстановим.
        original_bytes = target_path.read_bytes()

        # 8. Atomic rename: tmp → target (pathlib.Path.replace = POSIX rename /
        #    Windows MoveFileEx MOVEFILE_REPLACE_EXISTING — атомарно на одной ФС)
        try:
            tmp_path.replace(target_path)
        except OSError as exc:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise AssetStoreError(f"Atomic rename упал для '{bp_id}': {exc}") from exc

        # 9. Пересборка реестра с recovery (R1 — Master контрольный вопрос).
        #    Snapshot до load; при ошибке — восстановить файл + реестр.
        #    Сценарий: другой файл в каталоге стал битым одновременно с нашим save;
        #    load() пересобирает ВСЕ blueprints и падает на чужом файле.
        #    Recovery: восстановить наш оригинал (файловая консистентность) +
        #    реестр из snapshot (pre-save состояние). SaveResult не возвращается.
        _old_blueprints = dict(self._blueprints)
        _old_resources = dict(self._resources)
        _old_overrides = list(self._overrides)
        try:
            self.load()
        except Exception as reload_exc:
            # Восстановить оригинал файла
            try:
                target_path.write_bytes(original_bytes)
            except OSError as restore_exc:
                logger.error(
                    "[ASSET_STORE] CRITICAL: restore упал для '%s': %s — "
                    "файл может быть неконсистентен, см. .history/%s.%d.json",
                    bp_id,
                    restore_exc,
                    bp_id,
                    record.version,
                )
            # Восстановить реестр из snapshot (pre-save состояние)
            self._blueprints = _old_blueprints
            self._resources = _old_resources
            self._overrides = _old_overrides
            raise AssetStoreError(
                f"Reload упал после rename для '{bp_id}'. "
                f"Оригинал восстановлен, реестр в pre-save состоянии: {reload_exc}"
            ) from reload_exc

        # 10. Внешний refresh кэшей (CatalogIndex + OBJECT_PRESETS + опц. ENTITY_SPRITE_MAP)
        #     Файл уже сохранён; если refresh упадёт — кэши устарели, реестр актуален
        cache_stale = False
        if on_cache_refresh is not None:
            try:
                on_cache_refresh()
            except Exception as exc:  # noqa: BLE001 — внешний callback
                logger.warning(
                    "[ASSET_STORE] cache refresh упал для '%s': %s — файл сохранён, реестр актуален, кэши устарели",
                    bp_id,
                    exc,
                )
                cache_stale = True

        new_record = self._blueprints.get(bp_id)
        new_version = new_record.version if new_record is not None else int(new_data.get(_KEY_VERSION, record.version))

        return SaveResult(
            ok=True,
            blueprint_id=bp_id,
            version=new_version,
            path=target_path,
            cache_stale=cache_stale,
        )

    def save_new_blueprint_atomic(
        self,
        new_id: str,
        new_data: dict,
        *,
        validator: Optional[Any] = None,
        on_cache_refresh: Optional[Callable[[], None]] = None,
    ) -> SaveResult:
        """Атомарное создание нового Blueprint (ME-2.1-G-8).

        Вариант (a) Master: отдельная операция, не маскировать создание
        под обновление. Не дублирует транзакцию G-1 — общая последовательность
        write→test-load→rename→reload.

        Защита от гонки: target_path.exists() проверяется ПЕРЕД rename.
        Если файл создан другой сессией между проверкой list_blueprints и
        rename — откажем без перезаписи.

        Args:
            new_id: blueprint_id нового чертежа (slug, без / и ..).
            new_data: dict чертежа. blueprint_id ДОЛЖЕН == new_id.
            validator: Optional duck-typed.
            on_cache_refresh: Optional callback.

        Raises:
            AssetStoreError: ID недопустим, уже существует, или ошибка записи.
            SaveBlocked: validator нашёл errors.
        """
        import re

        # 1. Проверка допустимости ID
        if not isinstance(new_id, str) or not new_id:
            raise AssetStoreError("new_id должен быть непустой строкой")
        if not re.match(r"^[a-zA-Z0-9_]+$", new_id):
            raise AssetStoreError(f"new_id '{new_id}' недопустим — только латиница, цифры, _")
        if "/" in new_id or "\\" in new_id or ".." in new_id:
            raise AssetStoreError(f"new_id '{new_id}' содержит запрещённые символы")

        # 2. Проверка blueprint_id в new_data
        actual_id = new_data.get(_KEY_BLUEPRINT_ID)
        if actual_id != new_id:
            raise AssetStoreError(f"blueprint_id в new_data ('{actual_id}') != new_id ('{new_id}')")

        # 3. Ранняя проверка уникальности
        if new_id in self._blueprints:
            raise AssetStoreError(f"Blueprint '{new_id}' уже существует в реестре")

        # 4. Валидация
        if validator is not None:
            validation = validator.validate_blueprint(new_data)
            issues = getattr(validation, "issues", [])
            errors = [i for i in issues if getattr(i, "level", "") == "error"]
            if errors:
                raise SaveBlocked(new_id, errors)

        # 5. Определить target_path (global catalogs/base/blueprints/)
        target_path = self._base / _GLOBAL_CATALOGS_DIR / "base" / _BLUEPRINTS_DIR / f"{new_id}.json"

        # 6. Гонка: проверить что файл не существует ПЕРЕД записью
        if target_path.exists():
            raise AssetStoreError(f"Файл '{target_path}' уже существует — race condition или внешний процесс")

        # 7. Запись в tmp
        tmp_path = target_path.with_suffix(".tmp")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp_path.write_text(
                json.dumps(new_data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            raise AssetStoreError(f"Не удалось записать tmp '{tmp_path}': {exc}") from exc

        # 8. Test-load tmp
        problems: List[str] = []
        test_store = AssetStore.__new__(AssetStore)
        test_store._base = self._base
        test_store._campaign_id = self._campaign_id
        test_store._blueprints = {}
        test_store._resources = {}
        test_store._overrides = []
        test_store._register_blueprint(tmp_path, "test", problems)
        if problems:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise AssetStoreError(f"Test-load tmp упал для '{new_id}':\n  " + "\n  ".join(problems))

        # 9. Гонка: повторная проверка перед rename
        if target_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise AssetStoreError(f"Файл '{target_path}' создан другой сессией — отказ без перезаписи")

        # 10. Atomic rename (нет оригинала — нет backup/recovery оригинала)
        try:
            tmp_path.replace(target_path)
        except OSError as exc:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise AssetStoreError(f"Atomic rename упал для '{new_id}': {exc}") from exc

        # 11. Пересборка реестра с recovery (как G-1, но нет original_bytes)
        _old_blueprints = dict(self._blueprints)
        _old_resources = dict(self._resources)
        _old_overrides = list(self._overrides)
        try:
            self.load()
        except Exception as reload_exc:
            # Удалить новый файл (он единственный мог сломать load)
            try:
                target_path.unlink(missing_ok=True)
            except OSError:
                pass
            # Восстановить реестр из snapshot
            self._blueprints = _old_blueprints
            self._resources = _old_resources
            self._overrides = _old_overrides
            raise AssetStoreError(
                f"Reload упал после создания '{new_id}'. Файл удалён, реестр в pre-create состоянии: {reload_exc}"
            ) from reload_exc

        # 12. Cache refresh
        cache_stale = False
        if on_cache_refresh is not None:
            try:
                on_cache_refresh()
            except Exception as exc:
                logger.warning("[ASSET_STORE] cache refresh упал для '%s': %s", new_id, exc)
                cache_stale = True

        new_version = int(new_data.get(_KEY_VERSION, 1))

        return SaveResult(
            ok=True,
            blueprint_id=new_id,
            version=new_version,
            path=target_path,
            cache_stale=cache_stale,
        )

    def _load_catalog(self, catalog_dir: Path, source: str, problems: List[str]) -> None:
        bp_dir = catalog_dir / _BLUEPRINTS_DIR
        if bp_dir.is_dir():
            for path in sorted(bp_dir.glob("*.json")):
                self._register_blueprint(path, source, problems)
        res_dir = catalog_dir / _RESOURCES_DIR
        if res_dir.is_dir():
            for path in sorted(res_dir.rglob("*")):
                if path.is_file() and is_supported_format(path.suffix):
                    self._register_resource(path, res_dir, source, problems)

    def _register_blueprint(self, path: Path, source: str, problems: List[str]) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path}: не читается или битый JSON — {exc}")
            return
        if not isinstance(raw, dict):
            problems.append(f"{path}: чертёж обязан быть JSON-объектом, получен {type(raw).__name__}")
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
            problems.append(f"{path}: blueprint_id '{bid}' не совпадает с именем файла '{path.stem}'")
            return
        version = raw[_KEY_VERSION]
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            problems.append(f"{path}: поле 'version' — целое число >= 1")
            return
        compat = raw[_KEY_COMPAT]
        if not isinstance(compat, int) or isinstance(compat, bool) or compat < 1:
            problems.append(f"{path}: поле 'compat' — целое число >= 1")
            return
        fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
        record = BlueprintRecord(
            data=raw,
            version=version,
            source=source,
            path=path,
            fingerprint=fingerprint,
        )
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
            self._overrides.append(f"{record.blueprint_id}: {existing.source} -> {record.source}")
            self._blueprints[record.blueprint_id] = record
            return
        problems.append(
            f"{record.path}: два чертежа с именем '{record.blueprint_id}'"
            f" ({existing.source} и {record.source}) — переименуйте один"
        )

    def _register_resource(self, path: Path, res_root: Path, source: str, problems: List[str]) -> None:
        rel = path.relative_to(res_root).with_suffix("")
        resource_id = rel.as_posix()
        fmt = normalize_format(path.suffix)
        try:
            fingerprint = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            problems.append(f"{path}: не читается для fingerprint — {exc}")
            return
        record = ResourceRecord(
            resource_id=resource_id,
            version=1,
            source=source,
            path=path,
            format=fmt,
            fingerprint=fingerprint,
        )
        existing = self._resources.get(record.resource_id)
        if existing is None:
            self._resources[record.resource_id] = record
            return
        new_is_campaign = record.source.startswith(_SOURCE_CAMPAIGN)
        old_is_campaign = existing.source.startswith(_SOURCE_CAMPAIGN)
        if new_is_campaign and not old_is_campaign:
            self._overrides.append(f"ресурс {record.resource_id}: {existing.source} -> {record.source}")
            self._resources[record.resource_id] = record
            return
        problems.append(
            f"{path}: два ресурса с именем '{record.resource_id}'"
            f" ({existing.source} и {record.source}) — переименуйте один"
        )

    def _validate_resource_id(self, resource_id: str) -> str:
        """ME-2.1-H-2: Валидация логического resource_id (G3 + C4).

        Контракт:
        - isinstance(str) + non-empty
        - absolute check ДО нормализации (C4): запрет / \\ в начале, drive letter
        - NFC normalisation (Unicode визуально одинаковые → один ID)
        - нормализация разделителей: \\ → /
        - запрет любого компонента "..", ".", ""
        - запрет управляющих символов (< 0x20, NUL)
        - canonical check: путь внутри target resources/

        Returns:
            Нормализованный posix path (NFC, без ведущих/завершающих /).

        Raises:
            AssetStoreError: если ID недопустим.
        """
        if not isinstance(resource_id, str) or not resource_id:
            raise AssetStoreError("resource_id должен быть непустой строкой")

        # C4: absolute check ДО нормализации (strip может убрать ведущий /)
        if resource_id.startswith("/") or resource_id.startswith("\\"):
            raise AssetStoreError(f"resource_id '{resource_id}' недопустим — абсолютный путь запрещён")
        if len(resource_id) >= 2 and resource_id[1] == ":":
            raise AssetStoreError(f"resource_id '{resource_id}' недопустим — Windows drive letter запрещён")

        # NFC normalisation (Unicode визуально одинаковые → один ID)
        normalized = unicodedata.normalize("NFC", resource_id)

        # Запрет управляющих символов (NUL, < 0x20)
        for i, c in enumerate(normalized):
            if ord(c) < 0x20:
                raise AssetStoreError(f"resource_id содержит управляющий символ (code={ord(c)}) на позиции {i}")

        # Нормализация разделителей + разбор на компоненты
        parts = normalized.replace("\\", "/").strip("/").split("/")

        # Запрет любого компонента "..", ".", ""
        for part in parts:
            if part in ("", ".", ".."):
                raise AssetStoreError(f"resource_id '{resource_id}' содержит недопустимый компонент: '{part}'")

        if not parts:
            raise AssetStoreError(f"resource_id '{resource_id}' пуст после нормализации")

        return "/".join(parts)

    # ===== ME-2.1-H-2: Staging + Lock + Atomic Registration =====

    def _staging_root(self) -> Path:
        """Корень staging: self._base / .staging/."""
        return self._base / _STAGING_DIR

    def _staging_tmp_root(self) -> Path:
        """Каталог для временных файлов регистрации: .staging/.tmp/."""
        return self._staging_root() / _STAGING_TMP_DIR

    def _staging_lock_root(self) -> Path:
        """Каталог для lock-файлов: .staging/.locks/."""
        return self._staging_root() / _STAGING_LOCKS_DIR

    def prepare_staging(self, source_path: Path) -> Path:
        """ME-2.1-H-2: Копировать source_path в assets/.staging/<uuid>.<ext>.

        Caller валидирует staging_path (через ResourceValidator.validate_resource),
        затем передаёт в save_new_resource_atomic. Staging НЕ очищается
        автоматически при load() — явная операция cleanup_stale_staging.

        Args:
            source_path: путь к исходному файлу (внешний, не в assets/).

        Returns:
            staging_path внутри assets/.staging/.

        Raises:
            AssetStoreError: если source_path не существует или не читается.
        """
        staging_dir = self._staging_root()
        staging_dir.mkdir(parents=True, exist_ok=True)
        if not source_path.is_file():
            raise AssetStoreError(f"source_path не существует или не файл: {source_path}")
        ext = source_path.suffix.lower()
        staging_path = staging_dir / f"{uuid.uuid4().hex}{ext}"
        try:
            shutil.copy2(source_path, staging_path)
        except OSError as exc:
            raise AssetStoreError(f"Не удалось скопировать в staging: {exc}") from exc
        return staging_path

    def cancel_staging(self, staging_path: Path) -> None:
        """ME-2.1-H-2: Удалить staging-файл. R2-защита: path внутри .staging/.

        Raises:
            AssetStoreError: если staging_path вне .staging/.
        """
        staging_root = self._staging_root().resolve()
        try:
            staging_path.resolve().relative_to(staging_root)
        except ValueError:
            raise AssetStoreError(f"Staging path вне .staging/: {staging_path}")
        try:
            staging_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("[ASSET_STORE] cancel_staging: %s", exc)

    def cleanup_stale_staging(self, max_age_seconds: int = 86400) -> int:
        """ME-2.1-H-2: Удалить staging-файлы старше max_age.

        Уточнение 1: пропускает активные staging-файлы (из self._active_staging).
        Не трогает .locks/ и .tmp/ (управляются отдельно).

        Args:
            max_age_seconds: максимальный возраст файла в секундах (default 24h).

        Returns:
            Количество удалённых файлов.
        """
        staging_dir = self._staging_root()
        if not staging_dir.is_dir():
            return 0
        now = time.time()
        count = 0
        for f in staging_dir.iterdir():
            if not f.is_file():
                continue
            # Пропустить активные staging (используются в save_new_resource_atomic)
            if f in self._active_staging:
                continue
            try:
                age = now - f.stat().st_mtime
            except OSError:
                continue
            if age > max_age_seconds:
                try:
                    f.unlink()
                    count += 1
                except OSError:
                    pass
        return count

    def _acquire_resource_lock(self, resource_id: str) -> tuple:
        """ME-2.1-H-2 C2: OS-level advisory lock на resource_id.

        Lock-файл: .staging/.locks/sha256(resource_id).hex[:16].lock
        (SHA-256 от ID, не replace('/', '__') — устраняет коллизию имён).

        POSIX: fcntl.flock(LOCK_EX | LOCK_NB) — non-blocking, OS auto-release.
        Windows: msvcrt.locking(LK_NBLCK) — non-blocking, OS auto-release.

        Lock-файл НЕ удаляется после использования — OS освобождает блокировку,
        файл остаётся (без блокировки). Следующий acquire открывает тот же файл.

        Returns:
            Кортеж (lock_file_handle, lock_path). Handle ДОЛЖЕН быть открытым
            пока блокировка удерживается (flock/locking привязаны к descriptor).

        Raises:
            ResourceRegistrationBusy: если lock уже удерживается.
            AssetStoreError: если не удалось создать/открыть lock-файл.
        """
        lock_dir = self._staging_lock_root()
        lock_dir.mkdir(parents=True, exist_ok=True)
        id_hash = hashlib.sha256(resource_id.encode("utf-8")).hexdigest()[:16]
        lock_path = lock_dir / f"{id_hash}.lock"

        try:
            lock_fh = open(lock_path, "a+b")
        except OSError as exc:
            raise AssetStoreError(f"Не удалось открыть lock-файл '{lock_path}': {exc}") from exc

        import sys

        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                lock_fh.close()
                raise ResourceRegistrationBusy(resource_id) from exc
        else:
            import fcntl

            try:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                lock_fh.close()
                raise ResourceRegistrationBusy(resource_id) from exc

        return (lock_fh, lock_path)

    def _release_resource_lock(self, lock_handle: tuple) -> None:
        """ME-2.1-H-2 C2: Освободить OS-level lock.

        Args:
            lock_handle: кортеж (lock_file_handle, lock_path) из _acquire_resource_lock.
        """
        lock_fh, _lock_path = lock_handle
        import sys

        if sys.platform == "win32":
            import msvcrt

            try:
                lock_fh.seek(0)
                msvcrt.locking(lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError as exc:
                logger.warning("[ASSET_STORE] lock release (msvcrt) упал: %s", exc)
        else:
            import fcntl

            try:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            except OSError as exc:
                logger.warning("[ASSET_STORE] lock release (fcntl) упал: %s", exc)

        try:
            lock_fh.close()
        except OSError:
            pass

    def save_new_resource_atomic(
        self,
        staging_path: Path,
        resource_id: str,
        *,
        validator: Any,
        on_cache_refresh: Callable[[], None] | None = None,
    ) -> SaveResourceResult:
        """ME-2.1-H-2: Атомарная регистрация нового ресурса (16 шагов, C1-C5).

        Контракты:
        - C1: os.link (без перезаписи) — атомарная публикация
        - C2: fcntl/msvcrt advisory lock (OS auto-release)
        - C3: 7-step fingerprint (fp1 → validate → fp2 → copy → fp_tmp → compare)
        - C4: _validate_resource_id (absolute до strip, NFC, Unicode)
        - C5: tmp в .staging/.tmp/ (правильный resource_id при test-load)
        - Поправка C: override-aware коллизии
        - Поправка B: recovery _blueprints + _resources + _overrides

        Args:
            staging_path: путь к staged-файлу в assets/.staging/.
            resource_id: логический ID (posix path без расширения, Unicode).
            validator: ОБЯЗАТЕЛЬНЫЙ duck-typed объект с методом
                validate_resource(path) -> ResourceValidationResult.
            on_cache_refresh: Optional callback после успешной регистрации.

        Raises:
            AssetStoreError: ID недопустим, staging вне .staging/, ошибка записи,
                recovery неудачен, TOCTOU (staging изменён).
            SaveBlocked: validator.validate_resource нашёл errors.
            ResourceRegistrationBusy: lock не получен.
        """
        # Шаг 0: R2-защита — staging_path внутри .staging/
        staging_root = self._staging_root().resolve()
        try:
            staging_path.resolve().relative_to(staging_root)
        except ValueError:
            raise AssetStoreError(f"staging_path вне .staging/: {staging_path}")
        # Не включаем .tmp/ и .locks/ как staging
        tmp_root = self._staging_tmp_root().resolve()
        try:
            staging_path.resolve().relative_to(tmp_root)
            raise AssetStoreError(f"staging_path в .tmp/ (недопустимо): {staging_path}")
        except ValueError:
            pass  # OK — не в .tmp/
        if not staging_path.is_file():
            raise AssetStoreError(f"staging_path не существует: {staging_path}")

        # Шаг 1: Валидация resource_id (G3 + C4)
        normalized_id = self._validate_resource_id(resource_id)

        # Шаг 2: C3 — fingerprint_staged (фиксация содержимого для TOCTOU)
        try:
            fp1 = hashlib.sha256(staging_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise AssetStoreError(f"Не удалось прочитать staging для fingerprint: {exc}") from exc

        # Шаг 3: Валидация (validator ОБЯЗАТЕЛЕН, не Optional — C3)
        if validator is None:
            raise AssetStoreError("validator обязателен для save_new_resource_atomic (C3)")
        validation = validator.validate_resource(staging_path)
        issues = getattr(validation, "issues", [])
        errors = [i for i in issues if getattr(i, "level", "") == "error"]
        if errors:
            raise SaveBlocked(normalized_id, errors)

        # Шаг 4: C3 — повторный fingerprint после валидации
        try:
            fp2 = hashlib.sha256(staging_path.read_bytes()).hexdigest()
        except OSError as exc:
            raise AssetStoreError(f"Не удалось прочитать staging (post-validate): {exc}") from exc
        if fp1 != fp2:
            raise AssetStoreError(
                f"TOCTOU: staging '{staging_path}' изменён во время валидации (fp1={fp1[:8]}.. fp2={fp2[:8]}..)"
            )

        # Шаг 5: Определить target_source и target_path (G6 — из campaign_id)
        if self._campaign_id is None:
            target_source = f"{_SOURCE_GLOBAL}:base"
            target_dir = self._base / _GLOBAL_CATALOGS_DIR / "base" / _RESOURCES_DIR
        else:
            target_source = f"{_SOURCE_CAMPAIGN}:{self._campaign_id}"
            target_dir = self._base / self._campaign_id / _RESOURCES_DIR

        fmt = normalize_format(staging_path.suffix)
        if not fmt:
            raise AssetStoreError(f"Не удалось определить формат из staging: {staging_path.suffix}")

        # target_path: target_dir / <resource_id с / → os.sep> . <format>
        id_path_parts = normalized_id.split("/")
        target_path = target_dir.joinpath(*id_path_parts).with_suffix(f".{fmt}")

        # Шаг 6: Приобрести блокировку (C2) + добавить staging в active
        lock_handle = self._acquire_resource_lock(normalized_id)
        self._active_staging.add(staging_path)
        try:
            # Шаг 7: Override-aware коллизии (поправка C)
            existing = self._resources.get(normalized_id)
            if existing is not None:
                existing_is_campaign = existing.source.startswith(_SOURCE_CAMPAIGN)
                target_is_campaign = target_source.startswith(_SOURCE_CAMPAIGN)
                if existing_is_campaign == target_is_campaign:
                    raise AssetStoreError(f"Ресурс '{normalized_id}' уже существует в {target_source}")
                if existing_is_campaign and not target_is_campaign:
                    raise AssetStoreError(
                        f"Ресурс '{normalized_id}' существует в campaign — global импорт не может перезаписать"
                    )
                # existing global, target campaign → override разрешён

            # Шаг 8: Гонка — target_path.exists() (первая проверка)
            if target_path.exists():
                raise AssetStoreError(f"Файл '{target_path}' уже существует — race condition или внешний процесс")

            # Шаг 9: C5 — копирование staging → tmp (в .staging/.tmp/, не target+.tmp)
            tmp_dir = self._staging_tmp_root()
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_name = normalized_id.replace("/", "__") + f".{fmt}"
            tmp_path = tmp_dir / tmp_name
            try:
                shutil.copy2(staging_path, tmp_path)
            except OSError as exc:
                raise AssetStoreError(f"Не удалось скопировать staging в tmp: {exc}") from exc

            # Шаг 10: C3 — fingerprint tmp (должен совпадать с fp2)
            try:
                fp_tmp = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
            except OSError as exc:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise AssetStoreError(f"Не удалось прочитать tmp для fingerprint: {exc}") from exc
            if fp_tmp != fp2:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise AssetStoreError(
                    f"TOCTOU: tmp '{tmp_path}' отличается от staging (fp2={fp2[:8]}.. fp_tmp={fp_tmp[:8]}..)"
                )

            # Шаг 11: Test-load tmp через изолированный _register_resource (C5)
            problems: List[str] = []
            test_store = AssetStore.__new__(AssetStore)
            test_store._base = self._base
            test_store._campaign_id = self._campaign_id
            test_store._blueprints = {}
            test_store._resources = {}
            test_store._overrides = []
            test_store._active_staging = set()
            test_store._register_resource(tmp_path, tmp_dir, "test", problems)
            if problems:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise AssetStoreError(f"Test-load tmp упал для '{normalized_id}':\n  " + "\n  ".join(problems))

            # C5: проверить что test-load зарегистрировал правильный resource_id
            test_record = test_store._resources.get(normalized_id)
            if test_record is None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                registered_ids = list(test_store._resources.keys())
                raise AssetStoreError(
                    f"Test-load tmp зарегистрировал неправильный ID: "
                    f"ожидался '{normalized_id}', получено {registered_ids}"
                )

            # Шаг 12: Гонка — повторная проверка target_path.exists()
            if target_path.exists():
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise AssetStoreError(f"Файл '{target_path}' создан другой сессией — отказ без перезаписи")

            # Шаг 13: C1 — атомарная публикация через os.link (без перезаписи)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            created_by_us = not target_path.exists()
            try:
                os.link(tmp_path, target_path)
            except FileExistsError as exc:
                raise AssetStoreError(
                    f"Файл '{target_path}' создан конкурентной операцией — отказ без перезаписи"
                ) from exc
            except OSError as exc:
                raise AssetStoreError(f"Atomic link упал для '{normalized_id}': {exc}") from exc
            finally:
                # tmp больше не нужен (hard link target указывает на те же байты)
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

            # Шаг 14: Пересборка реестра с ПОЛНЫМ recovery (поправка B)
            _old_blueprints = dict(self._blueprints)
            _old_resources = dict(self._resources)
            _old_overrides = list(self._overrides)
            try:
                self.load()
            except Exception as reload_exc:
                # Удалить ТОЛЬКО файл, созданный этой транзакцией
                if created_by_us:
                    try:
                        target_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                # Восстановить ВСЕ изменяемые load() поля
                self._blueprints = _old_blueprints
                self._resources = _old_resources
                self._overrides = _old_overrides
                raise AssetStoreError(
                    f"Reload упал после регистрации '{normalized_id}'. "
                    f"Файл {'удалён' if created_by_us else 'не удалён (существовал до)'}, "
                    f"реестр восстановлен: {reload_exc}"
                ) from reload_exc

            # Шаг 15: Cache refresh callback
            cache_stale = False
            if on_cache_refresh is not None:
                try:
                    on_cache_refresh()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[ASSET_STORE] cache refresh упал для '%s': %s",
                        normalized_id,
                        exc,
                    )
                    cache_stale = True

            # Шаг 16: Вернуть результат
            return SaveResourceResult(
                ok=True,
                resource_id=normalized_id,
                path=target_path,
                format=fmt,
                fingerprint=fp2,
                cache_stale=cache_stale,
            )
        finally:
            # Освободить блокировку (C2) + убрать staging из active
            self._release_resource_lock(lock_handle)
            self._active_staging.discard(staging_path)
