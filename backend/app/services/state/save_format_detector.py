"""
Назначение: детектор формата сейва campaign_state.json (COV-D59 / ADR-O-426,
Шаг 2 COV-1; вердикты Мастера В1-В8).

Трёхзначный вердикт вместо булева «легаси» (COV-GC-02: версия читается из ПОЛЯ
schema_version; структурный снифинг — только bootstrap безверсионных файлов,
прецедент _classify_* MigrationRunner):

  CURRENT    — schema_version == SAVE_SCHEMA_VERSION и структура v1 валидна;
  MIGRABLE   — распознанный старый формат, конвертация доказуема:
               V0_SINGLE (безверсионный single scene_state) или
               V1_UNSTAMPED (scenes без штампа, вкл. слияние-артефакт);
  UNMIGRABLE — неизвестный/повреждённый/будущий формат: честный отказ,
               файл не трогать (В3); причины — машинные (reason).

Неизвестное ≠ безопасное (Устав §ENIGMA-003): явная неизвестная версия (вкл.
schema_version=0) НИКОГДА не толкуется как v0 (негативный сценарий №4).

Ось версий payload НЕЗАВИСИМА от PRAGMA user_version SQLite (Ф7, ADR-O-426):
MigrationRunner не трогается. Вход контракта payload-версий (У-4): полный
KNOWN_ORGANS из app.models.causality_manifest — будущие payload-миграции,
меняющие состав органных полей сцены, сверяются с манифестом.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Текущая целевая версия payload-снапшота (лестница миграций — save_migrations).
SAVE_SCHEMA_VERSION = 1

# Статусы вердикта
CURRENT = "CURRENT"
MIGRABLE = "MIGRABLE"
UNMIGRABLE = "UNMIGRABLE"

# Распознаваемые источники миграции (source у MIGRABLE)
SOURCE_V0_SINGLE = "V0_SINGLE"
SOURCE_V1_UNSTAMPED = "V1_UNSTAMPED"

# Машинные причины отказа (reason у UNMIGRABLE)
REASON_CORRUPT_JSON = "CORRUPT_JSON"
REASON_NOT_DICT = "NOT_DICT"
REASON_NEWER_VERSION = "NEWER_VERSION"
REASON_UNKNOWN_VERSION = "UNKNOWN_VERSION"
REASON_UNKNOWN_FORMAT = "UNKNOWN_FORMAT"
REASON_INVALID_V0 = "INVALID_V0"
REASON_INVALID_SCENES = "INVALID_SCENES"
REASON_INCONSISTENT_V1 = "INCONSISTENT_V1"


@dataclass(frozen=True)
class SaveFormatVerdict:
    """Вердикт детектора; payload — распарсенный JSON (для CURRENT/MIGRABLE)."""

    status: str
    source: Optional[str] = None
    reason: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


def _scenes_valid(data: Dict[str, Any]) -> bool:
    """scenes обязан быть dict[str, dict]: сцена — всегда словарь."""
    scenes = data.get("scenes")
    if not isinstance(scenes, dict):
        return False
    return all(isinstance(scene, dict) for scene in scenes.values())


def classify_parsed_save(data: Any) -> SaveFormatVerdict:
    """Чистая классификация распарсенного JSON-значения (без файлового I/O)."""
    if not isinstance(data, dict):
        return SaveFormatVerdict(UNMIGRABLE, reason=REASON_NOT_DICT)

    version = data.get("schema_version")

    if version is None:
        # Безверсионный файл: bootstrap-снифинг структуры (В3)
        if "scenes" in data:
            if not _scenes_valid(data):
                return SaveFormatVerdict(UNMIGRABLE, reason=REASON_INVALID_SCENES)
            # scenes — истина формы (слияние-артефакт: легаси-ключ не переносится)
            return SaveFormatVerdict(MIGRABLE, source=SOURCE_V1_UNSTAMPED, payload=data)
        if "scene_state" in data:
            if not isinstance(data["scene_state"], dict):
                return SaveFormatVerdict(UNMIGRABLE, reason=REASON_INVALID_V0)
            return SaveFormatVerdict(MIGRABLE, source=SOURCE_V0_SINGLE, payload=data)
        return SaveFormatVerdict(UNMIGRABLE, reason=REASON_UNKNOWN_FORMAT)

    # Явный штамп: поле — контракт (COV-GC-02), структура обязана соответствовать
    if isinstance(version, bool) or not isinstance(version, int):
        return SaveFormatVerdict(UNMIGRABLE, reason=REASON_UNKNOWN_VERSION)
    if version > SAVE_SCHEMA_VERSION:
        return SaveFormatVerdict(UNMIGRABLE, reason=REASON_NEWER_VERSION)
    if version < SAVE_SCHEMA_VERSION:
        return SaveFormatVerdict(UNMIGRABLE, reason=REASON_UNKNOWN_VERSION)
    if "scene_state" in data or "scenes" not in data or not _scenes_valid(data):
        return SaveFormatVerdict(UNMIGRABLE, reason=REASON_INCONSISTENT_V1)
    return SaveFormatVerdict(CURRENT, payload=data)


def detect_save_format(state_file: Path) -> SaveFormatVerdict:
    """Читает файл сейва и выносит вердикт. Битый JSON → UNMIGRABLE(CORRUPT_JSON).
    BOM-толерантно (существующие читатели используют utf-8-sig)."""
    try:
        data = json.loads(state_file.read_bytes().decode("utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(f"[SAVE_DETECTOR] {state_file}: {e}")
        return SaveFormatVerdict(UNMIGRABLE, reason=REASON_CORRUPT_JSON)
    return classify_parsed_save(data)


def detect_legacy_saves(saves_dir: Path) -> List[str]:
    """Inventory-API (вход D70/UI): campaign_id с сейвами, ожидающими миграции
    (MIGRABLE). UNMIGRABLE сюда НЕ входит: отказ загрузки — отдельная проблема,
    не «старый формат». Замена одноимённой функции эпохи «детект-и-удалить»."""
    legacy: List[str] = []
    if not saves_dir.exists():
        return legacy
    for campaign_dir in saves_dir.iterdir():
        if not campaign_dir.is_dir():
            continue
        state_file = campaign_dir / "campaign_state.json"
        if not state_file.exists():
            continue
        if detect_save_format(state_file).status == MIGRABLE:
            legacy.append(campaign_dir.name)
    return legacy
