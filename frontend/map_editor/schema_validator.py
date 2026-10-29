"""path: /frontend/map_editor/schema_validator.py

Назначение: Единый валидатор схемы локаций (ME-1.4, Этап 01; категория 1
    по AR-ME-3 — ошибки схемы). Обобщает валидаторную семью S349 в один
    модуль с адресом проблемы «файл → сущность → поле»: объекты — прежняя
    проверка S349 (вызывается та же функция из data_manager, не копия),
    новое — стены, комнаты, узлы, NPC, надписи, верхний уровень,
    уникальность id. Режимы — наследие S349: чтение = громкий перечень
    (файл остаётся открытым), запись = write-gate.
    Правило живых данных: v1 требует только то, что уже выполняется во
    всех шести живых файлах. Легаси до ME-1.5 ошибкой НЕ считается:
    строка-wall_id у дверей (хак S129), ключ portals, связи узлов на
    несуществующие узлы (живая таверна: «Вход» ссылается на три призрака;
    чистка данных — вопрос Мастеру, зафиксирован в журнале ME-1.4). Кампании:
    validate_campaign_meta — перенос из campaign_manager (ME-1.4), одна
    точка правды на обе схемы.

Зависимости: data_manager — лениво, внутри функции (прямой импорт создал
    бы цикл: data_manager сам импортирует этот модуль для load/save).
    Backend не импортируется (граница фронта, Закон 1.1).

Основные сущности: validate_location, validate_location_top_level, validate_campaign_meta.
"""

from __future__ import annotations

# Верхний уровень локации: всё перечисленное уже есть в шести живых файлах
# player_spawn НЕ в обязательных: живой шаблон location_templates/market_square.json
# его не содержит, а загрузчик штатно создаёт дефолт (setdefault в load_all) —
# это миграция, не порча. Форма значения, если ключ есть, — в _check_spawn.
_LOC_REQUIRED_KEYS = (
    "label",
    "location_id",
    "origin",
    "size",
    "rooms",
    "walls",
    "nodes",
    "objects",
    "npcs",
    "labels",
    "global_coords",
)


def _is_num(value: object) -> bool:
    """Число (int/float), но не bool: bool — подкласс int в Python."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_location_top_level(data: dict, source: str) -> list[str]:
    """Схема верхнего уровня СЫРОГО файла (до применения дефолтов).

    Ловит усечённую локацию до того, как load_all молча долечит её
    дефолтами (ME-D10 «молчаливые дефолты»). global_coords обязателен и
    равен True: игра (world_context) доверяет флагу и не пересчитывает
    координаты сама — файл без флага она прочтёт как мировые напрямую.
    """
    if not isinstance(data, dict):
        return [
            f"{source}: локация должна быть JSON-объектом, "
            f"получен {type(data).__name__}"
        ]
    errors: list[str] = []
    for key in _LOC_REQUIRED_KEYS:
        if key not in data:
            errors.append(f"{source}: отсутствует обязательное поле '{key}'")
    if data.get("global_coords") is not True:
        errors.append(
            f"{source}: global_coords отсутствует или не True — координаты "
            f"не мигрированы, игра прочтёт их как мировые без пересчёта"
        )
    for key in ("label", "location_id"):
        value = data.get(key)
        if not isinstance(value, str) or not value:
            errors.append(f"{source}: поле '{key}' — непустая строка")
    return errors


def validate_location(data: dict, source: str) -> list[str]:
    """Полная схема локации; пустой список = валидна.

    Вызывается после разворота экземпляров-ссылок (пути load/save в
    DataManager): объектные проверки рассчитывают на полную старую форму.
    """
    from data_manager import _validate_location_objects  # цикл модулей — лениво

    if not isinstance(data, dict):
        return [
            f"{source}: локация должна быть JSON-объектом, "
            f"получен {type(data).__name__}"
        ]
    errors = validate_location_top_level(data, source)
    errors.extend(_check_origin_size(data, source))
    errors.extend(_check_spawn(data, source))
    errors.extend(_validate_location_objects(data, source))
    errors.extend(_check_walls(data, source))
    errors.extend(_check_rooms(data, source))
    errors.extend(_check_nodes(data, source))
    errors.extend(_check_npcs(data, source))
    errors.extend(_check_labels(data, source))
    errors.extend(_check_unique_object_ids(data, source))
    errors.extend(_check_levels(data, source))  # ME-1.9: multi-level contract
    errors.extend(_check_spatial_contract(data, source))  # ME-1.12: spatial contract
    return errors


def _check_origin_size(data: dict, source: str) -> list[str]:
    errors: list[str] = []
    origin = data.get("origin")
    if isinstance(origin, dict):
        for key in ("x", "y"):
            if not _is_num(origin.get(key)):
                errors.append(f"{source}: origin: поле '{key}' — число")
    size = data.get("size")
    if isinstance(size, dict):
        for key in ("w", "h"):
            if not _is_num(size.get(key)):
                errors.append(f"{source}: size: поле '{key}' — число")
    return errors


def _check_spawn(data: dict, source: str) -> list[str]:
    spawn = data.get("player_spawn")
    if spawn is None:
        return []
    if not isinstance(spawn, dict):
        return [f"{source}: player_spawn — объект"]
    errors: list[str] = []
    for key in ("x", "y", "z"):
        if not _is_num(spawn.get(key)):
            errors.append(f"{source}: player_spawn: поле '{key}' — число")
    return errors


def _check_walls(data: dict, source: str) -> list[str]:
    """Стены: id, координаты концов, ненулевая длина (форма — факт tavern)."""
    errors: list[str] = []
    seen: set[str] = set()
    for idx, wall in enumerate(data.get("walls") or []):
        if not isinstance(wall, dict):
            errors.append(f"{source}: стена <index {idx}>: запись не объект")
            continue
        if "id" not in wall:
            errors.append(f"{source}: стена <index {idx}>: отсутствует поле 'id'")
            continue
        wid = wall["id"]
        if not isinstance(wid, str) or not wid:
            errors.append(
                f"{source}: стена <index {idx}>: поле 'id' — непустая строка"
            )
            continue
        if wid in seen:
            errors.append(f"{source}: стена {wid}: дублирующийся id")
        seen.add(wid)
        coords: dict[str, float] = {}
        for key in ("x1", "y1", "x2", "y2"):
            value = wall.get(key)
            if not _is_num(value):
                errors.append(
                    f"{source}: стена {wid}: поле '{key}' — число "
                    f"(получено {type(value).__name__})"
                )
            else:
                coords[key] = value
        if len(coords) == 4:
            dx = coords["x2"] - coords["x1"]
            dy = coords["y2"] - coords["y1"]
            if dx * dx + dy * dy == 0:
                errors.append(f"{source}: стена {wid}: нулевая длина")
        thickness = wall.get("thickness")
        if thickness is not None and not _is_num(thickness):
            errors.append(f"{source}: стена {wid}: поле 'thickness' — число")
    return errors


def _check_rooms(data: dict, source: str) -> list[str]:
    """Комнаты: id, имя, прямоугольник, полигон ≥3 точек, площадь (факт)."""
    errors: list[str] = []
    seen: set[str] = set()
    for idx, room in enumerate(data.get("rooms") or []):
        if not isinstance(room, dict):
            errors.append(f"{source}: комната <index {idx}>: запись не объект")
            continue
        if "id" not in room:
            errors.append(f"{source}: комната <index {idx}>: отсутствует поле 'id'")
            continue
        rid = room["id"]
        if not isinstance(rid, str) or not rid:
            errors.append(
                f"{source}: комната <index {idx}>: поле 'id' — непустая строка"
            )
            continue
        if rid in seen:
            errors.append(f"{source}: комната {rid}: дублирующийся id")
        seen.add(rid)
        if not isinstance(room.get("name"), str) or not room.get("name"):
            errors.append(f"{source}: комната {rid}: поле 'name' — непустая строка")
        for key in ("x", "y", "width", "height"):
            if not _is_num(room.get(key)):
                errors.append(f"{source}: комната {rid}: поле '{key}' — число")
        polygon = room.get("polygon")
        if not isinstance(polygon, list) or len(polygon) < 3:
            errors.append(f"{source}: комната {rid}: polygon — список из ≥3 точек")
        else:
            for pidx, point in enumerate(polygon):
                if (
                    not isinstance(point, (list, tuple))
                    or len(point) != 2
                    or not all(_is_num(c) for c in point)
                ):
                    errors.append(
                        f"{source}: комната {rid}: polygon точка {pidx} — пара чисел"
                    )
                    break
        if not _is_num(room.get("area_sqm")):
            errors.append(f"{source}: комната {rid}: поле 'area_sqm' — число")
    return errors


def _check_nodes(data: dict, source: str) -> list[str]:
    """Узлы навигации: словарь «имя → {x, y, ...}» (факт tavern).

    Связи (connections) в v1 НЕ проверяются: живая таверна ссылается на
    три несуществующих узла — чистка данных это вопрос Мастеру, не
    блокиратор сохранения (решение ME-1.4, журнал).
    """
    nodes = data.get("nodes")
    if nodes is None:
        return []
    if not isinstance(nodes, dict):
        return [f"{source}: nodes — словарь «имя узла → узел»"]
    errors: list[str] = []
    for name, node in nodes.items():
        if not isinstance(node, dict):
            errors.append(f"{source}: узел {name}: запись не объект")
            continue
        for key in ("x", "y"):
            if not _is_num(node.get(key)):
                errors.append(f"{source}: узел {name}: поле '{key}' — число")
    return errors


def _check_npcs(data: dict, source: str) -> list[str]:
    """NPC: ref_id, позиция; room_id (если есть) обязан существовать."""
    errors: list[str] = []
    room_ids = {
        room.get("id")
        for room in (data.get("rooms") or [])
        if isinstance(room, dict)
    }
    seen: set[str] = set()
    for idx, npc in enumerate(data.get("npcs") or []):
        if not isinstance(npc, dict):
            errors.append(f"{source}: npc <index {idx}>: запись не объект")
            continue
        if "ref_id" not in npc:
            errors.append(f"{source}: npc <index {idx}>: отсутствует поле 'ref_id'")
            continue
        ref = npc["ref_id"]
        if not isinstance(ref, str) or not ref:
            errors.append(
                f"{source}: npc <index {idx}>: поле 'ref_id' — непустая строка"
            )
            continue
        if ref in seen:
            errors.append(f"{source}: npc {ref}: дублирующийся ref_id в локации")
        seen.add(ref)
        pos = npc.get("position")
        if (
            not isinstance(pos, dict)
            or not _is_num(pos.get("x"))
            or not _is_num(pos.get("y"))
        ):
            errors.append(f"{source}: npc {ref}: position без числовых x/y")
        room_id = npc.get("room_id")
        if room_id is not None and room_id not in room_ids:
            errors.append(
                f"{source}: npc {ref}: room_id '{room_id}' ссылается на "
                f"несуществующую комнату"
            )
    return errors


def _check_labels(data: dict, source: str) -> list[str]:
    """Надписи: форма — факт add_label (в живых файлах надписей нет)."""
    errors: list[str] = []
    seen: set[str] = set()
    for idx, label in enumerate(data.get("labels") or []):
        if not isinstance(label, dict):
            errors.append(f"{source}: надпись <index {idx}>: запись не объект")
            continue
        if "id" not in label:
            errors.append(f"{source}: надпись <index {idx}>: отсутствует поле 'id'")
            continue
        lid = label["id"]
        if not isinstance(lid, str) or not lid:
            errors.append(
                f"{source}: надпись <index {idx}>: поле 'id' — непустая строка"
            )
            continue
        if lid in seen:
            errors.append(f"{source}: надпись {lid}: дублирующийся id")
        seen.add(lid)
        for key in ("x", "y"):
            if not _is_num(label.get(key)):
                errors.append(f"{source}: надпись {lid}: поле '{key}' — число")
        if not isinstance(label.get("text"), str) or not label.get("text"):
            errors.append(f"{source}: надпись {lid}: поле 'text' — непустая строка")
        font = label.get("font_size")
        if not isinstance(font, int) or isinstance(font, bool):
            errors.append(f"{source}: надпись {lid}: поле 'font_size' — целое")
    return errors


def _check_unique_object_ids(data: dict, source: str) -> list[str]:
    """Дубли id объектов: генератор новых id опирается на уникальность —
    дубль ломает его тихо (номер следующего предмета перевирается)."""
    errors: list[str] = []
    seen: set[str] = set()
    for obj in data.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        oid = obj.get("id")
        if oid is None:
            continue  # отсутствие id ловит объектная проверка S349
        if oid in seen:
            errors.append(f"{source}: объект {oid}: дублирующийся id")
        seen.add(oid)
    return errors


# === ME-1.9: многоуровневый контракт levels[] (ME-R-101/105) ===


def _check_levels(data: dict, source: str) -> list[str]:
    """levels[] — опциональный многоуровневый контракт (ME-1.9).

    Если levels[] отсутствует — локация одноуровневая (backward compatible).
    Если присутствует — определяет уровни (этажи, подвалы, туннели):
    id (int, может быть отрицательным), label (str), elevation (float?, высота).

    Сущности (objects, walls, rooms, npcs, nodes) могут иметь поле 'level'
    (int, default 0) — ссылка на id из levels[]. Если level отсутствует —
    сущность на уровне 0 (backward compatible).

    SpatialDataLoader не меняется (ME-1.9 — editor-only контракт).
    Multi-level: игра читает flat arrays — известное ограничение до S-ME1.
    """
    levels = data.get("levels")
    if levels is None:
        return []
    if not isinstance(levels, list):
        return [f"{source}: levels — список, получен {type(levels).__name__}"]

    errors: list[str] = []
    seen_ids: set[int] = set()
    level_ids: set[int] = set()

    for idx, lvl in enumerate(levels):
        if not isinstance(lvl, dict):
            errors.append(f"{source}: levels[{idx}]: запись не объект")
            continue
        lid = lvl.get("id")
        if not isinstance(lid, int) or isinstance(lid, bool):
            errors.append(
                f"{source}: levels[{idx}]: поле 'id' — целое "
                f"(может быть отрицательным)"
            )
            continue
        if lid in seen_ids:
            errors.append(f"{source}: levels[{idx}]: дублирующийся id={lid}")
        seen_ids.add(lid)
        level_ids.add(lid)
        label = lvl.get("label")
        if not isinstance(label, str) or not label:
            errors.append(
                f"{source}: levels[{idx}] (id={lid}): поле 'label' — непустая строка"
            )
        elevation = lvl.get("elevation")
        if elevation is not None and not _is_num(elevation):
            errors.append(
                f"{source}: levels[{idx}] (id={lid}): "
                f"поле 'elevation' — число (опционально)"
            )

    if level_ids:
        for entity_type in ("objects", "walls", "rooms", "npcs"):
            entities = data.get(entity_type) or []
            for idx, ent in enumerate(entities):
                if not isinstance(ent, dict):
                    continue
                level = ent.get("level")
                if level is None:
                    continue
                if not isinstance(level, int) or isinstance(level, bool):
                    errors.append(
                        f"{source}: {entity_type}[{idx}]: поле 'level' — целое"
                    )
                    continue
                if level not in level_ids:
                    errors.append(
                        f"{source}: {entity_type}[{idx}]: "
                        f"level={level} не найден в levels[]"
                    )
        nodes = data.get("nodes") or {}
        for name, node in nodes.items():
            if not isinstance(node, dict):
                continue
            level = node.get("level")
            if level is None:
                continue
            if not isinstance(level, int) or isinstance(level, bool):
                errors.append(f"{source}: узел {name}: поле 'level' — целое")
                continue
            if level not in level_ids:
                errors.append(
                    f"{source}: узел {name}: level={level} не найден в levels[]"
                )
    return errors


# === ME-1.12: глобальный пространственный контракт v1.2/v1.3 (§5Б) ===


def _check_spatial_contract(data: dict, source: str) -> list[str]:
    """Пространственный контракт (ME-1.12, §5Б).

    Инварианты:
    1. Логические координаты (метры) в JSON, не пиксели (SCALE — rendering).
    2. grid_cell_size > 0 — явное преобразование cell->meter.
    3. spatial_ref (if present) — string, ссылка на область.
    4. world_boundary (if present) — mode in {open, hard, transition}.
    5. levels[] + active_level — ME-1.9 (validated by _check_levels).
    6. Depth (elevation) != Floor (level id) — ME-1.9 contract.

    НЕ валидирует: SCALE (rendering, canonical=20 per audit, fix in ME-2.8);
    SpatialDataLoader (game-side, S-ME1).
    """
    errors: list[str] = []

    gcs = data.get("grid_cell_size")
    if gcs is not None:
        if not _is_num(gcs) or gcs <= 0:
            errors.append(
                f"{source}: grid_cell_size — положительное число "
                f"(получено {gcs!r})"
            )

    wb = data.get("world_boundary")
    if wb is not None:
        if not isinstance(wb, dict):
            errors.append(f"{source}: world_boundary — объект")
        else:
            mode = wb.get("mode")
            if mode not in ("open", "hard", "transition"):
                errors.append(
                    f"{source}: world_boundary.mode — один из "
                    f"'open', 'hard', 'transition' (получено {mode!r})"
                )

    for entity_type in ("objects", "walls", "rooms", "npcs"):
        for idx, ent in enumerate(data.get(entity_type) or []):
            if not isinstance(ent, dict):
                continue
            sref = ent.get("spatial_ref")
            if sref is not None and not isinstance(sref, str):
                errors.append(
                    f"{source}: {entity_type}[{idx}]: "
                    f"spatial_ref — строка (получено {type(sref).__name__})"
                )

    return errors


# === ME-1.4: схема meta campaign.json (перенос из campaign_manager; исходно ME-D1/S349) ===

_KEY_NAME = "name"
_KEY_DESCRIPTION = "description"
_KEY_CREATED_AT = "created_at"
_KEY_MODIFIED_AT = "modified_at"
_META_REQUIRED_KEYS = (_KEY_NAME, _KEY_DESCRIPTION, _KEY_CREATED_AT, _KEY_MODIFIED_AT)


def validate_campaign_meta(data: object, source: str) -> dict:
    """Fail-loud валидация meta кампании (ME-D1; логика идентична S349).

    Тело локации в campaign.json — валидный JSON с ЧУЖОЙ схемой: json.load
    его пропускает, except не срабатывает, порча маскируется и вечно
    перезаписывается write-gate'ом. Категория 1 (AR-ME-3).
    """
    if not isinstance(data, dict):
        raise ValueError(
            f"{source}: campaign.json должен быть JSON-объектом, "
            f"получен {type(data).__name__}"
        )
    missing = [k for k in _META_REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(
            f"{source}: campaign.json не является meta кампании — "
            f"отсутствуют поля {missing} (похоже на тело локации?)"
        )
    for key in _META_REQUIRED_KEYS:
        if not isinstance(data[key], str):
            raise ValueError(
                f"{source}: поле '{key}' должно быть строкой, "
                f"получен {type(data[key]).__name__}"
            )
    return data
