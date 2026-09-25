"""
path: /frontend/ui_workbench/workbench_screen.py
Назначение: Shell UI Workbench v3a — оверлей окон поверх сцены (game или editor),
drag заголовком с магнитным прилипанием (SnapEngine, паттерн Windhawk),
free_rect-геометрия, safe-area, живой dialog_journal в game-контексте.
Зависимости: pygame, ui_workbench.*
Основные сущности: WorkbenchScreen
"""
import pygame
from pathlib import Path
from typing import Dict, Optional, Tuple

from ui_workbench import (
    InputDispatcher, ThemeLoader, WindowRegistry, WindowState,
    WorkbenchPersistence,
)
from ui_workbench.layout import AnchoredRect
from ui_workbench.snap_engine import SnapEngine
from ui_workbench.windows.board_window import BOARD_MANIFEST
from ui_workbench.windows.journal_window import JOURNAL_MANIFEST

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
        from ui_workbench.windows.mini_windows import WORLD_CLOCK_MANIFEST, TIME_SCALE_MANIFEST
        self.registry.register(WORLD_CLOCK_MANIFEST)
        self.registry.register(TIME_SCALE_MANIFEST)
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
                self.registry.restore(wid, record.get("state", "hidden"))
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
        self._title_rects: Dict[str, pygame.Rect] = {}
        self._arrow_rects: Dict[str, pygame.Rect] = {}  # зоны ▸/▾ (toggle, OS-паттерн)
        self._active_tab: Dict[str, str] = {}   # wid → tab_id (dialog по умолчанию)
        self._tab_rects: Dict[str, list] = {}   # wid → [(hit_rect, tab_id)]
        self.hud_time_scale: str = "▶ 1x"  # M-HUD: канал мини-окна time_scale (пишет game_screen)
        self._journal_body_rects: Dict[str, pygame.Rect] = {}  # M19: зона wheel-скролла
        self._journal_scroll: Dict[str, int] = {}  # M19: wid → скрытых НОВЫХ блоков снизу (0 = низ)
        self._scroll_hint_rects: Dict[str, tuple] = {}  # M19: wid → (▲-hit, ▼-hit) или (None, None)

        # Phase 4: Investigation Board — интеракции (MVI)
        self._board_cache: Optional[dict] = None
        self._board_error: Optional[str] = None
        self._board_selected: list = []       # до 2 card_id
        self._board_drag_id: Optional[str] = None
        self._board_drag_off = (0, 0)
        self._board_link_kind = "PLAYER_SUPPORTS"

        # Демо-данные (editor-контекст); game_context их не использует.
        # M19/M12 smoke-набор: все 4 канала, 3 подряд-реплики одного
        # спикера (будущий тест группировки), 2 длинных текста (wrap и
        # превышение бюджета → индикатор "▲ N ниже"), пары NPC→NPC
        # (прообраз M17: подслушанное обращение = tentative-имя).
        self._demo_journal = [
            {"speaker": "Рассказчик", "text": "Демо: таверна «Серебряный волк» открывается на закате. Сквозь щели ставень тянет дымом и запахом жареного лука.", "channel": "narrative"},
            {"speaker": "Торнин Серебряная Луна", "text": "Демо: проходи, не стой в дверях. Вечер только начался.", "channel": "direct"},
            {"speaker": "Кузнец Орм", "text": "Демо: сталь не соврёт, если её спросить.", "channel": "direct"},
            {"speaker": "Ты", "text": "Демо: *оглядываешь зал и присаживаешься у очага.*", "channel": "self"},
            {"speaker": "Торнин Серебряная Луна", "text": "Демо: Эй, Борко! Ведро унеси от печи, пока не опрокинул.", "channel": "overheard"},
            {"speaker": "Борко", "text": "Демо: Уже несу. Вчерашний козёл снова сбежал с двора, весь день ловлю.", "channel": "overheard"},
            {"speaker": "Тень", "text": "Демо: ...тихо. Слишком тихо.", "channel": "direct"},
            {"speaker": "Тень", "text": "Демо: за той дверью кто-то ходит всю ночь. Шаги лёгкие, почти без звука. Я считал — сорок два круга до рассвета.", "channel": "direct"},
            {"speaker": "Тень", "text": "Демо: я никому не скажу, что ты спрашивал.", "channel": "direct"},
            {"speaker": "Рассказчик", "text": "Демо: за стойкой Торнин протирает кружку одним и тем же движением — и смотрит не на кружку, а на дверь.", "channel": "narrative"},
            {"speaker": "Служанка Люся", "text": "Демо: Орм, опять клинок принёс? Третий за неделю.", "channel": "overheard"},
            {"speaker": "Кузнец Орм", "text": "Демо: люди платят, я кую. Спрашивать не положено — таков порядок в наших краях, и он старше любой стены этой таверны.", "channel": "overheard"},
            {"speaker": "Ты", "text": "Демо: *делаешь глоток эля. Хмель горчит сильнее, чем ты привык.*", "channel": "self"},
            {"speaker": "Торнин Серебряная Луна", "text": "Демо: про волка на вывеске спрашивают каждый прибывший. Отвечаю каждому: волк приходил сам, в метель, и мы его не выгнали. Кто-то из нас тогда умер, но вывеску не поменяешь — заказано при живом мастере, а мастер умер первым.", "channel": "direct"},
            {"speaker": "Борко", "text": "Демо: Эй, кто-нибудь видел мою рукавицу? Левую!", "channel": "overheard"},
            {"speaker": "Рассказчик", "text": "Демо: где-то наверху скрипнула половица. Шаги стихли у самой лестницы.", "channel": "narrative"},
            {"speaker": "Тень", "text": "Демо: сорок третий.", "channel": "direct"},
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

        self._font_title = pygame.font.SysFont("consolas", 16)
        self._font_text = pygame.font.SysFont("consolas", 14)

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

    def open_journal_dialog_tab(self) -> None:
        """Авто-открытие: журнал FULL на вкладке «Диалог». Не навязчиво:
        если игрок его закрыл — открываем только по новому фокусу ввода."""
        if self.registry.state("journal") != WindowState.FULL:
            self.registry.transition("journal", WindowState.FULL)
        self._active_tab["journal"] = "dialog"

    def enter(self) -> None:
        self.active = True
        # Пауза мира (game-контекст): флаг читает game_screen перед idle_tick.
        # Мир не тикает, пока верстак открыт (решение Мастера: редактируем на паузе,
        # выходим — досимулировали нужную сцену — открыли снова).
        if self.game_context:
            self._core.workbench_paused = True

    def exit(self) -> None:
        self.active = False
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
            # оптимистичный апдейт кэша (мир не владеет доской — races нет),
            # затем REST — файл как SSOT
            for _c in self._board_cache.get("cards", []):
                if _c.get("id") == _cid:
                    _c["pos"] = [float(_rect.x), float(_rect.y)]
                    break
            try:
                self._core._gateway.board_card_move(
                    self._core.campaign_folder, _cid,
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
                    self._core._gateway.board_link(
                        self._core.campaign_folder, _a, _b,
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
                            self._core._gateway.board_link(
                                self._core.campaign_folder,
                                _l.get("from"), _l.get("to"), _l.get("kind"),
                                unlink_op=True)
                            _removed = True
                        except Exception as e:
                            self._board_error = str(e)
                self._refresh_board()
                return True or _removed
            if event.key == pygame.K_x and self._board_selected:
                for _cid in list(self._board_selected):
                    try:
                        self._core._gateway.board_card_remove(
                            self._core.campaign_folder, _cid)
                    except Exception as e:
                        self._board_error = str(e)
                self._board_selected = []
                self._refresh_board()
                return True
            if event.key == pygame.K_n and self._board_cache is not None:
                # CREATE_HYPOTHESIS: текст-плейсхолдер, правится через REST
                # (полноценный text-input — следующая итерация UI)
                try:
                    self._core._gateway.board_hypothesis(
                        self._core.campaign_folder, "create",
                        text="[опишите гипотезу]")
                except Exception as e:
                    self._board_error = str(e)
                self._refresh_board()
                return True
        return False

    def handle_event(self, event) -> None:
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
                    rect = self._rects[wid]
                    self._drag = [wid, (event.pos[0] - rect.x, event.pos[1] - rect.y)]
                    return
        elif event.type == pygame.MOUSEWHEEL:
            # M19: колесо над телом журнала = скролл ленты (блок за шаг ×3).
            # event.pos ненадёжен в MOUSEWHEEL → get_pos(); wheel вверх = старее.
            mouse = pygame.mouse.get_pos()
            for wid, r in self._journal_body_rects.items():
                if self.registry.state(wid) != WindowState.FULL:
                    continue
                if r and r.collidepoint(mouse):
                    self._journal_scroll[wid] = max(0, self._journal_scroll.get(wid, 0) + event.y * 3)
                    return
        elif event.type == pygame.MOUSEMOTION and self._drag:
            self._do_drag(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._drag = None
        # (вкладочная ветка перенесена в начало MOUSEBUTTONDOWN — удалена отсюда)

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
                "UI WORKBENCH  [F12/ESC] выход  тянуть за заголовок — магнит  вкладки — клик",
                True, self.theme.token("accent"),
            )
            screen.blit(hint_surf, (viewport.left + 10, viewport.bottom - 26))

        for wid in self.registry.visible_ids():
            manifest = self.registry.manifest(wid)
            state = self.registry.state(wid)
            collapsed = state == WindowState.COLLAPSED_TO_TITLE
            rect = self._resolve_rect(wid, manifest, viewport)
            self._rects[wid] = rect

            self._draw_window_frame(screen, wid, manifest, rect, collapsed)
            if not collapsed:
                self._draw_content(screen, wid, manifest, rect)

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
        # точка роста: другие data_source по мере регистрации окон

    # ── Phase 4: Investigation Board ────────────────────────────────
    # Кэш организации доски. Мир на паузе при открытом workbench →
    # достаточно refresh при открытии (toggle_board) и после операций.
    _BOARD_CARD_W, _BOARD_CARD_H = 130, 64

    def toggle_board(self) -> None:
        """Открытие/скрытие Доски. При каждом открытии — refresh кэша
        (HTTP GET; мир стоит, данные между открытиями не меняются)."""
        state = self.registry.state("board")
        if state == WindowState.FULL:
            self.registry.transition("board", WindowState.COLLAPSED_TO_TITLE)
            return
        self.registry.transition("board", WindowState.FULL)
        self._refresh_board()

    def _refresh_board(self) -> None:
        """GET /api/board/{campaign} → кэш. Ошибка транспорта — НЕ тихий
        отказ: рисуем текст ошибки в окне (L4-совместимо)."""
        self._board_error = None
        try:
            self._board_cache = self._core._gateway.get_board(
                self._core.campaign_folder)
        except Exception as e:  # BackendError / urllib — наблюдаемо в UI
            self._board_cache = None
            self._board_error = str(e)

    def _board_live_journal_ids(self) -> set:
        """Живые event_id журнала — канал уже проекцирован с event_id
        (ADR-O-404). Записи narrative/self без event_id карточками
        быть не могут (TЗ Phase 4: не выдумывать identity)."""
        return {
            e.get("event_id")
            for e in getattr(self._core, "_dialog_journal_backend", [])
            if e.get("event_id")
        }

    def _draw_board(self, screen, body: pygame.Rect, wid: str) -> None:
        """Рендер организации: карточки по pos, гипотезы списком.
        Мёртвая journal-карточка — серым с ref-хвостом (валидное
        состояние ТЗ §2). Клиент НЕ вычисляет семантику."""
        if getattr(self, "_board_cache", None) is None:
            msg = f"Доска недоступна: {getattr(self, '_board_error', '?')}"
            surf = self._font_text.render(msg[:90], True,
                                          self.theme.token("text_muted"))
            screen.blit(surf, (body.x + 10, body.y + 10))
            return
        _live = self._board_live_journal_ids()
        _hyp_texts = {h.get("id", ""): h.get("text", "")
                      for h in self._board_cache.get("hypotheses", [])}
        # Хитбоксы карточек (интеракции — U3)
        self._board_card_rects = {}
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
            _line2 = ""
            if _c.get("ref_type") == "journal":
                _alive = _c.get("ref_id", "") in _live
                _line2 = _c.get("ref_id", "")[:18]
            elif _c.get("ref_type") == "hypothesis":
                _line2 = _hyp_texts.get(_c.get("ref_id", ""), "???")
            else:
                # claim/belief: persisted opaque — рендер серым (вердикт М)
                _alive = False
                _line2 = f"{_c.get('ref_type', '?')}:{_c.get('ref_id', '')[:12]}"
            _color = (self.theme.token("surface_panel")
                      if _alive else self.theme.token("text_muted"))
            pygame.draw.rect(screen, _color, _rect, border_radius=6)
            _border_color = self.theme.token("accent")
            _border_w = 1
            if _cid in getattr(self, "_board_selected", []):
                _border_color = (255, 220, 120)  # выбранная: тёплый контур
                _border_w = 2
            pygame.draw.rect(screen, _border_color, _rect, _border_w,
                             border_radius=6)
            _l1 = f"{_c.get('ref_type', '?')}"
            screen.blit(self._font_text.render(
                _l1, True, self.theme.token("text_default")),
                (_x + 6, _y + 5))
            screen.blit(self._font_text.render(
                _line2, True, self.theme.token("text_muted")),
                (_x + 6, _y + 24))
        # Гипотезы — списком в подвале окна
        _yy = body.bottom - 22
        for _h in self._board_cache.get("hypotheses", [])[-3:]:
            _t = f"· {_h.get('text', '')[:40]}"
            screen.blit(self._font_text.render(
                _t, True, self.theme.token("text_default")), (body.x + 8, _yy))
            _yy -= 18

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

    def _journal_entries(self, tab: str = "all") -> list:
        """SSOT данных + фильтр по channel-метке (записана в момент
        восприятия — эпистемически честна). Вкладки НЕ пересекаются:
        dialog = direct + self (беседа), npc = overheard, narrator = narrative.
        game_context → backend (уже с именами); editor → демо."""
        entries = (getattr(self._core, "_dialog_journal_backend", [])
                   if self.game_context else self._demo_journal) or []
        if tab == "dialog":
            return [e for e in entries if e.get("channel") in ("direct", "self")]
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
        entries = list(reversed(self._journal_entries(tab)))  # хронологический порядок

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
            blocks.append((ch, speaker, lines, h, w))

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
        y = body.y + 8
        theme = self.theme
        for ch, speaker, lines, h, w in visible:
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
                ty = y + 17
                for line in lines:
                    ts = self._font_text.render(line, True, theme.token("text_primary"))
                    screen.blit(ts, (bubble.x + 10, ty))
                    ty += lh
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