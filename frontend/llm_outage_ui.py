# -*- coding: utf-8 -*-
"""frontend/llm_outage_ui.py — COV-2/D61: фронтенд-контур обязательной LLM.

Назначение: watcher-поток статуса LLM (/api/llm/outage), модалка двух
выборов (Перезапустить | Выйти), generation-счётчик против устаревших
результатов. Доктрина (вердикты Мастера, ТЗ D61 §3.1): отказа без паузы
не существует; продолжение без LLM запрещено; авто-возобновление запрещено.

Зависимости: threading + стандартная библиотека; pygame — лениво и только
для draw_outage_modal (контроллер работает headless в тестах T-пауза).
Модуль не знает backend (Закон 6.2 Устава): gateway инъектируется извне.

Шрифт — локальный pygame.font.SysFont("Arial") внутри модуля: атрибуты
GameScreen не верифицированы (ТЗ §3.2).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

try:  # headless-тесты контроллера идут без pygame
    import pygame
except ImportError:  # pragma: no cover
    pygame = None  # type: ignore[assignment]

_LOG = logging.getLogger(__name__)

# Статусы /api/llm/outage (контракт D61-бэкенда, коммит 31387976)
_STATUS_OUTAGE = "outage"            # доказанный pool backoff -> пауза сразу
_STATUS_UNCONFIRMED = "unconfirmed"  # health offline при чистом пуле
_STATUS_ONLINE = "online"

# Состояния модалки
M_OUTAGE = "OUTAGE"
M_RESTARTING = "RESTARTING"
M_SUCCESS = "SUCCESS"
M_FAILED = "FAILED"

# Рестарт-флоу владеет модалкой в этих состояниях — watcher не вмешивается
_RESTART_FLOW = (M_RESTARTING, M_SUCCESS, M_FAILED)

_POLL_INTERVAL = 5.0    # доктрина №6: один поток, интервал 5 с
_UNCONFIRMED_LIMIT = 2  # доктрина №2: дебаунс 2 проб подряд

# Доктрина №6 «один поток»: гасим watcher прошлой сессии run()
_ACTIVE: "Optional[LlmOutageController]" = None
_ACTIVE_LOCK = threading.Lock()


class LlmOutageController:
    """Контроллер паузы LLM: watcher-поток + автомат модалки.

    Потоковая модель: `_poll_loop` (daemon) меняет состояние только при
    живом поколении; главный поток читает llm_paused/modal_state и владеет
    рестарт-флоу. Поколение `_gen` — единственный арбитр свежести: любые
    переходы (resume/stop) инкрементируют его, захваченные раньше
    результаты отбрасываются (доктрина №6).
    """

    def __init__(self, gateway: Any) -> None:
        self.gateway = gateway
        # Публичное состояние (читает главный цикл game_screen)
        self.llm_paused: bool = False
        self.modal_state: Optional[str] = None
        self.modal_reason: str = ""
        # Приватная механика
        self._gen: int = 0
        self._stop_evt = threading.Event()
        self._unconfirmed: int = 0
        self._thread: Optional[threading.Thread] = None
        self._restart_result: "Optional[tuple[Optional[dict], int]]" = None
        self._restart_busy: bool = False
        # Клик модалки: rising edge, не event-очередь (риск ТЗ §3.4)
        self._modal_prev_mouse: bool = False
        self._modal_drawn_state: Optional[str] = None
        # Замороженный кадр мира под оверлеем: буфер после flip не
        # определён, снимок даёт детерминированный фон модалки
        self._modal_snapshot: Optional[Any] = None

    # ---------------------------------------------------- жизненный цикл

    def start(self) -> None:
        """Запуск watcher-потока; повторный вызов при живом — no-op."""
        global _ACTIVE
        with _ACTIVE_LOCK:
            if self._thread is not None and self._thread.is_alive():
                return
            if _ACTIVE is not None and _ACTIVE is not self:
                _ACTIVE.stop()  # доктрина №6: watcher всегда один
            _ACTIVE = self
            self._stop_evt.clear()
            self._thread = threading.Thread(
                target=self._poll_loop, daemon=True, name="llm-outage-watcher"
            )
            self._thread.start()

    def stop(self) -> None:
        """Остановка: новое поколение + сигнал завершения потока."""
        self._gen += 1
        self._stop_evt.set()
        self._modal_snapshot = None

    def _poll_loop(self) -> None:
        while not self._stop_evt.wait(_POLL_INTERVAL):
            my_gen = self._gen
            try:
                payload = self.gateway.get_llm_outage()
            except Exception as exc:
                # Транспортный сбой — НЕ LLM-отказ: пауза без
                # доказательства запрещена (доктрина №2)
                _LOG.debug("[D61] outage-poll транспорт: %s", exc)
                continue
            if my_gen != self._gen:
                continue  # поколение устарело (resume/stop) — отбой
            status = (payload or {}).get("status")
            if status not in (_STATUS_OUTAGE, _STATUS_UNCONFIRMED, _STATUS_ONLINE):
                continue  # неизвестный статус — доказательства отказа нет
            self._apply_status(status, (payload or {}).get("reason", ""))

    # ---------------------------------------------------- применение статуса

    def _apply_status(self, status: str, reason: str = "") -> None:
        """Статус бэкенда -> пауза/модалка. Вызывается из watcher-потока
        и из старт-гейта run() (компонент D ТЗ) — доктрина одна."""
        if self.modal_state in _RESTART_FLOW:
            return  # рестарт-флоу владеет модалкой
        if status == _STATUS_OUTAGE:
            self._pause_with_modal(reason)
        elif status == _STATUS_UNCONFIRMED:
            self._unconfirmed += 1
            if self._unconfirmed >= _UNCONFIRMED_LIMIT:
                self._pause_with_modal(reason)
        elif status == _STATUS_ONLINE:
            self._unconfirmed = 0  # авто-возобновление запрещено (№3)

    def _pause_with_modal(self, reason: str) -> None:
        self.llm_paused = True
        self.modal_state = M_OUTAGE
        self.modal_reason = reason or "LLM-контур недоступен"

    # ---------------------------------------------------- рестарт-флоу

    def begin_restart(self) -> None:
        """RESTARTING; предыдущая попытка (если была) обнуляется."""
        self.modal_state = M_RESTARTING
        self.modal_reason = ""
        self._restart_busy = False
        self._restart_result = None

    def poll_restart(self) -> None:
        """Главный поток зовёт каждый кадр в RESTARTING: применяет готовый
        результат воркера (с проверкой поколения) либо запускает воркер
        gateway.restart_llm() ровно один раз."""
        if self._restart_result is not None:
            res, my_gen = self._restart_result
            self._restart_result = None
            self._restart_busy = False
            if my_gen != self._gen:
                return  # поколение устарело — результат отброшен
            if res is not None and res.get("restarted"):
                self.modal_state = M_SUCCESS
            else:
                reason = (res or {}).get("reason") or "неизвестная причина"
                detail = (res or {}).get("detail") or ""
                self.modal_state = M_FAILED
                self.modal_reason = reason + (" — " + detail if detail else "")
            return
        if not self._restart_busy:
            self._restart_busy = True
            my_gen = self._gen

            def _worker() -> None:
                try:
                    res = self.gateway.restart_llm()
                except Exception as exc:
                    # транспортный провал = провал рестарта, причина показывается
                    res = {
                        "restarted": False,
                        "reason": "транспортная ошибка рестарта",
                        "detail": str(exc),
                    }
                self._restart_result = (res, my_gen)

            threading.Thread(
                target=_worker, daemon=True, name="llm-restart-worker"
            ).start()

    # ---------------------------------------------------- выходы модалки

    def confirm_resume(self) -> None:
        """«Возобновить»: новое поколение, снятие паузы, закрытие модалки."""
        self._gen += 1
        self._unconfirmed = 0
        self.llm_paused = False
        self.modal_state = None
        self.modal_reason = ""
        self._modal_snapshot = None

    def retry(self) -> None:
        """Возврат к OUTAGE-модалке (два выбора) без нового рестарта."""
        self.modal_state = M_OUTAGE


# ---------------------------------------------------------------------------
# Модалка: рисование + клик. Клик — rising edge левой кнопки
# (pygame.mouse.get_pressed), не event-очередь: детекция не зависит от
# порядка выборки событий главным циклом (риск ТЗ §3.4 закрыт так).
# ---------------------------------------------------------------------------

_TITLES = {
    M_OUTAGE: "LLM недоступна — мир остановлен",
    M_RESTARTING: "Перезапуск LLM-сервера...",
    M_SUCCESS: "LLM-сервер восстановлен",
    M_FAILED: "Перезапуск не удался",
}

_BODIES = {
    M_OUTAGE: "Игровое время остановлено. Продолжение без LLM невозможно.",
    M_RESTARTING: "Загрузка модели может занять до ~90 секунд. Подождите...",
    M_SUCCESS: "Сервер отвечает. Мир на паузе — продолжает только игрок.",
    M_FAILED: "Пауза сохраняется. Причина показана выше.",
}

# Кнопки по состоянию: (метка, действие); действия: restart | resume | exit
_BUTTONS = {
    M_OUTAGE: (("Перезапустить LLM", "restart"), ("Выйти", "exit")),
    M_RESTARTING: (("Выйти", "exit"),),
    M_SUCCESS: (("Возобновить", "resume"), ("Выйти", "exit")),
    M_FAILED: (("Повторить", "restart"), ("Выйти", "exit")),
}

_FONT_CACHE: "dict[tuple[int, bool], Any]" = {}


def _get_font(size: int = 22, bold: bool = False) -> Any:
    """Локальный шрифт модуля (ТЗ §3.2): GameScreen не верифицирован."""
    if pygame is None:
        raise RuntimeError("pygame недоступен: модалке D61 нужен график")
    key = (size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont("Arial", size)
        if bold:
            font.set_bold(True)
        _FONT_CACHE[key] = font
    return font


def _wrap_px(font: Any, text: str, max_px: int) -> "list[str]":
    """Перенос по пиксельной ширине (причина — не более 4 строк, ТЗ §3.2)."""
    words = text.split()
    if not words:
        return []
    lines: "list[str]" = []
    cur = words[0]
    for word in words[1:]:
        cand = cur + " " + word
        if font.size(cand)[0] > max_px:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    lines.append(cur)
    return lines


def draw_outage_modal(
    screen: Any, ctrl: LlmOutageController, font: Any = None
) -> Optional[str]:
    """Рисует модалку D61 поверх кадра; возвращает действие клика/None.

    font не используется (сигнатура ТЗ §3.2): шрифт локальный (_get_font).
    """
    if pygame is None:  # Law L4: громкий отказ, а не тихая пустота
        raise RuntimeError("pygame недоступен: модалке D61 нужен график")
    state = ctrl.modal_state
    if state is None:
        return None

    sw, sh = screen.get_size()

    # Смена состояния модалки: гасим клик, который её открыл; снимок мира
    # берём один раз — буфер после flip не определён (детерминированный фон)
    if ctrl._modal_drawn_state != state or ctrl._modal_snapshot is None:
        if ctrl._modal_snapshot is None:
            ctrl._modal_snapshot = screen.copy()
        ctrl._modal_drawn_state = state
        ctrl._modal_prev_mouse = True

    screen.blit(ctrl._modal_snapshot, (0, 0))
    overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    overlay.fill((8, 10, 14, 175))  # затемнение: мир под паузой
    screen.blit(overlay, (0, 0))

    box_w, box_h = 620, 340
    box = pygame.Rect((sw - box_w) // 2, (sh - box_h) // 2, box_w, box_h)
    pygame.draw.rect(screen, (24, 26, 34), box, border_radius=8)
    pygame.draw.rect(screen, (146, 118, 62), box, width=2, border_radius=8)

    f_title = _get_font(24, bold=True)
    f_body = _get_font(22)
    f_btn = _get_font(22, bold=True)

    title = f_title.render(_TITLES.get(state, str(state)), True, (232, 226, 206))
    screen.blit(title, title.get_rect(midtop=(box.centerx, box.top + 20)))

    inner_w = box_w - 60
    y = box.top + 64
    reason = (ctrl.modal_reason or "").strip()
    if reason:
        lines = _wrap_px(f_body, reason, inner_w)
        if len(lines) > 4:  # ТЗ §3.2: причина — не более 4 строк
            last = lines[3]
            while f_body.size(last + "...")[0] > inner_w and len(last) > 1:
                last = last[:-1]
            lines = lines[:3] + [last.rstrip() + "..."]
        for ln in lines:
            surf = f_body.render(ln, True, (210, 202, 186))
            screen.blit(surf, surf.get_rect(topleft=(box.left + 30, y)))
            y += 26
        y += 6
    for ln in _wrap_px(f_body, _BODIES.get(state, ""), inner_w):
        surf = f_body.render(ln, True, (178, 184, 196))
        screen.blit(surf, surf.get_rect(topleft=(box.left + 30, y)))
        y += 26

    mouse_pos = pygame.mouse.get_pos()
    btn_rects: "list[tuple[Any, str]]" = []
    bw, bh = 240, 46
    entries = _BUTTONS.get(state, ())
    total = bw * len(entries) + 20 * max(0, len(entries) - 1)
    bx = box.centerx - total // 2
    by = box.bottom - 70
    for label, action in entries:
        rect = pygame.Rect(bx, by, bw, bh)
        hovered = rect.collidepoint(mouse_pos)
        bg = (64, 76, 98) if hovered else (40, 46, 60)
        pygame.draw.rect(screen, bg, rect, border_radius=6)
        pygame.draw.rect(screen, (146, 118, 62), rect, width=1, border_radius=6)
        surf = f_btn.render(label, True, (240, 236, 226))
        screen.blit(surf, surf.get_rect(center=rect.center))
        btn_rects.append((rect, action))
        bx += bw + 20

    pressed = pygame.mouse.get_pressed()
    now_down = bool(pressed[0]) if len(pressed) >= 1 else False
    clicked = now_down and not bool(ctrl._modal_prev_mouse)
    ctrl._modal_prev_mouse = now_down
    if clicked:
        for rect, action in btn_rects:
            if rect.collidepoint(mouse_pos):
                return action
    return None
