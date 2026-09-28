"""
path: /frontend/ui_workbench/workbench_screen.py
Назначение: Shell UI Workbench v3a — оверлей окон поверх сцены (game или editor),
drag заголовком с магнитным прилипанием (SnapEngine, паттерн Windhawk),
free_rect-геометрия, safe-area, живой dialog_journal в game-контексте.
Зависимости: pygame, ui_workbench.*
Основные сущности: WorkbenchScreen
"""
import colorsys
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import pygame

from ui_workbench import (
    InputDispatcher,
    ThemeLoader,
    WindowRegistry,
    WindowState,
    WorkbenchPersistence,
)
from ui_workbench.editor_board_stub import EditorBoardStub
from ui_workbench.fonts import FontProvider as _FontProvider
from ui_workbench.layout import AnchoredRect
from ui_workbench.snap_engine import SnapEngine
from ui_workbench.windows.board_window import BOARD_MANIFEST
from ui_workbench.windows.journal_window import JOURNAL_MANIFEST

_WORKBENCH_DIR = Path(__file__).parent
_LAYOUT_PATH = _WORKBENCH_DIR / "window_layout.json"
_THEME_PATH = _WORKBENCH_DIR / "theme.json"
_STYLES_PATH = _WORKBENCH_DIR / "style_overrides.json"  # S4: персист стилей

_TITLE_H = 34
_AVATAR = 60  # S3.11: аватар журнала (Discord-стиль, читаемый размер)

# S3.5: русификация стилевых токенов (панель СТИЛЬ + HSV-пикер)
_TOKEN_RU = {
    "surface_panel": "Фон окна",
    "surface_title": "Фон заголовка",
    "border": "Рамка",
    "border_accent": "Рамка-акцент",
    "text_primary": "Текст основной",
    "text_muted": "Текст приглушённый",
    "accent": "Акцент",
    "player_bubble": "Пузырь игрока",
    "player_name": "Имя игрока",
    "noise_tint": "Подтон узора",
}

# S3.7: дефолты нестандартных токенов (их нет в theme.json)
_TOKEN_DEFAULTS = {
    "player_bubble": (35, 45, 70),
    "player_name": (255, 200, 100),
    "noise_tint": (255, 255, 255),
}

# S3.14: узоры «штукатурки» фона (grain=зерно, wave=волны, speck=крап)
_PATTERN_RU = {"grain": "Зерно", "wave": "Волны", "speck": "Крап"}

# S3.10: пресеты палитр окон — благородные сочетания, читаемость текста.
# Каждый пресет полностью задаёт _colors (включая альфы поверхностей
# и прозрачную подложку — фон окон единообразен, см. S3.9-фикс).
_COLOR_PRESETS = {
    "Полночь": {
        "surface_panel": (26, 26, 36), "surface_title": (34, 34, 48),
        "border": (70, 70, 90), "border_accent": (200, 160, 80),
        "text_primary": (222, 222, 232), "text_muted": (150, 150, 165),
        "accent": (200, 160, 80), "player_bubble": (35, 45, 70),
        "player_name": (255, 200, 100), "backdrop_rgb": (10, 10, 18),
        "surface_panel_alpha": 255, "surface_title_alpha": 255,
        "border_alpha": 255, "border_accent_alpha": 255,
        "player_bubble_alpha": 255, "backdrop_alpha": 0,
    },
    "Грувбокс": {  # gruvbox dark: тёплый винтаж, золотой акцент
        "surface_panel": (40, 40, 38), "surface_title": (60, 56, 54),
        "border": (80, 73, 69), "border_accent": (215, 153, 33),
        "text_primary": (235, 219, 178), "text_muted": (146, 131, 116),
        "accent": (215, 153, 33), "player_bubble": (60, 56, 54),
        "player_name": (250, 189, 47), "backdrop_rgb": (40, 40, 38),
        "surface_panel_alpha": 255, "surface_title_alpha": 255,
        "border_alpha": 255, "border_accent_alpha": 255,
        "player_bubble_alpha": 255, "backdrop_alpha": 0,
    },
    "Солариз": {  # solarized dark: CIELAB-контраст, глубокий сине-зелёный
        "surface_panel": (0, 43, 54), "surface_title": (7, 54, 66),
        "border": (88, 110, 117), "border_accent": (181, 137, 0),
        "text_primary": (131, 148, 150), "text_muted": (88, 110, 117),
        "accent": (181, 137, 0), "player_bubble": (7, 54, 66),
        "player_name": (203, 161, 30), "backdrop_rgb": (0, 43, 54),
        "surface_panel_alpha": 255, "surface_title_alpha": 255,
        "border_alpha": 255, "border_accent_alpha": 255,
        "player_bubble_alpha": 255, "backdrop_alpha": 0,
    },
    "Норд": {  # nord: полярная ночь + тёплая «аврора»
        "surface_panel": (46, 52, 64), "surface_title": (59, 66, 82),
        "border": (76, 86, 106), "border_accent": (235, 203, 139),
        "text_primary": (216, 222, 233), "text_muted": (129, 161, 193),
        "accent": (136, 192, 208), "player_bubble": (59, 66, 82),
        "player_name": (235, 203, 139), "backdrop_rgb": (46, 52, 64),
        "surface_panel_alpha": 255, "surface_title_alpha": 255,
        "border_alpha": 255, "border_accent_alpha": 255,
        "player_bubble_alpha": 255, "backdrop_alpha": 0,
    },
    "Обсидиан": {  # чёрный + золото
        "surface_panel": (16, 15, 14), "surface_title": (24, 22, 19),
        "border": (60, 52, 38), "border_accent": (197, 160, 74),
        "text_primary": (224, 216, 196), "text_muted": (146, 136, 116),
        "accent": (197, 160, 74), "player_bubble": (28, 25, 20),
        "player_name": (232, 195, 105), "backdrop_rgb": (12, 11, 10),
        "surface_panel_alpha": 255, "surface_title_alpha": 255,
        "border_alpha": 255, "border_accent_alpha": 255,
        "player_bubble_alpha": 255, "backdrop_alpha": 0,
    },
    "Багрянец": {  # чёрный + багряная рамка + золотой текст
        "surface_panel": (22, 12, 14), "surface_title": (32, 16, 18),
        "border": (90, 32, 36), "border_accent": (176, 48, 48),
        "text_primary": (232, 216, 206), "text_muted": (168, 130, 122),
        "accent": (206, 160, 84), "player_bubble": (34, 16, 18),
        "player_name": (226, 176, 92), "backdrop_rgb": (16, 8, 9),
        "surface_panel_alpha": 255, "surface_title_alpha": 255,
        "border_alpha": 255, "border_accent_alpha": 255,
        "player_bubble_alpha": 255, "backdrop_alpha": 0,
    },
}


class _WindowThemeAdapter:
    """S3.5: локальный `theme` для рендера КОНТЕНТА окна: .token() читает
    цвет из стиля окна (пикер/broadcast), а не из темы. Рамка уже красится
    через _ct напрямую — это тот же контракт для ленты журнала."""

    def __init__(self, wb, wid: Optional[str]):
        self._wb = wb
        self._wid = wid

    def token(self, name: str):
        return self._wb._ct(self._wid, name)


class _StyledFontProxy:
    """S3.7: обёртка Font — render() применяет типографику стиля окна
    (обводка/тень букв). Все точки рендера зовут .render() как раньше —
    прокси прозрачен для вызывающих. Эффекты per-role (title/text)."""

    def __init__(self, font, wb, role: str, wid: Optional[str] = None):
        self._font = font
        self._wb = wb
        self._role = role
        self._wid = wid  # S3.8: фиксация окна для мировых потребителей

    def _pad(self) -> int:
        _ov = self._wb._ov(self._role, self._wid)
        return (int(_ov.get("outline", 0)) * 2
                + (3 if _ov.get("shadow") else 0)
                + int(round(float(_ov.get("glow", 0)) * 8))
                + (3 if _ov.get("underline") else 0))

    def _base(self, text, antialias, color, spacing):
        """S3.14: разрядка — посимвольный рендер с шагом spacing."""
        if spacing == 0 or not text:
            return self._font.render(text, antialias, color)
        _parts = [self._font.render(ch, antialias, color) for ch in text]
        _w = sum(p.get_width() for p in _parts) + spacing * max(0, len(_parts) - 1)
        _s = pygame.Surface((_w, self._font.get_height()), pygame.SRCALPHA)
        _x = 0
        for p in _parts:
            _s.blit(p, (_x, 0))
            _x += p.get_width() + spacing
        return _s

    def render(self, text, antialias, color):
        _ov = self._wb._ov(self._role, self._wid)
        _ol = int(_ov.get("outline", 0))
        _sh = bool(_ov.get("shadow", False))
        _gl = float(_ov.get("glow", 0))
        _sp = int(_ov.get("spacing", 0))
        _ul = bool(_ov.get("underline", False))
        base = self._base(text, antialias, color, _sp)
        if _ol <= 0 and not _sh and _gl <= 0 and _sp <= 0 and not _ul:
            return base
        _p = self._pad()
        surf = pygame.Surface((base.get_width() + _p * 2, base.get_height() + _p * 2),
                              pygame.SRCALPHA)
        if _sh:
            # Тень: полупрозрачная копия со смещением вниз-вправо
            _shc = tuple(_ov.get("shadow_color", (0, 0, 0, 150)))
            surf.blit(self._base(text, antialias, _shc, _sp), (_p + 2, _p + 2))
        if _gl > 0:
            # S3.14-фикс2: ореол = копии свечения, накопленные аддитивно
            # (BLEND_RGBA_ADD пишет и альфу) на СВОЕЙ поверхности по кругу:
            # центр насыщен, край мягко затухает. Масштабированные копии
            # текста давали «двойник» — убраны.
            # дробная интенсивность 0-1: гасит цвет и радиус ореола
            _gpow = max(0.05, min(1.0, _gl))
            _gc0 = tuple(_ov.get("glow_color", (255, 226, 150)))
            _gc = tuple(int(c * (0.25 + 0.75 * _gpow)) for c in _gc0)
            _gs = self._base(text, antialias, _gc, _sp)
            _halo = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            _r = 1 + int(round(_gpow * 3))  # радиус: 1..4
            for _dx in range(-_r, _r + 1):
                for _dy in range(-_r, _r + 1):
                    if _dx * _dx + _dy * _dy <= _r * _r + 1:
                        _halo.blit(_gs, (_p + _dx * 2, _p + _dy * 2),
                                   special_flags=pygame.BLEND_RGBA_ADD)
            surf.blit(_halo, (0, 0))
        if _ol > 0:
            # Обводка: 8/24/48 смещённых копий цветом контура
            _oc = tuple(_ov.get("outline_color", (10, 10, 14)))
            _ols = self._base(text, antialias, _oc, _sp)
            for _dx in range(-_ol, _ol + 1):
                for _dy in range(-_ol, _ol + 1):
                    if _dx or _dy:
                        surf.blit(_ols, (_p + _dx, _p + _dy))
        surf.blit(base, (_p, _p))
        if _ul:
            # S3.14: подчёркивание — НИЖЕ глифов (включая выносные р/у/д),
            # иначе пересекает их и выглядит зачёркиванием
            pygame.draw.line(surf, color,
                             (_p, _p + base.get_height() + 1),
                             (_p + base.get_width(), _p + base.get_height() + 1), 1)
        return surf

    def get_linesize(self):
        return self._font.get_linesize() + self._pad()

    def get_height(self):
        return self._font.get_height() + self._pad()

    def size(self, text):
        w, h = self._font.size(text)
        _p = self._pad()
        _ov = self._wb._ov(self._role, self._wid)
        _sp = int(_ov.get("spacing", 0))
        return (max(1, w + _sp * max(0, len(text) - 1) + _p * 2), h + _p * 2)


class WorkbenchScreen:
    def __init__(self, core, game_context: bool = False) -> None:
        """game_context=True: живой dialog_journal + safe-area гейта (game_screen).
        False (editor): демо-данные, зона = весь экран минус тосты."""
        self._core = core
        self.game_context = game_context
        self.active = False
        self._screen = core.screen

        self.registry = WindowRegistry()
        self.registry.register(JOURNAL_MANIFEST)
        from ui_workbench.windows.mini_windows import TIME_SCALE_MANIFEST, WORLD_CLOCK_MANIFEST
        self.registry.register(WORLD_CLOCK_MANIFEST)
        self.registry.register(TIME_SCALE_MANIFEST)
        from ui_workbench.windows.mini_windows import INVENTORY_MANIFEST, OBSERVATIONS_MANIFEST
        self.registry.register(OBSERVATIONS_MANIFEST)
        self.registry.register(INVENTORY_MANIFEST)
        self.registry.register(BOARD_MANIFEST)

        # ДО восстановления layout: free_rects инициализируется первым —
        # restore-цикл пишет в него (use-before-init ловится только при
        # непустом window_layout.json; fix: порядок объявления).
        self._free_rects: Dict[str, Optional[Tuple[int, int, int, int]]] = {}

        self._persist = WorkbenchPersistence(_LAYOUT_PATH)
        try:
            for wid, rec in self._persist.load_window_states().items():
                # v2-совместимость: строка → {"state": ...} (миграция on-read)
                record = {"state": rec, "free_rect": None} if isinstance(rec, str) else rec
                # Guard: в layout может лежать окно без манифеста (удалённое
                # из кода) — такой id пропускаем, restore бы упал KeyError.
                if wid not in self.registry.all_ids():
                    continue
                _state = record.get("state", "hidden")
                if wid == "board" and _state == "full":
                    # Доска — рабочая поверхность, не витрина: при старте
                    # игры всегда свёрнута (позиция/размер персистятся,
                    # состояние — нет). FULL живёт только внутри сессии.
                    _state = "collapsed"
                self.registry.restore(wid, _state)
                fr = record.get("free_rect")
                # Валидация free_rect против degenerate-геометрии (урок краша
                # Surface: [x, y, w, 34] от collapsed-сессии): меньше min_size
                # манифеста = считаем битым, окно живёт по анкеру.
                manifest = self.registry.manifest(wid)
                if (fr and len(fr) == 4
                        and fr[2] >= manifest.min_size[0]
                        and fr[3] >= manifest.min_size[1]):
                    self._free_rects[wid] = tuple(fr)
                else:
                    self._free_rects[wid] = None
        except (ValueError, TypeError) as e:
            print(f"[WORKBENCH] layout пропущен: {e}")

        self.theme = ThemeLoader(_THEME_PATH).load()
        self.dispatcher = InputDispatcher(self.registry)
        self._snap = SnapEngine()

        self._rects: Dict[str, pygame.Rect] = {}
        self._drag: Optional[list] = None  # [wid, grab-офсет] (drag — сразу, порога нет)
        self._resize: Optional[list] = None  # S3: [wid, [left,right,top,bottom], [x,y,w,h] старт]
        self._title_rects: Dict[str, pygame.Rect] = {}
        self._arrow_rects: Dict[str, pygame.Rect] = {}  # зоны ▸/▾ (toggle, OS-паттерн)
        self._active_tab: Dict[str, str] = {}   # wid → tab_id (dialog по умолчанию)
        self._tab_rects: Dict[str, list] = {}   # wid → [(hit_rect, tab_id)]
        self.hud_time_scale: str = "▶ 1x"  # M-HUD: канал мини-окна time_scale (пишет game_screen)
        self._journal_body_rects: Dict[str, pygame.Rect] = {}  # M19: зона wheel-скролла
        self._dialog_peer: Dict[str, Optional[str]] = {}  # Диалог-А: wid → спикер-фильтр (None = Все)
        self._peer_rects: Dict[str, list] = {}  # Диалог-А: wid → [(hit_rect, peer_or_None)]
        self._journal_entry_rects: Dict[str, list] = {}  # A1: wid → [(hit_rect, event_id_or_"")]
        self._journal_scroll: Dict[str, int] = {}  # M19: wid → скрытых НОВЫХ блоков снизу (0 = низ)
        self._scroll_hint_rects: Dict[str, tuple] = {}  # M19: wid → (▲-hit, ▼-hit) или (None, None)

        # Phase 4: Investigation Board — интеракции (MVI)
        self._board_cache: Optional[dict] = None
        self._board_error: Optional[str] = None
        self._board_selected: list = []       # до 2 card_id
        self._board_drag_id: Optional[str] = None
        self._board_drag_off = (0, 0)
        self._board_link_kind = "PLAYER_SUPPORTS"
        self._board_hover_tips: Dict[str, Optional[tuple]] = {}  # B3: cid → (speaker, полный текст)
        self._board_input = None            # C1: inline-TextInput гипотезы (ленивый)
        self._board_input_mode: Optional[tuple] = None  # None | ("create",) | ("edit", hyp_id)
        self._board_stub = EditorBoardStub()  # P: полигон редактора (in-memory)
        self._board_card_scroll: Dict[str, int] = {}  # №6: cid → скрытые строки сверху

        # Демо-данные (editor-контекст); game_context их не использует.
        # M19/M12 smoke-набор: все 4 канала, 3 подряд-реплики одного
        # спикера (будущий тест группировки), 2 длинных текста (wrap и
        # превышение бюджета → индикатор "▲ N ниже"), пары NPC→NPC
        # (прообраз M17: подслушанное обращение = tentative-имя).
        self._demo_journal = [
            {"speaker": "Рассказчик", "text": "Демо: таверна «Серебряный волк» открывается на закате. Сквозь щели ставень тянет дымом и запахом жареного лука.", "channel": "narrative"},
            {"speaker": "Торнин Серебряная Луна", "text": "Демо: проходи, не стой в дверях. Вечер только начался.", "channel": "direct", "event_id": "demo-evt-001"},
            {"speaker": "Кузнец Орм", "text": "Демо: сталь не соврёт, если её спросить.", "channel": "direct", "event_id": "demo-evt-002"},
            {"speaker": "Ты", "text": "Демо: *оглядываешь зал и присаживаешься у очага.*", "channel": "self"},
            {"speaker": "Торнин Серебряная Луна", "text": "Демо: Эй, Борко! Ведро унеси от печи, пока не опрокинул.", "channel": "overheard", "event_id": "demo-evt-003"},
            {"speaker": "Борко", "text": "Демо: Уже несу. Вчерашний козёл снова сбежал с двора, весь день ловлю.", "channel": "overheard", "event_id": "demo-evt-004"},
            {"speaker": "Тень", "text": "Демо: ...тихо. Слишком тихо.", "channel": "direct", "event_id": "demo-evt-005"},
            {"speaker": "Тень", "text": "Демо: за той дверью кто-то ходит всю ночь. Шаги лёгкие, почти без звука. Я считал — сорок два круга до рассвета.", "channel": "direct", "event_id": "demo-evt-006"},
            {"speaker": "Тень", "text": "Демо: я никому не скажу, что ты спрашивал.", "channel": "direct", "event_id": "demo-evt-007"},
            {"speaker": "Рассказчик", "text": "Демо: за стойкой Торнин протирает кружку одним и тем же движением — и смотрит не на кружку, а на дверь.", "channel": "narrative"},
            {"speaker": "Служанка Люся", "text": "Демо: Орм, опять клинок принёс? Третий за неделю.", "channel": "overheard", "event_id": "demo-evt-008"},
            {"speaker": "Кузнец Орм", "text": "Демо: люди платят, я кую. Спрашивать не положено — таков порядок в наших краях, и он старше любой стены этой таверны.", "channel": "overheard", "event_id": "demo-evt-009"},
            {"speaker": "Ты", "text": "Демо: *делаешь глоток эля. Хмель горчит сильнее, чем ты привык.*", "channel": "self"},
            {"speaker": "Торнин Серебряная Луна", "text": "Демо: про волка на вывеске спрашивают каждый прибывший. Отвечаю каждому: волк приходил сам, в метель, и мы его не выгнали. Кто-то из нас тогда умер, но вывеску не поменяешь — заказано при живом мастере, а мастер умер первым.", "channel": "direct", "event_id": "demo-evt-010"},
            {"speaker": "Борко", "text": "Демо: Эй, кто-нибудь видел мою рукавицу? Левую!", "channel": "overheard", "event_id": "demo-evt-011"},
            {"speaker": "Рассказчик", "text": "Демо: где-то наверху скрипнула половица. Шаги стихли у самой лестницы.", "channel": "narrative"},
            {"speaker": "Тень", "text": "Демо: сорок третий.", "channel": "direct", "event_id": "demo-evt-012"},
            {"speaker": "Ты", "text": "Демо: *кладёшь монету на стойку и киваешь Торнину.*", "channel": "self"},
            {"speaker": "Рассказчик", "text": "Демо: Торнин кивает в ответ. Кружка в его руке перестаёт вращаться.", "channel": "narrative"},
        ]
        # M12 ч.2 (демо-ветка): display_name → recognition_confidence.
        # Тень/Борко/Люся = tentative («?»), Торнин/Орм = confirmed.
        self._demo_recognition = {
            "Торнин Серебряная Луна": 1.0,
            "Кузнец Орм": 1.0,
            "Тень": 0.6,
            "Борко": 0.6,
            "Служанка Люся": 0.6,
        }

        # S1 стилизации: шрифты через FontProvider (per-window overrides,
        # роли title/text/ui). Голые SysFont заменены свойствами-прокси:
        # значение зависит от self._render_wid (окно, рисуемое сейчас).
        self._font_provider = _FontProvider()
        self._render_wid: Optional[str] = None
        self._font_title_base = pygame.font.SysFont("consolas", 16)
        self._font_text_base = pygame.font.SysFont("consolas", 14)
        self._style_overrides: dict = {}
        self._style_role = "text"
        self._style_target: Optional[str] = None
        # B2: тумблер панели «СТИЛЬ ДЛЯ ВСЕХ ОКОН» (куда пишется правка —
        # всем окнам или только цели) + флаг «в глобальном стиле» на каждое
        # окно (default ON). Флаг хранит только отклонения от дефолта.
        self._style_global: bool = False
        self._style_window_global: dict = {}
        # S3.10: именованный снимок стиля игрока («Мой стиль»)
        self._my_style: dict = {}
        # S3.11/S3.14: шум-рельеф: глубина ±6 (минус = светлый), масштаб,
        # зерно, подтон (цвет рельефа, пикер)
        self._style_texture: int = 0
        self._style_noise_scale: int = 16
        self._style_noise_seed: int = 0
        self._style_noise_tint: list = [255, 255, 255]
        self._texture_tiles: dict = {}
        # S3.14: размер аватара — живой ползунок (24-96)
        self._style_avatar_size: int = _AVATAR
        self._panel_slider_drag: Optional[str] = None
        # S3.12: фото-аватары журнала (кэш имя→Surface|None, негатив тоже)
        self._avatar_cache: dict = {}
        self._casting_repo_wb = None
        self._portrait_name_map: Optional[dict] = None
        # S3.13: свёрнутость секций панели СТИЛЬ (дефолты — в _sec_header)
        self._style_sections: dict = {}
        # S3.5: HSV-пикер (ползунки + градиентные шкалы, как в графредакторах)
        self._picker_token: Optional[str] = None
        self._picker_hsv: list = [0.0, 0.0, 0.0]
        self._picker_alpha: int = 215
        self._picker_rect: Optional[pygame.Rect] = None
        self._picker_sliders: list = []
        self._picker_drag: Optional[str] = None
        # S4: восстановление стилей прошлой сессии (версионированный json)
        try:
            if _STYLES_PATH.exists():
                _d = json.loads(_STYLES_PATH.read_text(encoding="utf-8-sig"))
                if _d.get("_version") in (1, 2):
                    self._style_overrides = _d.get("overrides", {})
                    # B2: ключ __global__ сломанной сессии мёртв — broadcast
                    # пишет прямо в окна, приоритетов больше нет.
                    self._style_overrides.pop("__global__", None)
                    self._style_target = _d.get("target")
                    self._style_role = _d.get("role", "text")
                    if _d.get("_version") >= 2:
                        self._style_global = bool(_d.get("global", False))
                        self._style_window_global = {
                            k: bool(v) for k, v in _d.get("window_global", {}).items()}
                        self._my_style = _d.get("my_style", {}) or {}
                        self._style_texture = int(_d.get("texture", 0))
                        self._style_avatar_size = int(_d.get("avatar_size", _AVATAR))
                        self._style_noise_scale = int(_d.get("noise_scale", 16))
                        self._style_noise_seed = int(_d.get("noise_seed", 0))
                        self._style_noise_tint = list(_d.get("noise_tint", (255, 255, 255)))
        except Exception as _e:
            print(f"[STYLE_LOAD] failed: {_e}")

    # ── S1: шрифтовые прокси ────────────────────────────────────────
    # 44 точки рендера читают _font_title/_font_text — прокси подставляет
    # per-window шрифт по текущему _render_wid. Fallback — базовые SysFont.

    def _ov(self, role: str, wid: Optional[str] = None) -> dict:
        # S3.8: явный wid — для мировых элементов (пузыри над NPC):
        # вне цикла окон _render_wid равен None
        _w = wid or self._render_wid
        return getattr(self, "_style_overrides", {}).get(_w, {}).get(role, {}) if _w else {}


    @property
    def _font_title(self) -> "_StyledFontProxy":
        # B2: broadcast-модель; S3.7: обёртка добавляет обводку/тень букв
        ov = self._ov("title")
        return _StyledFontProxy(self._font_provider.get(
            "title", ov.get("font_file", ""),
            int(ov.get("size_delta", 0)),
            bool(ov.get("bold", False)),
            bool(ov.get("italic", False))), self, "title")

    @property
    def _font_text(self) -> "_StyledFontProxy":
        ov = self._ov("text")
        return _StyledFontProxy(self._font_provider.get(
            "text", ov.get("font_file", ""),
            int(ov.get("size_delta", 0)),
            bool(ov.get("bold", False)),
            bool(ov.get("italic", False))), self, "text")

    # ── S3: цветовой прокси (per-window _colors > токен темы) ────────
    def _ct(self, wid: Optional[str], token: str, default=None):
        """Цвет окна: оверрайд из _colors, иначе токен темы (или явный
        default для нестандартных токенов). Broadcast уже разнёс
        глобальные правки по окнам — затенения нет."""
        _c = self._style_overrides.get(wid, {}).get("_colors", {}).get(token)
        if _c:
            return tuple(_c)
        if default is not None:
            return tuple(default)
        return self.theme.token(token)

    def _backdrop_alpha(self, wid: Optional[str]) -> int:
        """Прозрачность подложки ленты. Default 0 (S3.9-фикс): фон журнала
        единообразен с остальными окнами («Фон окна»); подложка — опция."""
        _a = self._style_overrides.get(wid, {}).get("_colors", {}).get("backdrop_alpha")
        return int(_a) if _a is not None else 0

    def _backdrop_rgb(self, wid: Optional[str]) -> tuple:
        """S3.5: цвет подложки ленты журнала (default 10,10,18)."""
        _c = self._style_overrides.get(wid, {}).get("_colors", {}).get("backdrop_rgb")
        return tuple(_c) if _c else (10, 10, 18)

    # ── S3.6: прозрачность поверхностей (текст — всегда непрозрачен) ──
    def _cta(self, wid: Optional[str], token: str, default=None) -> tuple:
        """(RGB, alpha) токена окна; alpha default 255 (непрозрачно)."""
        _a = self._style_overrides.get(wid, {}).get("_colors", {}).get(token + "_alpha")
        return self._ct(wid, token, default), (int(_a) if _a is not None else 255)

    def _fill_alpha(self, screen, rect, rgb, alpha, radius=0, texture=True) -> None:
        """Заливка с альфой и опциональным рельефом «штукатурка».
        texture=False — для заголовков: рельеф только на телах окон."""
        _tx = int(getattr(self, "_style_texture", 0)) if texture else 0
        if alpha >= 255 and not _tx:
            pygame.draw.rect(screen, rgb, rect, border_radius=radius)
            return
        _s = pygame.Surface(rect.size, pygame.SRCALPHA)
        _s.fill((*rgb, alpha))
        if _tx:
            self.apply_texture(_s, rect.width, rect.height)
        screen.blit(_s, rect.topleft)

    def _plaster_tile(self, _pat: Optional[str] = None) -> pygame.Surface:
        """S3.14: тайл рельефа — value noise (2 октавы, smoothstep), та же
        семья формул, что водные узоры в играх. Масштаб узора (ползунок)
        и зерно («Сменить узор») детерминированы; координаты зациклены
        модулём — тайл бесшовный. Кэш по (масштаб, зерно)."""
        _sc = max(4, min(48, int(getattr(self, "_style_noise_scale", 16))))
        _sd = int(getattr(self, "_style_noise_seed", 0))
        _tint = tuple(int(c) for c in
                      (getattr(self, "_style_noise_tint", None) or (255, 255, 255)))
        _key = (_sc, _sd, _tint)
        if _key in self._texture_tiles:
            return self._texture_tiles[_key]
        import random as _rnd
        _rng = _rnd.Random(31337 + _sd * 7919)
        _g1 = [[_rng.random() for _ in range(_sc)] for _ in range(_sc)]
        _g2 = [[_rng.random() for _ in range(_sc * 2)] for _ in range(_sc * 2)]

        def _n(g, m, fx, fy):
            _xi, _yi = int(fx) % m, int(fy) % m
            _xf, _yf = fx - int(fx), fy - int(fy)
            _sx = _xf * _xf * (3 - 2 * _xf)
            _sy = _yf * _yf * (3 - 2 * _yf)
            _a, _b = g[_yi][_xi], g[_yi][(_xi + 1) % m]
            _c, _d = g[(_yi + 1) % m][_xi], g[(_yi + 1) % m][(_xi + 1) % m]
            return (_a + (_b - _a) * _sx + (_c - _a) * _sy
                    + (_a - _b - _c + _d) * _sx * _sy)

        _tm = pygame.Surface((128, 128))
        _ta = pygame.Surface((128, 128))
        for _yy in range(0, 128, 2):
            for _xx in range(0, 128, 2):
                _u = _xx / 128.0 * _sc
                _v = _yy / 128.0 * _sc
                _f = max(0.0, min(1.0, _n(_g1, _sc, _u, _v) * 0.7
                                  + _n(_g2, _sc * 2, _u * 2.0, _v * 2.0) * 0.3))
                # MULT-тайл: белый → подтон (тёмный рельеф цвета подтона)
                _pm = tuple(int(255 + (c - 255) * _f) for c in _tint)
                # ADD-тайл (минусовая глубина): светлый рельеф подтоном
                _pa = tuple(int(c * _f) for c in _tint)
                pygame.draw.rect(_tm, _pm, (_xx, _yy, 2, 2))
                pygame.draw.rect(_ta, _pa, (_xx, _yy, 2, 2))
        self._texture_tiles[_key] = (_tm, _ta)
        return (_tm, _ta)

    def _stroke_alpha(self, screen, rect, rgb, alpha, width, radius=0) -> None:
        """Контур с альфой (255 — быстрый путь)."""
        if alpha >= 255:
            pygame.draw.rect(screen, rgb, rect, width, border_radius=radius)
            return
        _s = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(_s, (*rgb, alpha), _s.get_rect(), width, border_radius=radius)
        screen.blit(_s, rect.topleft)

    # ── S3.8: «мировой» стиль — общая палитра игровых элементов ───────
    def world_style(self) -> "_WindowThemeAdapter":
        """Пузыри/маркеры над NPC и прочие мировые элементы красятся из
        стиля Журнала (вердикт Мастера: «копируют общий стиль»)."""
        return _WindowThemeAdapter(self, "journal")

    def world_font(self) -> "_StyledFontProxy":
        """Шрифт мировых элементов — текстовая роль Журнала (+ эффекты)."""
        ov = self._ov("text", "journal")
        return _StyledFontProxy(self._font_provider.get(
            "text", ov.get("font_file", ""),
            int(ov.get("size_delta", 0)),
            bool(ov.get("bold", False)),
            bool(ov.get("italic", False))), self, "text", "journal")

    def world_cta(self, token: str, default=None) -> tuple:
        """S3.8: (RGB, alpha) мирового стиля для нестандартных токенов."""
        return self._cta("journal", token, default)

    def world_backdrop(self) -> tuple:
        """S3.8: (RGB, alpha) мировых пузырей: оверрайд ленты Журнала,
        если Мастер её настраивал; иначе видимый литерал-дефолт."""
        _c = self._style_overrides.get("journal", {}).get("_colors", {})
        if "backdrop_rgb" in _c or "backdrop_alpha" in _c:
            return self._backdrop_rgb("journal"), self._backdrop_alpha("journal")
        return (25, 25, 45), 210

    def apply_texture(self, surf, w: int, h: int) -> None:
        """S3.14: шум-рельеф на поверхность. Глубина ±6: плюс — тёмный
        рельеф (MULT к подтону), минус — светлый (ADD подтоном)."""
        _d = int(getattr(self, "_style_texture", 0))
        if _d == 0:
            return
        _tm, _ta = self._plaster_tile()
        for _ in range(abs(_d)):
            for _yy in range(0, h, 128):
                for _xx in range(0, w, 128):
                    if _d > 0:
                        surf.blit(_tm, (_xx, _yy), special_flags=pygame.BLEND_RGB_MULT)
                    else:
                        surf.blit(_ta, (_xx, _yy), special_flags=pygame.BLEND_RGB_ADD)

    def _avatar_size(self) -> int:
        """S3.14: размер аватара журнала — живой ползунок (24-96)."""
        return max(24, min(96, int(getattr(self, "_style_avatar_size", _AVATAR))))

    # ── Данные окна ──────────────────────────────────────────────────

    # (метод удалён — единственная версия ниже, с tab-фильтром и demo-fallback)

    # ── Lifecycle ────────────────────────────────────────────────────

    def toggle_journal(self) -> None:
        """J (M15, вердикт Мастера): журнал НИКОГДА не закрывается — только
        сворачивается и разворачивается. Цикл: FULL ↔ COLLAPSED_TO_TITLE;
        HIDDEN — только стартовое состояние до первого J."""
        state = self.registry.state("journal")
        if state == WindowState.FULL:
            self.registry.transition("journal", WindowState.COLLAPSED_TO_TITLE)
        else:
            # HIDDEN или COLLAPSED_TO_TITLE → развернуть на вкладке «Диалог»
            self.registry.transition("journal", WindowState.FULL)
            self._active_tab["journal"] = "dialog"

    def toggle_inventory(self) -> None:
        """I: инвентарь — HIDDEN ↔ FULL (долговременная память игрока,
        Doctrine IX слой 3; HIDDEN = стартовое, не нарушает M15 — он про журнал)."""
        state = self.registry.state("inventory")
        self.registry.transition(
            "inventory",
            WindowState.HIDDEN if state == WindowState.FULL else WindowState.FULL,
        )

    def toggle_observations(self) -> None:
        """Ё: окно Наблюдение — FULL ↔ COLLAPSED (не HIDDEN, паттерн M15)."""
        state = self.registry.state("observations")
        self.registry.transition(
            "observations",
            WindowState.COLLAPSED_TO_TITLE if state == WindowState.FULL else WindowState.FULL,
        )

    def open_journal_dialog_tab(self) -> None:
        """Авто-открытие: журнал FULL на вкладке «Диалог». Не навязчиво:
        если игрок его закрыл — открываем только по новому фокусу ввода."""
        if self.registry.state("journal") != WindowState.FULL:
            self.registry.transition("journal", WindowState.FULL)
        self._active_tab["journal"] = "dialog"

    def enter(self) -> None:
        self.active = True
        self._font_provider.scan()  # S1: шрифты накинуты в папку — подхват без перезапуска
        # Пауза мира (game-контекст): флаг читает game_screen перед idle_tick.
        # Мир не тикает, пока верстак открыт (решение Мастера: редактируем на паузе,
        # выходим — досимулировали нужную сцену — открыли снова).
        if self.game_context:
            self._core.workbench_paused = True

    def exit(self) -> None:
        self.active = False
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)  # S3: вернуть курсор
        self._picker_token = None  # S3.5: пикер не переживает выход из F12
        self._picker_drag = None
        # S4: персист стилей шрифтов (переживают перезапуск игры/редактора)
        try:
            _styles = {"_version": 2, "overrides": self._style_overrides,
                       "target": self._style_target, "role": self._style_role,
                       "global": bool(getattr(self, "_style_global", False)),
                       "window_global": dict(getattr(self, "_style_window_global", {})),
                       "my_style": dict(getattr(self, "_my_style", {})),
                       "texture": int(getattr(self, "_style_texture", 0)),
                       "avatar_size": int(getattr(self, "_style_avatar_size", _AVATAR)),
                       "noise_scale": int(getattr(self, "_style_noise_scale", 16)),
                       "noise_seed": int(getattr(self, "_style_noise_seed", 0)),
                       "noise_tint": list(getattr(self, "_style_noise_tint", (255, 255, 255)))}
            _STYLES_PATH.write_text(json.dumps(_styles, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
        except Exception as _e:
            print(f"[STYLE_SAVE] failed: {_e}")
        self._drag = None
        if self.game_context:
            self._core.workbench_paused = False
        states = {}
        for wid in self.registry.all_ids():
            fr = self._free_rects.get(wid)
            states[wid] = {
                "state": self.registry.state(wid).value,
                "free_rect": list(fr) if fr else None,
            }
        self._persist.save_window_states(states)

    @staticmethod
    def _norm_coord(entry):
        """Защитная нормализация элемента render_coords['npcs'] (формат
        вывода SceneRenderer не угадываем: tuple/list, dict{x,y},
        dict с вложенной позицией — все валидны)."""
        if isinstance(entry, (tuple, list)) and len(entry) >= 2:
            return int(entry[0]), int(entry[1])
        if isinstance(entry, dict):
            for k in ("screen", "pos", "xy"):
                v = entry.get(k)
                if isinstance(v, (tuple, list)) and len(v) >= 2:
                    return int(v[0]), int(v[1])
            if "x" in entry and "y" in entry:
                return int(entry["x"]), int(entry["y"])
            if "sx" in entry and "sy" in entry:
                # Фактический формат SceneRenderer.render: {"sx","sy","radius"}
                # — раньше не распознавался, все NPC отбрасывались (нет пузырей)
                return int(entry["sx"]), int(entry["sy"])
        return None, None

    def draw_demo_bubbles(self, screen, npc_coords, core=None) -> None:
        """Демо-облачка над NPC в editor-F12 (материал под Style-редактор):
        позиции — экранные из SceneRenderer.render (единая система
        координат с задником), тексты/каналы — из _demo_journal (первая
        direct/overheard реплика спикера). Имена — через core._npc_list.
        Стиль — токены темы; direct плотный, overheard призрачный."""
        if not npc_coords:
            return
        loc = getattr(getattr(core, "dm", None), "locations", {}).get(core.current_file) if core else None
        _name_by_ref: dict = {}
        if loc:
            for npc in loc.get("npcs", []):
                _name_by_ref[npc.get("ref_id", "")] = next(
                    (n["name"] for n in getattr(core, "_npc_list", [])
                     if n["id"] == npc.get("ref_id")), npc.get("ref_id", ""))
        if not _name_by_ref and core:
            # Фоллбэк: локация не нашлась (editor dm) — прямой id→name
            for n in getattr(core, "_npc_list", []):
                if n.get("id"):
                    _name_by_ref[n["id"]] = n.get("name", n["id"])
        _texts: dict = {}
        for e in self._demo_journal:
            ch = e.get("channel", "")
            if ch in ("direct", "overheard") and e["speaker"] not in _texts:
                _texts[e["speaker"]] = (e["text"].replace("Демо: ", ""), ch)
        _used = set()
        # S3.12: шрифт пузырей — мировой (Журнал: обводка/тень вживую)
        font = self.world_font()
        theme = self.theme
        for npc_id, entry in npc_coords.items():
            sx, sy = self._norm_coord(entry)
            if sx is None:
                continue
            # S3.12: радиус из формата SceneRenderer — пузырь ВЫШЕ имени
            # (имя рисует сцена на sy-radius-16; раньше пузырь накрывал его)
            _rad = int(entry.get("radius", 14)) if isinstance(entry, dict) else 14
            name = _name_by_ref.get(npc_id, npc_id)
            match = _texts.get(name)
            if not match or name in _used:
                continue
            _used.add(name)
            text, ch = match
            lines = self._wrap(text, 220)
            lh = font.get_linesize() + 1
            bw = max(font.size(l)[0] for l in lines) + 16
            bh = len(lines) * lh + 10
            bx = int(sx - bw // 2)
            # Пузырь занимает место имени (имя перерисуется выше пузыря)
            by = int(sy - _rad - bh + 4)
            alpha = 235 if ch == "direct" else 150
            surf = pygame.Surface((bw, bh + 6), pygame.SRCALPHA)
            # S3.7/S3.9: подложка демо-пузыря — оверрайд ленты журнала,
            # если настраивалась; иначе прежний видимый литерал
            _bc = self._style_overrides.get("journal", {}).get("_colors", {})
            if "backdrop_rgb" in _bc or "backdrop_alpha" in _bc:
                _br, _ba = self._backdrop_rgb("journal"), self._backdrop_alpha("journal")
            else:
                # 250 (почти глухо): сквозь 215 просвечивало имя сцены
                # ПОД пузырём — выглядело как дублирование имён
                _br, _ba = (18, 18, 28), 250
            pygame.draw.rect(surf, (*_br, int(alpha * _ba / 255)),
                             pygame.Rect(0, 0, bw, bh), border_radius=6)
            # S3.14: штукатурка демо-пузыря (все подложки под текстом)
            self.apply_texture(surf, bw, bh)
            pygame.draw.rect(surf, self._ct("journal", "border"), pygame.Rect(0, 0, bw, bh), 1, border_radius=6)
            ty = 5
            for line in lines:
                ts = font.render(line, True, self._ct("journal", "text_primary"))
                surf.blit(ts, (8, ty))
                ty += lh
            # Хвостик вниз к NPC
            pygame.draw.polygon(surf, (18, 18, 28, alpha),
                                [(bw // 2 - 5, bh - 1), (bw // 2 + 5, bh - 1), (bw // 2, bh + 6)])
            # Стереть имя сцены под пузырём (глухая заплатка цветом фона):
            # сквозь полупрозрачный пузырь оно просвечивало = дубль имени
            pygame.draw.rect(screen, _br, (bx, sy - _rad - 18, bw, 16))
            screen.blit(surf, (bx, by))
            # S3.12 (вердикт Мастера): пузырь выталкивает имя НАД себя —
            # рисуем заново стилем Журнала (цвет = канал реплики)
            _nc = self._ct("journal", "accent" if ch == "direct" else "text_muted")
            _nm = font.render(name, True, _nc)
            screen.blit(_nm, (bx + (bw - _nm.get_width()) // 2,
                              by - _nm.get_height() - 2))

    # ── Геометрия ────────────────────────────────────────────────────

    def _zone(self, viewport: pygame.Rect) -> pygame.Rect:
        """Safe-area: в game-контексте вычитаем только хинт-полосу снизу (~30px).
        Workbench рисуется ПОВЕРХ диалогового фрейма — тянуть туда можно.
        Editor-контекст: зона = viewport (панели редактора — magnet-цели не идут,
        v3a упрощение: их границы добавит Шаг Inspector через avoid_zones)."""
        if self.game_context:
            return pygame.Rect(viewport.left, viewport.top,
                               viewport.width, viewport.height - 30)
        return viewport

    def _resolve_rect(self, wid: str, manifest, viewport: pygame.Rect) -> pygame.Rect:
        """free_rect хранит ПОЛНУЮ (развёрнутую) геометрию; collapsed рендерится
        обрезанием до высоты заголовка. При развороте rect выталкивается обратно
        в зону (баг «развернулся за экраном»: заголовок у нижней кромки + полная
        высота = тело за пределами). Зона берётся лениво — draw-контекст."""
        fr = self._free_rects.get(wid)
        collapsed = self.registry.state(wid) == WindowState.COLLAPSED_TO_TITLE
        if fr:
            r = pygame.Rect(fr)
            if collapsed:
                r.height = _TITLE_H
                # №8: collapsed тоже клампится — заголовок за нижней
                # кромкой зоны = окно недосягаемо (smoke: наложение,
                # уход в угол). Развёрнутая ветка клампит всегда —
                # теперь и свёрнутое окно остаётся досягаемым.
                r.clamp_ip(self._zone(viewport))
            else:
                # J-FIX: free_rect вырожден по высоте (урок драга полосы)?
                # Восстанавливаем полную высоту из анкера.
                if r.height < manifest.min_size[1]:
                    full = AnchoredRect.resolve(manifest, viewport, collapsed=False)
                    r.height = full.height
                    r.left, r.top = full.left, full.top
                r.clamp_ip(self._zone(viewport))
            return r
        return AnchoredRect.resolve(manifest, viewport, collapsed=collapsed)

    # ── Input ────────────────────────────────────────────────────────

    def handle_event_overlay(self, event) -> bool:
        """Не-F12 маршрут: события отдают окнам, если попали в окно, ИЛИ
        drag уже активен (иначе MOUSEBUTTONUP/MOTION утекают в сцену и
        toggle/drag не завершаются — баг «toggle только в F12»)."""
        if self._drag is not None:
            self.handle_event(event)
            return True
        if event.type == pygame.MOUSEWHEEL:
            # M19: колесо над телом журнала в не-F12 — не утекает в сцену.
            mouse = pygame.mouse.get_pos()
            for wid in self.registry.visible_ids():
                r = self._journal_body_rects.get(wid)
                if r and r.collidepoint(mouse):
                    self.handle_event(event)
                    return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for wid in self.registry.visible_ids():
                r = self._rects.get(wid)
                if r and r.collidepoint(event.pos):
                    self.handle_event(event)
                    return True
        return False

    def _board_handle_event(self, event) -> bool:
        """Интеракции Доски (Phase 4 MVI). True = событие съедено.
        Все операции — REST через core._gateway; ошибки — в _board_error
        (рисуются, не глотаются), после каждой — refresh кэша."""
        if self._board_cache is None:
            return False  # доска не загружена — интеракций нет
        # C1: активный inline-ввод съедает клавиатуру целиком — буквы
        # N/L/U/X не дёргают операции доски во время набора. Enter/ESC —
        # commit/cancel (TextInput отдаёт Enter caller'у по контракту).
        if (self._board_input is not None
                and self._board_input.focused):
            if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN, pygame.K_KP_ENTER):
                self._board_commit_input()
                return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._board_close_input()
                return True
            self._board_input.handle_event(event)
            return True
        if event.type == pygame.MOUSEWHEEL:
            # №6: wheel над карточкой = внутренняя прокрутка текста.
            # Верхняя граница клампится в рендере (по числу строк против
            # бюджета) — здесь только инкремент. Журнальный wheel ниже по
            # цепочке не конфликтует (окна не пересекаются зонами).
            _mp = pygame.mouse.get_pos()
            for _cid, _rect in getattr(self, "_board_card_rects", {}).items():
                if _rect.collidepoint(_mp):
                    self._board_card_scroll[_cid] = max(
                        0, self._board_card_scroll.get(_cid, 0) - event.y)
                    return True
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for _cid, _rect in getattr(self, "_board_card_rects", {}).items():
                if _rect.collidepoint(event.pos):
                    self._board_drag_id = _cid
                    self._board_drag_off = (
                        event.pos[0] - _rect.x, event.pos[1] - _rect.y)
                    return True
            self._board_selected = []  # клик мимо карточек — снять выбор
            return False
        if (event.type == pygame.MOUSEBUTTONUP and event.button == 1
                and self._board_drag_id):
            _cid = self._board_drag_id
            _rect = self._board_card_rects.get(_cid)
            self._board_drag_id = None
            if _rect is None:
                return True
            # E2: clamp ДО записи в кэш/REST — файл = экран. Раньше
            # неклампнутые координаты уходили в файл, а кламп случался
            # только в следующем кадре рендера → расхождение файл/экран
            # (мина ТЗ §5, гейт: drag в угол → файл = экранная позиция).
            _brect = self._rects.get("board")
            if _brect is not None:
                _body = pygame.Rect(_brect.x, _brect.y + _TITLE_H,
                                    _brect.width, _brect.height - _TITLE_H)
                if _rect.x + self._BOARD_CARD_W > _body.right - 4:
                    _rect.x = _body.right - 4 - self._BOARD_CARD_W
                if _rect.y + self._BOARD_CARD_H > _body.bottom - 4:
                    _rect.y = _body.bottom - 4 - self._BOARD_CARD_H
                if _rect.x < _body.x + 4:
                    _rect.x = _body.x + 4
                if _rect.y < _body.y + 4:
                    _rect.y = _body.y + 4
            # оптимистичный апдейт кэша (мир не владеет доской — races нет),
            # затем REST — файл как SSOT
            for _c in self._board_cache.get("cards", []):
                if _c.get("id") == _cid:
                    _c["pos"] = [float(_rect.x), float(_rect.y)]
                    break
            try:
                self._board_gateway.board_card_move(
                    self._board_campaign, _cid,
                    [float(_rect.x), float(_rect.y)])
            except Exception as e:
                self._board_error = str(e)
            # выбрать карточку кликом (toggle в пределах двух)
            if _cid in self._board_selected:
                self._board_selected.remove(_cid)
            else:
                self._board_selected = (self._board_selected + [_cid])[-2:]
            return True
        if (event.type == pygame.MOUSEMOTION and self._board_drag_id):
            _rect = self._board_card_rects.get(self._board_drag_id)
            if _rect is not None:
                _rect.topleft = (event.pos[0] - self._board_drag_off[0],
                                 event.pos[1] - self._board_drag_off[1])
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_l and len(self._board_selected) == 2:
                # повторное L — переключает kind (S ↔ C)
                _a, _b = self._board_selected
                try:
                    self._board_gateway.board_link(
                        self._board_campaign, _a, _b,
                        self._board_link_kind)
                    self._board_link_kind = (
                        "PLAYER_CONTRADICTS"
                        if self._board_link_kind == "PLAYER_SUPPORTS"
                        else "PLAYER_SUPPORTS")
                except Exception as e:
                    self._board_error = str(e)
                self._refresh_board()
                return True
            if event.key == pygame.K_u and len(self._board_selected) == 2:
                _a, _b = self._board_selected
                _removed = False
                for _l in list(self._board_cache.get("links", [])):
                    _pair = {_l.get("from"), _l.get("to")}
                    if _pair == {_a, _b}:
                        try:
                            self._board_gateway.board_link(
                                self._board_campaign,
                                _l.get("from"), _l.get("to"), _l.get("kind"),
                                unlink_op=True)
                            _removed = True
                        except Exception as e:
                            self._board_error = str(e)
                self._refresh_board()
                return True or _removed
            if (event.key == pygame.K_e and len(self._board_selected) == 1):
                # C2 (вердикт М 7): E = edit — консистентный command
                # surface N/L/U/X/E вместо double-click (temporal state).
                # Редактируема только hypothesis-карточка — карточка-
                # указатель журнала материалом не владеет (board не
                # знает истину, править реплику с доски нельзя).
                _c = next((_c for _c in self._board_cache.get("cards", [])
                           if _c.get("id") == self._board_selected[0]), None)
                if _c is not None and _c.get("ref_type") == "hypothesis":
                    self._board_open_input(("edit", _c.get("ref_id", "")))
                return True
            if event.key == pygame.K_x and self._board_selected:
                for _cid in list(self._board_selected):
                    try:
                        self._board_gateway.board_card_remove(
                            self._board_campaign, _cid)
                    except Exception as e:
                        self._board_error = str(e)
                self._board_selected = []
                self._refresh_board()
                return True
            if event.key == pygame.K_n and self._board_cache is not None:
                # C1: inline-ввод (вердикт Мастера 9: одна команда =
                # одно намерение — create + карточка на столе)
                self._board_open_input(("create",))
                return True
        return False

    def board_focused(self) -> bool:
        """№1: рабочая фокусировка — Доска развёрнута или верстак активен
        (F12). game_screen синхронизирует workbench_paused каждый кадр —
        все пути закрытия (B, стрелка, ESC, reset_layout) покрыты."""
        return (self.registry.state("board") == WindowState.FULL
                or self.active)

    def board_keydown(self, event) -> bool:
        """Phase 4: KEYDOWN-маршрут Доски для обычного режима (вне F12).
        handle_event вызывается только при .active — KEYDOWN до board-
        интеракций не доходил (поймано smoke S290: N не создавал гипотезу).
        Вызывается из game_screen ПОСЛЕ ветки чата — text_input.focused
        уже отфильтровал ввод чата, буквы N/L/U/X не конфликтуют."""
        if self.registry.state("board") != WindowState.FULL:
            return False
        return self._board_handle_event(event)

    def reset_layout(self) -> None:
        """№8: аварийный сброс — все окна по якорям манифестов, геометрия
        из layout-файла забыта (ловушка «окна ушли в угол» обратима)."""
        for wid in self.registry.all_ids():
            self._free_rects[wid] = None
            self.registry.restore(wid, "hidden")
        self._persist.save_window_states({})  # чистый лист
        for wid in ("journal", "board"):
            self.registry.restore(wid, "collapsed")

    def handle_event(self, event) -> None:
        # S3.5: HSV-пикер — drag ползунков (MOUSEMOTION), клик/закрытие
        # (MOUSEBUTTONDOWN), отпускание (MOUSEBUTTONUP). Гейт в голове
        # метода: перехват раньше доски/панели/drag-логики окон.
        if self.active:
            if event.type == pygame.MOUSEMOTION and self._picker_drag:
                if self._color_picker_motion(event.pos):
                    return
            elif (event.type == pygame.MOUSEMOTION
                    and getattr(self, "_panel_slider_drag", None)
                    in ("avatar", "noise", "glow")):
                # S3.14: drag ползунков панели — аватар / узор / свечение
                _kind = self._panel_slider_drag
                if _kind == "avatar":
                    _asr = getattr(self, "_avatar_slider_rect", None)
                    if _asr is not None:
                        _f = max(0.0, min(1.0, (event.pos[0] - _asr.x) / max(1, _asr.width)))
                        self._style_avatar_size = int(24 + _f * (96 - 24))
                elif _kind == "noise":
                    _nsr = getattr(self, "_noise_slider_rect", None)
                    if _nsr is not None:
                        _f = max(0.0, min(1.0, (event.pos[0] - _nsr.x) / max(1, _nsr.width)))
                        self._style_noise_scale = int(4 + _f * (48 - 4))
                else:  # glow: дробная интенсивность 0.00-1.00
                    _gsr2 = getattr(self, "_glow_slider_rect", None)
                    if _gsr2 is not None:
                        _f = max(0.0, min(1.0, (event.pos[0] - _gsr2.x) / max(1, _gsr2.width)))
                        _new = round(_f * 100) / 100
                        for _w in self._style_targets():
                            self._style_overrides.setdefault(_w, {}).setdefault(
                                self._style_role, {})["glow"] = _new
                return
            elif (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                    and self._picker_token):
                if self._color_picker_click(event.pos):
                    return
            elif event.type == pygame.MOUSEBUTTONUP:
                self._picker_drag = None
                self._panel_slider_drag = None
        if (event.type == pygame.KEYDOWN
                and event.key == pygame.K_l
                and (pygame.key.get_mods() & pygame.KMOD_CTRL)
                and (pygame.key.get_mods() & pygame.KMOD_SHIFT)):
            self.reset_layout()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F12:
            self.exit()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.exit()
            return
        # Phase 4 Investigation Board: интеракции доски раньше диспетчера —
        # иначе клик по карточке проваливается в drag заголовка окна.
        # ESC/F12 выше — выход из верстака приоритетен.
        if (self.registry.state("board") == WindowState.FULL
                and self._board_handle_event(event)):
            return

        # Hotkeys (J и будущие) — всегда
        result = self.dispatcher.route(event)
        if result.consumed:
            return

        # Заголовочный клик/drag (клик-vs-drag порогом 5px, паттерн OS/Hawk):
        # нажатие на заголовок → потенциальный drag; движение > порога → drag;
        # отпускание без движения → toggle (свернуть/развернуть).
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.active and self._style_panel_click(event.pos):
                return  # S2: клик съеден панелью стилизации
            if self.active:
                _edge = self._resize_edge(event.pos)
                if _edge:
                    self._resize = _edge
                    return  # S3: захват края/угла окна = ресайз
            self._drag = None
            # Вкладки: проверяем ПЕРЕД drag (вкладки ниже заголовка,
            # пересечений нет, порядок безопасен)
            for wid, hits in self._tab_rects.items():
                if self.registry.state(wid) != WindowState.FULL:
                    continue
                for hit, tab_id in hits:
                    if hit.collidepoint(event.pos):
                        self._active_tab[wid] = tab_id
                        self._journal_scroll.pop(wid, None)  # M19: смена вкладки → к последним
                        return
            # Диалог-А: клик по чипу собеседника = фильтр ленты
            for wid, hits in self._peer_rects.items():
                if self.registry.state(wid) != WindowState.FULL:
                    continue
                for hit, peer in hits:
                    if hit.collidepoint(event.pos):
                        self._dialog_peer[wid] = peer
                        self._journal_scroll.pop(wid, None)
                        return
            # Phase 4.1-A: клик по записи журнала при открытой Доске —
            # «положить на стол» (ADD_CARD; дубль легален — вердикт М:
            # две организационные роли одного материала). Записи без
            # event_id не кликабельны (A3-граница, tooltip — следующая
            # итерация), скан их пропускает.
            if self.registry.state("board") == WindowState.FULL:
                for _hits in self._journal_entry_rects.values():
                    for _hit, _ev in _hits:
                        if _ev and _hit.collidepoint(event.pos):
                            self._board_add_journal_card(_ev)
                            return
            # M19: клики по ▲/▼ индикаторам скролла журнала
            for wid, (up_r, down_r) in self._scroll_hint_rects.items():
                if self.registry.state(wid) != WindowState.FULL:
                    continue
                if up_r and up_r.collidepoint(event.pos):
                    self._journal_scroll[wid] = self._journal_scroll.get(wid, 0) + 3
                    return
                if down_r and down_r.collidepoint(event.pos):
                    self._journal_scroll[wid] = 0  # «к последним»
                    return
            # Зона-стрелка (OS-паттерн): клик по ▸/▾ = toggle БЕЗ порогов
            # и гонок с drag-джиттером (доказано зондом: 4/4 кликов съедались
            # микродвижением). Стрелка — чёткая 22px зона справа заголовка.
            for wid in self.registry.visible_ids():
                arrow = self._arrow_rects.get(wid)
                if arrow and arrow.collidepoint(event.pos):
                    self.registry.toggle(wid)
                    return
            # Всё остальное в заголовке = drag-захват
            for wid in self.registry.visible_ids():
                tr = self._title_rects.get(wid)
                if tr and tr.collidepoint(event.pos):
                    if self.active:
                        self._style_target = wid  # S2: клик по шапке в F12 = цель стиля
                    rect = self._rects[wid]
                    self._drag = [wid, (event.pos[0] - rect.x, event.pos[1] - rect.y)]
                    return
        elif event.type == pygame.MOUSEWHEEL:
            _spa = getattr(self, "_style_font_area", None)
            if self.active and _spa and _spa.collidepoint(pygame.mouse.get_pos()):
                self._style_scroll = max(0, getattr(self, "_style_scroll", 0) - event.y * 2)
                return
            # M19: колесо над телом журнала = скролл ленты (блок за шаг ×3).
            # event.pos ненадёжен в MOUSEWHEEL → get_pos(); wheel вверх = старее.
            mouse = pygame.mouse.get_pos()
            for wid, r in self._journal_body_rects.items():
                if self.registry.state(wid) != WindowState.FULL:
                    continue
                if r and r.collidepoint(mouse):
                    self._journal_scroll[wid] = max(0, self._journal_scroll.get(wid, 0) + event.y * 3)
                    return
        elif event.type == pygame.MOUSEMOTION and self._resize:
            self._do_resize(event.pos)
        elif event.type == pygame.MOUSEMOTION and self._drag:
            self._do_drag(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._drag = None
            self._resize = None
        # (вкладочная ветка перенесена в начало MOUSEBUTTONDOWN — удалена отсюда)

    def _resize_edge(self, pos) -> Optional[list]:
        """S3: край/угол окна под курсором (зона 7px). Верхний по z — первым."""
        for wid in reversed(self.registry.visible_ids()):
            r = self._rects.get(wid)
            if not r or not r.collidepoint(pos):
                continue
            m = 7
            l = abs(pos[0] - r.left) <= m
            rt = abs(pos[0] - r.right) <= m
            t = abs(pos[1] - r.top) <= m
            b = abs(pos[1] - r.bottom) <= m
            if not (l or rt or t or b):
                continue
            return [wid, [l, rt, t, b], [r.x, r.y, r.width, r.height]]
        return None

    def _do_resize(self, pos) -> None:
        """S3: тянуть край/угол → новый размер; min_size; free_rect персистится
        при выходе из F12 (уже работает — exit() пишет _free_rects)."""
        wid, edges, start = self._resize
        mw, mh = self.registry.manifest(wid).min_size
        l, rt, t, b = edges
        x0, y0, w0, h0 = start
        new_x, new_y, new_w, new_h = x0, y0, w0, h0
        if l:
            new_x = min(pos[0], x0 + w0 - mw)
            new_w = x0 + w0 - new_x
        if rt:
            new_w = max(mw, pos[0] - x0)
        if t:
            new_y = min(pos[1], y0 + h0 - mh)
            new_h = y0 + h0 - new_y
        if b:
            new_h = max(mh, pos[1] - y0)
        new_rect = pygame.Rect(new_x, new_y, new_w, new_h)
        new_rect.clamp_ip(self._zone(self._screen.get_rect()))
        self._free_rects[wid] = (new_rect.x, new_rect.y, new_rect.width, new_rect.height)
        self._rects[wid] = new_rect

    def _do_drag(self, mouse_pos: Tuple[int, int]) -> None:
        if self._drag is None:
            return
        wid, grab = self._drag[0], self._drag[1]
        manifest = self.registry.manifest(wid)
        viewport = self._screen.get_rect()
        zone = self._zone(viewport)

        rect = self._rects[wid]
        new_rect = pygame.Rect(mouse_pos[0] - grab[0], mouse_pos[1] - grab[1],
                               rect.width, rect.height)
        # J-FIX: драг свёрнутой полосы НЕ должен записывать free_rect высотой 34
        # (иначе разворот рендерил полоску навсегда: state=FULL, геометрия — band).
        # Свёрнутую тянем, но в free_rect храним ПОЛНУЮ высоту разворота.
        if self.registry.state(wid) == WindowState.COLLAPSED_TO_TITLE:
            new_rect.height = AnchoredRect.resolve(manifest, viewport, collapsed=False).height

        # Прилипание (паттерн Hawk): цели = зона + грани прочих окон
        others = [r for w, r in self._rects.items() if w != wid]
        self._snap.build(zone, others)
        dx, dy = self._snap.snap_delta(new_rect)
        new_rect = new_rect.move(dx, dy)

        # Заголовок обязан остаться в зоне (IsRectInWorkArea-аналог)
        if not self._snap.clamp_title_inside(new_rect, zone):
            return
        # Выталкивание: окна не наслаиваются
        new_rect = SnapEngine.resolve_overlap(new_rect, others)
        # Кламп в зону: окно не покидает safe-area (гейт захвата заголовка
        # уже прошёл, это финальная подгонка краёв)
        new_rect.clamp_ip(zone)

        self._free_rects[wid] = (new_rect.x, new_rect.y, new_rect.width, new_rect.height)
        self._rects[wid] = new_rect

    # ── Update / Render ──────────────────────────────────────────────

    def update(self) -> None:
        pass  # точка роста: анимации переходов (TransitionSpec)

    _EDIT_TINT = (90, 110, 160, 38)  # холодный сине-фиолетовый — «режим бога» виден без слов

    def draw(self, screen, scene_state: Optional[dict] = None) -> None:
        # M12 ч.2: опциональный DTO-канал recognition из живой сцены
        # (npc_positions[*].display_name/recognition_confidence). Окно
        # читает, не мутирует (M7 / INV-FRONTEND-ISOLATION). None = демо.
        self._live_scene_state = scene_state if isinstance(scene_state, dict) else None

        # Режимы: окна видны ВСЕГДА (обычная игра), F12 = режим редактирования
        # (пауза мира + цветной фильтр + хинт). Единый рендер — DOUBLE TRUTH убит.
        viewport = screen.get_rect()
        if self.active:
            # Полноэкранный тинт: телеграфирует «мир стоит» (решение: без слова
            # «пауза» — ощущение через цвет, закон телесности Doctrine V)
            tint = pygame.Surface(viewport.size, pygame.SRCALPHA)
            tint.fill(self._EDIT_TINT)
            screen.blit(tint, (0, 0))
            hint_surf = self._font_title.render(
                "UI WORKBENCH  [F12/ESC] выход  [заголовок] тянуть — магнит  [край/угол] ресайз  "
                "[клик шапки] цель стиля  вкладки/чипы — клик  [Ctrl+Shift+L] сброс раскладки",
                True, self.theme.token("accent"),
            )
            screen.blit(hint_surf, (viewport.left + 10, viewport.bottom - 26))
            # S2: панель стилизации (справа, кликабельна)
            self._draw_style_panel(screen, viewport)

        for wid in self.registry.visible_ids():
            self._render_wid = wid  # S1: контекст шрифтовых прокси
            manifest = self.registry.manifest(wid)
            state = self.registry.state(wid)
            collapsed = state == WindowState.COLLAPSED_TO_TITLE
            rect = self._resolve_rect(wid, manifest, viewport)
            self._rects[wid] = rect

            self._draw_window_frame(screen, wid, manifest, rect, collapsed)
            if not collapsed:
                self._draw_content(screen, wid, manifest, rect)
        self._render_wid = None  # S1: вне цикла окон — базовые шрифты (хинт и пр.)
        # S3.5: HSV-пикер — поверх окон, только в F12 (слева от панели СТИЛЬ)
        if self.active:
            self._draw_color_picker(screen, viewport)
        # S3: курсор-ресайз при наведении на край/угол окна (только F12)
        if self.active:
            _edge = self._resize_edge(pygame.mouse.get_pos())
            if _edge:
                _l, _r, _t, _b = _edge[1]
                if (_l or _r) and not (_t or _b):
                    pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEWE)
                elif (_t or _b) and not (_l or _r):
                    pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZENS)
                else:
                    pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_SIZEALL)
            else:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)

    def _mini_window_value(self, data_source: str) -> str:
        """Значение мини-окна HUD (world_clock/time_scale) — единственная
        точка вычисления текста (без дублей frame/content)."""
        if data_source == "world_clock":
            _gts = 0
            _ls = getattr(self, "_live_scene_state", None)
            if _ls:
                _gts = int(_ls.get("game_time_seconds", 0) or 0)
            if self.game_context:
                from constants import format_world_date
                return format_world_date(_gts)
            return "Год 1, День 1, 12:01"
        return getattr(self, "hud_time_scale", "▶ 1x")

    def _draw_window_frame(self, screen, wid: str, manifest, rect, collapsed: bool) -> None:
        theme = self.theme
        # Тень/контраст: двойная рамка отделяет окно от сцены (фикс «всё смешалось»)
        # S3.6: каждый элемент рамки — со своей альфой (можно без фона вообще)
        self._stroke_alpha(screen, rect.inflate(4, 4), *self._cta(wid, "border_accent"), 1, 10)
        self._fill_alpha(screen, rect, *self._cta(wid, "surface_panel"), 8)
        self._stroke_alpha(screen, rect, *self._cta(wid, "border"), 2, 8)

        title_h = _TITLE_H if not collapsed else rect.height
        title_rect = pygame.Rect(rect.x, rect.y, rect.width, title_h)
        self._fill_alpha(screen, title_rect, *self._cta(wid, "surface_title"), 8, False)
        # Мини-окна HUD: в тайтле рисуется ЗНАЧЕНИЕ (дата/темп), не имя.
        # Один источник рисования — здесь (COLLAPSED = основное состояние).
        if manifest.data_source in ("world_clock", "time_scale"):
            _val = self._mini_window_value(manifest.data_source)
            title_surf = self._font_title.render(_val, True, self._ct(wid, "text_primary"))
        else:
            title_surf = self._font_title.render(manifest.title, True, self._ct(wid, "text_primary"))
        screen.blit(title_surf, (title_rect.x + 10, title_rect.y + (title_h - title_surf.get_height()) // 2))
        if not manifest.collapsible:
            self._arrow_rects.pop(wid, None)  # нет стрелки — нет toggle-зоны
        else:
            mark = "▸" if collapsed else "▾"
            mark_surf = self._font_title.render(mark, True, self._ct(wid, "accent"))
            _mx = title_rect.right - 24
            screen.blit(mark_surf, (_mx, title_rect.y + (title_h - mark_surf.get_height()) // 2))
            # Хитбокс стрелки (toggle-зона) — 22px квадрат у правого края заголовка
            self._arrow_rects[wid] = pygame.Rect(_mx - 4, title_rect.y, 24, title_h)

        self.dispatcher.bind_title_rect(wid, title_rect)
        self._title_rects[wid] = title_rect

    # Вкладки окна журнала (презентация channel-меток, не новая истина):
    # dialog = direct + narrative + self (беседа игрока с миром),
    # npc     = сгруппированное услышанное (overheard) — прообраз «О НПС»,
    # narrator = только narrative (лента мира, вердикт Мастера: смотрим в игре).
    # M2-именование: «Услышанное» = overheard-канал (чужие диалоги краем уха).
    # tab_id "npc" сохранён для совместимости фильтра _journal_entries.
    _JOURNAL_TABS = [("dialog", "Диалог"), ("npc", "Услышанное"), ("narrator", "Рассказчик")]

    def _draw_content(self, screen, wid: str, manifest, rect) -> None:
        theme = self.theme
        body = pygame.Rect(rect.x, rect.y + _TITLE_H, rect.width, rect.height - _TITLE_H)

        self._fill_alpha(screen, body, *self._cta(wid, "surface_panel"), 8)

        if manifest.data_source == "world_clock":
            # Дата/время рисуется в тайтле (мини-окно: COLLAPSED = весь
            # смысл). Источник: scene_state["game_time_seconds"] (M7);
            # fallback-формат = дефолт до первой синхронизации.
            _gts = 0
            _ls = getattr(self, "_live_scene_state", None)
            if _ls:
                _gts = int(_ls.get("game_time_seconds", 0) or 0)
            if self.game_context:
                from constants import format_world_date
                _t = format_world_date(_gts)
            else:
                _t = "Год 1, День 1, 12:01"
            title_surf = self._font_title.render(_t, True, self._ct(wid, "text_primary"))
            screen.blit(title_surf, (rect.x + 8, rect.y + (_TITLE_H - title_surf.get_height()) // 2))
            return
        if manifest.data_source == "time_scale":
            # Темп: DEBT-TS (визуально жив, функционально не работает) —
            # переносим как есть, функцию не чиним. Значение — core-флаг.
            _s = getattr(self._core, "hud_time_scale", "▶ 1x")
            title_surf = self._font_title.render(_s, True, self._ct(wid, "text_primary"))
            screen.blit(title_surf, (rect.x + 8, rect.y + (_TITLE_H - title_surf.get_height()) // 2))
            return
        if manifest.data_source == "dialog_journal":
            # Гейт дегенеративных размеров: free_rect от прошлых сессий может
            # быть меньше заголовка+табов → отрицательные высоты → pygame.error.
            # Окно меньше 80px высоты рендерим как заголовок-полоску (fail-open).
            if rect.height < _TITLE_H + 46:
                self._draw_window_frame(screen, wid, manifest, rect, collapsed=True)
                return
            self._draw_tabs(screen, body, wid)
            # S3.14: высота строки вкладок — из фактического linesize
            # (эффекты прокси растят его; фиксированные 28px клали вкладки
            # на чипы собеседников)
            _tabs_h = self._font_text.get_linesize() + 12
            tab_body = pygame.Rect(body.x, body.y + _tabs_h, body.width, body.height - _tabs_h)
            if tab_body.width <= 0 or tab_body.height <= 0:
                return
            # Подложка ленты: плотный тёмный фон — текст не сливается с миром.
            # S3: цвет+alpha — оверрайды окна (backdrop_rgb / backdrop_alpha).
            backdrop = pygame.Surface(tab_body.size, pygame.SRCALPHA)
            backdrop.fill((*self._backdrop_rgb(wid), self._backdrop_alpha(wid)))
            # S3.14: штукатурка на подложке ленты (вердикт: все подложки)
            self.apply_texture(backdrop, tab_body.width, tab_body.height)
            screen.blit(backdrop, tab_body.topleft)
            self._journal_body_rects[wid] = tab_body  # M19: wheel-зона
            self._draw_journal(screen, tab_body, wid)
        elif manifest.data_source == "investigation_board":
            # Phase 4: Доска расследования. Мир на паузе (workbench_paused),
            # board-кэш обновляется при открытии окна и после операций.
            if rect.height < _TITLE_H + 46:
                self._draw_window_frame(screen, wid, manifest, rect, collapsed=True)
                return
            self._draw_board(screen, body, wid)
        elif manifest.data_source == "observations":
            # Наблюдение: строки собирает GameScreen (единственный источник,
            # вынесен из legacy Ё-консоли); editor — демо. Скролл M19 пере-
            # используется: budget-цикл _draw_journal универсален, но здесь
            # лента проще — строки целиком, клип по низу.
            if self.game_context and getattr(self, "_live_scene_state", None):
                lines = self._core.collect_observation_lines(self._live_scene_state)
            else:
                lines = ["Тень (?): напряжённая поза", "Кузнец Орм: работает у наковальни",
                         "Торнин Серебряная Луна: обслуживает столы"]
            ty = body.y + 6
            lh = self._font_text.get_linesize() + 2
            for line in lines:
                if ty + lh > body.bottom - 4:
                    break  # клип: длинный список — следующий шаг M19-скролл
                ts = self._font_text.render(line, True, self._ct(wid, "text_primary"))
                screen.blit(ts, (body.x + 8, ty))
                ty += lh
            return
        elif manifest.data_source == "player_body_topology":
            topo = (self._live_scene_state or {}).get("player_body_topology", {}) \
                if self.game_context else self._demo_topology()
            if not topo:
                ts = self._font_text.render("Топология тела недоступна.",
                                            True, self._ct(wid, "text_muted"))
                screen.blit(ts, (body.x + 8, body.y + 8))
                return
            _contents = topo.get("contents", {})
            ty = body.y + 6
            lh = self._font_text.get_linesize() + 2

            def _blit_line(txt: str, col: str) -> None:
                nonlocal ty
                if ty + lh > body.bottom - 4:
                    return
                ts = self._font_text.render(txt, True, self._ct(wid, col))
                screen.blit(ts, (body.x + 8, ty))
                ty += lh

            # Человекочитаемые имена слотов (id остаются — для будущего
            # клик-интерактива; перевод презентационный, данные не трогаем).
            _SLOT_RU = {
                "hand_right": "правая рука", "hand_left": "левая рука",
                "worn_torso": "торс", "worn_legs": "ноги", "worn_feet": "ступни",
                "worn_cloak": "плащ", "belt_sheath": "ножны", "belt_pouch": "кошелёк",
                "belt_potion": "пояс-флакон", "pocket_left": "левый карман",
                "pocket_right": "правый карман", "pocket_inner": "внутренний карман",
                "backpack_main": "основной", "backpack_side": "боковой",
                "hidden_boot": "в сапоге", "hidden_lining": "подкладка",
            }
            for _gname, _slots in [("Руки", topo.get("hands", {})),
                                   ("Надето", topo.get("worn", {})),
                                   ("Пояс", topo.get("belt", [])),
                                   ("Карманы", topo.get("pockets", [])),
                                   ("Рюкзак", topo.get("backpack", [])),
                                   ("Скрытое", topo.get("hidden", []))]:
                _slot_list = list(_slots.values()) if isinstance(_slots, dict) else _slots
                if not _slot_list:
                    continue
                _blit_line(f"[{_gname}]", "accent")
                for _slot in _slot_list:
                    _sid = _slot.get("slot_id", "unknown")
                    _bp = _slot.get("body_part", "")
                    _bp_ru = _SLOT_RU.get(_bp, _bp)
                    _blit_line(f"  - {_bp_ru}", "text_muted")
                    for _item in _contents.get(_sid, []):
                        _blit_line(f"    • {_item.get('name', 'Предмет')} "
                                   f"(В:{_item.get('weight', 0.0)} кг, "
                                   f"Г:{_item.get('bulk', 1)})", "text_primary")
            _total_w = sum(i.get("weight", 0.0) for items in _contents.values() for i in items)
            _carry = topo.get("strength_score", 10) * 15.0
            _wc = "text_primary" if _total_w <= _carry else "border_accent"
            _blit_line(f"Вес: {_total_w:.1f} / {_carry:.1f}", _wc)
            _blit_line(f"Габаритность: {sum(i.get('bulk', 1) for items in _contents.values() for i in items)}",
                       "text_primary")
            return
        # точка роста: другие data_source по мере регистрации окон

    # ── Phase 4: Investigation Board ────────────────────────────────
    # Кэш организации доски. Мир на паузе при открытом workbench →
    # достаточно refresh при открытии (toggle_board) и после операций.
    _BOARD_CARD_W, _BOARD_CARD_H = 170, 96
    _BOARD_TIP_W = 360                     # tooltip: лимит «не простынёй» (вердикт М)

    def _board_add_journal_card(self, event_id: str) -> None:
        """A2: положить реплику на стол. Каскад — первая свободная клетка
        сетки (шаг = карточка + 8), занятость — по pos из кэша (файл =
        SSOT; карточка без pos рендерится в [10,10] → клетка (0,0)
        занята, синхронно с экраном). Предел 6×8 — дальше стопка в
        углу, clamp рендера ловит."""
        _pos = self._board_cascade_pos()
        try:
            self._board_gateway.board_card_add(
                self._board_campaign, "journal", event_id, _pos)
        except Exception as e:  # BackendError/urllib — наблюдаемо (E3 сделает видимым)
            self._board_error = str(e)
        self._refresh_board()

    def _board_cascade_pos(self) -> list:
        """Первая свободная клетка сетки (шаг = карточка + 8); занятость —
        по pos из кэша (файл = SSOT; карточка без pos ≈ клетка (0,0) —
        синхронно с рендер-дефолтом [10,10]). Предел 6×8, дальше — угол."""
        _step_x = self._BOARD_CARD_W + 8
        _step_y = self._BOARD_CARD_H + 8
        _occupied = set()
        for _c in (self._board_cache or {}).get("cards", []):
            _p = _c.get("pos")
            if not _p:
                _occupied.add((0, 0))
                continue
            _occupied.add((int(_p[0]) // _step_x, int(_p[1]) // _step_y))
        for _row in range(8):
            for _col in range(6):
                if (_col, _row) not in _occupied:
                    return [float(_col * _step_x), float(_row * _step_y)]
        return [float(5 * _step_x), float(7 * _step_y)]

    def _board_open_input(self, mode: tuple) -> None:
        """C1/C2: открыть inline-ввод. Ленивый TextInput (реюз чатового
        виджета), цвета — ТОЛЬКО токены темы (закон темы, RGB виджета
        не трогаем). Rect пересчитывается каждый кадр в _draw_board."""
        if self._board_input is None:
            from text_input import TextInput  # лениво: паттерн constants-импорта
            self._board_input = TextInput(
                rect=pygame.Rect(0, 0, 200, 28),
                font=self._font_text,
                colors={
                    "bg": self.theme.token("surface_panel"),
                    "border": self.theme.token("border"),
                    "border_active": self.theme.token("accent"),
                    "text": self.theme.token("text_primary"),
                    "cursor": self.theme.token("text_muted"),
                    "selection": self.theme.token("surface_title"),
                },
            )
        _prefill = ""
        if mode[0] == "edit":
            for _h in (self._board_cache or {}).get("hypotheses", []):
                if str(_h.get("id", "")) == mode[1]:
                    _prefill = _h.get("text", "")
                    break
        self._board_input_mode = mode
        self._board_input.text = _prefill
        self._board_input.visible = True
        self._board_input.focused = True

    def _board_close_input(self) -> None:
        self._board_input_mode = None
        if self._board_input is not None:
            self._board_input.visible = False  # setter снимает и фокус

    def _board_commit_input(self) -> None:
        """Enter: create (+авто-карточка, вердикт 9) или edit. Частичный
        успех НЕ молчит: гипотеза уже в файле — ошибка карточки честно
        видна; падение create/edit — ввод не теряется."""
        _mode = self._board_input_mode
        _text = (self._board_input.text.strip()
                 if self._board_input is not None else "")
        if _mode is None or not _text:
            self._board_close_input()
            return
        try:
            if _mode[0] == "create":
                _resp = self._board_gateway.board_hypothesis(
                    self._board_campaign, "create", text=_text)
                _hyp_id = str(_resp.get("hypothesis_id", ""))
                try:
                    self._board_gateway.board_card_add(
                        self._board_campaign, "hypothesis",
                        _hyp_id, self._board_cascade_pos())
                except Exception as e:
                    # Гипотеза сохранена, карточка — нет: не теряем
                    # первую половину и не притворяемся, что всё ок.
                    self._board_error = (
                        f"гипотеза сохранена, карточка не добавлена: {e}")
            else:
                self._board_gateway.board_hypothesis(
                    self._board_campaign, "edit",
                    hyp_id=_mode[1], text=_text)
            self._board_close_input()
        except Exception as e:  # create/edit упал — ввод сохраняем
            self._board_error = str(e)
        self._refresh_board()

    def board_input_active(self) -> bool:
        """Флаг для game_screen: Enter-отправка чата и WASD-движение
        обязаны уважать фокус инпута Доски."""
        return (self._board_input is not None
                and self._board_input.focused)

    def board_input_event(self, event) -> bool:
        """Маршрут TEXTINPUT/TEXTEDITING/KEYUP в инпут Доски (кириллица
        идёт TEXTINPUT-событием, KEYDOWN её не несёт). True = съедено."""
        if self._board_input is None or not self._board_input.focused:
            return False
        if event.type in (pygame.TEXTINPUT, pygame.TEXTEDITING,
                          pygame.KEYUP):
            self._board_input.handle_event(event)
            return True
        return False

    def board_input_update(self, dt: float) -> None:
        """Тик физики повтора клавиш (паттерн text_input.update)."""
        if self._board_input is not None:
            self._board_input.update(dt)

    def toggle_board(self) -> None:
        """Открытие/скрытие Доски. При каждом открытии — refresh кэша
        (HTTP GET; мир стоит, данные между открытиями не меняются)."""
        state = self.registry.state("board")
        if state == WindowState.FULL:
            self.registry.transition("board", WindowState.COLLAPSED_TO_TITLE)
            return
        self.registry.transition("board", WindowState.FULL)
        self._board_error = None  # E3: новая сессия просмотра — ошибки старые не висят
        self._refresh_board()

    def _refresh_board(self) -> None:
        """GET /api/board/{campaign} → кэш. Ошибка транспорта — НЕ тихий
        отказ: рисуем текст ошибки в окне (L4-совместимо)."""
        # E3 (вердикт М 8): refresh больше НЕ стирает ошибку операции —
        # иначе игрок не понимает, сохранилась ли гипотеза/связь. Чистый
        # лист — только при открытии окна (toggle_board).
        # P: editor-ветка удалена — роутер _board_gateway отдаёт stub,
        # единый путь для полигона и игры (stub не падает по построению).
        try:
            self._board_cache = self._board_gateway.get_board(
                self._board_campaign)
        except Exception as e:  # BackendError / urllib — наблюдаемо в UI
            self._board_cache = None
            self._board_error = str(e)

    @property
    def _board_gateway(self):
        """Роутер шлюза доски: игра → REST-gateway, редактор → полигон
        (in-memory stub с той же семантикой контракта). UI-код доски
        не знает, где работает — полигон и игра неразличимы."""
        if getattr(self, "game_context", False):
            return self._core._gateway
        return self._board_stub

    @property
    def _board_campaign(self) -> str:
        """campaign-ключ шлюза: stub его игнорирует, но контракт методов
        требует аргумент (editor-контекст core.campaign_folder не имеет)."""
        return getattr(self._core, "campaign_folder", "editor_demo")

    def _board_journal_index(self) -> dict:
        """Материал журнала по event_id — канал джойна карточек (M7):
        ref_id opaque, резолв материала — ответственность клиента.
        Записи narrative/self без event_id в индекс не попадают —
        адресоваться не могут (ADR-O-404: не выдумывать identity)."""
        # P: единый источник журнала (game → backend, editor → демо) —
        # джойн карточек работает и на полигоне
        return {
            e.get("event_id"): e
            for e in self._journal_entries("all")
            if e.get("event_id")
        }

    def _draw_board(self, screen, body: pygame.Rect, wid: str) -> None:
        """Рендер организации: карточки по pos, гипотезы списком.
        Мёртвая journal-карточка — серым с ref-хвостом (валидное
        состояние ТЗ §2). Клиент НЕ вычисляет семантику."""
        if getattr(self, "_board_cache", None) is None:
            # persistence-restore открывает окно в FULL без toggle_board →
            # refresh ещё не выполнялся: ленивая первичная загрузка. Если
            # и после refresh cache None — реальная ошибка транспорта.
            self._refresh_board()
        if getattr(self, "_board_cache", None) is None:
            msg = f"Доска недоступна: {getattr(self, '_board_error', '?')}"
            surf = self._font_text.render(msg[:90], True,
                                          self.theme.token("text_muted"))
            screen.blit(surf, (body.x + 10, body.y + 10))
            return
        _jmat = self._board_journal_index()
        _hyp_texts = {h.get("id", ""): h.get("text", "")
                      for h in self._board_cache.get("hypotheses", [])}
        # Хитбоксы карточек (интеракции — U3)
        self._board_card_rects = {}
        self._board_hover_tips = {}
        for _c in self._board_cache.get("cards", []):
            _cid = str(_c.get("id", ""))
            _pos = _c.get("pos") or [10.0, 10.0]
            _x = body.x + 8 + int(_pos[0])
            _y = body.y + 8 + int(_pos[1])
            if _x + self._BOARD_CARD_W > body.right - 4:
                _x = body.right - 4 - self._BOARD_CARD_W
            if _y + self._BOARD_CARD_H > body.bottom - 4:
                _y = body.bottom - 4 - self._BOARD_CARD_H
            _rect = pygame.Rect(_x, _y, self._BOARD_CARD_W, self._BOARD_CARD_H)
            self._board_card_rects[_cid] = _rect

            _alive = True
            _lines: list = []   # [(текст, цвет)] — материал карточки
            _body = ""
            _hover_tip = None   # (заголовок, полный текст) для tooltip
            if _c.get("ref_type") == "journal":
                _entry = _jmat.get(_c.get("ref_id", ""))
                _alive = _entry is not None
                if _alive:
                    # Материал = speaker + текст реплики (джойн M7).
                    # spans[]/event_id остаются в ref-происхождении —
                    # задел на работу с сущностями, UI не интерпретирует.
                    _lines.append(
                        (_entry.get("speaker", "???"),
                         self.theme.token("accent")))
                    _body = _entry.get("text", "")
                    _hover_tip = (_entry.get("speaker", "???"),
                                  _entry.get("text", ""))
                else:
                    # Мёртвая journal-карточка: FIFO cap-100 вытеснил
                    # запись из журнала — валидное состояние (ТЗ Phase 4
                    # §2). Указатель не врёт и не выдумывает материал:
                    # честная формула + provenance-хвост для игрока.
                    _lines.append(("материал вытеснен из журнала",
                                   self.theme.token("text_muted")))
                    _lines.append((f"ref: {_c.get('ref_id', '')[:24]}",
                                   self.theme.token("text_muted")))
            elif _c.get("ref_type") == "hypothesis":
                _lines.append(("гипотеза", self.theme.token("text_muted")))
                _body = _hyp_texts.get(_c.get("ref_id", ""), "???")
                _hover_tip = ("гипотеза", _body)
            else:
                # claim/belief: persisted opaque — рендер серым (вердикт М)
                _alive = False
                _lines.append(
                    (f"{_c.get('ref_type', '?')}:{_c.get('ref_id', '')[:12]}",
                     self.theme.token("text_muted")))
            _color = (self.theme.token("surface_panel")
                      if _alive else self.theme.token("text_muted"))
            pygame.draw.rect(screen, _color, _rect, border_radius=6)
            _border_color = self.theme.token("accent")
            _border_w = 1
            if _cid in getattr(self, "_board_selected", []):
                _border_color = self.theme.token("border_accent")  # выбранная: золотой контур (токен, не RGB-литерал — закон темы)
                _border_w = 2
            pygame.draw.rect(screen, _border_color, _rect, _border_w,
                             border_radius=6)
            # Обрезка по высоте: сколько строк влезает в карточку;
            # усечение помечаем «…» — игрок видит, что текст длиннее
            _lh = self._font_text.get_linesize() + 1
            _max_lines = (self._BOARD_CARD_H - 10) // _lh
            _wrapped = (self._wrap(_body, self._BOARD_CARD_W - 12)
                        if _body else [])
            _budget = _max_lines - len(_lines)
            if _budget > 0:
                # №6: прокрутка вместо обрезки — wheel листает текст,
                # «…» остаётся маркером скрытых строк (снизу/сверху).
                _sc = max(0, min(self._board_card_scroll.get(_cid, 0),
                                 max(0, len(_wrapped) - _budget)))
                self._board_card_scroll[_cid] = _sc
                _lines += [(l, self.theme.token("text_primary"))
                           for l in _wrapped[_sc:_sc + _budget]]
                if _sc + _budget < len(_wrapped) and _lines:
                    _t, _col = _lines[-1]
                    _lines[-1] = (
                        (_t[:-1] if _t else _t) + "…", _col)
                if _sc > 0 and _lines:
                    _t, _col = _lines[0]
                    _lines[0] = ("…" + _t, _col)
            if _hover_tip is not None:
                self._board_hover_tips[_cid] = _hover_tip
            _ty = _y + 5
            for _lt, _lc in _lines:
                screen.blit(self._font_text.render(
                    _lt, True, _lc), (_x + 6, _ty))
                _ty += _lh
        # D: рёбра — двумя проходами нельзя терять z-порядок дёшево; линии
        # после карточек читаются как связи ПОВЕРХ материала — осознанный
        # выбор: при 170×96 карточках линия под карточкой невидима в точках
        # крепления. Токены: SUPPORTS = accent, CONTRADICTS = danger
        # (вердикт М 5 — RGB вне реестра запрещён). Мёртвое ребро не рисуем.
        for _l in self._board_cache.get("links", []):
            _ra = self._board_card_rects.get(str(_l.get("from", "")))
            _rb = self._board_card_rects.get(str(_l.get("to", "")))
            if _ra is None or _rb is None:
                continue
            _col = (self.theme.token("accent")
                    if _l.get("kind") == "PLAYER_SUPPORTS"
                    else self.theme.token("danger"))
            pygame.draw.line(screen, _col,
                             _ra.center, _rb.center, 2)
        # E1: command surface — discoverability N/L/U/E/X/B (ТЗ §5) +
        # индикация текущего kind для L (гейт D ТЗ). Токены, не RGB.
        _lk = ("подтверждает" if self._board_link_kind == "PLAYER_SUPPORTS"
               else "опровергает")
        _hs = self._font_text.render(
            f"N гипотеза · L связь [{_lk}] · U развязать · E правка · X убрать · B закрыть",
            True, self.theme.token("text_muted"))
        screen.blit(_hs, (body.x + 8, body.bottom - 36))
        # E3: ошибка операции видима (danger-токен), не глотается
        if self._board_error:
            _es = self._font_text.render(
                f"⚠ {self._board_error[:90]}", True,
                self.theme.token("danger"))
            screen.blit(_es, (body.x + 8, body.bottom - 18))
        # Гипотезы — списком в подвале окна; при активном inline-вводе
        # уступают место инпуту (E2-геометрия: ввод на bottom-78)
        if self._board_input_mode is None:
            _yy = body.bottom - 56
            for _h in self._board_cache.get("hypotheses", [])[-3:]:
                _t = f"· {_h.get('text', '')[:40]}"
                screen.blit(self._font_text.render(
                    _t, True, self.theme.token("text_primary")), (body.x + 8, _yy))
                _yy -= 18
        # C1: inline-ввод гипотезы (N) — поверх, над футером гипотез;
        # rect обновляется каждый кадр (окно двигается/ресайзится).
        # Гард по mode (не по инстансу): закрытый ввод не рисуется.
        if (self._board_input_mode is not None
                and self._board_input is not None):
            _ir = pygame.Rect(body.x + 8, body.bottom - 78,
                              body.width - 16, 28)
            self._board_input.rect = _ir
            self._board_input.draw(screen)
            _hint = self._font_text.render(
                "Enter — сохранить · Esc — отмена", True,
                self.theme.token("text_muted"))
            screen.blit(_hint, (body.x + 8, body.bottom - 94))
        # Tooltip (hover): полный материал карточки — чтение без
        # заглядывания в журнал. Не рисуем при активном drag (рука
        # занята — tooltip после того, как положили). Мышь в рендере
        # легальна: UI-слой, не симуляция (§15.2).
        if self._board_drag_id is None:
            _mp = pygame.mouse.get_pos()
            for _cid, _rect in self._board_card_rects.items():
                if not _rect.collidepoint(_mp):
                    continue
                _tip = self._board_hover_tips.get(_cid)
                if _tip is None:
                    break
                _head, _full = _tip
                _tl = self._wrap(_full, self._BOARD_TIP_W - 16)[:8]
                _th = 6 + self._font_text.get_linesize() + 2 + len(_tl) * (self._font_text.get_linesize() + 1) + 6
                _tx = min(_mp[0] + 12, body.right - self._BOARD_TIP_W - 4)
                _ty = min(_mp[1] + 12, body.bottom - _th - 4)
                _trect = pygame.Rect(_tx, _ty, self._BOARD_TIP_W, _th)
                pygame.draw.rect(screen, self.theme.token("surface_title"), _trect, border_radius=4)
                pygame.draw.rect(screen, self.theme.token("border"), _trect, 1, border_radius=4)
                screen.blit(self._font_text.render(_head, True, self.theme.token("accent")), (_tx + 8, _ty + 6))
                _tyy = _ty + 6 + self._font_text.get_linesize() + 2
                for _l in _tl:
                    screen.blit(self._font_text.render(_l, True, self.theme.token("text_primary")), (_tx + 8, _tyy))
                    _tyy += self._font_text.get_linesize() + 1
                break

    def _demo_topology(self) -> dict:
        """Editor-F12: демо-топология для стилизации инвентаря без игры."""
        _slot = lambda sid, bp: {"slot_id": sid, "body_part": bp}
        _cont = {"hand_right": [{"name": "Короткий нож", "weight": 0.8, "bulk": 1}],
                 "belt_pouch": [{"name": "Мешочек с монетами", "weight": 0.3, "bulk": 1}],
                 "backpack_main": [{"name": "Буханка чёрного хлеба", "weight": 1.0, "bulk": 2},
                                    {"name": "Фляга с водой", "weight": 0.5, "bulk": 1}]}
        return {"strength_score": 10,
                "hands": {"hand_right": _slot("hand_right", "правая рука"),
                           "hand_left": _slot("hand_left", "левая рука")},
                "worn": {"worn_torso": _slot("worn_torso", "торс"),
                          "worn_feet": _slot("worn_feet", "ступни")},
                "belt": {"belt_pouch": _slot("belt_pouch", "кошелёк")},
                "pockets": {"pocket_left": _slot("pocket_left", "левый карман"),
                             "pocket_right": _slot("pocket_right", "правый карман")},
                "backpack": {"backpack_main": _slot("backpack_main", "основной")},
                "hidden": {},
                "contents": _cont}

    def _draw_style_panel(self, screen, viewport: pygame.Rect) -> None:
        """S2/S3.13: панель стилизации (только F12) — сворачиваемые секции
        (клик по заголовку ▾/▸): Цвет → Стили/пресеты → Окна → Шрифт.
        Шрифт последняя: список шрифтов занимает весь остаток панели
        до низа (скролл колесом над списком)."""
        _pw, _ph = 300, 680
        # S3.13 (вердикт Мастера): панель по ЦЕНТРУ правого края — верх не
        # перекрывается мини-окнами даты/ускорения (анкер top_right занят)
        _py = max(12, (viewport.height - _ph) // 2)
        panel = pygame.Rect(viewport.right - _pw - 12, viewport.top + _py, _pw, _ph)
        self._style_panel_rect = panel
        pygame.draw.rect(screen, self.theme.token("surface_panel"), panel, border_radius=8)
        pygame.draw.rect(screen, self.theme.token("border_accent"), panel, 2, border_radius=8)
        _f = self._font_provider.get("ui", "", 0, False, False)
        _lh = _f.get_linesize() + 4
        _x, _y = panel.x + 10, panel.y + 8
        self._style_hits: list = []
        _sec = getattr(self, "_style_sections", None) \
            or {"font": True, "color": True, "presets": False, "windows": False}

        def _row(txt: str, col: str, act: str = "", val: str = "") -> None:
            nonlocal _y
            s = _f.render(txt, True, self.theme.token(col))
            screen.blit(s, (_x, _y))
            if act:
                self._style_hits.append((pygame.Rect(panel.x + 4, _y - 2, _pw - 8, _lh), act, val))
            _y += _lh

        def _sec_header(key: str, title: str) -> bool:
            _open = bool(_sec.get(key, key in ("font", "color")))
            _row(f"{'▾' if _open else '▸'} {title}", "accent", "section", key)
            return _open

        _glob = getattr(self, "_style_global", False)
        _row(f"[{'X' if _glob else ' '}] СТИЛЬ ДЛЯ ВСЕХ ОКОН"
             f"{' — ВКЛЮЧЁН: правки идут во все [X] окна' if _glob else ' — выключен: правки только цели'}",
             "accent" if _glob else "text_muted", "global_toggle")
        _tgt_title = (self.registry.manifest(self._style_target).title
                      if self._style_target else None)
        _row(f"СТИЛЬ  цель: {_tgt_title or '— (клик по шапке окна)'}"
             + ("  ← правка уйдёт во все [X] окна" if _glob
                else "  (правка: только это окно)"),
             "accent" if _glob else "text_primary")
        _y += 6
        _ov = self._style_overrides.get(self._style_target, {}).get(self._style_role, {})
        _sov = self._style_overrides.get(self._style_target, {}).get("_colors", {})

        # ── Секция: Цвет и прозрачность ──
        if _sec_header("color", "Цвет и прозрачность (клик = пикер)"):
            for _tok in ("surface_panel", "surface_title", "border", "border_accent",
                         "text_primary", "text_muted", "accent", "player_bubble",
                         "player_name"):
                _c = _sov.get(_tok) or _TOKEN_DEFAULTS.get(_tok) or list(self.theme.token(_tok))
                _row(f"{_TOKEN_RU.get(_tok, _tok)}  {tuple(_c)}", "text_primary", "color_edit", _tok)
            _row(f"Подложка журнала (цвет+альфа): a {_sov.get('backdrop_alpha', 0)}",
                 "text_primary", "backdrop")
            _y += 4

        # ── Секция: Стили окон и штукатурка ──
        if _sec_header("presets", "Стили окон и штукатурка"):
            _px = panel.x + 10
            for _pname in _COLOR_PRESETS:
                _s = _f.render(_pname, True, self.theme.token("text_primary"))
                if _px + _s.get_width() > panel.right - 8:
                    _px = panel.x + 10  # перенос строки пресетов (6 штук)
                    _y += _lh
                screen.blit(_s, (_px, _y))
                self._style_hits.append((pygame.Rect(_px - 3, _y - 2, _s.get_width() + 6, _lh),
                                         "preset", _pname))
                _px += _s.get_width() + 14
            if getattr(self, "_my_style", None):
                _s = _f.render("·Мой стиль", True, self.theme.token("accent"))
                screen.blit(_s, (_px, _y))
                self._style_hits.append((pygame.Rect(_px - 3, _y - 2, _s.get_width() + 6, _lh),
                                         "preset", "__my__"))
            _y += _lh
            _s = _f.render("[Сохранить мой стиль (с цели)]", True, self.theme.token("border_accent"))
            screen.blit(_s, (panel.x + 10, _y))
            self._style_hits.append((pygame.Rect(panel.x + 6, _y - 2, _s.get_width() + 8, _lh),
                                     "style_save", ""))
            _y += _lh
            _row(f"Глубина рельефа: {int(getattr(self, '_style_texture', 0))}"
                 f"   (клик ±1; минус = светлый)",
                 "text_primary", "texture")
            _nt = tuple(int(c) for c in
                        (getattr(self, "_style_noise_tint", None) or (255, 255, 255)))
            _row(f"Подтон узора  {_nt}   (клик = пикер)", "text_primary",
                 "color_edit", "noise_tint")
            _row(f"Масштаб узора: {int(getattr(self, '_style_noise_scale', 16))}",
                 "text_primary", "")
            _nsr = pygame.Rect(panel.x + 10, _y, _pw - 20, 10)
            _nf = (int(getattr(self, "_style_noise_scale", 16)) - 4) / (48 - 4)
            for _i in range(_nsr.width // 4 + 1):
                _g8 = int(110 + (_i / (_nsr.width // 4)) * 100)
                pygame.draw.rect(screen, (_g8, _g8, _g8),
                                 (_nsr.x + _i * 4, _nsr.y, 4, _nsr.height))
            pygame.draw.rect(screen, self.theme.token("border"), _nsr, 1)
            _hx = int(_nsr.x + _nf * _nsr.width)
            pygame.draw.rect(screen, (255, 255, 255), (_hx - 2, _nsr.y - 3, 4, _nsr.height + 6))
            self._style_hits.append((_nsr, "noise_slide", ""))
            self._noise_slider_rect = _nsr
            _y += 14
            _row(f"Сменить узор  (шум #{int(getattr(self, '_style_noise_seed', 0))})",
                 "border_accent", "noise_seed")
            _row("[Сбросить это окно]", "border_accent", "reset")
            _y += 4

        # ── Секция: Окна ([X]-бокс = глобальность, клик по строке = показ) ──
        if _sec_header("windows", "Окна: [X] глоб. | клик = показ"):
            for _wid in self.registry.all_ids():
                _wm = self.registry.manifest(_wid)
                _on = bool(getattr(self, "_style_window_global", {}).get(_wid, True))
                _st = self.registry.state(_wid)
                _v = _st != WindowState.HIDDEN
                _txt = f"[{'X' if _on else ' '}] {'▲' if _v else '▾'} {_wm.title}"
                screen.blit(_f.render(_txt, True,
                                     self.theme.token("accent" if _v else "text_muted")),
                            (_x, _y))
                self._style_hits.append((pygame.Rect(_x - 4, _y - 2, 30, _lh),
                                         "win_global_toggle", _wid))
                self._style_hits.append((pygame.Rect(panel.x + 4, _y - 2, _pw - 8, _lh),
                                         "win_toggle", _wid))
                _y += _lh
            _y += 4

        # ── Секция: Шрифт и типографика (ПОСЛЕДНЯЯ — список шрифтов
        # занимает весь остаток панели до низа) ──
        if _sec_header("font", "Шрифт и типографика"):
            _row(f"Роль: {'заголовок' if self._style_role == 'title' else 'текст'}   (клик — переключить)",
                 "text_primary", "role")
            _cur = _ov.get("font_file") or "consolas (системный)"
            _row(f"Шрифт: {_cur[:34]}", "text_primary", "font_cycle")
            _row(f"Размер: {16 if self._style_role == 'title' else 14}{_ov.get('size_delta', 0):+d}   [+/−]",
                 "text_primary", "size_cycle")
            _row(f"Жирный: {'ДА' if _ov.get('bold') else 'нет'}", "text_primary", "bold")
            _row(f"Курсив: {'ДА' if _ov.get('italic') else 'нет'}", "text_primary", "italic")
            # S3.7: типографика (per-role) — читаемость текста без фона
            _row(f"Обводка букв: {_ov.get('outline', 0)}   (клик +1 / Shift −1)",
                 "text_primary", "outline")
            _row(f"Тень букв: {'ДА' if _ov.get('shadow') else 'нет'}", "text_primary", "shadow")
            # S3.14: свечение — дробный ползунок 0-1 (per-role)
            _row(f"Свечение: {float(_ov.get('glow', 0)):.2f}", "text_primary", "")
            _gsr = pygame.Rect(panel.x + 10, _y, _pw - 20, 10)
            _gf = max(0.0, min(1.0, float(_ov.get("glow", 0))))
            for _i in range(_gsr.width // 4 + 1):
                _g8 = int(110 + (_i / (_gsr.width // 4)) * 100)
                pygame.draw.rect(screen, (_g8, _g8, _g8),
                                 (_gsr.x + _i * 4, _gsr.y, 4, _gsr.height))
            pygame.draw.rect(screen, self.theme.token("border"), _gsr, 1)
            _hx = int(_gsr.x + _gf * _gsr.width)
            pygame.draw.rect(screen, (255, 255, 255), (_hx - 2, _gsr.y - 3, 4, _gsr.height + 6))
            self._style_hits.append((_gsr, "glow_slide", ""))
            self._glow_slider_rect = _gsr
            _y += 14
            _row(f"Разрядка букв: {_ov.get('spacing', 0)}   (клик +1 / Shift −1)",
                 "text_primary", "spacing")
            _row(f"Подчёркивание: {'ДА' if _ov.get('underline') else 'нет'}",
                 "text_primary", "underline")
            # S3.14: живой ползунок размера аватара (клик/перетаскивание)
            _row(f"Размер аватара: {self._avatar_size()}", "text_primary", "")
            _asr = pygame.Rect(panel.x + 10, _y, _pw - 20, 10)
            _af = (self._avatar_size() - 24) / (96 - 24)
            for _i in range(_asr.width // 4 + 1):
                _g8 = int(110 + (_i / (_asr.width // 4)) * 100)
                pygame.draw.rect(screen, (_g8, _g8, _g8),
                                 (_asr.x + _i * 4, _asr.y, 4, _asr.height))
            pygame.draw.rect(screen, self.theme.token("border"), _asr, 1)
            _hx = int(_asr.x + _af * _asr.width)
            pygame.draw.rect(screen, (255, 255, 255), (_hx - 2, _asr.y - 3, 4, _asr.height + 6))
            self._style_hits.append((_asr, "avatar_slide", ""))
            self._avatar_slider_rect = _asr
            _y += 14
            _y += 4
            _row("── Шрифты (клик = применить) ──", "text_muted")
            self._style_font_area = pygame.Rect(panel.x + 4, _y, _pw - 8, panel.bottom - _y - 8)
            _names = self._font_provider.names()
            _scroll = getattr(self, "_style_scroll", 0)
            _vis = int(self._style_font_area.height // _lh)
            _scroll = max(0, min(_scroll, max(0, len(_names) - _vis)))
            self._style_scroll = _scroll
            for _nm in _names[_scroll:_scroll + _vis]:
                _on = _nm == _ov.get("font_file", "")
                _cyr = self._font_provider.supports_cyrillic(_nm)
                _mark = "" if _cyr else "  [нет кириллицы]"
                _col = ("accent" if _on else ("text_primary" if _cyr else "text_muted"))
                _row((_nm or "consolas (системный)") + _mark, _col, "pick", _nm)
            if len(_names) > _vis:
                _row(f"(колесо мыши над списком — ещё {len(_names) - _vis})", "text_muted")
        else:
            self._style_font_area = None

    def _style_panel_click(self, pos) -> bool:
        """S2: клик по панели стилизации. True = событие съедено."""
        panel = getattr(self, "_style_panel_rect", None)
        if not panel or not panel.collidepoint(pos) or not self._style_target:
            return False
        for rect, act, val in getattr(self, "_style_hits", []):
            if not rect.collidepoint(pos):
                continue
            if not self._style_target:
                return  # нет цели — некуда писать
            # B2: глобальный режим = broadcast — правка пишется в каждое окно
            # с флагом [X]; обычный — только выбранному. Новое значение
            # считается от ЦЕЛИ и разносится одинаковым всем.
            _wids = ([w for w in self.registry.all_ids()
                      if getattr(self, "_style_window_global", {}).get(w, True)]
                     if getattr(self, "_style_global", False) else [self._style_target])
            _ov = self._style_overrides.setdefault(self._style_target, {}).setdefault(self._style_role, {})
            if act == "section":
                # S3.13: сворачивание/разворачивание секции панели
                _sec = getattr(self, "_style_sections", None) or {}
                _sec[val] = not _sec.get(val, val in ("font", "color"))
                self._style_sections = _sec
            elif act == "role":
                self._style_role = "text" if self._style_role == "title" else "title"
            elif act == "font_cycle":
                _names = self._font_provider.names()
                try:
                    _i = _names.index(_ov.get("font_file", ""))
                except ValueError:
                    _i = 0
                _new = _names[(_i + 1) % len(_names)]
                for _w in _wids:
                    self._style_overrides.setdefault(_w, {}).setdefault(self._style_role, {})["font_file"] = _new
            elif act == "size_cycle":
                _new = int(_ov.get("size_delta", 0)) + 1 if _ov.get("size_delta", 0) < 20 else -6
                for _w in _wids:
                    self._style_overrides.setdefault(_w, {}).setdefault(self._style_role, {})["size_delta"] = _new
            elif act == "bold":
                _new = not _ov.get("bold", False)
                for _w in _wids:
                    self._style_overrides.setdefault(_w, {}).setdefault(self._style_role, {})["bold"] = _new
            elif act == "italic":
                _new = not _ov.get("italic", False)
                for _w in _wids:
                    self._style_overrides.setdefault(_w, {}).setdefault(self._style_role, {})["italic"] = _new
            elif act == "outline":
                _mods = pygame.key.get_mods()
                _new = max(0, min(4, int(_ov.get("outline", 0))
                                  + (-1 if (_mods & pygame.KMOD_SHIFT) else 1)))
                for _w in _wids:
                    self._style_overrides.setdefault(_w, {}).setdefault(self._style_role, {})["outline"] = _new
            elif act == "shadow":
                _new = not _ov.get("shadow", False)
                for _w in _wids:
                    self._style_overrides.setdefault(_w, {}).setdefault(self._style_role, {})["shadow"] = _new
            elif act == "glow_slide":
                _f = max(0.0, min(1.0, (pos[0] - rect.x) / max(1, rect.width)))
                _new = round(_f * 100) / 100
                for _w in _wids:
                    self._style_overrides.setdefault(_w, {}).setdefault(
                        self._style_role, {})["glow"] = _new
                self._glow_slider_rect = rect
                self._panel_slider_drag = "glow"
            elif act == "spacing":
                _mods = pygame.key.get_mods()
                _new = max(-4, min(8, int(_ov.get("spacing", 0))
                                   + (-1 if (_mods & pygame.KMOD_SHIFT) else 1)))
                for _w in _wids:
                    self._style_overrides.setdefault(_w, {}).setdefault(self._style_role, {})["spacing"] = _new
            elif act == "underline":
                _new = not _ov.get("underline", False)
                for _w in _wids:
                    self._style_overrides.setdefault(_w, {}).setdefault(self._style_role, {})["underline"] = _new
            elif act == "avatar_slide":
                # S3.14: клик по ползунку аватара (drag стартует здесь)
                _f = max(0.0, min(1.0, (pos[0] - rect.x) / max(1, rect.width)))
                self._style_avatar_size = int(24 + _f * (96 - 24))
                self._avatar_slider_rect = rect
                self._panel_slider_drag = "avatar"
            elif act == "color_edit":
                # S3.5: клик по цветовой строке = открыть HSV-пикер (ползунки)
                _base = self._style_overrides.get(self._style_target, {}) \
                    .get("_colors", {}).get(val)
                if _base is None:
                    # dict.get(k, expr) вычисляет expr ВСЕГДА — даже когда
                    # ключ найден; fail-fast theme поднимал KeyError
                    _d = _TOKEN_DEFAULTS.get(val)
                    _base = list(_d) if _d is not None else list(self.theme.token(val))
                h, s, v = colorsys.rgb_to_hsv(_base[0] / 255.0, _base[1] / 255.0,
                                              _base[2] / 255.0)
                self._picker_hsv = [h, s, v]
                _a = self._style_overrides.get(self._style_target, {}) \
                    .get("_colors", {}).get(val + "_alpha")
                self._picker_alpha = int(_a) if _a is not None else 255
                self._picker_token = val
            elif act == "backdrop":
                # S3.5: подложка — цвет + прозрачность в том же пикере
                _c = self._style_overrides.get(self._style_target, {}).get("_colors", {})
                _base = list(_c.get("backdrop_rgb", (10, 10, 18)))
                h, s, v = colorsys.rgb_to_hsv(_base[0] / 255.0, _base[1] / 255.0,
                                              _base[2] / 255.0)
                self._picker_hsv = [h, s, v]
                self._picker_alpha = int(_c.get("backdrop_alpha", 0))
                self._picker_token = "backdrop"
            elif act == "reset":
                for _w in _wids:
                    self._style_overrides.pop(_w, None)
            elif act == "preset":
                # S3.10: пресет/«Мой стиль» — полный набор _colors всем адресатам
                _p = dict(_COLOR_PRESETS[val]) if val != "__my__" \
                    else dict(getattr(self, "_my_style", {}))
                if not _p:
                    return True
                for _w in _wids:
                    self._style_overrides.setdefault(_w, {})["_colors"] = dict(_p)
            elif act == "style_save":
                # S3.10: снимок ЭФФЕКТИВНЫХ цветов+альф цели (включая
                # унаследованные из темы дефолты — восстановимо целиком)
                _snap: dict = {}
                for _tok in ("surface_panel", "surface_title", "border", "border_accent",
                             "text_primary", "text_muted", "accent", "player_bubble",
                             "player_name"):
                    _snap[_tok] = list(self._ct(self._style_target, _tok,
                                                _TOKEN_DEFAULTS.get(_tok)))
                _snap["backdrop_rgb"] = list(self._backdrop_rgb(self._style_target))
                _snap["backdrop_alpha"] = self._backdrop_alpha(self._style_target)
                for _tok in ("surface_panel", "surface_title", "border",
                             "border_accent", "player_bubble"):
                    _a = self._style_overrides.get(self._style_target, {}) \
                        .get("_colors", {}).get(_tok + "_alpha")
                    if _a is not None:
                        _snap[_tok + "_alpha"] = int(_a)
                self._my_style = _snap
            elif act == "texture":
                _mods = pygame.key.get_mods()
                self._style_texture = max(
                    -6, min(6, int(getattr(self, "_style_texture", 0))
                            + (-1 if (_mods & pygame.KMOD_SHIFT) else 1)))
            elif act == "noise_seed":
                # S3.14: новое зерно шума — уникальный узор
                self._style_noise_seed = int(getattr(self, "_style_noise_seed", 0)) + 1
            elif act == "noise_slide":
                _f = max(0.0, min(1.0, (pos[0] - rect.x) / max(1, rect.width)))
                self._style_noise_scale = int(4 + _f * (48 - 4))
                self._noise_slider_rect = rect
                self._panel_slider_drag = "noise"
            elif act == "win_toggle":
                _st = self.registry.state(val)
                if _st == WindowState.HIDDEN:
                    self.registry.transition(val, WindowState.FULL)
                    # Окно из HIDDEN может оказаться под панелью/за краем
                    # (анкер top_right занят СТИЛЬ+мини-окнами) — ставим
                    # гарантированно видимую геометрию слева-по-центру.
                    _vp = self._screen.get_rect()
                    _zone = self._zone(_vp)
                    self._free_rects[val] = (
                        _zone.x + 20, _zone.y + int(_zone.height * 0.3),
                        int(_zone.width * 0.34), int(_zone.height * 0.5))
                elif _st == WindowState.COLLAPSED_TO_TITLE:
                    self.registry.transition(val, WindowState.FULL)
                else:
                    self.registry.transition(val, WindowState.COLLAPSED_TO_TITLE)
            elif act == "global_toggle":
                self._style_global = not getattr(self, "_style_global", False)
            elif act == "win_global_toggle":
                # B2: флаг «в глобальном стиле» у окна (default ON).
                _wg = getattr(self, "_style_window_global", {})
                _wg[val] = not _wg.get(val, True)
            elif act == "pick":
                if val:
                    for _w in _wids:
                        self._style_overrides.setdefault(_w, {}).setdefault(self._style_role, {})["font_file"] = val
            return True
        return False

    # ── S3.5: HSV-пикер цвета (ползунки + градиентные шкалы) ─────────
    def _style_targets(self) -> list:
        """B2: адресаты стилевой правки — broadcast ([X]-окна) или цель."""
        if getattr(self, "_style_global", False):
            return [w for w in self.registry.all_ids()
                    if getattr(self, "_style_window_global", {}).get(w, True)]
        return [self._style_target] if self._style_target else []

    def _picker_apply(self) -> None:
        """Записать текущее HSV-пикера в оверрайды адресатов (мгновенно)."""
        _tok = self._picker_token
        if not _tok or not self._style_target:
            return
        h, s, v = self._picker_hsv
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        _rgb = [int(round(r * 255)), int(round(g * 255)), int(round(b * 255))]
        if _tok == "noise_tint":
            # S3.14: подтон шума — глобальный параметр (не per-window)
            self._style_noise_tint = _rgb
            return
        if _tok == "backdrop":
            for _w in self._style_targets():
                _c = self._style_overrides.setdefault(_w, {}).setdefault("_colors", {})
                _c["backdrop_rgb"] = _rgb
                _c["backdrop_alpha"] = int(self._picker_alpha)
        else:
            # S3.6: альфа пишется только поверхностям — текст непрозрачен
            _with_a = _tok not in ("text_primary", "text_muted", "accent", "player_name",
                                   "noise_tint")
            for _w in self._style_targets():
                _c = self._style_overrides.setdefault(_w, {}).setdefault("_colors", {})
                _c[_tok] = _rgb
                if _with_a:
                    _c[_tok + "_alpha"] = int(self._picker_alpha)

    def _picker_set(self, kind: str, frac: float) -> None:
        """Ползунок kind в позицию frac (0-1, кламп) + применить."""
        frac = max(0.0, min(1.0, frac))
        if kind == "h":
            self._picker_hsv[0] = frac
        elif kind == "s":
            self._picker_hsv[1] = frac
        elif kind == "v":
            self._picker_hsv[2] = frac
        elif kind == "a":
            self._picker_alpha = int(round(frac * 255))
        self._picker_apply()

    def _color_picker_click(self, pos) -> bool:
        """Клик в пикере. True = съедено. Клик мимо — закрыть, НЕ съедая:
        клик по другой цветовой строке тут же переоткроет пикер."""
        if not self._picker_token:
            return False
        pr = getattr(self, "_picker_rect", None)
        if not pr or not pr.collidepoint(pos):
            self._picker_token = None
            self._picker_drag = None
            return False
        for bar, kind in self._picker_sliders:
            if bar.collidepoint(pos):
                self._picker_drag = kind
                self._picker_set(kind, (pos[0] - bar.x) / max(1, bar.width))
                return True
        return True  # внутри пикера мимо ползунков — съесть

    def _color_picker_motion(self, pos) -> bool:
        """Drag ползунка: позиция мыши → frac (кламп по краям шкалы)."""
        if not self._picker_drag:
            return False
        for bar, kind in self._picker_sliders:
            if kind == self._picker_drag:
                self._picker_set(kind, (pos[0] - bar.x) / max(1, bar.width))
                return True
        return False

    def _draw_color_picker(self, screen, viewport: pygame.Rect) -> None:
        """S3.5: HSV-пикер — Тон (радуга) / Насыщенность / Яркость; для
        подложки журнала + цвет и Прозрачность. Ползунки тянутся мышью,
        применение мгновенное (мир под панелями на паузе)."""
        _tok = self._picker_token
        if not _tok:
            self._picker_rect = None
            return
        _w, _h = 250, 192
        # S3.13: пикер — на уровне панели СТИЛЬ (не под мини-окнами)
        _sp = getattr(self, "_style_panel_rect", None)
        _py = _sp.y if _sp is not None else viewport.top + 12
        panel = pygame.Rect(viewport.right - 312 - 8 - _w, _py, _w, _h)
        self._picker_rect = panel
        pygame.draw.rect(screen, self.theme.token("surface_panel"), panel, border_radius=8)
        pygame.draw.rect(screen, self.theme.token("border_accent"), panel, 2, border_radius=8)
        _f = self._font_provider.get("ui", "", 0, False, False)
        self._picker_sliders = []
        h, s, v = self._picker_hsv

        _title = "Подложка журнала: цвет + прозрачность" if _tok == "backdrop" \
            else f"Цвет: {_TOKEN_RU.get(_tok, _tok)}"
        screen.blit(_f.render(_title[:36], True, self.theme.token("text_primary")),
                    (panel.x + 10, panel.y + 8))
        # Превью «стало» — живой текущий цвет
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        pygame.draw.rect(screen, (int(round(r * 255)), int(round(g * 255)),
                                  int(round(b * 255))),
                         (panel.x + 10, panel.y + 28, _w - 20, 18))

        def _bar(kind: str, label: str, frac: float, y: int) -> None:
            bar = pygame.Rect(panel.x + 10, y, _w - 20, 14)
            _n = bar.width // 4
            for i in range(_n + 1):
                _fr = i / _n
                if kind == "h":
                    rr, gg, bb = colorsys.hsv_to_rgb(_fr, 1.0, 1.0)
                elif kind == "s":
                    rr, gg, bb = colorsys.hsv_to_rgb(h, _fr, v)
                elif kind == "v":
                    rr, gg, bb = colorsys.hsv_to_rgb(h, s, _fr)
                else:  # a: шкала непрозрачности 0-1 (единый масштаб с rr/gg/bb)
                    rr = gg = bb = _fr
                pygame.draw.rect(screen, (min(255, int(rr * 255)),
                                          min(255, int(gg * 255)),
                                          min(255, int(bb * 255))),
                                 (bar.x + i * 4, bar.y, 4, bar.height))
            pygame.draw.rect(screen, self.theme.token("border"), bar, 1)
            _hx = int(bar.x + max(0.0, min(1.0, frac)) * bar.width)
            pygame.draw.rect(screen, (255, 255, 255), (_hx - 2, bar.y - 3, 4, bar.height + 6))
            pygame.draw.rect(screen, (0, 0, 0), (_hx - 2, bar.y - 3, 4, bar.height + 6), 1)
            screen.blit(_f.render(label, True, self.theme.token("text_muted")),
                        (panel.x + 10, y - 15))
            self._picker_sliders.append((bar, kind))

        _y = panel.y + 66
        _bar("h", "Тон", h, _y)
        _y += 34
        _bar("s", "Насыщенность", s, _y)
        _y += 34
        _bar("v", "Яркость", v, _y)
        if _tok not in ("text_primary", "text_muted", "accent", "player_name",
                        "noise_tint"):
            # S3.6: прозрачность поверхностей (рамки/фоны/подложка)
            _y += 34
            _bar("a", f"Прозрачность: {int(self._picker_alpha)}",
                 self._picker_alpha / 255.0, _y)

    def _draw_tabs(self, screen, body: pygame.Rect, wid: str) -> None:
        """Полоса вкладок под заголовком. Активная — акцентом, хитбоксы — в
        self._tab_rects (клики — в handle_event)."""
        x = body.x + 8
        y = body.y + 4
        self._tab_rects[wid] = []
        active = self._active_tab.get(wid, "dialog")
        for tab_id, label in self._JOURNAL_TABS:
            color = self._ct(wid, "accent") if tab_id == active else self._ct(wid, "text_muted")
            surf = self._font_text.render(label, True, color)
            hit = pygame.Rect(x, y, surf.get_width() + 12, 22)
            screen.blit(surf, (x + 6, y + 3))
            if tab_id == active:
                # S3.14-фикс: линия под ФАКТИЧЕСКОЙ высотой метки — эффекты
                # прокси растят surface, фиксированная y+22 прорезала буквы
                _uy = y + 3 + surf.get_height() + 1
                pygame.draw.line(screen, self._ct(wid, "accent"),
                                 (x, _uy), (x + hit.width, _uy), 2)
            self._tab_rects[wid].append((hit, tab_id))
            x += hit.width + 8

    def _journal_entries(self, tab: str = "all", wid: Optional[str] = None) -> list:
        """SSOT данных + фильтр по channel-метке (записана в момент
        восприятия — эпистемически честна). Вкладки НЕ пересекаются:
        dialog = direct + self (беседа), npc = overheard, narrator = narrative.
        game_context → backend (уже с именами); editor → демо."""
        entries = (getattr(self._core, "_dialog_journal_backend", [])
                   if self.game_context else self._demo_journal) or []
        if tab == "dialog":
            # Interim (DEBT-JOURNAL-CHANNEL): backend-эхо player-реплик
            # приходит с channel=overheard и сырым speaker="player" —
            # это заведомо self-реплики игрока (эпистемически честно:
            # игрок знает свои слова). Правильный канал починит backend.
            base = [e for e in entries
                    if e.get("channel") in ("direct", "self")
                    or e.get("speaker") == "player"]
            base = [{**e, "channel": "self"} if e.get("speaker") == "player" else e for e in base]
            # Диалог-А: peer-фильтр. Self-реплика прикрепляется к последнему
            # direct-спикеру (frontend-эвристика v1; DEBT-JOURNAL-PEER: честный
            # peer_id придёт из backend-журнала вместе с spans[]).
            _peer = self._dialog_peer.get(wid or "")
            if not _peer:
                return base
            out = []
            _last = ""
            for e in base:
                if e.get("channel") == "direct":
                    _last = e.get("speaker", "")
                if e.get("speaker", "") == _peer or (e.get("channel") == "self" and _last == _peer):
                    out.append(e)
            return out
        if tab == "npc":
            return [e for e in entries if e.get("channel") == "overheard"]
        if tab == "narrator":
            return [e for e in entries if e.get("channel", "narrative") == "narrative"]
        return entries

    def _casting_wb(self):
        """S3.12: ленивый VisualCastingRepository (frontend-модуль, читает
        только конфиг-контент — изоляция фронтенда не нарушается)."""
        if self._casting_repo_wb is None:
            try:
                from visual_casting_repository import VisualCastingRepository
                self._casting_repo_wb = VisualCastingRepository()
            except Exception as _e:
                print(f"[AVATAR_CASTING] failed: {_e}")  # наблюдаемо, не тихо
                self._casting_repo_wb = False
        return self._casting_repo_wb or None

    def _portrait_npc_id(self, speaker: str) -> Optional[str]:
        """S3.12: имя журнала → npc_id (individuals: name + name_forms;
        точное совпадение, затем вхождение — «Борко» ⊂ «стражник борко»)."""
        if self._portrait_name_map is None:
            _m: dict = {}
            _dir = Path(__file__).parent.parent.parent / "config" / "npc" / "individuals"
            if _dir.exists():
                for _f in _dir.glob("*.json"):
                    try:
                        _d = json.loads(_f.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    _id = _d.get("id")
                    if not _id:
                        continue
                    for _nm in ({_d.get("name", "") or "", *_d.get("name_forms", [])}):
                        if _nm:
                            _m.setdefault(_nm.strip().lower(), _id)
            self._portrait_name_map = _m
        _key = (speaker or "").strip().lower()
        if not _key:
            return None
        if _key in self._portrait_name_map:
            return self._portrait_name_map[_key]
        for _nm, _id in self._portrait_name_map.items():
            if _key in _nm or _nm in _key:
                return _id
        return None

    def _journal_portrait(self, speaker: str):
        """S3.12/S3.14: фото-аватар по спикеру (кэш по (имя, размер);
        None = круг-инициал). Asset-контракт — как у PortraitRenderer."""
        _sz = self._avatar_size()
        _key = (speaker, _sz)
        if _key in self._avatar_cache:
            return self._avatar_cache[_key]
        _surf = None
        _repo = self._casting_wb()
        _npc = self._portrait_npc_id(speaker)
        if _repo is not None and _npc:
            _asset = _repo.get_fallback_asset(_npc)
            if _asset and _asset[0]:
                try:
                    from sprite_registry import sprite_registry as _sr
                    if len(_asset) >= 5:
                        _src = _sr.get_rect(
                            _asset[0], int(_asset[1]), int(_asset[2]),
                            int(_asset[3]), int(_asset[4]),
                            int(_asset[5]) if len(_asset) > 5 else 220,
                            int(_asset[6]) if len(_asset) > 6 else 1)
                    else:
                        _src = _sr.get(_asset[0], _asset[1], _asset[2])
                    if _src:
                        # Зум на верхний квадрат спрайта (голова/бюст):
                        # полный арт в 40px — нечитаемая каша (урок S3.12)
                        sw, sh = _src.get_size()
                        _side = min(sw, sh)
                        _sub = _src.subsurface(
                            pygame.Rect((sw - _side) // 2, 0, _side, _side))
                        _surf = pygame.transform.smoothscale(_sub, (_sz, _sz))
                except ImportError as _e:
                    print(f"[AVATAR_SPRITES] sprite_registry не найден: {_e}")
                except Exception:
                    _surf = None
        self._avatar_cache[_key] = _surf
        return _surf

    def _draw_avatar(self, screen, speaker: str, x: int, y: int, size: int,
                     ring_color) -> None:
        """S3.11/S3.12: аватар журнала (Discord-стиль). Приоритет — фото NPC
        из visual_casting (круговой кроп), фоллбэк — круг с инициалом.
        Кольцо — из палитры (цвет канала/рамки)."""
        _ph = self._journal_portrait(speaker)
        _avs = pygame.Surface((size, size), pygame.SRCALPHA)
        if _ph is not None:
            _avs.blit(_ph, ((size - _ph.get_width()) // 2,
                            (size - _ph.get_height()) // 2))
            _mask = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(_mask, (255, 255, 255, 255),
                               (size // 2, size // 2), size // 2 - 2)
            _avs.blit(_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        else:
            _h = (sum(ord(c) for c in (speaker or "?")) % 360) / 360.0
            r, g, b = colorsys.hsv_to_rgb(_h, 0.45, 0.72)
            pygame.draw.circle(_avs, (int(r * 255), int(g * 255), int(b * 255)),
                               (size // 2, size // 2), size // 2 - 2)
            _f = pygame.font.SysFont("consolas", max(9, size - 10))
            _ini = _f.render((speaker or "?")[:1].upper(), True, (240, 240, 240))
            _avs.blit(_ini, ((size - _ini.get_width()) // 2,
                             (size - _ini.get_height()) // 2))
        pygame.draw.circle(_avs, ring_color, (size // 2, size // 2), size // 2 - 2, 2)
        screen.blit(_avs, (x, y))

    def _draw_journal(self, screen, body: pygame.Rect, wid: Optional[str] = None) -> None:
        """F&F-лента: narration = полноширинный блок без пузыря (левая
        акцент-линия), self = пузырь справа, direct/overheard = пузырь NPC
        слева с именем. Хронология сверху-вниз, автоскролл к низу
        (рисуем последние помещающиеся)."""
        tab = self._active_tab.get(wid, "dialog") if wid else "all"
        # S3.5: контент журнала красится из стиля ОКНА (пикер/broadcast) —
        # тот же контракт, что у рамки через _ct. Локальный алиас подменён
        # адаптером: все theme.token(...) ниже читают оверрайды окна.
        theme = _WindowThemeAdapter(self, wid)
        entries = list(reversed(self._journal_entries(tab, wid)))  # хронологический порядок

        # Диалог-А: чипы собеседников (строка под вкладками). «Все» +
        # спикеры direct-записей (то, что игрок ЗНАЕТ как собеседника).
        self._peer_rects[wid or "__all__"] = []
        if wid and tab == "dialog":
            _seen: list = []
            for e in self._journal_entries("dialog"):
                _sp = e.get("speaker", "")
                if e.get("channel") == "direct" and _sp and _sp not in _seen:
                    _seen.append(_sp)
            if _seen:
                _cx, _cy = body.x + 8, body.y + 2
                _active = self._dialog_peer.get(wid)
                for _lbl in ["Все"] + _seen:
                    _on = (_lbl == "Все" and not _active) or _lbl == _active
                    _col = theme.token("accent") if _on else theme.token("text_muted")
                    _s = self._font_text.render(_lbl, True, _col)
                    _hit = pygame.Rect(_cx, _cy, _s.get_width() + 10, 18)
                    pygame.draw.rect(screen, theme.token("surface_title"), _hit, border_radius=4)
                    screen.blit(_s, (_cx + 5, _cy + 2))
                    self._peer_rects[wid].append((_hit, None if _lbl == "Все" else _lbl))
                    _cx += _hit.width + 6
                body = body.move(0, 22)
                body.height -= 22

        # M12 ч.2: карта распознавания имён (display_name → confidence).
        # game_context — живой scene_state из draw(); editor — демо-карта.
        # Отсутствие имени в карте = без «(?)», не выдумываем (§ENIGMA-003).
        if self.game_context and getattr(self, "_live_scene_state", None):
            _recog_names = {
                p.get("display_name", ""): p.get("recognition_confidence", 1.0)
                for p in (self._live_scene_state.get("npc_positions", {}) or {}).values()
                if isinstance(p, dict) and p.get("display_name")
            }
        else:
            _recog_names = getattr(self, "_demo_recognition", {})

        # Пре-расчёт блоков (entry → [lines-render-spec]) и бюджета высоты
        blocks = []  # (kind, speaker, lines, height)
        budget = body.height - 16
        for entry in entries:
            ch = entry.get("channel", "narrative")
            speaker = entry.get("speaker", "???")
            text = entry.get("text", "")
            if ch == "self":
                w = int(body.width * 0.62)
                lines = self._wrap(text, w - 20)
                h = 18 + len(lines) * (self._font_text.get_linesize() + 1) + 12
            elif ch == "narrative":
                w = body.width - 20
                lines = self._wrap(text, w - 14)
                h = len(lines) * (self._font_text.get_linesize() + 1) + 10
            else:
                w = int(body.width * 0.72)
                lines = self._wrap(text, w - 20)
                h = 16 + len(lines) * (self._font_text.get_linesize() + 1) + 12
            blocks.append((ch, speaker, lines, h, w, entry.get("event_id", "")))

        # M19 скролл: hidden_bottom = сколько НОВЫХ блоков скрыто снизу.
        # 0 = прижаты к последним (автоскролл доноров): новые записи
        # удлиняют content снизу, видимое окно остаётся у низа. При
        # hidden_bottom > 0 читающий историю не дёргается. Скролл в
        # ЦЕЛЫХ блоках: пузыри неделимы — нет частичных обрезок и
        # вылезания за рамку окна.
        hidden_bottom = self._journal_scroll.get(wid or "__all__", 0)
        # K_max: максимум скрытых-снизу, при котором старая история ещё
        # заполняет viewport (суффиксные суммы высот от старейшего конца).
        # Наивный clamp len-1 давал «один блок и пустота» на максимуме
        # скролла-вверх. Правильно: упор в НАЧАЛО истории — первые
        # сообщения заполняют окно; короткая история не скроллится
        # вовсе (пустое место снизу — под будущие записи).
        _suffix = 0
        _k_max = 0
        for _i in range(len(blocks) - 1, -1, -1):
            _suffix += blocks[_i][3] + 6
            if _suffix >= budget:
                _k_max = _i
                break
        hidden_bottom = max(0, min(hidden_bottom, _k_max))
        if wid:
            self._journal_scroll[wid] = hidden_bottom
        # ВНИМАНИЕ: blocks идут НОВЫЕ→СТАРЫЕ (reversed на входе + insert(0)
        # в бюджет-цикле дают итоговый M18-порядок на рендере). Новейшие k
        # блоков = blocks[:k], поэтому hidden_bottom отрезает НАЧАЛО списка
        # (скрытые новые снизу ленты), а не конец (не старые!).
        pool = blocks[hidden_bottom:] if hidden_bottom else blocks
        visible = []
        used = 0
        # M18 (вердикт Мастера): чат-порядок — старые сверху, новые снизу
        # (entries уже хронологические, второй reverse давал обратный порядок).
        for blk in pool:
            # +6: межблоковый зазор учитывается в бюджете (рендер даёт
            # y += h + 6 на каждый блок) — иначе накопленные зазоры
            # выталкивают последний пузырь за нижнюю рамку окна.
            if used + blk[3] + 6 > budget and visible:
                break
            visible.insert(0, blk)
            used += blk[3] + 6

        # Рендер
        self._journal_entry_rects[wid or "__all__"] = []  # A1: пересборка на кадр
        y = body.y + 8
        for ch, speaker, lines, h, w, ev_id in visible:
            lh = self._font_text.get_linesize() + 1
            _av = self._avatar_size()  # S3.14: живой размер (ползунок)
            if ch == "self":
                # S3.11: аватар игрока — справа от пузыря (Discord-стиль)
                bx = body.right - w - 10 - _av - 6
                bubble = pygame.Rect(bx, y, w, h - 6)
                # S3.7: пузырь игрока — токен (был RGB-литерал 35,45,70)
                self._fill_alpha(screen, bubble, *self._cta(wid, "player_bubble", (35, 45, 70)), 8)
                self._stroke_alpha(screen, bubble, *self._cta(wid, "border_accent"), 1, 8)
                # S3.9: имя игрока — отдельный токен «Имя игрока» (был
                # сцеплен с border_accent: затемнение рамки чернило имя)
                name_s = self._font_text.render(
                    speaker, True, self._ct(wid, "player_name", _TOKEN_DEFAULTS["player_name"]))
                screen.blit(name_s, (bx + 8, y + 2))
                self._draw_avatar(screen, speaker, body.right - _av - 10, y + 2,
                                  _av, self._ct(wid, "border_accent"))
                ty = y + 18
                for line in lines:
                    ts = self._font_text.render(line, True, theme.token("text_primary"))
                    screen.blit(ts, (bx + 10, ty))
                    ty += lh
            elif ch == "narrative":
                # Нарратив мира: без пузыря, левая акцент-линия, приглушённый
                pygame.draw.line(screen, theme.token("border"),
                                 (body.x + 6, y + 2), (body.x + 6, y + h - 6), 2)
                ty = y + 4
                for line in lines:
                    ts = self._font_text.render(line, True, theme.token("text_muted"))
                    screen.blit(ts, (body.x + 16, ty))
                    ty += lh
            else:
                bw = min(max(w, 120), max(100, body.width - _av - 26))
                bubble = pygame.Rect(body.x + 10 + _av + 6, y, bw, h - 6)
                self._fill_alpha(screen, bubble, *self._cta(wid, "surface_title"), 8)
                self._stroke_alpha(screen, bubble, *self._cta(wid, "border"), 1, 8)
                # M12 (вердикт): эпистемические маркеры у имени.
                # ● = сказано тебе (direct), ◌ = подслушано (overheard).
                # Цвет имени дублирует маркер (цветовая избыточность —
                # доступность без различения оттенков).
                _mark = "● " if ch == "direct" else "◌ "
                _nc = theme.token("accent") if ch == "direct" else theme.token("text_muted")
                _conf = _recog_names.get(speaker, 1.0)
                _name_txt = speaker if _conf >= 0.99 else f"{speaker} (?)"
                mark_s = self._font_text.render(_mark, True, _nc)
                name_s = self._font_text.render(_name_txt, True, _nc)
                screen.blit(mark_s, (bubble.x + 8, y + 1))
                screen.blit(name_s, (bubble.x + 8 + mark_s.get_width(), y + 1))
                # S3.11: аватар NPC слева (кольцо = цвет канала ●/◌)
                self._draw_avatar(screen, speaker, body.x + 10, y + 1, _av, _nc)
                # A1: маркер «+» — «положить на Доску». Только при открытой
                # Доске ∧ непустом event_id (ADR-O-404: narrative/self не
                # адресуются — маркер им не положен, граница видима).
                if (ev_id
                        and self.registry.state("board") == WindowState.FULL):
                    _plus = self._font_text.render("+", True,
                                                   theme.token("accent"))
                    screen.blit(_plus, (bubble.right - _plus.get_width() - 6,
                                        y + 1))
                ty = y + 17
                for line in lines:
                    ts = self._font_text.render(line, True, theme.token("text_primary"))
                    screen.blit(ts, (bubble.x + 10, ty))
                    ty += lh
            # A1: hit-зона записи — пузырь либо полный блок narrative
            _hit_r = (pygame.Rect(body.x + 4, y, body.width - 8, h)
                      if ch == "narrative" else bubble)
            self._journal_entry_rects[wid or "__all__"].append((_hit_r, ev_id))
            y += h + 6

        # M19 индикаторы (кликабельны, хитбоксы в _scroll_hint_rects):
        # ▲ N ниже — есть скрытые новые записи; ▼ к последним — возврат к низу.
        key = wid or "__all__"
        up_rect, down_rect = None, None
        if hidden_bottom > 0:
            hint = self._font_text.render(f"▲ {hidden_bottom} ниже", True,
                                          theme.token("text_muted"))
            up_rect = pygame.Rect(body.right - hint.get_width() - 12, body.y + 2,
                                  hint.get_width() + 8, 18)
            screen.blit(hint, (up_rect.x + 4, body.y + 4))
            back = self._font_text.render("▼ к последним", True,
                                          theme.token("accent"))
            down_rect = pygame.Rect(body.right - back.get_width() - 12,
                                    body.bottom - 20, back.get_width() + 8, 18)
            screen.blit(back, (down_rect.x + 4, down_rect.y + 2))
        self._scroll_hint_rects[key] = (up_rect, down_rect)
        # A3: hover по неадресуемой записи при открытой Доске — граница
        # объясняется, а не молчит (ADR-O-404: narrative/self без event_id
        # карточками быть не могут — выдумывать identity запрещено).
        if self.registry.state("board") == WindowState.FULL:
            _mp = pygame.mouse.get_pos()
            for _hit, _ev in self._journal_entry_rects.get(
                    wid or "__all__", []):
                if not _ev and _hit.collidepoint(_mp):
                    _msg = "нельзя адресовать — запись не привязана к событию"
                    _ms = self._font_text.render(
                        _msg, True, theme.token("text_primary"))
                    _mw = _ms.get_width() + 12
                    _mrect = pygame.Rect(
                        min(_mp[0] + 12, body.right - _mw - 4),
                        min(_mp[1] + 12, body.bottom - 30),
                        _mw, 26)
                    pygame.draw.rect(screen, theme.token("surface_title"),
                                     _mrect, border_radius=4)
                    pygame.draw.rect(screen, theme.token("border"),
                                     _mrect, 1, border_radius=4)
                    screen.blit(_ms, (_mrect.x + 6, _mrect.y + 5))
                    break

    def _wrap(self, text: str, width: int) -> list:
        """Перенос строк. Список (не generator): потребители считают len()."""
        out = []
        line = ""
        for word in text.split(" "):
            test = line + word + " "
            if self._font_text.size(test)[0] < width:
                line = test
            else:
                if line:
                    out.append(line)
                line = word + " "
        if line:
            out.append(line)
        return out
