"""
path: backend/tests/test_roadmap_baseline.py
Назначение: P0-02 — базовые smoke-тесты и эталоны.
            ROADMAP: ENIGMA_ROADMAP_восстановление_редактора_мира_runtime.md
            Фиксирует ТЕКУЩЕЕ поведение (даже баговое) как эталон "до"
            для сравнения "после" правок P1-P4.
Зависимости: backend/app/*, frontend/map_editor/assets/resource_resolver.py,
             frontend/map_editor/campaigns/Open_road/compiled/spatial_registry.json
Основные сущности: T0-a (starting_location), T0-b (resource_resolver),
                   T0-c (footprint violations), T0-d (find_chunks)

Не запускает серверы. Не требует LLM. Не изменяет данные.
Ограничения ROADMAP §Фаза 0: существующие тесты не правятся.
"""

import json
import sys
from pathlib import Path

# === sys.path setup (как в conftest.py + frontend) ===
_ROOT = Path(__file__).resolve().parents[2]  # Enigma/
_BACKEND = _ROOT / "backend"
_FRONTEND = _ROOT / "frontend"

for _p in (str(_ROOT), str(_BACKEND), str(_FRONTEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# =============================================================================
# T0-a: _find_starting_location("Open_road") == "tavern"
# =============================================================================
def test_t0_a_starting_location_tavern():
    """T0-a: стартовая локация кампании Open_road = 'tavern'.

    Фиксирует ТЕКУЩЕЕ поведение _find_starting_location:
    приоритет 1 (player_spawn + npcs) — tavern.json имеет оба поля.

    Связь ROADMAP: B-04 (create_location), C-P1 (стартовая сцена),
    матрица G/R1 (T1-T4 + ручной).
    """
    from app.services.scene_state.editor_locator import _find_starting_location

    campaigns_dir = _BACKEND / "data" / "campaigns"
    result = _find_starting_location(campaigns_dir, "Open_road")

    assert result == "tavern", (
        f"Expected 'tavern' (priority: player_spawn + npcs), got '{result}'. "
        f"If changed — verify against C-P1 (start scene root cause)."
    )


# =============================================================================
# T0-b: resource_resolver — Pers/Люся vs текстуры/Pers/Люся
# =============================================================================
def test_t0_b_resource_resolver_broken_links():
    """T0-b: битые ссылки персонажей (B-22) — эталон ДО Фазы 5.

    resolve('Pers/Люся')     → None  (битая: нет 'текстуры/' префикса)
    resolve('текстуры/Pers/Люся') → Path (корректная)

    Файлы лежат в pixels/текстуры/Pers/*.png; ссылки в JSON — 'Pers/...' без 'текстуры/'.
    Resolver probe: <id> → <id>.png → None (legacy-семантика R3).

    ИМПОРТ ЧЕРЕЗ importlib.util: обход map_editor/assets/__init__.py:8
    (`from .asset_store import ...` → `from assets.resource_formats import ...`
    — чужой баг импорта, не мой контур по §11 Anti-Race). resource_resolver.py
    standalone (только stdlib imports: __future__, pathlib, typing).

    Связь ROADMAP: B-22 (ресурсы), C-P3 (корневая причина), Фаза 5 (P5-01).
    Открытый долг: __init__.py:8 имеет битый импорт 'from assets.resource_formats'
    (должен быть 'from map_editor.assets.resource_formats' или '.resource_formats')
    — НЕ чиню (чужой WIP).
    """
    import importlib.util

    rr_path = _FRONTEND / "map_editor" / "assets" / "resource_resolver.py"
    assert rr_path.is_file(), f"resource_resolver.py missing: {rr_path}"

    # Загрузка модуля напрямую (без __init__.py пакета)
    spec = importlib.util.spec_from_file_location(
        "_roadmap_baseline_resource_resolver", rr_path
    )
    assert spec is not None and spec.loader is not None, "spec_from_file_location failed"
    rr_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rr_module)
    LegacyDirResolver = rr_module.LegacyDirResolver

    pixels_root = _FRONTEND / "map_editor" / "pixels"
    resolver = LegacyDirResolver(root_dir=pixels_root)

    # Битая ссылка (как в tavern.json и config/npc/individuals)
    broken = resolver.resolve("Pers/Люся")
    assert broken is None, (
        f"Expected None for 'Pers/Люся' (B-22 broken link baseline), got {broken}. "
        f"P5-01 may have already been applied — check if links were fixed."
    )

    # Корректная ссылка (с префиксом 'текстуры/')
    fixed = resolver.resolve("текстуры/Pers/Люся")
    assert fixed is not None, "Expected path for 'текстуры/Pers/Люся'"
    assert fixed.is_file(), f"Resolved path does not exist: {fixed}"
    assert "текстуры" in str(fixed).replace("\\", "/"), (
        f"Path should contain 'текстуры': {fixed}"
    )


# =============================================================================
# T0-c: доля координатных полей tavern.json вне footprint
# =============================================================================
def test_t0_c_tavern_footprint_violations(capsys):
    """T0-c: разбор tavern.json — доля координатных полей вне footprint.

    Фиксирует B-08: tavern.json имеет global_coords=true, но ВСЕ координатные
    поля — в локальном фрейме. Это нарушение инварианта B-07
    (frame(entities) == frame(geometry); при global_coords=true — мировой фрейм).

    Мировой footprint: [origin.x, origin.x+size.w] × [origin.y, origin.y+size.h]
                       = [25.033, 45.033] × [5.018, 20.018]
    Локальный footprint: [0, size.w] × [0, size.h] = [0, 20] × [0, 15]

    Эталон (ДО P1-03):
      - global_coords: True
      - в мировом footprint: 0 полей (0%) — НИ ОДНОГО
      - в локальном footprint: ≥90% полей
    Это и есть корень P1 (C-P1): файл противоречит собственному флагу.

    Связь ROADMAP: B-03 (миграция), B-07 (инвариант), B-08 (гетерогенность),
                   C-P1, P1-03 (нормализация данных).
    """
    tavern_path = (
        _FRONTEND / "map_editor" / "campaigns" / "Open_road" / "locations" / "tavern.json"
    )
    data = json.loads(tavern_path.read_text(encoding="utf-8"))

    origin_x = float(data["origin"]["x"])
    origin_y = float(data["origin"]["y"])
    size_w = float(data["size"]["w"])
    size_h = float(data["size"]["h"])

    # Мировой footprint
    fx_min, fx_max = origin_x, origin_x + size_w
    fy_min, fy_max = origin_y, origin_y + size_h

    # Локальный footprint
    lx_min, lx_max = 0.0, size_w
    ly_min, ly_max = 0.0, size_h

    def in_world(x: float, y: float) -> bool:
        return fx_min <= x <= fx_max and fy_min <= y <= fy_max

    def in_local(x: float, y: float) -> bool:
        return lx_min <= x <= lx_max and ly_min <= y <= ly_max

    # Сбор всех координатных полей файла (как dict → список (имя, x, y))
    coords: list[tuple[str, float, float]] = []

    # player_spawn
    if data.get("player_spawn"):
        coords.append((
            "player_spawn",
            float(data["player_spawn"]["x"]),
            float(data["player_spawn"]["y"]),
        ))

    # npcs[i].position
    for i, npc in enumerate(data.get("npcs", [])):
        pos = npc.get("position")
        if pos:
            coords.append((
                f"npcs[{i}].position ({npc.get('ref_id', '?')})",
                float(pos["x"]),
                float(pos["y"]),
            ))

    # nodes (dict node_id → {x, y, ...})
    nodes = data.get("nodes", {})
    if isinstance(nodes, dict):
        for k, v in nodes.items():
            if v and "x" in v and "y" in v:
                coords.append((f"nodes.{k}", float(v["x"]), float(v["y"])))

    # walls[i] — отрезок (x1,y1)-(x2,y2), обе точки
    for i, w in enumerate(data.get("walls", [])):
        if "x1" in w and "y1" in w:
            coords.append((f"walls[{i}].p1", float(w["x1"]), float(w["y1"])))
        if "x2" in w and "y2" in w:
            coords.append((f"walls[{i}].p2", float(w["x2"]), float(w["y2"])))

    # objects[i].position
    for i, o in enumerate(data.get("objects", [])):
        pos = o.get("position")
        if pos:
            coords.append((
                f"objects[{i}].position",
                float(pos["x"]),
                float(pos["y"]),
            ))

    # rooms[i] — rect: 2 угловые точки
    for i, r in enumerate(data.get("rooms", [])):
        if "x" in r and "y" in r:
            rx, ry = float(r["x"]), float(r["y"])
            rw, rh = float(r["width"]), float(r["height"])
            coords.append((f"rooms[{i}].corner_min", rx, ry))
            coords.append((f"rooms[{i}].corner_max", rx + rw, ry + rh))

    # labels (если есть)
    labels = data.get("labels", [])
    if isinstance(labels, list):
        for i, l in enumerate(labels):
            if l and "x" in l and "y" in l:
                coords.append((f"labels[{i}]", float(l["x"]), float(l["y"])))

    # passages (если есть)
    passages = data.get("passages", [])
    if isinstance(passages, list):
        for i, p in enumerate(passages):
            if p and "x" in p and "y" in p:
                coords.append((f"passages[{i}]", float(p["x"]), float(p["y"])))

    # Статистика
    total = len(coords)
    assert total > 0, "No coord fields found in tavern.json — structure changed?"

    in_world_count = sum(1 for _, x, y in coords if in_world(x, y))
    in_local_count = sum(1 for _, x, y in coords if in_local(x, y))
    out_of_both = sum(
        1 for _, x, y in coords if not in_world(x, y) and not in_local(x, y)
    )

    # Логирование эталона (capsys перехватывает; -s показывает)
    print(f"\n[T0-c] tavern.json footprint analysis:")
    print(f"  global_coords: {data.get('global_coords')}")
    print(f"  origin: ({origin_x}, {origin_y})")
    print(f"  size:   {size_w} x {size_h}")
    print(f"  world footprint: [{fx_min}, {fx_max}] x [{fy_min}, {fy_max}]")
    print(f"  local footprint: [{lx_min}, {lx_max}] x [{ly_min}, {ly_max}]")
    print(f"  total coord fields: {total}")
    print(f"  in world footprint: {in_world_count} ({100*in_world_count/total:.1f}%)")
    print(f"  in local footprint: {in_local_count} ({100*in_local_count/total:.1f}%)")
    print(f"  out of both:        {out_of_both} ({100*out_of_both/total:.1f}%)")

    # КОНТРАКТ ТЕСТА: фиксация POST-P1-03 состояния (W1 baseline)
    # После P1-03 (нормализация в мировой фрейм): все координатные поля мировые.
    # in_world_count == total (100%), out_of_both == 0.
    assert in_world_count == total, (
        f"Expected ALL {total} fields in world footprint (post-P1-03 W1 baseline), "
        f"got only {in_world_count}. P1-03 regression?"
    )
    assert out_of_both == 0, (
        f"Expected 0 fields outside both footprints, got {out_of_both}. "
        f"Some fields are neither world nor local — investigate."
    )


# =============================================================================
# T0-d: find_chunks(45.0333, 10) — порядок и [0]
# =============================================================================
def test_t0_d_find_chunks_boundary(capsys):
    """T0-d: find_chunks на границе city_gate/tavern — РЕАЛЬНЫЙ baseline.

    ЗАМЕТКА ОТ ПЕРВОНАЧАЛЬНОЙ ГИПОТЕЗЫ (отвергнута по §3.6 археология):
    Изначально ожидалось, что точка (45.0333, 10) лежит на inclusive-границе
    city_gate и tavern → возвращает [city_gate, tavern]. АРХЕОЛОГИЯ ОПРОВЕРГЛА:
    float gap между cg_left (45.033333333333324) и tv_right (45.03333333333332)
    делает общую точку НЕВОЗМОЖНОЙ в inclusive `<=` арифметике:
      - cg_left = float(cg.origin_x)         = 45.033333333333324
      - tv_right = float(tv.origin_x) + 20.0 = 45.03333333333332
      - cg_left > tv_right на ~4e-15

    B-09 (find_chunks возвращает несколько чанков на общей границе) — теоретический
    риск (если будущие правки координат уберут float gap), но на текущих данных
    НЕ воспроизводится. Этим тестом фиксируем РЕАЛЬНОЕ поведение.

    Связь ROADMAP: B-09 (find_chunks), B-10 (владелец границы), C-P1,
                   D.2 (контракт выбора локации), P2-01 (детерминированный владелец).
    Открытый долг: P2-01 должен учитывать float-precision — правило D.2
    (минимальная площадь → лексикографически меньший id) применимо только
    когда несколько чанков реально пересекаются (после нормализации float).
    """
    from app.services.spatial.spatial_registry import (
        AdjacencyEntry,
        ChunkDescriptor,
        SpatialRegistry,
        WorldBounds,
    )

    # Загрузка compiled-артефакта напрямую (без тяжёлой инициализации)
    sr_path = (
        _FRONTEND
        / "map_editor"
        / "campaigns"
        / "Open_road"
        / "compiled"
        / "spatial_registry.json"
    )
    data = json.loads(sr_path.read_text(encoding="utf-8"))

    chunks = [
        ChunkDescriptor(
            location_id=c["location_id"],
            filename=c["filename"],
            origin_x=float(c["origin_x"]),
            origin_y=float(c["origin_y"]),
            width=float(c["width"]),
            height=float(c["height"]),
            is_outdoor=bool(c["is_outdoor"]),
            label=c["label"],
            content_hash=c["content_hash"],
        )
        for c in data["chunks"]
    ]

    adjacency = [
        AdjacencyEntry(
            location_a=a["location_a"],
            location_b=a["location_b"],
            contact_axis=a["contact_axis"],
            contact_coord=float(a["contact_coord"]),
            overlap_start=float(a["overlap_start"]),
            overlap_end=float(a["overlap_end"]),
            connection_type=a["connection_type"],
        )
        for a in data["adjacency"]
    ]

    wb = data["world_bounds"]
    world_bounds = WorldBounds(
        min_x=float(wb["min_x"]),
        min_y=float(wb["min_y"]),
        max_x=float(wb["max_x"]),
        max_y=float(wb["max_y"]),
    )

    registry = SpatialRegistry(chunks, adjacency, world_bounds, campaign_id="Open_road")

    # === Поиск чанков для точки (45.0333, 10.0) — ожидаемая граница ===
    # x=45.0333 (4 знака) < cg_left (45.03333...24) → НЕ в city_gate
    # x=45.0333 < tv_right (45.03333...32)? ДА → в tavern
    result_at_rounded = registry.find_chunks(45.0333, 10.0)
    ids_rounded = [c.location_id for c in result_at_rounded]

    # === Поиск для cg_left (точное значение origin_x city_gate) ===
    cg_chunk = next(c for c in chunks if c.location_id == "city_gate")
    tv_chunk = next(c for c in chunks if c.location_id == "tavern")
    result_at_cg_left = registry.find_chunks(cg_chunk.origin_x, 10.0)
    ids_at_cg_left = [c.location_id for c in result_at_cg_left]

    # === Поиск для tv_right (точное значение origin_x + width tavern) ===
    tv_right = tv_chunk.origin_x + tv_chunk.width
    result_at_tv_right = registry.find_chunks(tv_right, 10.0)
    ids_at_tv_right = [c.location_id for c in result_at_tv_right]

    # Float gap диагностика
    float_gap = cg_chunk.origin_x - tv_right

    print(f"\n[T0-d] find_chunks on city_gate/tavern boundary (y=10.0):")
    print(f"  cg_left   = {cg_chunk.origin_x!r}")
    print(f"  tv_right  = {tv_right!r}")
    print(f"  float gap = {float_gap!r}  (cg_left - tv_right)")
    print(f"  cg_left == tv_right (float)?  {cg_chunk.origin_x == tv_right}")
    print(f"  cg_left >  tv_right (float)?  {cg_chunk.origin_x > tv_right}")
    print()
    print(f"  find_chunks(45.0333, 10.0)      = {ids_rounded}")
    print(f"  find_chunks(cg_left, 10.0)       = {ids_at_cg_left}")
    print(f"  find_chunks(tv_right, 10.0)      = {ids_at_tv_right}")
    print()
    print(f"  B-09 theoretical risk: if cg_left == tv_right (float-equal),")
    print(f"  result would be [city_gate, tavern] (artifact order).")
    print(f"  Current reality: float gap → single-chunk everywhere.")
    print(f"  P2-01 (D.2 rule) applies only when multi-chunk occurs.")

    # === КОНТРАКТ ТЕСТА: фиксация РЕАЛЬНОГО поведения ===

    # (1) Float gap существует (cg_left > tv_right на микро-значение)
    assert cg_chunk.origin_x > tv_right, (
        f"Expected cg_left > tv_right (float gap, baseline). "
        f"Got cg_left={cg_chunk.origin_x!r}, tv_right={tv_right!r}. "
        f"If equal — float gap may have been resolved; revisit B-09 reproduction."
    )

    # (2) На округлённой точке (45.0333) — только tavern (т.к. < cg_left)
    assert ids_rounded == ["tavern"], (
        f"Expected ['tavern'] at (45.0333, 10.0) — x < cg_left → not in city_gate. "
        f"Got {ids_rounded}. P2-01 may have changed find_chunks semantics."
    )

    # (3) На точном cg_left — только city_gate (т.к. cg_left > tv_right → not in tavern)
    assert ids_at_cg_left == ["city_gate"], (
        f"Expected ['city_gate'] at (cg_left, 10.0) — cg_left > tv_right → not in tavern. "
        f"Got {ids_at_cg_left}."
    )

    # (4) На точном tv_right — только tavern (т.к. tv_right < cg_left → not in city_gate)
    assert ids_at_tv_right == ["tavern"], (
        f"Expected ['tavern'] at (tv_right, 10.0) — tv_right < cg_left → not in city_gate. "
        f"Got {ids_at_tv_right}."
    )

    # (5) НИ ОДНА точка не даёт multi-chunk — это и есть baseline
    multi_chunk_observed = any(
        len(ids) > 1 for ids in [ids_rounded, ids_at_cg_left, ids_at_tv_right]
    )
    assert not multi_chunk_observed, (
        f"Multi-chunk observed — B-09 reproduced. "
        f"Update T0-d baseline to reflect new behavior."
    )

    # (6) Порядок артефакта: [city_gate, market_square, tavern] (как в compiled JSON)
    artifact_order = [c.location_id for c in chunks]
    assert artifact_order == ["city_gate", "market_square", "tavern"], (
        f"Artifact order changed: {artifact_order}. "
        f"This affects [0]-selection in 4 consumers (B-09)."
    )