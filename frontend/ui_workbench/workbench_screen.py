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
                self.registry.restore(wid, record.get("state", "hidden"))
                self._free_rects[wid] = tuple(record["free_rect"]) if record.get("free_rect") else None
        except (ValueError, TypeError) as e:
            print(f"[WORKBENCH] layout пропущен: {e}")

        self.theme = ThemeLoader(_THEME_PATH).load()
        self.dispatcher = InputDispatcher(self.registry)
        self._snap = SnapEngine()

        self._rects: Dict[str, pygame.Rect] = {}
        # drag-состояние: [wid, grab-офсет, стартовая точка, сдвинулся?]
        self._drag: Optional[list] = None
        self._title_rects: Dict[str, pygame.Rect] = {}  # своя копия геометрии заголовков

        # Демо-данные (editor-контекст); game_context их не использует
        self._demo_journal = [
            {"speaker": "Торнин Серебряная Луна", "text": "Демо: таверна открывается на закате."},
            {"speaker": "Кузнец Орм", "text": "Демо: сталь не соврёт, если её спросить."},
            {"speaker": "Тень", "text": "Демо: ...тихо. Слишком тихо."},
        ]

        self._font_title = pygame.font.SysFont("consolas", 16)
        self._font_text = pygame.font.SysFont("consolas", 14)

    # ── Данные окна ──────────────────────────────────────────────────

    def _journal_entries(self) -> list:
        """SSOT данных: game_context → backend dialog_journal (уже с именами),
        editor → демо. Окна не ходят в backend сами (закон пакета)."""
        if self.game_context:
            return getattr(self._core, "_dialog_journal_backend", []) or []
        return self._demo_journal

    # ── Lifecycle ────────────────────────────────────────────────────

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
                r.clamp_ip(self._zone(viewport))
            return r
        return AnchoredRect.resolve(manifest, viewport, collapsed=collapsed)

    # ── Input ────────────────────────────────────────────────────────

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
            for wid in self.registry.visible_ids():
                tr = self._title_rects.get(wid)
                if tr and tr.collidepoint(event.pos):
                    rect = self._rects[wid]
                    self._drag = [wid, (event.pos[0] - rect.x, event.pos[1] - rect.y),
                                  event.pos, False]
                    return
        elif event.type == pygame.MOUSEMOTION and self._drag:
            if not self._drag[3]:
                sx, sy = self._drag[2]
                if abs(event.pos[0] - sx) + abs(event.pos[1] - sy) > 5:
                    self._drag[3] = True
            if self._drag[3]:
                self._do_drag(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._drag:
            if not self._drag[3]:
                self.registry.toggle(self._drag[0])  # клик = toggle
            self._drag = None

    def _do_drag(self, mouse_pos: Tuple[int, int]) -> None:
        wid, grab = self._drag[0], self._drag[1]
        manifest = self.registry.manifest(wid)
        viewport = self._screen.get_rect()
        zone = self._zone(viewport)

        rect = self._rects[wid]
        new_rect = pygame.Rect(mouse_pos[0] - grab[0], mouse_pos[1] - grab[1],
                               rect.width, rect.height)

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

    def draw(self, screen) -> None:
        if not self.active:
            return
        viewport = screen.get_rect()

        hint_surf = self._font_title.render(
            "UI WORKBENCH  [F12/ESC] выход (мир на паузе)  [J] журнал  тянуть за заголовок — магнит",
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
        screen.blit(mark_surf, (title_rect.right - 24, title_rect.y + (title_h - mark_surf.get_height()) // 2))

        self.dispatcher.bind_title_rect(wid, title_rect)
        self._title_rects[wid] = title_rect

    def _draw_content(self, screen, wid: str, manifest, rect) -> None:
        body = pygame.Rect(rect.x, rect.y + _TITLE_H, rect.width, rect.height - _TITLE_H)
        pygame.draw.rect(screen, self.theme.token("surface_panel"), body, border_radius=8)

        if manifest.data_source == "dialog_journal":
            self._draw_journal(screen, body)
        # точка роста: другие data_source по мере регистрации окон

    def _draw_journal(self, screen, body: pygame.Rect) -> None:
        y = body.y + 8
        for entry in reversed(self._journal_entries()):  # свежие сверху
            speaker = entry.get("speaker", "???")
            text = entry.get("text", "")
            name_surf = self._font_text.render(f"{speaker}:", True, self.theme.token("accent"))
            screen.blit(name_surf, (body.x + 10, y))
            y += name_surf.get_height() + 2
            for line in self._wrap(text, body.width - 24):
                ts = self._font_text.render(line, True, self.theme.token("text_primary"))
                screen.blit(ts, (body.x + 10, y))
                y += ts.get_height() + 1
            y += 8
            if y > body.bottom - 20:
                break

    def _wrap(self, text: str, width: int):
        line = ""
        for word in text.split(" "):
            test = line + word + " "
            if self._font_text.size(test)[0] < width:
                line = test
            else:
                if line:
                    yield line
                line = word + " "
        if line:
            yield line