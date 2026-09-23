"""
Назначение: поиск editor-JSON локаций (filesystem-локатор). DEGOD ITER2: перенос из SSM (:788–944). Методы класса → функции от campaigns_dir. Path(__file__)-путь адаптирован на +1 parent (файл глубже на уровень пакета).
Зависимости: json, math, pathlib
Основные сущности: _find_editor_location, _find_first_editor_location, _find_starting_location, _nearest_node_to_xy
"""

import json
import logging
import math
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


def _find_editor_location(
    campaigns_dir: Path, campaign_id: str, location_id: str
) -> dict | None:
    """Ищет editor JSON с совпадающим location_id.
    Поддерживает: точное совпадение, частичное совпадение label, пустой location_id."""
    search_dirs = [
        campaigns_dir / campaign_id / "locations",
        # DEGOD ITER2: файл на уровень глубже (app/services/scene_state/), поэтому
        # цепочка parent удлинена на один узел — итоговый путь идентичен прежнему.
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "frontend"
        / "map_editor"
        / "campaigns"
        / campaign_id
        / "locations",
    ]
    for loc_dir in search_dirs:
        if not loc_dir.exists():
            continue
        for json_file in loc_dir.glob("*.json"):
            try:
                data: dict[str, Any] = json.loads(json_file.read_text(encoding="utf-8-sig"))
                lid = data.get("location_id", "")
                label = data.get("label", "")
                # Точное совпадение
                if lid == location_id or label == location_id:
                    logger.info(
                        f"[SCENE] Найден editor JSON: {json_file} для location_id={location_id}"
                    )
                    return data
                # Частичное совпадение label (в одну сторону)
                if label and location_id and (location_id.lower() in label.lower()):
                    logger.info(
                        f"[SCENE] Найден editor JSON по частичному label: {json_file}"
                    )
                    return data
                # Пустой location_id в файле — берём первую попавшуюся с rooms
                if not lid and location_id and data.get("rooms"):
                    logger.info(
                        f"[SCENE] Fallback на первый файл с rooms: {json_file}"
                    )
                    return data
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"[SCENE] Пропуск невалидного editor JSON {json_file}: {e}")
                continue
    return None


def _find_first_editor_location(campaigns_dir: Path, campaign_id: str) -> dict | None:
    """Возвращает первую найденную локацию из editor JSON — fallback при несовпадении location_id."""
    search_dirs = [
        campaigns_dir / campaign_id / "locations",
        # DEGOD ITER2: +1 parent (см. _find_editor_location)
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "frontend"
        / "map_editor"
        / "campaigns"
        / campaign_id
        / "locations",
    ]
    for loc_dir in search_dirs:
        if not loc_dir.exists():
            continue
        for json_file in loc_dir.glob("*.json"):
            try:
                data: dict[str, Any] = json.loads(json_file.read_text(encoding="utf-8-sig"))
                if data.get("rooms") or data.get("walls"):
                    logger.info(f"[SCENE] Fallback: первая локация из {json_file}")
                    return data
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"[SCENE] Пропуск невалидного location JSON {json_file}: {e}")
                continue
    return None


def _find_starting_location(campaigns_dir: Path, campaign_id: str) -> str:
    """Находит начальную локацию для кампании из editor JSON.
    Приоритет: player_spawn + NPC → player_spawn → rooms/walls → 'tavern'."""
    search_dirs = [
        campaigns_dir / campaign_id / "locations",
        # DEGOD ITER2: +1 parent (см. _find_editor_location)
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "frontend"
        / "map_editor"
        / "campaigns"
        / campaign_id
        / "locations",
    ]
    # Приоритет 1: локация с player_spawn И NPC (лучшая стартовая точка)
    for loc_dir in search_dirs:
        if not loc_dir.exists():
            continue
        for json_file in sorted(loc_dir.glob("*.json")):
            try:
                data: dict[str, Any] = json.loads(json_file.read_text(encoding="utf-8-sig"))
                if data.get("player_spawn") and data.get("npcs"):
                    return cast(str, data.get("location_id", json_file.stem))
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"[SCENE] Пропуск невалидного JSON (NPC+spawn) {json_file}: {e}")
                continue
    # Приоритет 2: локация с player_spawn (без NPC)
    for loc_dir in search_dirs:
        if not loc_dir.exists():
            continue
        for json_file in sorted(loc_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8-sig"))
                if data.get("player_spawn"):
                    return cast(str, data.get("location_id", json_file.stem))
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"[SCENE] Пропуск невалидного JSON (spawn only) {json_file}: {e}")
                continue
    # Приоритет 3: первая локация с rooms/walls/nodes
    for loc_dir in search_dirs:
        if not loc_dir.exists():
            continue
        for json_file in sorted(loc_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8-sig"))
                if data.get("rooms") or data.get("walls") or data.get("nodes"):
                    return cast(str, data.get("location_id", json_file.stem))
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"[SCENE] Пропуск невалидного JSON (rooms/walls/nodes) {json_file}: {e}")
                continue
    return "tavern"


def _nearest_node_to_xy(editor_data: dict, x: float, y: float) -> str:
    """Находит ближайший навигационный узел к координате XY."""
    nodes = editor_data.get("nodes", {})
    if not nodes:
        return ""
    best_node = ""
    best_dist = float("inf")
    for node_id, node_data in nodes.items():
        nx = node_data.get("x", 0)
        ny = node_data.get("y", 0)
        dist = math.sqrt((nx - x) ** 2 + (ny - y) ** 2)
        if dist < best_dist:
            best_dist = dist
            best_node = node_id
    return best_node
