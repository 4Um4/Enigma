"""
path: /frontend/ui_workbench/workbench_screen.py
Назначение: Shell UI Workbench v3a — оверлей окон поверх сцены (game или editor),
drag заголовком с магнитным прилипанием (SnapEngine, паттерн Windhawk),
free_rect-геометрия, safe-area, живой dialog_journal в game-контексте.
Зависимости: pygame, ui_workbench.*
Основные сущности: WorkbenchScreen
"""
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
from ui_workbench.layout import AnchoredRect
from ui_workbench.snap_engine import SnapEngine
from ui_workbench.editor_board_stub import EditorBoardStub
from ui_workbench.windows.board_window import BOARD_MANIFEST
from ui_workbench.windows.journal_window import JOURNAL_MANIFEST
from ui_workbench.fonts import FontProvider as _FontProvider

_WORKBENCH_DIR = Path(__file__).parent
_LAYOUT_PATH = _WORKBENCH_DIR / "window_layout.json"
_THEME_PATH = _WORKBENCH_DIR / "theme.json"

_TITLE_H = 34


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

    # ── S1: шрифтовые прокси ────────────────────────────────────────
    # 44 точки рендера читают _font_title/_font_text — прокси подставляет
    # per-window шрифт по текущему _render_wid. Fallback — базовые SysFont.

    def _ov(self, role: str) -> dict:
        wid = self._render_wid
        return getattr(self, "_style_overrides", {}).get(wid, {}).get(role, {}) if wid else {}


    @property
    def _font_title(self) -> pygame.font.Font:
        ov = (self._style_overrides.get(self._render_wid, {}).get("title", {})
              if self._render_wid else {})
        ov = self._ov("title")
        return self._font_provider.get("title", ov.get("font_file", ""),
                                       int(ov.get("size_delta", 0)),
                                       bool(ov.get("bold", False)),
                                       bool(ov.get("italic", False)))

    @property
    def _font_text(self) -> pygame.font.Font:
        ov = self._ov("text")
        return self._font_provider.get("text", ov.get("font_file", ""),
                                       int(ov.get("size_delta", 0)),
                                       bool(ov.get("bold", False)),
                                       bool(ov.get("italic", False)))

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
        _texts: dict = {}
        for e in self._demo_journal:
            ch = e.get("channel", "")
            if ch in ("direct", "overheard") and e["speaker"] not in _texts:
                _texts[e["speaker"]] = (e["text"].replace("Демо: ", ""), ch)
        _used = set()
        font = self._font_text
        theme = self.theme
        for npc_id, entry in npc_coords.items():
            sx, sy = self._norm_coord(entry)
            if sx is None:
                continue
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
            by = int(sy - 30 - bh)
            alpha = 235 if ch == "direct" else 150
            surf = pygame.Surface((bw, bh + 6), pygame.SRCALPHA)
            pygame.draw.rect(surf, (18, 18, 28, alpha), pygame.Rect(0, 0, bw, bh), border_radius=6)
            pygame.draw.rect(surf, theme.token("border"), pygame.Rect(0, 0, bw, bh), 1, border_radius=6)
            ty = 5
            for line in lines:
                ts = font.render(line, True, theme.token("text_primary"))
                surf.blit(ts, (8, ty))
                ty += lh
            # Хвостик вниз к NPC
            pygame.draw.polygon(surf, (18, 18, 28, alpha),
                                [(bw // 2 - 5, bh - 1), (bw // 2 + 5, bh - 1), (bw // 2, bh + 6)])
            screen.blit(surf, (bx, by))

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
        pygame.draw.rect(screen, theme.token("border_accent"), rect.inflate(4, 4), 1, border_radius=10)
        pygame.draw.rect(screen, theme.token("surface_panel"), rect, border_radius=8)
        pygame.draw.rect(screen, theme.token("border"), rect, 2, border_radius=8)

        title_h = _TITLE_H if not collapsed else rect.height
        title_rect = pygame.Rect(rect.x, rect.y, rect.width, title_h)
        pygame.draw.rect(screen, theme.token("surface_title"), title_rect,
                         border_radius=8)
        # Мини-окна HUD: в тайтле рисуется ЗНАЧЕНИЕ (дата/темп), не имя.
        # Один источник рисования — здесь (COLLAPSED = основное состояние).
        if manifest.data_source in ("world_clock", "time_scale"):
            _val = self._mini_window_value(manifest.data_source)
            title_surf = self._font_title.render(_val, True, theme.token("text_primary"))
        else:
            title_surf = self._font_title.render(manifest.title, True, theme.token("text_primary"))
        screen.blit(title_surf, (title_rect.x + 10, title_rect.y + (title_h - title_surf.get_height()) // 2))
        if not manifest.collapsible:
            self._arrow_rects.pop(wid, None)  # нет стрелки — нет toggle-зоны
        else:
            mark = "▸" if collapsed else "▾"
            mark_surf = self._font_title.render(mark, True, theme.token("accent"))
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

        pygame.draw.rect(screen, self.theme.token("surface_panel"), body, border_radius=8)

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
            title_surf = self._font_title.render(_t, True, self.theme.token("text_primary"))
            screen.blit(title_surf, (rect.x + 8, rect.y + (_TITLE_H - title_surf.get_height()) // 2))
            return
        if manifest.data_source == "time_scale":
            # Темп: DEBT-TS (визуально жив, функционально не работает) —
            # переносим как есть, функцию не чиним. Значение — core-флаг.
            _s = getattr(self._core, "hud_time_scale", "▶ 1x")
            title_surf = self._font_title.render(_s, True, self.theme.token("text_primary"))
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
            tab_body = pygame.Rect(body.x, body.y + 28, body.width, body.height - 28)
            if tab_body.width <= 0 or tab_body.height <= 0:
                return
            # Подложка ленты: плотный тёмный фон — текст не сливается с миром.
            # TODO: alpha → токен темы "journal_backdrop_alpha" (Style-редактор)
            backdrop = pygame.Surface(tab_body.size, pygame.SRCALPHA)
            backdrop.fill((10, 10, 18, 215))
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
                ts = self._font_text.render(line, True, self.theme.token("text_primary"))
                screen.blit(ts, (body.x + 8, ty))
                ty += lh
            return
        elif manifest.data_source == "player_body_topology":
            topo = (self._live_scene_state or {}).get("player_body_topology", {}) \
                if self.game_context else {}
            if not topo:
                ts = self._font_text.render("Топология тела недоступна.",
                                            True, self.theme.token("text_muted"))
                screen.blit(ts, (body.x + 8, body.y + 8))
                return
            _contents = topo.get("contents", {})
            ty = body.y + 6
            lh = self._font_text.get_linesize() + 2

            def _blit_line(txt: str, col: str) -> None:
                nonlocal ty
                if ty + lh > body.bottom - 4:
                    return
                ts = self._font_text.render(txt, True, self.theme.token(col))
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

    def _draw_style_panel(self, screen, viewport: pygame.Rect) -> None:
        """S2: панель стилизации (только F12). Кликабельна: цель/роль/шрифт/
        размер/жирность/курсив/сброс + список шрифтов (скролл колесом)."""
        _pw, _ph = 300, 500
        panel = pygame.Rect(viewport.right - _pw - 12, viewport.top + 12, _pw, _ph)
        self._style_panel_rect = panel
        pygame.draw.rect(screen, self.theme.token("surface_panel"), panel, border_radius=8)
        pygame.draw.rect(screen, self.theme.token("border_accent"), panel, 2, border_radius=8)
        _f = self._font_provider.get("ui", "", 0, False, False)
        _lh = _f.get_linesize() + 4
        _x, _y = panel.x + 10, panel.y + 8
        self._style_hits: list = []

        def _row(txt: str, col: str, act: str = "", val: str = "") -> None:
            nonlocal _y
            s = _f.render(txt, True, self.theme.token(col))
            screen.blit(s, (_x, _y))
            if act:
                self._style_hits.append((pygame.Rect(panel.x + 4, _y - 2, _pw - 8, _lh), act, val))
            _y += _lh

        _row(f"СТИЛЬ  цель: {self._style_target or '— (клик по шапке окна)'}", "accent")
        _y += 6
        _row(f"Роль: {self._style_role}   (клик — переключить)", "text_primary", "role")
        _ov = self._style_overrides.get(self._style_target, {}).get(self._style_role, {})
        _cur = _ov.get("font_file") or "consolas (системный)"
        _row(f"Шрифт: {_cur[:34]}", "text_primary", "font_cycle")
        _row(f"Размер: {16 if self._style_role == 'title' else 14}{_ov.get('size_delta', 0):+d}   [+/−]",
             "text_primary", "size_cycle")
        _row(f"Жирный: {'ДА' if _ov.get('bold') else 'нет'}", "text_primary", "bold")
        _row(f"Курсив: {'ДА' if _ov.get('italic') else 'нет'}", "text_primary", "italic")
        _row("[Сбросить это окно]", "border_accent", "reset")
        _y += 8
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

    def _style_panel_click(self, pos) -> bool:
        """S2: клик по панели стилизации. True = событие съедено."""
        panel = getattr(self, "_style_panel_rect", None)
        if not panel or not panel.collidepoint(pos) or not self._style_target:
            return False
        for rect, act, val in getattr(self, "_style_hits", []):
            if not rect.collidepoint(pos):
                continue
            _ov = self._style_overrides.setdefault(self._style_target, {}).setdefault(self._style_role, {})
            if act == "role":
                self._style_role = "text" if self._style_role == "title" else "title"
            elif act == "font_cycle":
                _names = self._font_provider.names()
                try:
                    _i = _names.index(_ov.get("font_file", ""))
                except ValueError:
                    _i = 0
                _ov["font_file"] = _names[(_i + 1) % len(_names)]
            elif act == "size_cycle":
                _ov["size_delta"] = int(_ov.get("size_delta", 0)) + 1 if _ov.get("size_delta", 0) < 20 else -6
            elif act == "bold":
                _ov["bold"] = not _ov.get("bold", False)
            elif act == "italic":
                _ov["italic"] = not _ov.get("italic", False)
            elif act == "reset":
                self._style_overrides.pop(self._style_target, None)
            elif act == "pick":
                if val:
                    _ov["font_file"] = val
            return True
        return False

    def _draw_tabs(self, screen, body: pygame.Rect, wid: str) -> None:
        """Полоса вкладок под заголовком. Активная — акцентом, хитбоксы — в
        self._tab_rects (клики — в handle_event)."""
        x = body.x + 8
        y = body.y + 4
        self._tab_rects[wid] = []
        active = self._active_tab.get(wid, "dialog")
        for tab_id, label in self._JOURNAL_TABS:
            color = self.theme.token("accent") if tab_id == active else self.theme.token("text_muted")
            surf = self._font_text.render(label, True, color)
            hit = pygame.Rect(x, y, surf.get_width() + 12, 22)
            screen.blit(surf, (x + 6, y + 3))
            if tab_id == active:
                pygame.draw.line(screen, self.theme.token("accent"),
                                 (x, y + 22), (x + hit.width, y + 22), 2)
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

    def _draw_journal(self, screen, body: pygame.Rect, wid: Optional[str] = None) -> None:
        """F&F-лента: narration = полноширинный блок без пузыря (левая
        акцент-линия), self = пузырь справа, direct/overheard = пузырь NPC
        слева с именем. Хронология сверху-вниз, автоскролл к низу
        (рисуем последние помещающиеся)."""
        tab = self._active_tab.get(wid, "dialog") if wid else "all"
        theme = self.theme
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
            if ch == "self":
                bx = body.right - w - 10
                bubble = pygame.Rect(bx, y, w, h - 6)
                pygame.draw.rect(screen, (35, 45, 70), bubble, border_radius=8)
                pygame.draw.rect(screen, theme.token("border_accent"), bubble, 1, border_radius=8)
                name_s = self._font_text.render(speaker, True, theme.token("border_accent"))
                screen.blit(name_s, (bx + 8, y + 2))
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
                bw = max(w, 120)
                bubble = pygame.Rect(body.x + 10, y, bw, h - 6)
                pygame.draw.rect(screen, theme.token("surface_title"), bubble, border_radius=8)
                pygame.draw.rect(screen, theme.token("border"), bubble, 1, border_radius=8)
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
