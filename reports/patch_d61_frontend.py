# -*- coding: utf-8 -*-
"""scripts/patch_d61_frontend.py — COV-2/D61: применение фронтенд-патчей (v3).

v3 — после ABORT v2 (A4 вне run; риск ТЗ §3.4-4 подтверждён):
  + фолбэк ТЗ §3.4-4: гвард submit через self._llm_ctrl; врезка 1
    присваивает self._llm_ctrl. Безопасность доказывается, не предполагается:
    (1) хозяин A4 — метод с self; (2) run и хозяин A4 — прямые методы одного
    класса (AST identity); (3) ВСЕ call-sites хозяина A4 внутри run после
    врезки 1 (атрибут существует до любого вызова; без getattr-заглушек);
  + пост-вставочный AST-контроль гварда submit;
  + def stop( во frontend — твёрдое требование (exit-путь ТЗ §3.4-5);
  + модалка: снимок экрана при открытии -> детерминированный оверлей.

Запуск из корня: python scripts/patch_d61_frontend.py [--check-only]
Одноразовый: после применения удалить или перенести в reports/.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
P_UI = ROOT / "frontend" / "llm_outage_ui.py"
P_API = ROOT / "frontend" / "api_client.py"
P_GS = ROOT / "frontend" / "game_screen.py"
P_TEST = ROOT / "backend" / "tests" / "micro" / "test_llm_resilience_v1.py"

CHECK_ONLY = "--check-only" in sys.argv


class Abort(Exception):
    """Громкий отказ (Law L4): ничего не записано."""


def req(cond: object, msg: str) -> None:
    if not cond:
        raise Abort(msg)


def dump(lines: list, a: int, b: int, tag: str) -> None:
    print(f"--- DUMP {tag}: строки {a + 1}..{min(b, len(lines) - 1) + 1} ---")
    for k in range(max(0, a), min(len(lines), b + 1)):
        print(f"{k + 1:5d}: {lines[k]}")
    print("--- конец DUMP ---")


def read_text(p: Path) -> "tuple[str, bytes, bool]":
    raw = p.read_bytes()
    bom = b""
    if raw.startswith(b"\xef\xbb\xbf"):  # урок S317: utf-8-sig BOM
        bom = raw[:3]
        raw = raw[3:]
    text = raw.decode("utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")
    return text, bom, crlf


def write_text(p: Path, text: str, bom: bytes, crlf: bool) -> None:
    if crlf:
        text = text.replace("\n", "\r\n")
    p.write_bytes(bom + text.encode("utf-8"))


def innermost(node: ast.AST, line: int, kinds: tuple) -> Optional[ast.AST]:
    best = None
    best_span = None
    for sub in ast.walk(node):
        if isinstance(sub, kinds):
            start = sub.lineno  # type: ignore[attr-defined]
            end = sub.end_lineno or start  # type: ignore[attr-defined]
            if start <= line <= end:
                span = end - start
                if best is None or span < best_span:
                    best, best_span = sub, span
    return best


# =========================================================================
# Компонент A: frontend/llm_outage_ui.py (дословное содержимое нового файла)
# =========================================================================
MODULE_A = '''# -*- coding: utf-8 -*-
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
'''


# =========================================================================
# Тесты T-пауза x3 (дописка в test_llm_resilience_v1.py, ТЗ §3.6)
# =========================================================================
TEST_APPEND = '''# ===========================================================================
# COV-2/D61: T-пауза x3 — фронтенд-контроллер LlmOutageController (ТЗ §3.6)
# ===========================================================================
import os as _os
import sys as _sys
import time as _time

_ROOT_D61 = _os.path.dirname(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
)
_FE_D61 = _os.path.join(_ROOT_D61, "frontend")
if _FE_D61 not in _sys.path:
    _sys.path.append(_FE_D61)  # ТЗ §3.6: sys.path += frontend

from llm_outage_ui import LlmOutageController  # noqa: E402


class _D61CountingGateway:
    """Мок-gateway: программируемый статус + счётчики idle/skip."""

    def __init__(self, status: str = "online", reason: str = "") -> None:
        self.status = status
        self.reason = reason
        self.idle_calls = 0
        self.skip_calls = 0
        self.restart_calls = 0

    def get_llm_outage(self) -> dict:
        return {"status": self.status, "reason": self.reason}

    def restart_llm(self) -> dict:
        self.restart_calls += 1
        return {"restarted": True}

    def idle_tick(self) -> None:
        self.idle_calls += 1

    def skip_time(self) -> None:
        self.skip_calls += 1


def _d61_frame_gates(ctrl: LlmOutageController, gw: _D61CountingGateway) -> None:
    """Мини-реплика гейтов кадра game_screen (врезки 2-3 ТЗ D61).

    Условия скопированы дословно из патча: idle-гейт и skip-гейты обязаны
    молчать при llm_paused. Настоящие гейты в game_screen.py проверяет smoke.
    """
    _skip_time_active = [False]
    _workbench_paused = False
    if (
        not _skip_time_active[0]
        and not _workbench_paused
        and not ctrl.llm_paused
    ):
        gw.idle_tick()
    if not ctrl.llm_paused:
        gw.skip_time()


def test_t_pause_1_outage_immediate_pause_and_gates_silent() -> None:
    """T-пауза 1: доказанный outage -> пауза немедленно; гейты молчат."""
    gw = _D61CountingGateway(status="outage", reason="pool backoff доказан")
    ctrl = LlmOutageController(gw)
    assert ctrl.llm_paused is False
    ctrl._apply_status("outage", "pool backoff доказан")
    assert ctrl.llm_paused is True
    assert ctrl.modal_state == "OUTAGE"
    assert "backoff" in ctrl.modal_reason
    for _ in range(5):
        _d61_frame_gates(ctrl, gw)
    assert gw.idle_calls == 0
    assert gw.skip_calls == 0


def test_t_pause_2_unconfirmed_debounce_two_probes() -> None:
    """T-пауза 2: unconfirmed x1 — без паузы; x2 подряд — пауза; online."""
    gw = _D61CountingGateway(status="unconfirmed", reason="health offline")
    ctrl = LlmOutageController(gw)
    ctrl._apply_status("unconfirmed", "health offline")
    assert ctrl.llm_paused is False
    assert ctrl.modal_state is None
    ctrl._apply_status("unconfirmed", "health offline")
    assert ctrl.llm_paused is True
    assert ctrl.modal_state == "OUTAGE"
    # online НЕ снимает паузу — авто-возобновление запрещено (доктрина №3)
    ctrl._apply_status("online", "")
    assert ctrl.llm_paused is True
    assert ctrl.modal_state == "OUTAGE"
    # сброс счётчика до порога: unconfirmed/online/unconfirmed — без паузы
    ctrl2 = LlmOutageController(gw)
    ctrl2._apply_status("unconfirmed", "x")
    ctrl2._apply_status("online", "")
    ctrl2._apply_status("unconfirmed", "x")
    assert ctrl2.llm_paused is False


def test_t_pause_3_generation_invalidation() -> None:
    """T-пауза 3: confirm_resume меняет поколение — старый результат отбит."""
    gw = _D61CountingGateway(status="online")
    ctrl = LlmOutageController(gw)
    ctrl._apply_status("outage", "r")
    assert ctrl.llm_paused is True
    ctrl.begin_restart()
    assert ctrl.modal_state == "RESTARTING"
    stale_gen = ctrl._gen
    ctrl._restart_result = ({"restarted": True}, stale_gen)
    ctrl.confirm_resume()
    assert ctrl._gen == stale_gen + 1
    assert ctrl.llm_paused is False
    assert ctrl.modal_state is None
    ctrl.poll_restart()  # результат старого поколения обязан быть отброшен
    assert ctrl.modal_state is None
    assert ctrl.llm_paused is False
    # свежее поколение: рестарт применяется и переводит модалку в SUCCESS
    ctrl._apply_status("outage", "r")
    ctrl.begin_restart()
    ctrl.poll_restart()  # запуск воркера restart_llm
    for _ in range(200):
        ctrl.poll_restart()
        if ctrl.modal_state == "SUCCESS":
            break
        _time.sleep(0.01)
    assert ctrl.modal_state == "SUCCESS"
    assert gw.restart_calls == 1
'''


def main() -> int:
    print("=" * 72)
    print("COV-2/D61 фронтенд-патч v3. Режим:",
          "CHECK-ONLY" if CHECK_ONLY else "ПРИМЕНЕНИЕ")
    print("=" * 72)

    # ---------- загрузка + сентинелы чистоты ----------
    req((ROOT / "frontend").is_dir(), f"Корень проекта не найден: {ROOT}")
    for p in (P_API, P_GS, P_TEST):
        req(p.exists(), f"Не найден {p}")
    api_text, api_bom, api_crlf = read_text(P_API)
    gs_text, gs_bom, gs_crlf = read_text(P_GS)
    test_text, test_bom, test_crlf = read_text(P_TEST)

    req(not P_UI.exists(), f"{P_UI} уже существует — патч применён/конфликт.")
    req("def get_llm_outage" not in api_text,
        "api_client.py уже содержит get_llm_outage — патч применён?")
    req("_llm_ctrl" not in gs_text,
        "game_screen.py уже содержит _llm_ctrl — патч применён?")
    req("_d61_" not in gs_text,
        "game_screen.py уже содержит маркеры _d61_ — патч применён?")
    req("test_t_pause_1" not in test_text,
        "Тесты T-пауза уже добавлены — патч применён?")
    print("[ok] Сентинелы чистоты: дерево не содержит следов D61-фронтенда")

    # ---------- якоря A1/A2/A4/A5 (по содержимому, §13.1) ----------
    gs_lines = gs_text.split("\n")
    A1 = "        _gateway, action_queue = create_game_gateway()"
    A2 = "                if not _skip_time_active[0] and not self.workbench_paused:"
    A4 = ("        action_queue.submit(campaign_folder, player_name, "
          "text, px, py, _wx, _wy)")
    A5a = "            # === Poll backend responses ==="
    A5b = "            result = action_queue.poll()"

    def find_one(target: str) -> int:
        hits = [i for i, ln in enumerate(gs_lines) if ln == target]
        req(len(hits) == 1,
            f"Якорь найден {len(hits)} раз (ожидался 1): {target!r}")
        return hits[0]

    i1 = find_one(A1)
    i2 = find_one(A2)
    i4 = find_one(A4)
    i5 = find_one(A5a)
    req(gs_lines[i5 + 1] == A5b,
        "За '# === Poll backend responses ===' не следует "
        "'result = action_queue.poll()' — прочитай файл (§13.1).")
    for label, idx in (("idle", i2), ("submit", i4), ("poll", i5)):
        req(idx > i1, f"Якорь {label} выше создания gateway — неожиданно.")
    req("import pygame" in gs_text, "game_screen.py не импортирует pygame.")
    req(re.search(r"^logger\s*=", gs_text, re.M) is not None
        or "logger.info(" in gs_text,
        "logger в game_screen.py не найден — гварды ТЗ используют logger.info.")
    print(f"[ok] Якоря: A1@{i1 + 1}, A2@{i2 + 1}, A4@{i4 + 1}, A5@{i5 + 1}")

    # ---------- skip-гейты: поиск по ФАКТИЧЕСКОМУ коду ----------
    spawn_idx = [
        i for i, ln in enumerate(gs_lines)
        if "_do_skip_time" in ln and not ln.lstrip().startswith("def ")
    ]
    if len(spawn_idx) != 4:
        dump(gs_lines, 810, 910, "регион skip-клавиш (ожидание x4 сайтов)")
        req(False,
            f"Сайтов _do_skip_time найдено {len(spawn_idx)} (ТЗ: x4). DUMP выше — "
            "пришли дословно: якорь строится только по прочитанному (§13.1).")
    gate_idx: "list[int]" = []
    for sp in spawn_idx:
        gate = None
        for j in range(sp - 1, max(sp - 15, -1), -1):
            if "text_input.focused" in gs_lines[j]:
                t = gs_lines[j].strip()
                if re.match(r"^(if|elif)\s+.+:$", t) and "llm_paused" not in t:
                    gate = j
                break  # ближайшая строка с focused: либо гейт, либо аномалия
        if gate is None:
            dump(gs_lines, sp - 15, sp + 3, f"спавн _do_skip_time @строка {sp + 1}")
        req(gate is not None,
            f"Над спавном _do_skip_time (строка {sp + 1}) нет однострочного "
            "if/elif-гейта с text_input.focused. DUMP выше — пришли дословно.")
        gate_idx.append(gate)
    req(len(set(gate_idx)) == 4,
        "Skip-гейты не уникальны (один if на два спавна?) — нужен DUMP 810-910.")
    print(f"[ok] Skip-гейты x4: строки {sorted(j + 1 for j in gate_idx)}")

    # ---------- ast: функция-хозяин run, цикл, имена ----------
    try:
        gs_tree = ast.parse(gs_text)
    except SyntaxError as e:
        raise Abort(f"game_screen.py не парсится (чужой WIP?): {e}. "
                    "Не чинить — эскалация.")
    host = innermost(gs_tree, i1 + 1, (ast.FunctionDef, ast.AsyncFunctionDef))
    req(host is not None, "Функция-хозяин якоря create_game_gateway не найдена.")
    host_end = host.end_lineno or host.lineno
    for label, idx in ([("A2 idle", i2), ("A5 poll", i5)]
                       + [(f"skip#{k}", g) for k, g in enumerate(gate_idx)]):
        req(host.lineno <= idx + 1 <= host_end,
            f"Якорь {label} (строка {idx + 1}) вне функции {host.name} "
            f"({host.lineno}-{host_end}) — неожиданно, остановись и доложи.")
    loop = innermost(host, i5 + 1, (ast.While,))
    req(loop is not None, "while-цикл вокруг Poll-якоря не найден.")
    loop_end = loop.end_lineno or loop.lineno
    if not (loop.lineno <= i2 + 1 <= loop_end):
        print(f"[!] ВНИМАНИЕ: idle-гейт (строка {i2 + 1}) вне главного цикла "
              f"({loop.lineno}-{loop_end}); гейт llm_paused самодостаточен, "
              "но проверь в smoke.")

    # ---------- A4: хозяин и режим гварда (ТЗ §3.4-4) ----------
    submit_host = innermost(gs_tree, i4 + 1,
                            (ast.FunctionDef, ast.AsyncFunctionDef))
    req(submit_host is not None, "Функция-хозяин A4 не найдена.")
    submit_expr = "_llm_ctrl"  # замыкание (A4 внутри run)
    if submit_host is not host:
        # Фолбэк ТЗ §3.4-4: гвард через self-атрибут. Доказательства:
        dump(gs_lines, submit_host.lineno - 1,
             min(submit_host.lineno + 2, len(gs_lines) - 1),
             f"def {submit_host.name} (хозяин A4)")
        req(submit_host.args.args
            and submit_host.args.args[0].arg == "self",
            f"A4 в '{submit_host.name}' без self — self-фолбэк невозможен. "
            "DUMP выше, пришли дословно.")
        req(host.args.args and host.args.args[0].arg == "self",
            f"{host.name} без self — присвоение self._llm_ctrl невозможно.")

        def classes_directly_owning(tree: ast.AST,
                                    fn: ast.AST) -> "list[ast.ClassDef]":
            return [c for c in ast.walk(tree)
                    if isinstance(c, ast.ClassDef)
                    and any(b is fn for b in c.body)]

        run_classes = classes_directly_owning(gs_tree, host)
        sub_classes = classes_directly_owning(gs_tree, submit_host)
        common = [c for c in run_classes if any(c is s for s in sub_classes)]
        req(len(run_classes) == 1 and len(common) == 1,
            f"run и {submit_host.name} не являются методами одного класса "
            f"(run: {[c.name for c in run_classes]}, "
            f"{submit_host.name}: {[c.name for c in sub_classes]}) — "
            "self в A4 может быть ДРУГИМ объектом. Остановись и доложи.")

        # Все call-sites хозяина A4 — внутри run, после врезки 1:
        # тогда self._llm_ctrl существует до любого вызова (без getattr).
        pat = re.compile(r"\b" + re.escape(submit_host.name) + r"\s*\(")
        sub_end = submit_host.end_lineno or submit_host.lineno
        calls = [k for k, ln in enumerate(gs_lines) if pat.search(ln)]
        calls = [k for k in calls if not (submit_host.lineno <= k + 1 <= sub_end)]
        req(calls,
            f"Вызовы {submit_host.name}(...) в файле не найдены — внешний "
            "вызов не доказуем, self._llm_ctrl может отсутствовать. "
            "Остановись и доложи.")
        bad = [k + 1 for k in calls if not (i1 < k < host_end)]
        req(not bad,
            f"{submit_host.name} вызывается вне run (строки {bad}) — "
            "возможен вызов до создания self._llm_ctrl. Остановись и доложи.")
        submit_expr = "self._llm_ctrl"
        print(f"[ok] ТЗ §3.4-4: A4 в методе {submit_host.name}() класса "
              f"{common[0].name}; вызовы только из run: "
              f"{[k + 1 for k in calls]} -> гвард через self._llm_ctrl")
    else:
        print("[ok] A4 внутри run — гвард через замыкание _llm_ctrl")

    # running: имя из условия while (или None -> выход только return "PAUSE")
    test_node = loop.test
    running_expr: Optional[str] = None
    if isinstance(test_node, ast.Name):
        running_expr = test_node.id
    elif isinstance(test_node, ast.Attribute):
        running_expr = ast.unparse(test_node)
    elif isinstance(test_node, ast.Constant) and test_node.value is True:
        running_expr = None
    else:
        names = sorted({n.id for n in ast.walk(test_node)
                        if isinstance(n, ast.Name)})
        if len(names) == 1:
            running_expr = names[0]
        else:
            dump(gs_lines, loop.lineno - 1, loop.lineno + 2, "условие цикла")
    if running_expr is not None:
        req(re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*",
                running_expr),
            f"Некорректное имя running: {running_expr!r}")
    print(f"[i] Хозяин: {host.name} ({host.lineno}-{host_end}); цикл: "
          f"{loop.lineno}-{loop_end}, условие: {ast.unparse(test_node)}")
    print(f"[i] running -> {running_expr!r}"
          + ("" if running_expr else
             " (выход только return \"PAUSE\" — smoke обязан проверить выход)"))

    # screen: локальное имя или self.screen
    names_in_host = {n.id for n in ast.walk(host) if isinstance(n, ast.Name)}
    if "screen" in names_in_host:
        screen_expr = "screen"
    elif any(isinstance(n, ast.Attribute) and n.attr == "screen"
             for n in ast.walk(host)):
        screen_expr = "self.screen"
    else:
        dump(gs_lines, host.lineno - 1, host.lineno + 25, "начало функции-хозяина")
        raise Abort("В функции-хозяине нет ни 'screen', ни 'self.screen' — "
                    "DUMP выше, пришли дословно (§13.1).")
    print(f"[i] screen -> {screen_expr}")

    # темп кадра модалки: общий clock если есть, иначе pygame.time.wait
    host_src = "\n".join(gs_lines[host.lineno - 1:host_end])
    m_clock = re.search(
        r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)\.tick\(",
        host_src)
    if m_clock and "clock" in m_clock.group(1).lower():
        pace = f"{m_clock.group(1)}.tick(30)  # темп кадра модалки (общий clock)"
    else:
        pace = "pygame.time.wait(15)  # мягкий темп кадра (clock за continue)"
    print(f"[i] pacing -> {pace.strip()}")

    # риск ТЗ §3.4: event.get/poll в цикле ДО точки вставки
    ev_before = [k + 1 for k in range(loop.lineno - 1, i5)
                 if "pygame.event.get(" in gs_lines[k]
                 or "pygame.event.poll(" in gs_lines[k]]
    if ev_before:
        print(f"[!] ВНИМАНИЕ (риск ТЗ §3.4): pygame.event.get/poll в цикле ДО "
              f"точки вставки: {ev_before}. Клик-детект модалки от очереди не "
              "зависит (rising edge), но клики могут протекать в главный "
              "обработчик — проверить в smoke; при утечке — ТЗ-фолбэк "
              "(MOUSEBUTTONDOWN в главном event-loop по флагу modal_state).")
    else:
        print("[ok] event.get/poll в цикле до вставки: нет — дренаж модалки первый")

    # ---------- action_queue.stop(): твёрдое требование (exit-путь ТЗ) ----------
    fe_files = sorted((ROOT / "frontend").glob("*.py"))
    gw_file = None
    stop_hits: "list[str]" = []
    for p in fe_files:
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if gw_file is None and "def create_game_gateway" in t:
            gw_file = p.name
        if "def stop(" in t:
            stop_hits.append(p.name)
    print(f"[i] create_game_gateway -> {gw_file or 'НЕ НАЙДЕН в frontend/*.py'}; "
          f"def stop( в: {stop_hits or 'НИГДЕ'}")
    req(stop_hits,
        "Ни один frontend-модуль не определяет stop() — API очереди неясен, "
        "exit-путь ТЗ §3.4-5 (action_queue.stop()) нельзя собрать вслепую. "
        "Остановись и доложи фактический API очереди.")

    # ---------- api_client: якорь по телу /api/health ----------
    api_lines = api_text.split("\n")
    health_heads = [i for i, ln in enumerate(api_lines)
                    if ln.strip() == "def health(self) -> dict:"]
    anchor_idx = [h for h in health_heads
                  if h + 1 < len(api_lines)
                  and api_lines[h + 1].strip()
                  == 'return self._t.get("/api/health")']
    if len(anchor_idx) != 1:
        for h in health_heads:
            dump(api_lines, h, min(h + 3, len(api_lines) - 1),
                 f"health @строка {h + 1}")
        req(False,
            f"Якорь health (с телом /api/health) найден {len(anchor_idx)} раз "
            "(ожидался 1). DUMP выше — пришли дословно.")
    h0 = anchor_idx[0]
    req(api_lines[h0] == "    def health(self) -> dict:"
        and api_lines[h0 + 1] == '        return self._t.get("/api/health")',
        "Неожиданный отступ якоря health — прочитай файл (§13.1).")
    api_anchor = api_lines[h0] + "\n" + api_lines[h0 + 1]
    m = re.search(r"def post\(self[^)]*\)", api_text)
    req(m is not None, "api_client.py: не найден def post(self, ...).")
    inner = m.group(0)
    args = [a.strip() for a in
            inner[inner.index("(") + 1:-1].split(",") if a.strip()]
    req(len(args) >= 3,
        f"post() принимает {len(args)} аргумента ({args}); вставка ТЗ требует "
        "post(path, {{}}) — прочитай сигнатуру и адаптируй.")
    print(f"[ok] api_client: якорь health@{h0 + 1}; post{args}")

    # ---------- сборка новых текстов ----------
    # 1) skip-гейты (по строкам, по убыванию)
    for j in sorted(gate_idx, reverse=True):
        old = gs_lines[j]
        indent = old[: len(old) - len(old.lstrip())]
        m_gate = re.match(r"^(if|elif)\s+(.+):$", old.strip())
        req(m_gate is not None, f"Неожиданная форма гейта: {old!r}")
        kw, body = m_gate.group(1), m_gate.group(2)
        gs_lines[j:j + 1] = [
            indent + kw + " (",
            indent + "    " + body,
            indent + "    and not _llm_ctrl.llm_paused  # COV-2/D61",
            indent + "):",
        ]
    new_gs = "\n".join(gs_lines)
    if gs_text.endswith("\n"):
        new_gs += "\n"

    # 2) врезка 1 + старт-гейт D (+ self-фолбэк §3.4-4)
    self_line = ""
    if submit_expr == "self._llm_ctrl":
        self_line = ("        self._llm_ctrl = _llm_ctrl"
                     f"  # ТЗ §3.4-4: гвард submit в {submit_host.name}\n")
    INS1 = (
        A1 + "\n"
        "        # COV-2/D61: фронтенд-контур обязательной LLM (ветка Б)\n"
        "        from llm_outage_ui import LlmOutageController, draw_outage_modal\n"
        "        _llm_ctrl = LlmOutageController(_gateway)\n"
        + self_line +
        "        _llm_ctrl.start()\n"
        "        # Старт-гейт (ТЗ §3.5): мир не стартует при доказанном отказе;\n"
        "        # unconfirmed на старте — без модалки, watcher доберёт пробой 2\n"
        "        try:\n"
        "            _d61_out = _gateway.get_llm_outage()\n"
        "        except Exception as _d61_exc:\n"
        "            logger.info(\"[D61] старт-гейт: бэкенд недоступен (%s)\", _d61_exc)\n"
        "            _d61_out = None\n"
        "        _d61_status = (_d61_out or {}).get(\"status\")\n"
        "        if _d61_status in (\"outage\", \"unconfirmed\"):\n"
        "            _llm_ctrl._apply_status(\n"
        "                _d61_status, (_d61_out or {}).get(\"reason\", \"\")\n"
        "            )"
    )
    new_gs = new_gs.replace(A1, INS1, 1)

    # 3) врезка 2 (idle-гейт)
    INS2 = (
        "                if (\n"
        "                    not _skip_time_active[0]\n"
        "                    and not self.workbench_paused\n"
        "                    and not _llm_ctrl.llm_paused  # COV-2/D61: мир стоит\n"
        "                ):"
    )
    new_gs = new_gs.replace(A2, INS2, 1)

    # 4) врезка 4 (гвард submit; expr = замыкание ИЛИ self-фолбэк §3.4-4)
    INS4 = (
        f"        if {submit_expr}.llm_paused:  # COV-2/D61: без LLM запрещено\n"
        "            logger.info(\"[D61] действие отклонено: LLM-пауза\")\n"
        "            return\n" + A4
    )
    new_gs = new_gs.replace(A4, INS4, 1)

    # 5) врезка 5 (модалка; running/screen — только вычисленные имена)
    run_line = (f"                    {running_expr} = False\n"
                if running_expr else "")
    INS5 = (
        "            # === COV-2/D61: модалка LLM-отказа (поглощает кадр) ===\n"
        "            if _llm_ctrl.modal_state is not None:\n"
        "                if _llm_ctrl.modal_state == \"RESTARTING\":\n"
        "                    _llm_ctrl.poll_restart()\n"
        "                # Модалка владеет кадром: дренаж событий; QUIT не глотаем\n"
        "                _d61_quit = False\n"
        "                for _d61_ev in pygame.event.get():\n"
        "                    if _d61_ev.type == pygame.QUIT:\n"
        "                        _d61_quit = True\n"
        "                        break\n"
        "                if _d61_quit:\n"
        "                    _d61_act = \"exit\"\n"
        "                else:\n"
        f"                    _d61_act = draw_outage_modal({screen_expr}, _llm_ctrl, None)\n"
        "                if _d61_act == \"restart\":\n"
        "                    _llm_ctrl.begin_restart()\n"
        "                elif _d61_act == \"resume\":\n"
        "                    _llm_ctrl.confirm_resume()\n"
        "                elif _d61_act == \"exit\":\n"
        "                    _llm_ctrl.stop()\n"
        "                    action_queue.stop()\n"
        f"{run_line}"
        "                    return \"PAUSE\"\n"
        "                pygame.display.flip()\n"
        f"                {pace}\n"
        "                continue\n"
        + A5a + "\n" + A5b
    )
    new_gs = new_gs.replace(A5a + "\n" + A5b, INS5, 1)

    # 6) api_client
    API_INS = (
        "\n\n    def get_llm_outage(self) -> dict:\n"
        "        \"\"\"COV-2/D61: статус LLM-контура бэкенда.\n\n"
        "        {\"status\": \"outage\"|\"unconfirmed\"|\"online\", \"reason\": str}:\n"
        "        доказанный outage (pool backoff) — пауза фронта немедленно;\n"
        "        unconfirmed (health offline, чистый пул) — дебаунс 2 проб.\n"
        "        \"\"\"\n"
        "        return self._t.get(\"/api/llm/outage\")\n\n"
        "    def restart_llm(self) -> dict:\n"
        "        \"\"\"COV-2/D61: перезапуск llama-server (прод-роут lifecycle).\"\"\"\n"
        "        return self._t.post(\"/api/llm/restart\", {})"
    )
    new_api = api_text.replace(api_anchor, api_anchor + API_INS, 1)

    # 7) тесты
    new_test = test_text.rstrip("\n") + "\n\n\n" + TEST_APPEND.strip("\n") + "\n"

    # ---------- стражи write-пути ----------
    req("{running}" not in new_gs and "{screen}" not in new_gs,
        "Утечка плейсхолдеров {running}/{screen} — запись отменена (инцидент v1).")
    try:
        new_tree = ast.parse(new_gs)
    except SyntaxError as e:
        raise Abort(f"Новый game_screen.py не парсится (запись отменена): {e}")
    call_line = None
    for i, ln in enumerate(new_gs.split("\n")):
        if "draw_outage_modal(" in ln and "import" not in ln:
            call_line = i + 1
            break
    req(call_line is not None, "Вызов draw_outage_modal не найден в новом тексте.")
    new_host = innermost(new_tree, call_line, (ast.FunctionDef, ast.AsyncFunctionDef))
    new_loop = innermost(new_tree, call_line, (ast.While,))
    req(new_host is not None and new_loop is not None,
        "Модалка оказалась вне while-цикла функции-хозяина — структура неожиданна.")
    print(f"[ok] AST-контроль: модалка внутри while "
          f"({new_loop.lineno}-{new_loop.end_lineno}) в {new_host.name}")
    if submit_expr == "self._llm_ctrl":
        guard_line = None
        for i, ln in enumerate(new_gs.split("\n")):
            if "self._llm_ctrl.llm_paused" in ln:
                guard_line = i + 1
                break
        req(guard_line is not None, "Гвард submit не найден в новом тексте.")
        g_host = innermost(new_tree, guard_line,
                           (ast.FunctionDef, ast.AsyncFunctionDef))
        req(g_host is not None and g_host.name == submit_host.name,
            f"Гвард submit оказался в "
            f"{g_host.name if g_host else None}, ожидался {submit_host.name}.")
        print(f"[ok] AST-контроль: гвард submit внутри {g_host.name}")

    for name, src in (
        ("frontend/llm_outage_ui.py", MODULE_A),
        ("frontend/api_client.py", new_api),
        ("frontend/game_screen.py", new_gs),
        ("backend/tests/micro/test_llm_resilience_v1.py", new_test),
    ):
        try:
            compile(src, name, "exec")
        except SyntaxError as e:
            raise Abort(f"Компиляция {name} не прошла (запись отменена): {e}")
    print("[ok] Компиляция всех четырёх текстов в памяти: GREEN")

    if CHECK_ONLY:
        print("\nCHECK-ONLY: запись пропущена. Все проверки пройдены.")
        return 0

    # ---------- запись ----------
    write_text(P_UI, MODULE_A, b"", False)
    write_text(P_API, new_api, api_bom, api_crlf)
    write_text(P_GS, new_gs, gs_bom, gs_crlf)
    write_text(P_TEST, new_test, test_bom, test_crlf)
    print("[ok] Записано: llm_outage_ui.py (новый), api_client.py, "
          "game_screen.py, test_llm_resilience_v1.py")

    # ---------- пост-сентинелы (перечитывание с диска) ----------
    gs_chk = read_text(P_GS)[0]
    api_chk = read_text(P_API)[0]
    test_chk = read_text(P_TEST)[0]
    ui_chk = read_text(P_UI)[0]
    req(gs_chk.count("and not _llm_ctrl.llm_paused") == 5,
        "Пост-сентинел: 'and not _llm_ctrl.llm_paused' != 5")
    req(gs_chk.count("_llm_ctrl.llm_paused") == 6,
        "Пост-сентинел: '_llm_ctrl.llm_paused' != 6")
    req(gs_chk.count("draw_outage_modal(") == 1, "Пост-сентинел: вызов модалки != 1")
    req(gs_chk.count("LlmOutageController(") == 1, "Пост-сентинел: контроллер != 1")
    req("{running}" not in gs_chk and "{screen}" not in gs_chk,
        "Пост-сентинел: плейсхолдеры на диске — откат и разбор.")
    if submit_expr == "self._llm_ctrl":
        req(gs_chk.count("self._llm_ctrl = _llm_ctrl") == 1,
            "Пост-сентинел: self-присвоение != 1")
        req(gs_chk.count("self._llm_ctrl.llm_paused") == 1,
            "Пост-сентинел: self-гвард != 1")
    req(api_chk.count("def get_llm_outage") == 1
        and api_chk.count("def restart_llm") == 1, "Пост-сентинел: api-методы")
    req(test_chk.count("def test_t_pause_") == 3, "Пост-сентинел: T-пауза != 3")
    req("class LlmOutageController" in ui_chk
        and "def draw_outage_modal" in ui_chk, "Пост-сентинел: ui-модуль")
    print("[ok] Пост-сентинелы: гейты/модалка/тесты на месте")

    print(
        "\nПатч применён. Далее (ТЗ §3.8, порядок НЕИЗМЕНЕН):\n"
        "  ruff check --no-fix frontend/llm_outage_ui.py "
        "frontend/game_screen.py frontend/api_client.py\n"
        "  python -m compileall frontend\n"
        "  python -c \"import sys; sys.path.insert(0, 'frontend'); "
        "import llm_outage_ui; print('import ok')\"\n"
        "  cd backend ; python -m pytest tests/micro/"
        "test_llm_resilience_v1.py -q ; cd ..\n"
        "  python scripts/lint_flags.py\n"
        "  python backend/tests/IPT.py 2>&1 | Select-Object -Last 6\n"
        "Скрипт одноразовый: после коммита удалить или перенести в reports/."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Abort as e:
        print(f"\n[ABORT] {e}\nНичего не записано. §13.1: DUMP выше — пришли "
              "дословно, якорь будет уточнён.",
              file=sys.stderr)
        sys.exit(2)
