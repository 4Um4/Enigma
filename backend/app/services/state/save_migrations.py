"""
path: backend/app/services/state/save_migrations.py
Назначение: лестница payload-миграций сейва campaign_state.json (COV-D59,
ADR-O-426 Шаг 2; вердикты Мастера В1-В8): чистые миграторы + верификация +
файловая процедура «детект-и-мигрировать» (.pre-migration.bak, В6) +
version-aware хелперы читателей (В4).
Зависимости: app.services.state.save_format_detector
Основные сущности: migrate_payload_to_v1, migrate_save_file_if_needed,
SaveMigrationOutcome, extract_scene_payload, resolve_current_location
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from app.services.state.save_format_detector import (
    CURRENT,
    REASON_CORRUPT_JSON,
    REASON_INCONSISTENT_V1,
    REASON_INVALID_SCENES,
    REASON_INVALID_V0,
    REASON_NEWER_VERSION,
    REASON_NOT_DICT,
    REASON_UNKNOWN_FORMAT,
    REASON_UNKNOWN_VERSION,
    SAVE_SCHEMA_VERSION,
    SOURCE_V0_SINGLE,
    SOURCE_V1_UNSTAMPED,
    UNMIGRABLE,
    classify_parsed_save,
    detect_save_format,
)

logger = logging.getLogger(__name__)

_BACKUP_SUFFIX = ".pre-migration.bak"
_TMP_SUFFIX = ".migration-tmp"
_MISSING = object()

# Исходы файловой процедуры (статусы ответа загрузки — в campaign_lifecycle)
STATUS_NOT_FOUND = "not_found"
STATUS_CURRENT = "current"
STATUS_MIGRATED = "migrated"
STATUS_REFUSED = "refused"

# Игрокочитаемые тексты отказа (В7): не маскировать потерю данных, если
# исходник сохранён; не предлагать новую игру как единственный выход.
_REFUSAL_TEXTS = {
    REASON_CORRUPT_JSON: "файл сохранения повреждён и не может быть прочитан",
    REASON_NOT_DICT: "файл сохранения имеет неожиданную структуру",
    REASON_NEWER_VERSION: "сохранение создано более новой версией игры",
    REASON_UNKNOWN_VERSION: "версия формата сохранения не поддерживается этой версией игры",
    REASON_UNKNOWN_FORMAT: "формат сохранения не распознан",
    REASON_INVALID_V0: "структура сохранения не соответствует старому формату",
    REASON_INVALID_SCENES: "структура сцен сохранения повреждена",
    REASON_INCONSISTENT_V1: (
        "сохранение внутренне противоречиво: заявленная версия не совпадает "
        "со структурой"
    ),
    "BACKUP_CONFLICT": (
        "резервная копия .pre-migration.bak уже существует и отличается от "
        "исходника — автоматическая перезапись запрещена"
    ),
}

_REFUSAL_TAIL = (
    " Исходный файл сохранён без изменений. Начните новую игру или "
    "восстановите резервную копию файла, если она у вас есть."
)


@dataclass(frozen=True)
class SaveMigrationOutcome:
    """Исход файловой процедуры (status ∈ not_found|current|migrated|refused)."""

    status: str
    state_file: Path
    reason: Optional[str] = None
    refusal_text: Optional[str] = None
    backup_file: Optional[Path] = None


def _refuse(state_file: Path, reason: str) -> SaveMigrationOutcome:
    text = _REFUSAL_TEXTS.get(reason, "формат сохранения не поддерживается")
    return SaveMigrationOutcome(
        status=STATUS_REFUSED,
        state_file=state_file,
        reason=reason,
        refusal_text=f"Сохранение не может быть безопасно загружено: {text}.{_REFUSAL_TAIL}",
    )


# ── Чистые миграторы (лестница: сегодня v0 → v1) ──────────────────────────

def migrate_payload_to_v1(data: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Чистая конвертация распознанного формата в v1 (без I/O).

    V0_SINGLE: scenes = {location_id | 'default': scene_state}.
    V1_UNSTAMPED: scenes как есть (scenes — истина; легаси-ключ не переносится).
    Все прочие top-level ключи (вкл. metadata) копируются as-is (В2).
    """
    result: Dict[str, Any] = {k: v for k, v in data.items() if k != "scene_state"}
    if source == SOURCE_V0_SINGLE:
        scene = data["scene_state"]
        result["scenes"] = {scene.get("location_id", "default"): scene}
    elif source != SOURCE_V1_UNSTAMPED:
        raise ValueError(f"Неизвестный источник миграции: {source!r}")
    result["schema_version"] = SAVE_SCHEMA_VERSION
    return result


def _verify_migration(
    source_data: Dict[str, Any], source: str, migrated: Dict[str, Any]
) -> None:
    """Структурная + содержательная верификация (В6): результат = CURRENT;
    сцены сохранены дословно (deep-equal); прочие top-level ключи as-is (В2)."""
    if classify_parsed_save(migrated).status != CURRENT:
        raise ValueError("Результат миграции не классифицируется как CURRENT")
    if source == SOURCE_V0_SINGLE:
        scene = source_data["scene_state"]
        expected_scenes = {scene.get("location_id", "default"): scene}
    else:
        expected_scenes = source_data["scenes"]
    if migrated["scenes"] != expected_scenes:
        raise ValueError("Сцены изменились при миграции (deep-equal провален)")
    for key, value in source_data.items():
        if key in ("scene_state", "scenes", "schema_version"):
            continue
        if migrated.get(key, _MISSING) != value:
            raise ValueError(f"Top-level ключ '{key}' не перенесён as-is")


# ── Файловая процедура (В6) ───────────────────────────────────────────────

def _backup_path(state_file: Path) -> Path:
    return state_file.with_name(state_file.name + _BACKUP_SUFFIX)


def _tmp_path(state_file: Path) -> Path:
    return state_file.with_name(state_file.name + _TMP_SUFFIX)


def migrate_save_file_if_needed(state_file: Path) -> SaveMigrationOutcome:
    """Файловая процедура «детект-и-мигрировать» (В6, жёсткий порядок):

    1) файл не существует → not_found (no-op, ничего не создаётся);
    2) CURRENT → no-op: повторная загрузка v1 не пишет ничего (№1);
    3) UNMIGRABLE → отказ: ни одной записи, файл не тронут (В3/№4);
    4) MIGRABLE: чистая миграция в памяти + верификация (барьер до записей);
    5) .pre-migration.bak из ИСХОДНЫХ байтов + обратное чтение + побайтовое
       сравнение; существующий .bak: равен → переиспользуется (повтор после
       аварии), отличается → отказ (единственный .bak не перезаписывается);
    6) tmp-запись результата + обратное чтение + parse + deep-equal;
    7) os.replace(tmp, state_file) — ЕДИНСТВЕННОЕ касание оригинала (атомарно).

    Авария до шага 7 оставляет оригинал нетронутым: частичной записи оригинала
    не существует by construction (№2/№3). Ошибки I/O — fail-loud (L4):
    никаких авто-откатов с потерей диагностических данных (В6).
    """
    if not state_file.exists():
        return SaveMigrationOutcome(status=STATUS_NOT_FOUND, state_file=state_file)

    verdict = detect_save_format(state_file)
    if verdict.status == CURRENT:
        return SaveMigrationOutcome(status=STATUS_CURRENT, state_file=state_file)
    if verdict.status == UNMIGRABLE:
        return _refuse(state_file, verdict.reason or REASON_UNKNOWN_FORMAT)
    if verdict.payload is None:
        return _refuse(state_file, REASON_UNKNOWN_FORMAT)

    source = verdict.source or SOURCE_V0_SINGLE
    source_data = verdict.payload
    source_bytes = state_file.read_bytes()

    # 4) миграция в памяти + верификация — до любых записей
    try:
        migrated = migrate_payload_to_v1(source_data, source)
        _verify_migration(source_data, source, migrated)
    except ValueError as e:
        logger.error(f"[SAVE_MIGRATION] Верификация провалена ({state_file}): {e}")
        return _refuse(
            state_file,
            REASON_INVALID_V0 if source == SOURCE_V0_SINGLE else REASON_INVALID_SCENES,
        )

    # 5) бэкап-барьер (В6)
    backup = _backup_path(state_file)
    if backup.exists():
        if backup.read_bytes() != source_bytes:
            logger.error(
                f"[SAVE_MIGRATION] {backup} существует и отличается от исходника — "
                "отказ: единственный .bak не перезаписывается непроверенной копией"
            )
            return _refuse(state_file, "BACKUP_CONFLICT")
    else:
        backup.write_bytes(source_bytes)
        if backup.read_bytes() != source_bytes:
            raise OSError(f"Бэкап {backup} не прошёл побайтовую верификацию")

    # 6) tmp + round-trip верификация
    tmp = _tmp_path(state_file)
    try:
        tmp.write_bytes(
            json.dumps(migrated, ensure_ascii=False, indent=2).encode("utf-8")
        )
        if json.loads(tmp.read_bytes().decode("utf-8-sig")) != migrated:
            raise OSError(f"tmp-файл {tmp} не прошёл round-trip верификацию")
    except Exception:
        # tmp — мусор, оригинал не тронут; fail-loud наружу (L4)
        try:
            tmp.unlink()
        except OSError:
            logger.warning(f"[SAVE_MIGRATION] tmp {tmp} не удалён — мусор остался")
        raise

    # 7) атомарная замена — единственное касание оригинала
    os.replace(tmp, state_file)
    logger.info(
        f"[SAVE_MIGRATION] {state_file.name}: конвертирован в "
        f"v{SAVE_SCHEMA_VERSION}, резервная копия: {backup.name}"
    )
    return SaveMigrationOutcome(
        status=STATUS_MIGRATED, state_file=state_file, backup_file=backup
    )


# ── Version-aware читатели (В4: оба читателя, единое правило) ─────────────

def extract_scene_payload(
    data: Dict[str, Any], location_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Сцена снапшота для локации. Единое правило (В4): scenes-layout
    (штампованный или нет — scenes есть истина формы) → выбор по location_id;
    без location_id — единственная сцена, при неоднозначности честный None
    (§ENIGMA-006: не угадываем); иначе легаси-ключ scene_state (обратная
    совместимость v0-ридера, В5)."""
    scenes = data.get("scenes")
    if isinstance(scenes, dict):
        if location_id:
            scene = scenes.get(location_id)
            return scene if isinstance(scene, dict) else None  # noqa: ENIGMA001 — честный None (§ENIGMA-006)
        if len(scenes) == 1:
            scene = next(iter(scenes.values()))
            return scene if isinstance(scene, dict) else None  # noqa: ENIGMA001 — честный None (§ENIGMA-006)
        return None
    scene = data.get("scene_state")
    return scene if isinstance(scene, dict) else None  # noqa: ENIGMA001 — легаси v0-РИДЕР, честный None


def resolve_current_location(data: Dict[str, Any]) -> Optional[str]:
    """Текущая локация игрока для routes (К4): локация сцены снапшота →
    fallback metadata.current_location (SSOT локации, routes:1053)."""
    scene = extract_scene_payload(data)
    if isinstance(scene, dict):
        location = scene.get("location_id")
        if isinstance(location, str) and location:
            return location
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        location = metadata.get("current_location")
        if isinstance(location, str) and location:
            return location
    return None
