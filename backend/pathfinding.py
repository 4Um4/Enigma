"""
backend/pathfinding.py
A* pathfinding с человеческим поведением:
  - "Страх стен" — COST_FIELD, A* избегает ходить вплотную
  - LOS-сглаживание — путь по прямым линиям, не "ступеньки"
  - Catmull-Rom сплайн — плавные дуги на поворотах
  - Микро-шум — живость траектории
"""

import heapq
import math
import random
from typing import Dict, List, Optional, Tuple

CELL_SIZE = 0.5
WALL_COST_RADIUS = 1.5  # метров — зона повышенной стоимости у стен


def _point_near_segment(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    threshold: float,
) -> bool:
    """Расстояние от точки до отрезка меньше threshold"""
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - x1, py - y1) < threshold
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y) < threshold


def _point_to_segment_dist(
    px: float,
    py: float,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    """Точное расстояние от точки до отрезка"""
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def _build_grid_and_costs(
    scene_w: float,
    scene_h: float,
    walls: List[dict],
    obstacles: List[dict],
) -> Tuple[Dict[Tuple[int, int], bool], Dict[Tuple[int, int], float]]:
    """
    Строит grid (проходимость) и cost_map (страх стен).
    cost_map > 1.0 у стен — A* выбирает центр коридора.
    """
    cols = int(math.ceil(scene_w / CELL_SIZE))
    rows = int(math.ceil(scene_h / CELL_SIZE))
    grid: Dict[Tuple[int, int], bool] = {}
    cost_map: Dict[Tuple[int, int], float] = {}

    for r in range(rows):
        for c in range(cols):
            grid[(c, r)] = True
            cost_map[(c, r)] = 1.0

    # Блокируем стены + считаем расстояние для cost_map
    for wall in walls:
        x1, y1 = wall["x1"], wall["y1"]
        x2, y2 = wall["x2"], wall["y2"]

        c1 = max(0, min(int(x1 / CELL_SIZE), int(x2 / CELL_SIZE)) - 1)
        r1 = max(0, min(int(y1 / CELL_SIZE), int(y2 / CELL_SIZE)) - 1)
        c2 = min(cols - 1, max(int(x1 / CELL_SIZE), int(x2 / CELL_SIZE)) + 1)
        r2 = min(rows - 1, max(int(y1 / CELL_SIZE), int(y2 / CELL_SIZE)) + 1)

        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                cx = (c + 0.5) * CELL_SIZE
                cy = (r + 0.5) * CELL_SIZE
                if _point_near_segment(cx, cy, x1, y1, x2, y2, CELL_SIZE * 0.6):
                    grid[(c, r)] = False
                elif (c, r) in grid:
                    # Страх стен — экспоненциальный штраф
                    dist = _point_to_segment_dist(cx, cy, x1, y1, x2, y2)
                    if dist < WALL_COST_RADIUS:
                        penalty = 1.0 + 3.0 * math.exp(-dist * 2.0)
                        cost_map[(c, r)] = max(cost_map[(c, r)], penalty)

    # Блокируем препятствия + cost вокруг них
    for obs in obstacles:
        ox, oy = obs["x"], obs["y"]
        ow, oh = obs["w"], obs["h"]

        # Data-driven: проверяем возможность преодоления (перепрыгнуть/проползти)
        passthrough = obs.get("passability", {})
        can_bypass = passthrough.get("jump_over", False) or passthrough.get(
            "crawl_under", False
        )
        # Штраф за преодоление — A* выберет обход, если он дешевле
        bypass_cost = 3.0
        if passthrough.get("jump_over", False):
            bypass_cost = 2.5  # Перепрыгнуть быстрее, чем ползти
        elif passthrough.get("crawl_under", False):
            bypass_cost = 4.0  # Ползти медленно

        c1 = max(0, int((ox - ow / 2) / CELL_SIZE) - 1)
        r1 = max(0, int((oy - oh / 2) / CELL_SIZE) - 1)
        c2 = min(cols - 1, int((ox + ow / 2) / CELL_SIZE) + 1)
        r2 = min(rows - 1, int((oy + oh / 2) / CELL_SIZE) + 1)

        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if (c, r) not in grid:
                    continue
                # Центр внутри препятствия
                ccx = (c + 0.5) * CELL_SIZE
                ccy = (r + 0.5) * CELL_SIZE
                half_w = ow / 2 + 0.1
                half_h = oh / 2 + 0.1
                if (
                    ox - half_w <= ccx <= ox + half_w
                    and oy - half_h <= ccy <= oy + half_h
                ):
                    if can_bypass:
                        # Разрешаем прохождение со штрафом к стоимости пути
                        grid[(c, r)] = True
                        cost_map[(c, r)] = max(cost_map[(c, r)], bypass_cost)
                    else:
                        grid[(c, r)] = False
                else:
                    dist = _rect_distance(ccx, ccy, ox, oy, ow, oh)
                    if dist < WALL_COST_RADIUS:
                        penalty = 1.0 + 4.0 * math.exp(-dist * 2.5)
                        cost_map[(c, r)] = max(cost_map[(c, r)], penalty)

    return grid, cost_map


def _rect_distance(
    px: float,
    py: float,
    rx: float,
    ry: float,
    rw: float,
    rh: float,
) -> float:
    """Расстояние от точки до прямоугольника"""
    cx = max(rx - rw / 2, min(px, rx + rw / 2))
    cy = max(ry - rh / 2, min(py, ry + rh / 2))
    return math.hypot(px - cx, py - cy)


def _world_to_grid(x: float, y: float) -> Tuple[int, int]:
    return int(x / CELL_SIZE), int(y / CELL_SIZE)


def _grid_to_world(col: int, row: int) -> Tuple[float, float]:
    return (col + 0.5) * CELL_SIZE, (row + 0.5) * CELL_SIZE


def _heuristic(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy)


def _neighbors(
    node: Tuple[int, int], grid: Dict[Tuple[int, int], bool]
) -> List[Tuple[int, int]]:
    c, r = node
    result = []
    for dc in (-1, 0, 1):
        for dr in (-1, 0, 1):
            if dc == 0 and dr == 0:
                continue
            neighbor = (c + dc, r + dr)
            if grid.get(neighbor, False):
                result.append(neighbor)
    return result


def _find_nearest_free(
    node: Tuple[int, int],
    grid: Dict[Tuple[int, int], bool],
    max_radius: int = 8,
) -> Optional[Tuple[int, int]]:
    for radius in range(1, max_radius + 1):
        for dc in range(-radius, radius + 1):
            for dr in range(-radius, radius + 1):
                if abs(dc) != radius and abs(dr) != radius:
                    continue
                candidate = (node[0] + dc, node[1] + dr)
                if grid.get(candidate, False):
                    return candidate
    return None


def find_path(
    start_x: float,
    start_y: float,
    goal_x: float,
    goal_y: float,
    scene_w: float,
    scene_h: float,
    walls: List[dict],
    obstacles: List[dict],
    max_iterations: int = 3000,
    humanize: bool = True,
) -> Optional[List[Tuple[float, float]]]:
    """
    A* с cost-field, LOS-сглаживанием и Catmull-Rom сплайном.
    humanize=True — добавляет микро-шум для живости.
    """
    grid, cost_map = _build_grid_and_costs(scene_w, scene_h, walls, obstacles)

    start = _world_to_grid(start_x, start_y)
    goal = _world_to_grid(goal_x, goal_y)

    if not grid.get(goal, False):
        goal = _find_nearest_free(goal, grid)
    if not grid.get(start, False):
        start = _find_nearest_free(start, grid)
    if goal is None or start is None:
        return None

    if start == goal:
        return [_grid_to_world(*goal)]

    # A* с cost_map
    open_set: list = [(0.0, start)]
    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
    g_score: Dict[Tuple[int, int], float] = {start: 0.0}
    closed: set = set()
    iterations = 0

    while open_set and iterations < max_iterations:
        iterations += 1
        _, current = heapq.heappop(open_set)

        if current == goal:
            raw_path = _reconstruct_grid_path(came_from, current)
            world_path = [_grid_to_world(*n) for n in raw_path]
            smoothed = _los_smooth(world_path, walls, obstacles)
            splined = _catmull_rom(smoothed)
            if humanize:
                splined = _humanize_path(splined)
            return splined

        if current in closed:
            continue
        closed.add(current)

        for neighbor in _neighbors(current, grid):
            if neighbor in closed:
                continue

            dc = abs(neighbor[0] - current[0])
            dr = abs(neighbor[1] - current[1])
            step_cost = math.sqrt(2) if dc + dr == 2 else 1.0
            step_cost *= cost_map.get(neighbor, 1.0)

            tentative_g = g_score[current] + step_cost

            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + _heuristic(neighbor, goal)
                heapq.heappush(open_set, (f, neighbor))

    return None


def _reconstruct_grid_path(
    came_from: Dict[Tuple[int, int], Tuple[int, int]],
    current: Tuple[int, int],
) -> List[Tuple[int, int]]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


# === LOS-сглаживание ===


def _has_los(
    a: Tuple[float, float],
    b: Tuple[float, float],
    walls: List[dict],
    obstacles: List[dict],
    steps: int = 20,
) -> bool:
    """Проверяет прямую видимость между двумя точками"""
    for i in range(1, steps):
        t = i / steps
        x = a[0] + (b[0] - a[0]) * t
        y = a[1] + (b[1] - a[1]) * t

        for wall in walls:
            if _point_near_segment(
                x, y, wall["x1"], wall["y1"], wall["x2"], wall["y2"], 0.2
            ):
                return False

        for obs in obstacles:
            half_w = obs["w"] / 2
            half_h = obs["h"] / 2
            if (
                obs["x"] - half_w - 0.1 <= x <= obs["x"] + half_w + 0.1
                and obs["y"] - half_h - 0.1 <= y <= obs["y"] + half_h + 0.1
            ):
                return False
    return True


def _los_smooth(
    path: List[Tuple[float, float]],
    walls: List[dict],
    obstacles: List[dict],
) -> List[Tuple[float, float]]:
    """Сглаживание через прямые видимости — убирает "ступеньки" сетки"""
    if len(path) <= 2:
        return path

    smoothed = [path[0]]
    i = 0
    while i < len(path) - 1:
        # Ищем самую дальнюю точку до которой можно дойти напрямую
        j = len(path) - 1
        while j > i + 1:
            if _has_los(smoothed[-1], path[j], walls, obstacles):
                break
            j -= 1
        smoothed.append(path[j])
        i = j
    return smoothed


# === Catmull-Rom сплайн ===


def _catmull_rom(
    path: List[Tuple[float, float]],
    samples_per_segment: int = 4,
) -> List[Tuple[float, float]]:
    """Интерполирует путь Catmull-Rom сплайном для плавных поворотов"""
    if len(path) <= 2:
        return list(path)

    # Добавляем виртуальные точки в начале и конце
    extended = [path[0]] + list(path) + [path[-1]]

    result: List[Tuple[float, float]] = [path[0]]
    for i in range(1, len(extended) - 2):
        p0 = extended[i - 1]
        p1 = extended[i]
        p2 = extended[i + 1]
        p3 = extended[i + 2]

        for t_idx in range(1, samples_per_segment + 1):
            t = t_idx / samples_per_segment
            t2 = t * t
            t3 = t2 * t

            x = 0.5 * (
                (2 * p1[0])
                + (-p0[0] + p2[0]) * t
                + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                (2 * p1[1])
                + (-p0[1] + p2[1]) * t
                + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
            )
            result.append((x, y))

    return result


# === Живость ===


def _humanize_path(
    path: List[Tuple[float, float]],
    amplitude: float = 0.08,
) -> List[Tuple[float, float]]:
    """Добавляет микро-отклонения — траектория не идеальная прямая"""
    if len(path) <= 3:
        return list(path)

    result = [path[0]]
    for i in range(1, len(path) - 1):
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(0, amplitude)
        x = path[i][0] + math.cos(angle) * dist
        y = path[i][1] + math.sin(angle) * dist
        result.append((x, y))
    result.append(path[-1])
    return result
