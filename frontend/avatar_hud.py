"""
path: /frontend/avatar_hud.py
Назначение: HUD аватара — числа-виджеты до-релизной версии (вердикт
    Мастера: отдельный интегрируемый файл; замена файла = любые виды
    отображения без правки game_screen). Читает ТОЛЬКО существующие
    каналы: embodied_status (gold/food/weight/needs) + avatar_state
    (body_state: current_hp/money, life_status). Отсутствие поля =
    строка не рисуется (§ENIGMA-003: отсутствие ≠ 0). Стиль — токены
    темы через инъекцию (закон темы; RGB-литералы AnalysisRenderer
    не наследуются).
Зависимости: pygame
Основные сущности: draw()
"""
import pygame

# Позиционирование: левый нижний угол, выше safe-area workbench (~30px
# hint-полоса) — как у прежнего embodied-рендера S151, но без наложения.
_MARGIN = 15
_LINE_H = 20


def _need_label(nid: str) -> str:
    _names = {"food": "Голод", "income": "Финансы", "shelter": "Усталость",
              "social": "Одиночество"}
    return _names.get(nid, nid)


def _need_color(sev: str, theme) -> tuple:
    # Severity-градация каналами темы: жёлтый→оранжевый→красный
    # отражается token-ами (danger для критичных; текст — text_primary)
    _map = {"moderate": "text_primary", "major": "accent",
            "critical": "danger", "extreme": "danger"}
    return theme.token(_map.get(sev, "text_muted"))


def draw(screen: pygame.Surface, scene_state: dict, theme, font=None) -> None:
    """Контракт интеграции: одна точка вызова из game_screen. theme —
    WorkbenchScreen.theme (токены); font — шрифт (по умолчанию SysFont 15,
    консистентно AnalysisRenderer-кеглю S151)."""
    if not isinstance(scene_state, dict):
        return
    if font is None:
        font = pygame.font.SysFont("consolas", 15)

    _emb = scene_state.get("embodied_status") or {}
    _av = scene_state.get("avatar_state") or {}
    _bs = (_av.get("body_state") or {}) if isinstance(_av, dict) else {}

    _lines = []  # [(text, color-token)]
    # HP: из body_state (SSOT ADR-HP-UNIFICATION); нет поля — нет строки
    _hp = _bs.get("current_hp")
    _hp_max = _bs.get("max_hp") or _bs.get("effective_max_hp")
    if _hp is not None:
        _hp_s = f"HP {_hp:.0f}" + (f"/{_hp_max:.0f}" if _hp_max else "")
        _hp_tok = ("danger" if _av.get("life_status") == "DEAD" or
                   (_hp_max and _hp < _hp_max * 0.3) else "text_primary")
        _lines.append((_hp_s, _hp_tok))
    # Деньги: embodied.gold — феноменологический канал S151
    _gold = _emb.get("gold")
    if _gold is not None:
        _lines.append((f"Золото: {_gold:.0f}", "accent"))
    # Еда
    _food = _emb.get("food_count")
    if _food is not None:
        _lines.append((f"Еда: {_food:.0f}", "text_primary"))
    # Вес (только перегруз ≥80% — не мусорим HUD в норме)
    _w, _mw = _emb.get("current_weight"), _emb.get("max_weight")
    if _w and _mw and _w > _mw * 0.8:
        _lines.append((f"Вес: {_w:.1f}/{_mw:.0f}", "danger"))
    # Потребности: moderate+ (канал S151; числа по вердикту — до-релиз)
    for _need in (_emb.get("active_needs") or []):
        _sev = _need.get("severity", "minor")
        if _sev in ("moderate", "major", "critical", "extreme"):
            _lines.append((
                f"{_need_label(_need.get('id', ''))}: "
                f"{_need.get('urgency', 0):.2f}",
                _need_color(_sev, theme)))

    if not _lines:
        return  # пустой аватар — пустой HUD (не рисуем рамку-пустышку)

    # Полупрозрачная подложка (текст непрозрачен — вердикт Мастера)
    _x = _MARGIN
    _y = screen.get_height() - 30 - _MARGIN - len(_lines) * _LINE_H
    _bg = pygame.Surface((_bg_w := max(font.size(t)[0] for t, _ in _lines) + 16,
                          len(_lines) * _LINE_H + 8), pygame.SRCALPHA)
    _bg.fill((*theme.token("surface_panel"), 180))
    screen.blit(_bg, (_x - 8, _y - 4))
    for _t, _tok in _lines:
        _s = font.render(_t, True, theme.token(_tok))
        screen.blit(_s, (_x, _y))
        _y += _LINE_H
