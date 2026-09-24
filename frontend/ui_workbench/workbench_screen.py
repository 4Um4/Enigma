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

        # Демо-данные (editor-контекст); game_context их не использует
        self._demo_journal = [
            {"speaker": "Торнин Серебряная Луна", "text": "Демо: таверна открывается на закате."},
            {"speaker": "Кузнец Орм", "text": "Демо: сталь не соврёт, если её спросить."},
            {"speaker": "Тень", "text": "Демо: ...тихо. Слишком тихо."},
        ]

        self._font_title = pygame.font.SysFont("consolas", 16)
        self._font_text = pygame.font.SysFont("consolas", 14)

    # ── Данные окна ──────────────────────────────────────────────────

    # (метод удалён — единственная версия ниже, с tab-фильтром и demo-fallback)

    # ── Lifecycle ────────────────────────────────────────────────────

    def toggle_journal(self) -> None:
        """J: toggle окна журнала (FSM). Открытие — на вкладке «Диалог»."""
        if self.registry.state("journal") != WindowState.FULL:
            self.registry.transition("journal", WindowState.FULL)
            self._active_tab["journal"] = "dialog"
        else:
            self.registry.transition("journal", WindowState.HIDDEN)

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
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for wid in self.registry.visible_ids():
                r = self._rects.get(wid)
                if r and r.collidepoint(event.pos):
                    self.handle_event(event)
                    return True
        return False

    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_F12:
            self.exit()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.exit()
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

    def draw(self, screen) -> None:
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
    _JOURNAL_TABS = [("dialog", "Диалог"), ("npc", "О НПС"), ("narrator", "Рассказчик")]

    def _draw_content(self, screen, wid: str, manifest, rect) -> None:
        body = pygame.Rect(rect.x, rect.y + _TITLE_H, rect.width, rect.height - _TITLE_H)
        pygame.draw.rect(screen, self.theme.token("surface_panel"), body, border_radius=8)

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
            self._draw_journal(screen, tab_body, wid)
        # точка роста: другие data_source по мере регистрации окон

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

        # Автоскролл: берём последние блоки, влезающие в бюджет
        visible = []
        used = 0
        for blk in reversed(blocks):
            if used + blk[3] > budget and visible:
                break
            visible.insert(0, blk)
            used += blk[3]

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
                # Имя: direct — акцентом (сказано тебе), overheard — приглушённо
                _nc = theme.token("accent") if ch == "direct" else theme.token("text_muted")
                name_s = self._font_text.render(speaker, True, _nc)
                screen.blit(name_s, (bubble.x + 8, y + 1))
                ty = y + 17
                for line in lines:
                    ts = self._font_text.render(line, True, theme.token("text_primary"))
                    screen.blit(ts, (bubble.x + 10, ty))
                    ty += lh
            y += h + 6

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