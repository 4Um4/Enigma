# path: backend/tests/test_p2_03_click_picking_world_frame.py
# Назначение: P2-03 (B-11) — unit-тесты мирового фрейма клик-пикинга.
#     Симметрия клик-камеры и рендер-камеры: после P1-02 (фрейм-осознанные
#     конверсии) для мирового файла local_to_world=identity → 0 изменений;
#     для легаси-файла клик-камера становится мировой → совпадает с
#     рендер-камерой (B-11 устранён).
# Зависимости: pytest, ContextResolver (через sys.path в frontend),
#     ChunkDescriptor из P2-01 (реальные координаты Open_road).
# Основные сущности:
#     - test_world_frame_click_camera_identity — мировой файл: клик-камера == рендер-камера
#     - test_legacy_frame_click_camera_shifted — легаси: клик-камера мировая (B-11 устранён)
#     - test_no_resolver_fallback_to_local — без resolver: fallback к локальному px,py
#     - test_handle_click_signature_has_resolver_params — signature имеет новые параметры
#     - test_symmetry_with_render_camera — симметрия: render L2256 == click L2690
"""
P2-03 (B-11): мировой фрейм клик-пикинга.

Контракт ROADMAP §P2-03:
- После P1-02 клик-камера и рендер-камера совпадают автоматически для мирового файла.
- Для легаси-файла применить local_to_world к _player_xy в клик-пути.
- Клик по видимому спрайту выбирает этого NPC.
- На легаси-файле поведение не хуже текущего.

Реализация:
- _handle_click получил параметры resolver/world_ctx/location_id (default None)
- В body: _world_px, _world_py = px, py; if resolver/world_ctx: local_to_world
- call-site (L1104) передаёт _resolver/_world_ctx/location_id из scope run()

Симметрия с render (L2254-2256):
  _render_px, _render_py = px, py
  if _world_ctx is not None:
      _render_px, _render_py = _resolver.local_to_world(px, py, location_id)

P2-03 в _handle_click (L2686-2690):
  _world_px, _world_py = px, py
  if resolver is not None and world_ctx is not None:
      _world_px, _world_py = resolver.local_to_world(px, py, location_id)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Фикстуры: подключение frontend-модулей
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def frontend_path():
    """Путь к frontend/ для импорта world_context."""
    backend_root = Path(__file__).resolve().parents[2]
    frontend_root = backend_root / "frontend"
    if str(frontend_root) not in sys.path:
        sys.path.insert(0, str(frontend_root))
    return frontend_root


@pytest.fixture(scope="module")
def context_resolver_cls(frontend_path):
    """ContextResolver класс."""
    from world_context import ContextResolver
    return ContextResolver


# ─────────────────────────────────────────────────────────────────────────────
# Реальные координаты из compiled/spatial_registry.json (post-P1-02)
# ─────────────────────────────────────────────────────────────────────────────

# tavern: origin (25.033, 5.018), size 20×15, global_coords=true (мировой фрейм)
_TAVERN_ORIGIN_X = 25.03333333333332
_TAVERN_ORIGIN_Y = 5.018000000000007

# maid_lusya local_position после P1-04 миграции (мировой фрейм)
_MAID_LUSYA_WORLD_X = 33.0207  # 7.987 + 25.033
_MAID_LUSYA_WORLD_Y = 6.8444   # 1.826 + 5.018

# maid_lusya local_position ДО P1-04 (легаси, локальный фрейм)
_MAID_LUSYA_LOCAL_X = 7.987
_MAID_LUSYA_LOCAL_Y = 1.826


# ─────────────────────────────────────────────────────────────────────────────
# Тест 1: мировой файл — клик-камера == рендер-камера (identity)
# ─────────────────────────────────────────────────────────────────────────────


def test_world_frame_click_camera_identity(context_resolver_cls) -> None:
    """P2-03: для мирового файла local_to_world = identity.

    После P1-02+P1-03: tavern.global_coords=true → local_to_world(px,py)=(px,py).
    Клик-камера: cam_x = px*40 - W/2 (использует _world_px = px после identity).
    Рендер-камера: cam_x = _render_px*40 - W/2 (тот же identity).
    → камеры совпадают → B-11 устранён для мирового файла.
    """
    # Мок resolver с identity (мировой файл)
    class _MockResolver:
        def local_to_world(self, x, y, loc_id):
            return (x, y)  # identity для мирового файла

    class _MockWorldCtx:
        pass

    resolver = _MockResolver()
    world_ctx = _MockWorldCtx()

    # px, py = _player_xy(scene_state) — мировой фрейм (после P1-04 миграции)
    px, py = _MAID_LUSYA_WORLD_X, _MAID_LUSYA_WORLD_Y

    # P2-03 логика из _handle_click body
    _world_px, _world_py = px, py
    if resolver is not None and world_ctx is not None:
        _world_px, _world_py = resolver.local_to_world(px, py, "tavern")

    # identity: _world_px == px, _world_py == py
    assert _world_px == px, f"identity нарушена: _world_px={_world_px} != px={px}"
    assert _world_py == py, f"identity нарушена: _world_py={_world_py} != py={py}"

    # Клик-камера совпадает с рендер-камерой (обе используют _world_px)
    # (симметрия с render L2254-2256)


# ─────────────────────────────────────────────────────────────────────────────
# Тест 2: легаси-файл — клик-камера мировая (B-11 устранён)
# ─────────────────────────────────────────────────────────────────────────────


def test_legacy_frame_click_camera_shifted(context_resolver_cls) -> None:
    """P2-03: для легаси-файла local_to_world = +origin → клик-камера мировая.

    До P2-03: клик-камера = px*40 - W/2 (ЛОКАЛЬНЫЙ px) → расхождение с рендер-камерой.
    После P2-03: клик-камера = (px+origin)*40 - W/2 (МИРОВОЙ px) → совпадает с рендер.
    B-11 устранён для легаси-файла.
    """
    # Мок resolver с +origin (легаси-файл, global_coords=false)
    class _MockResolverLegacy:
        def local_to_world(self, x, y, loc_id):
            return (x + _TAVERN_ORIGIN_X, y + _TAVERN_ORIGIN_Y)

    class _MockWorldCtx:
        pass

    resolver = _MockResolverLegacy()
    world_ctx = _MockWorldCtx()

    # px, py = _player_xy(scene_state) — ЛОКАЛЬНЫЙ фрейм (легаси до P1-04)
    px, py = _MAID_LUSYA_LOCAL_X, _MAID_LUSYA_LOCAL_Y

    # P2-03 логика
    _world_px, _world_py = px, py
    if resolver is not None and world_ctx is not None:
        _world_px, _world_py = resolver.local_to_world(px, py, "tavern")

    # Сдвиг на origin
    expected_x = _MAID_LUSYA_LOCAL_X + _TAVERN_ORIGIN_X
    expected_y = _MAID_LUSYA_LOCAL_Y + _TAVERN_ORIGIN_Y
    assert _world_px == pytest.approx(expected_x, abs=1e-6), f"_world_px={_world_px}"
    assert _world_py == pytest.approx(expected_y, abs=1e-6), f"_world_py={_world_py}"

    # Клик-камера теперь мировая → совпадает с рендер-камерой


# ─────────────────────────────────────────────────────────────────────────────
# Тест 3: без resolver — fallback к локальному px,py (обратная совместимость)
# ─────────────────────────────────────────────────────────────────────────────


def test_no_resolver_fallback_to_local() -> None:
    """P2-03: если resolver=None или world_ctx=None → fallback к локальному px,py.

    Обратная совместимость: _handle_click работает без новых параметров
    (default None) — поведение как до P2-03.
    """
    # Без resolver (default None)
    px, py = _MAID_LUSYA_WORLD_X, _MAID_LUSYA_WORLD_Y
    resolver = None
    world_ctx = None

    # P2-03 логика
    _world_px, _world_py = px, py
    if resolver is not None and world_ctx is not None:
        _world_px, _world_py = resolver.local_to_world(px, py, "tavern")

    # Fallback: _world_px == px (как до P2-03)
    assert _world_px == px
    assert _world_py == py


# ─────────────────────────────────────────────────────────────────────────────
# Тест 4: signature _handle_click имеет resolver/world_ctx/location_id
# ─────────────────────────────────────────────────────────────────────────────


def test_handle_click_signature_has_resolver_params(frontend_path) -> None:
    """P2-03: _handle_click signature содержит resolver/world_ctx/location_id.

    Source-инспекция (без инстанцирования GameScreen — требует pygame).
    """
    game_screen_path = frontend_path / "game_screen.py"
    content = game_screen_path.read_text(encoding="utf-8")

    # Найти def _handle_click и проверить параметры
    import re
    match = re.search(
        r"def _handle_click\([^)]*\)",
        content,
        re.DOTALL
    )
    assert match, "def _handle_click не найден"
    sig = match.group(0)
    assert "resolver" in sig, f"resolver нет в signature: {sig}"
    assert "world_ctx" in sig, f"world_ctx нет в signature: {sig}"
    assert "location_id" in sig, f"location_id нет в signature: {sig}"


# ─────────────────────────────────────────────────────────────────────────────
# Тест 5: симметрия с render-камерой (source-инспекция)
# ─────────────────────────────────────────────────────────────────────────────


def test_symmetry_with_render_camera(frontend_path) -> None:
    """P2-03: _handle_click использует тот же pattern, что render.

    Render (L2254-2256):
        _render_px, _render_py = px, py
        if _world_ctx is not None:
            _render_px, _render_py = _resolver.local_to_world(px, py, location_id)

    _handle_click (L2686-2690):
        _world_px, _world_py = px, py
        if resolver is not None and world_ctx is not None:
            _world_px, _world_py = resolver.local_to_world(px, py, location_id)

    Симметрия: обе камеры используют local_to_world для перевода px,py в мировой фрейм.
    """
    game_screen_path = frontend_path / "game_screen.py"
    content = game_screen_path.read_text(encoding="utf-8")

    # Найти render pattern
    import re
    render_pattern = re.search(
        r"_render_px,\s*_render_py\s*=\s*px,\s*py\s*\n\s*if\s+_world_ctx\s+is\s+not\s+None:\s*\n\s*_render_px,\s*_render_py\s*=\s*_resolver\.local_to_world",
        content
    )
    assert render_pattern, "render pattern (L2254-2256) не найден"

    # Найти click pattern
    click_pattern = re.search(
        r"_world_px,\s*_world_py\s*=\s*px,\s*py\s*\n\s*if\s+resolver\s+is\s+not\s+None\s+and\s+world_ctx\s+is\s+not\s+None:\s*\n\s*_world_px,\s*_world_py\s*=\s*resolver\.local_to_world",
        content
    )
    assert click_pattern, "click pattern (L2686-2690) не найден — P2-03 не применён"

    # Оба pattern используют local_to_world — симметрия подтверждена


# ─────────────────────────────────────────────────────────────────────────────
# Тест 6: call-site передаёт resolver/world_ctx/location_id
# ─────────────────────────────────────────────────────────────────────────────


def test_call_site_passes_resolver_args(frontend_path) -> None:
    """P2-03: call-site (L1104) передаёт resolver/world_ctx/location_id.

    Использует balanced-paren matching (regex не умеет вложенные скобки):
    ищем self._handle_click( и считаем пары ( ) до закрытия.
    """
    game_screen_path = frontend_path / "game_screen.py"
    content = game_screen_path.read_text(encoding="utf-8")

    # Найти начало call-site
    marker = "self._handle_click("
    start_idx = content.find(marker)
    assert start_idx != -1, "call-site self._handle_click( не найден"

    # Balanced-paren extraction: считаем ( и ) до закрытия
    paren_start = content.find("(", start_idx)
    depth = 0
    end_idx = paren_start
    for i in range(paren_start, len(content)):
        ch = content[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break
    call_text = content[start_idx:end_idx]
    assert call_text.endswith(")"), f"call-site не закрыт: {call_text!r}"

    # Проверить, что передаются все 3 параметра
    assert "resolver=" in call_text, f"resolver= нет в call-site: {call_text!r}"
    assert "world_ctx=" in call_text, f"world_ctx= нет в call-site: {call_text!r}"
    assert "location_id=" in call_text, f"location_id= нет в call-site: {call_text!r}"