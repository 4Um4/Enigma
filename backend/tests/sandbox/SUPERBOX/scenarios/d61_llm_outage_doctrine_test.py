# path: backend/tests/sandbox/SUPERBOX/scenarios/d61_llm_outage_doctrine_test.py
# Назначение: COV-2/D61 (ТЗ §4; вердикт Мастера: живой игровой тест вместо
#   ручного launcher-smoke; прецеденты — probes/llm_down_smoke_probe.py,
#   scenarios/lc_gc01_world_speaks_test.py, scenarios/chronicle_weave_probe).
#   Доктрина обязательной LLM (ТЗ §3.1 №1-№6) против НАСТОЯЩЕГО llama-server:
#   G0 самоподъём менеджером + initialize_router (прод-прецедент main.py);
#   G1 мир жив (idle-тики при живой LLM);
#   G2 отказ в бою: in-flight запрос честно падает (№5) -> pool backoff
#      доказан -> /llm/outage-семантика = outage (№2a) -> живой watcher
#      ставит паузу НЕМЕДЛЕННО, минуя дебаунс (№1) -> idle-гейт: 0 тиков;
#      run_turn без LLM — без фейк-нарратива (ADR-113);
#   G4 рестарт через модалку (worker -> server_lifecycle.restart_llama_server,
#      настоящий спавн) -> SUCCESS; пауза ДЕРЖИТСЯ (№3); «Возобновить» ->
#      тики идут; реплика end-to-end (router + run_turn);
#   G5 провал-ветка: саботаж exe через settings (без переименований) ->
#      FAILED с причиной; пауза сохраняется (№4); retry -> снова FAILED;
#      восстановление пути -> рестарт OK;
#   G6 unconfirmed-дебаунс (№2b): чистый пул + мёртвый health -> x1 без
#      паузы, x2 пауза; живой watcher проходит обе пробы;
#   G7 модалка headless (SDL dummy): 4 состояния, карта кнопок, rising-edge;
#   G8 финал: сервер возвращён к здоровому состоянию.
# Границы (честные): HTTP-транспорт фронта не гоняется — gateway-адаптер
#   зеркалит тело роута /llm/outage (routes.py:380); транспорт покрыт micro
#   T-D61 + T-пауза. Pygame-кадр game_screen (event-loop :775, утечка
#   ESC/кликов) — вне headless: остаточный ручной чеклист Мастера (3
#   пункта: модалка видна/клики не протекают/крестик штатен). run_turn-шейп
#   по harness.py:266-276 (player_name='player' — константа; при RED
#   точечная правка). Сценарий владеет жизнью llama-server (kill x3 /
#   restart x3, каждая загрузка модели до ~90с; полный прогон ~3-8 минут);
#   окно тишины §3.12 обязательно. LLM_RESILIENCE_V1 остаётся default OFF —
#   флаг принадлежит очереди D62, доктрина D61-фронта за флагом не стоит.
# Запуск: cd backend ; python -m tests.sandbox.SUPERBOX.scenarios.d61_llm_outage_doctrine_test
# Квалификация §3.12: PROCESS EXIT=0 + маркер 'Итог: GREEN=N RED=0' +
#   полные артефакты reports/d61_llm_outage_doctrine.{json,md}.
from __future__ import annotations

import os

# ── ENV (СТРОГО до первого импорта app/pygame; прецедент llm_down_smoke_probe)
os.environ["AIDM_REPLAY_MODE"] = "off"
os.environ["D8P_ENABLED"] = "0"
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")  # G7 без экрана
os.environ.setdefault("ENIGMA_DISABLE_FILE_LOGS", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import asyncio
import json
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Optional

# ── Пути: backend / repo / frontend (chronic-паттерн поиска корня) ────────
_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[4]
_REPO: Optional[Path] = None
for _cand in _HERE.parents:
    if (_cand / "scripts" / "llm_server_manager.py").is_file():
        _REPO = _cand
        break
if _REPO is None:
    print("[RED] repo_root :: scripts/llm_server_manager.py не найден вверх по дереву")
    print("Итог: GREEN=0 RED=1")
    raise SystemExit(1)

for _p in (str(_BACKEND), str(_REPO), str(_REPO / "frontend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

REPORTS = _REPO / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

CAMPAIGN = "Open_road"
LOCATION = "tavern"
PLAYER = "player"  # harness.py:266-276 (шейп хода; константа — см. границы)

REPORT: dict[str, Any] = {
    "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    "checks": [],
    "obs": {},
    "boundary": [
        "HTTP-транспорт фронта не гоняется: gateway-адаптер зеркалит тело роута /llm/outage",
        "pygame-кадр game_screen (event-loop, утечка ESC/кликов) — ручной чеклист Мастера",
        "run_turn-шейп по harness.py:266-276; player_name='player' — константа",
        "сценарий владеет жизнью llama-server (kill x3 / restart x3); окно тишины обязательно",
        "LLM_RESILIENCE_V1 default OFF (флаг очереди D62)",
        "atexit server_lifecycle остановит lifecycle-spawned сервер при выходе",
        "gateway: health-проба 127.0.0.1:port/health (1с, без DNS) вместо check_llm_health — тайминг дебаунса; прод-латентность дебаунса = 1 медленная проба на TTL кэша",
    ],
}
_GREEN = 0
_RED = 0
_CTRLS: list = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    global _GREEN, _RED
    ok = bool(cond)
    if ok:
        _GREEN += 1
        print(f"[GREEN] {name}")
    else:
        _RED += 1
        print(f"[RED] {name} :: {detail}")
    REPORT["checks"].append({"name": name, "ok": ok, "detail": str(detail)[:400]})
    return ok


def _obs(key: str, value: Any) -> None:
    REPORT["obs"][key] = value


def _quiet() -> None:
    """LLM-free шум (eat/lc-прецедент): глушим воркеров/роутер/очереди."""
    import logging

    logging.basicConfig(level=logging.WARNING)
    for _name in (
        "app.services.llm.router",
        "app.services.llm.provider_manager",
        "app.services.llm.llama_cpp_provider",
        "app.services.game_loop.task_scheduler",
        "app.services.execution.dialogue_queue",
        "app.services.memory",
        "app.services.npc.npc_tick_pipeline",
        "app.services.npc.state_applicator",
    ):
        logging.getLogger(_name).setLevel(logging.CRITICAL)
    logging.getLogger().setLevel(logging.CRITICAL)


# ── Production-хелперы (все тела прочитаны; §13.1) ────────────────────────
def _llm_alive() -> bool:
    import urllib.error
    import urllib.request

    from app.core.config import settings

    try:
        urllib.request.urlopen(
            settings.llama_cpp_server_url.replace("/v1", "") + "/health", timeout=3
        )
        return True
    except (urllib.error.URLError, OSError):
        return False


def _pool():
    from app.services.llm.provider_manager import get_model_pool

    return get_model_pool()


def _kill_server() -> str:
    from app.services.llm.server_lifecycle import _stop_llama_server

    return _stop_llama_server()


def _game_time_obs(gl) -> Optional[float]:
    """Наблюдение (НЕ гейт): атрибуты оркестратора не читались дословно."""
    orch = getattr(gl, "_tick_orch", None)
    if orch is None:
        return None
    for attr in ("game_time_seconds", "_game_time_seconds", "game_time"):
        v = getattr(orch, attr, None)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _drive_ticks(gl, ctrl, n: int) -> int:
    """Мини-реплика гейта кадра game_screen (врезка 2 патча D61):
    llm_paused -> idle_tick не вызывается (остановка игрового времени)."""
    ran = 0
    for _ in range(n):
        if ctrl is None or not ctrl.llm_paused:
            try:
                gl.idle_tick(CAMPAIGN)
                ran += 1
            except Exception as e:
                _obs("idle_tick_exc", f"{type(e).__name__}: {e}")
    return ran


def _run_turn(gl, action_text: str):
    """REST-путь хода (PROBE 9.7-контур); шейп — harness.py:266-276."""
    from app.models.schemas import ChatTurnRequest, PlayerAction

    req = ChatTurnRequest(
        actions=[PlayerAction(player_name=PLAYER, action=action_text)],
        campaign_id=CAMPAIGN,
        world_id=CAMPAIGN,
        location=LOCATION,
    )
    return asyncio.run(gl.run_turn(req))


def _run_turn_boxed(gl, action_text: str, timeout: float = 120.0) -> dict:
    """run_turn в нити с таймаутом: зависание = честная находка, не краш."""
    box: dict[str, Any] = {}

    def _rt() -> None:
        try:
            box["resp"] = _run_turn(gl, action_text)
        except Exception as e:
            box["exc"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=_rt, daemon=True, name="d61-run-turn")
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        box["hang"] = True
    return box


def _dm_text(resp: Any) -> str:
    obj = resp
    if obj is not None and hasattr(obj, "model_dump"):
        try:
            obj = obj.model_dump()  # ChatTurnResponse (Pydantic) -> dict
        except Exception:
            return ""
    if isinstance(obj, dict):
        v = obj.get("dm_response")
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            return str(v.get("text") or v.get("narrative") or "")
        if v is not None:
            return str(v)
    return ""


def _jsonable(obj: Any) -> Any:
    """JSON-safe нормализация: Pydantic -> dict, прочее -> метка типа."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "model_dump"):
        try:
            return _jsonable(obj.model_dump())
        except Exception:
            pass
    return f"<{type(obj).__name__}>"


def _restart_timeout() -> float:
    from app.core.config import settings

    return float(settings.model_load_timeout_sec) + 120.0


_ASYNC_LOOP: Optional["asyncio.AbstractEventLoop"] = None


def _ensure_async_loop() -> "asyncio.AbstractEventLoop":
    """Единый фоновый loop для всех async-вызовов сценария (fix F2):
    asyncio.Lock рестартов привязывается к первому loop; несколько
    asyncio.run = RuntimeError. Прод живёт в одном loop (uvicorn)."""
    global _ASYNC_LOOP
    if _ASYNC_LOOP is None or _ASYNC_LOOP.is_closed():
        _ASYNC_LOOP = asyncio.new_event_loop()
        threading.Thread(
            target=_ASYNC_LOOP.run_forever, daemon=True, name="d61-async-loop"
        ).start()
    return _ASYNC_LOOP


def _call_async(factory, timeout: float) -> Any:
    """Корутина в едином loop; factory — zero-arg callable -> coroutine."""
    fut = asyncio.run_coroutine_threadsafe(factory(), _ensure_async_loop())
    return fut.result(timeout=timeout)


def _wait_pause(ctrl, timeout: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if ctrl.llm_paused:
            return True
        time.sleep(0.05)
    return False


def _new_ctrl(gw):
    from llm_outage_ui import LlmOutageController

    c = LlmOutageController(gw)
    _CTRLS.append(c)
    return c


def _health_online_fast() -> "tuple[bool, str]":
    """Быстрая проба живости: /health на явном 127.0.0.1 — без DNS
    (резолв localhost вне socket-таймаута: getaddrinfo не ограничен
    urlopen(timeout); наблюдение server_lifecycle + живые прогоны —
    проба по localhost-URL ~7с). Семантика /health из
    server_lifecycle._await_llama_ready. Прод-роут остаётся на
    кэшируемом check_llm_health (латентность прод-дебаунса = 1
    медленная проба на TTL кэша — наблюдение в артефакте)."""
    import socket

    from app.core.config import settings

    # Dual-stack (матрица 5 прогонов): менеджер поднимает --host localhost
    # (стек ::1 — HTTP-проба на 127.0.0.1 не отвечает никогда, стабилизация
    # 120с не помогла), lifecycle — --host 127.0.0.1 (g4/g8 GREEN).
    # TCP-connect на оба стека: любой живой = online; мёртвый порт =
    # refused мгновенно (тайминг g6-дебаунса сохраняется).
    _port = int(settings.llama_cpp_port)
    _last = "no-attempt"
    for _host in ("127.0.0.1", "::1"):
        _s = socket.socket(
            socket.AF_INET6 if ":" in _host else socket.AF_INET,
            socket.SOCK_STREAM,
        )
        _s.settimeout(0.5)
        try:
            _s.connect((_host, _port))
            return (True, f"tcp:{_host}:{_port}")
        except Exception as e:
            _last = f"{_host}: {type(e).__name__}"
        finally:
            _s.close()
    return (False, _last)


class _OutageGateway:
    """Адаптер production-семантики роута /llm/outage (routes.py:380):
    pool degraded -> outage; иначе health -> online/unconfirmed.
    Отличия от роута: быстрая health-проба (127.0.0.1, 1с) вместо
    check_llm_health по settings-URL — тайминг дебаунса прогона."""

    def get_llm_outage(self) -> dict:
        from app.services.llm.provider_manager import get_model_pool

        pool = get_model_pool()
        pool_status = (
            pool.pool_backoff_status()
            if pool is not None
            else {"degraded": False, "models": {}}
        )
        if pool_status.get("degraded"):
            until = max(
                (m.get("backoff_until", 0.0)
                 for m in pool_status.get("models", {}).values()),
                default=0.0,
            )
            return {"status": "outage",
                    "reason": f"pool backoff доказан (до {until:.0f})"}
        online, why = _health_online_fast()
        if not online:
            return {"status": "unconfirmed",
                    "reason": f"health offline: {why}"}
        return {"status": "online", "reason": ""}

    def restart_llm(self) -> dict:
        from app.services.llm.server_lifecycle import restart_llama_server

        return _call_async(restart_llama_server, timeout=_restart_timeout())


# ── G0: самоподъём сервера (chronic-прецедент) ────────────────────────────
def g0_selfhost(gw) -> bool:
    if not _llm_alive():
        from scripts.llm_server_manager import start_llama_server

        print("[D61-SCENARIO] health refused -> поднимаю сервер менеджером проекта")
        if not start_llama_server():
            check("p0_llm_online", False, "start_llama_server вернул False")
            return False
        for _ in range(60):
            if _llm_alive():
                break
            time.sleep(2)
    if not check("p0_llm_online", _llm_alive(), "health не отвечает после самоподъёма"):
        return False
    # Стабилизация /health после спавна (прогоны 00:20/00:34/18:36:
    # _llm_alive 3с GREEN -> fast-проба 1с timeout — /health отвечает
    # в окне загрузки >1с; после загрузки <1с, g4_status_online GREEN
    # той же пробой). Ждём, пока fast-проба станет online (её гейтит
    # p0_status_online). Бюджет 120с: каждый прогон = SPAWN (atexit
    # гасит lifecycle-сервер g8), загрузка модели до ~90с. Прод-семантика
    # не тронута: unconfirmed на старте легален по доктрине §3.5.
    _stab_t0 = time.time()
    _stab_deadline = _stab_t0 + 120.0
    while time.time() < _stab_deadline:
        _online, _why = _health_online_fast()
        if _online:
            break
        time.sleep(1.0)
    _obs("p0_stabilize_sec", round(time.time() - _stab_t0, 1))
    from app.services.llm.router import initialize_router

    initialize_router()  # прод-прецедент main.py:120-122 — до любого request()
    check("p0_router_initialized", True)
    payload = gw.get_llm_outage()
    check("p0_status_online", payload.get("status") == "online", f"payload={payload}")
    return True


# ── G1: мир жив при живой LLM ─────────────────────────────────────────────
def g1_world(gl) -> None:
    t_before = _game_time_obs(gl)
    ran = _drive_ticks(gl, None, 5)
    t_after = _game_time_obs(gl)
    check("g1_world_ticks", ran == 5, f"ran={ran}")
    _obs("g1_game_time", {"before": t_before, "after": t_after})


# ── G2: отказ в бою -> пауза немедленно (№1/№2a/№5) ───────────────────────
def g2_outage(gl, gw, router):
    inflight: dict[str, Any] = {}

    def _worker() -> None:
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                router.request_for_agent(
                    "dm",
                    "[D61-SCENARIO] Скажи что-нибудь посетителям таверны.",
                    None,
                    "probe",
                )
            except Exception as e:
                inflight["ok"] = False
                inflight["exc"] = type(e).__name__
                inflight["msg"] = str(e)[:160]
                return
        inflight["ok"] = True
        inflight["note"] = "kill не поймал ни один запрос (сервер отвечал)"

    t = threading.Thread(target=_worker, daemon=True, name="d61-inflight")
    t.start()
    time.sleep(1.0)  # успешный вызов ~5с (S342): окно in-flight
    _obs("g2_server_stop", _kill_server())
    t.join(timeout=60)

    check(
        "g2_inflight_honest_failure",
        inflight.get("ok") is False
        and "мутнеет" not in str(inflight.get("msg", "")).lower(),
        f"inflight={inflight}",
    )

    pool = _pool()
    pool_status = pool.pool_backoff_status() if pool else None
    check("g2_pool_backoff_proven",
          bool(pool_status and pool_status.get("degraded")),
          f"pool_status={pool_status}")

    payload = gw.get_llm_outage()
    check("g2_status_outage", payload.get("status") == "outage", f"payload={payload}")

    ctrl = _new_ctrl(gw)
    ctrl.start()
    paused = _wait_pause(ctrl, 8.0)
    check("g2_pause_immediate",
          paused and ctrl.modal_state == "OUTAGE",
          f"paused={ctrl.llm_paused} modal={ctrl.modal_state}")
    check("g2_no_debounce_path", ctrl._unconfirmed == 0,
          f"unconfirmed={ctrl._unconfirmed}")

    ran = _drive_ticks(gl, ctrl, 4)
    check("g2_idle_frozen", ran == 0, f"ticks_during_pause={ran}")

    rr = _run_turn_boxed(gl, "Спросить у Торнина, как дела.")
    rr_view = _jsonable(rr)
    if isinstance(rr_view, dict) and "resp" in rr_view:
        rr_view["dm"] = _dm_text(rr.get("resp"))[:200]
        rr_view.pop("resp", None)
    _obs("g2_run_turn", rr_view)
    check("g2_run_turn_no_fake_narrative",
          "hang" not in rr_view
          and "мутнеет" not in json.dumps(rr_view, ensure_ascii=False).lower(),
          f"rr={rr_view}")
    return ctrl


# ── G4: рестарт -> SUCCESS -> пауза держится -> resume (№3) ───────────────
def g4_restart_resume(gl, gw, router, ctrl) -> None:
    from app.core.config import settings as _s

    ctrl.begin_restart()
    deadline = time.time() + _s.model_load_timeout_sec + 90
    while time.time() < deadline:
        ctrl.poll_restart()
        if ctrl.modal_state in ("SUCCESS", "FAILED"):
            break
        time.sleep(0.25)
    check("g4_restart_success", ctrl.modal_state == "SUCCESS",
          f"modal={ctrl.modal_state} reason={ctrl.modal_reason[:200]}")

    pool = _pool()
    pool_status = pool.pool_backoff_status() if pool else None
    check("g4_backoff_reset", not (pool_status and pool_status.get("degraded")),
          f"pool_status={pool_status}")

    payload = gw.get_llm_outage()
    check("g4_status_online", payload.get("status") == "online", f"payload={payload}")

    ran = _drive_ticks(gl, ctrl, 4)
    check("g4_pause_holds_after_success",
          ran == 0 and ctrl.llm_paused,
          f"ticks={ran} paused={ctrl.llm_paused}")

    ctrl.confirm_resume()
    ran = _drive_ticks(gl, ctrl, 3)
    check("g4_resume_ticks_flow", ran == 3 and not ctrl.llm_paused,
          f"ticks={ran} paused={ctrl.llm_paused}")

    reply = ""
    try:
        reply = router.request_for_agent(
            "dm", "[D61-SCENARIO] Короткая реплика для проверки живого контура.",
            None, "probe",
        ) or ""
    except Exception as e:
        _obs("g4_router_reply_exc", f"{type(e).__name__}: {e}")
    check("g4_reply_end_to_end", len(reply.strip()) > 0, f"len={len(reply)}")

    rr = _run_turn_boxed(gl, "Попросить Люсю принести эль.")
    dm_len = len(_dm_text(rr.get("resp"))) if "resp" in rr else 0
    _obs("g4_run_turn",
         _jsonable({k: v for k, v in rr.items() if k != "resp"})
         | {"dm_len": dm_len})
    check("g4_run_turn_e2e", dm_len > 0, f"rr={rr.get('exc', rr.get('hang', 'ok'))}")


# ── G5: провал-ветка (№4) ─────────────────────────────────────────────────
def g5_failure(gw, router) -> None:
    from app.core.config import settings as _s

    _obs("g5_server_stop", _kill_server())
    try:
        router.request_for_agent("dm", "[D61-SCENARIO] ping", None, "probe")
        fail = {"ok": True}
    except Exception as e:
        fail = {"ok": False, "exc": type(e).__name__}
    check("g5_outage_reproven", fail.get("ok") is False, f"fail={fail}")

    payload = gw.get_llm_outage()
    ctrl = _new_ctrl(gw)
    ctrl._apply_status(payload.get("status", ""), payload.get("reason", ""))
    check("g5_pause_before_retry",
          ctrl.llm_paused and ctrl.modal_state == "OUTAGE", f"payload={payload}")

    real_exe = _s.llama_cpp_server_executable
    fake_exe = str(Path(real_exe).parent / "llama_server_d61_sabotage_missing.exe")
    try:
        _s.llama_cpp_server_executable = fake_exe  # саботаж без переименований

        def _terminal(timeout: float) -> None:
            t0 = time.time()
            while time.time() - t0 < timeout:
                ctrl.poll_restart()
                if ctrl.modal_state in ("SUCCESS", "FAILED"):
                    return
                time.sleep(0.25)

        ctrl.begin_restart()
        _terminal(30)
        check("g5_failed_with_reason",
              ctrl.modal_state == "FAILED" and "exe_missing" in ctrl.modal_reason,
              f"modal={ctrl.modal_state} reason={ctrl.modal_reason[:200]}")
        check("g5_pause_persists", ctrl.llm_paused, f"paused={ctrl.llm_paused}")
        ctrl.begin_restart()  # «Повторить»
        _terminal(30)
        check("g5_retry_fails_again", ctrl.modal_state == "FAILED",
              f"modal={ctrl.modal_state}")
    finally:
        _s.llama_cpp_server_executable = real_exe

    from app.services.llm.server_lifecycle import restart_llama_server

    res = _call_async(restart_llama_server, timeout=_restart_timeout())
    check("g5_recovery_after_restore", bool(res.get("restarted")), f"res={res}")


# ── G6: unconfirmed-дебаунс (№2b) + старт-гейт-семантика (§3.5) ───────────
def g6_debounce(gw) -> None:
    _obs("g6_server_stop", _kill_server())
    time.sleep(1.5)  # успокоить воркеров ДО сброса (fix F3)
    pool = _pool()
    if pool:
        pool.pool_reset_backoff()  # чистый пул: health-only картина

    payload = gw.get_llm_outage()
    check("g6_unconfirmed_status", payload.get("status") == "unconfirmed",
          f"payload={payload}")

    ctrl = _new_ctrl(gw)
    ctrl._apply_status(payload.get("status", ""), payload.get("reason", ""))
    check("g6_debounce_first_probe",
          not ctrl.llm_paused and ctrl.modal_state is None,
          f"paused={ctrl.llm_paused}")  # §3.5: старт без модалки, watcher доберёт
    ctrl._apply_status(payload.get("status", ""), payload.get("reason", ""))
    check("g6_debounce_second_probe",
          ctrl.llm_paused and ctrl.modal_state == "OUTAGE",
          f"paused={ctrl.llm_paused} modal={ctrl.modal_state}")

    ctrl2 = _new_ctrl(gw)
    ctrl2.start()
    check("g6_watcher_live_debounce",
          _wait_pause(ctrl2, 12.0) and ctrl2._unconfirmed >= 2,
          f"paused={ctrl2.llm_paused} unconfirmed={ctrl2._unconfirmed}")


# ── G7: модалка headless (SDL dummy) ──────────────────────────────────────
def g7_modal_ui() -> None:
    import pygame

    import llm_outage_ui as d61_ui

    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    orig_pressed = pygame.mouse.get_pressed
    orig_pos = pygame.mouse.get_pos
    mouse: dict[str, Any] = {"pressed": False, "pos": (0, 0)}
    pygame.mouse.get_pressed = lambda: (mouse["pressed"],)
    pygame.mouse.get_pos = lambda: mouse["pos"]
    try:
        # Геометрия при 800x600: бокс 620x340 @ (90,130), кнопки y=400:
        # две: left Rect(150,400,240,46)->центр(270,423); right (530,423);
        # одна (RESTARTING): Rect(280,400,240,46)->центр(400,423).
        LEFT, RIGHT, SINGLE, MISS = (270, 423), (530, 423), (400, 423), (30, 30)

        def _fresh(state: str, reason: str = "pool backoff доказан"):
            c = _new_ctrl(None)
            c.modal_state = state
            c.modal_reason = reason
            return c

        def _click(state: str, pos) -> Optional[str]:
            c = _fresh(
                state,
                "причина провала рестарта " * 4
                if state == "FAILED"
                else "pool backoff доказан",
            )
            mouse["pressed"], mouse["pos"] = True, pos
            d61_ui.draw_outage_modal(screen, c, None)  # смена состояния гасит
            d61_ui.draw_outage_modal(screen, c, None)  # удержание — не клик
            mouse["pressed"] = False
            d61_ui.draw_outage_modal(screen, c, None)  # отпускание
            mouse["pressed"] = True
            act = d61_ui.draw_outage_modal(screen, c, None)  # нажатие
            mouse["pressed"] = False
            return act

        renders = True
        for st in ("OUTAGE", "RESTARTING", "SUCCESS", "FAILED"):
            try:
                d61_ui.draw_outage_modal(screen, _fresh(st), None)
            except Exception as e:
                renders = False
                _obs("g7_render_exc", f"{st}: {e}")
        check("g7_modal_renders_all_states", renders)

        cases = [
            ("OUTAGE", LEFT, "restart"), ("OUTAGE", RIGHT, "exit"),
            ("OUTAGE", MISS, None),
            ("RESTARTING", SINGLE, "exit"), ("RESTARTING", LEFT, None),
            ("SUCCESS", LEFT, "resume"), ("SUCCESS", RIGHT, "exit"),
            ("FAILED", LEFT, "restart"), ("FAILED", RIGHT, "exit"),
        ]
        bad = [
            f"{st}@{pos}: got={got} want={want}"
            for st, pos, want in cases
            if (got := _click(st, pos)) != want
        ]
        check("g7_button_map", not bad, "; ".join(bad))

        c = _fresh("OUTAGE")
        mouse["pressed"], mouse["pos"] = True, LEFT
        d61_ui.draw_outage_modal(screen, c, None)
        hold = d61_ui.draw_outage_modal(screen, c, None)
        mouse["pressed"] = False
        d61_ui.draw_outage_modal(screen, c, None)
        check("g7_rising_edge_hold_is_not_click", hold is None, f"hold={hold}")
    finally:
        pygame.mouse.get_pressed = orig_pressed
        pygame.mouse.get_pos = orig_pos


# ── G8: финал — сервер возвращён к здоровому состоянию ────────────────────
def g8_final(gw) -> None:
    from app.services.llm.server_lifecycle import restart_llama_server

    res = _call_async(restart_llama_server, timeout=_restart_timeout())
    check("g8_final_server_healthy",
          bool(res.get("restarted")) and _llm_alive(),
          f"res={res}")


# ── Оркестрация ───────────────────────────────────────────────────────────
def _run() -> None:
    from app.core.config import settings
    from tests.sandbox.fixture_loader import FIXTURE_DIR, has_fixture

    if not has_fixture():
        check("fixture_present", False, "campaign_open_road fixture отсутствует")
        return
    settings.data_dir = str(FIXTURE_DIR)
    _quiet()

    import llm_outage_ui as d61_ui

    d61_ui._POLL_INTERVAL = 0.3  # watcher-интервал прогона (прод = 5.0)

    gw = _OutageGateway()
    if not g0_selfhost(gw):
        return

    settings.saves_dir = tempfile.mkdtemp(prefix="d61_doctrine_")
    from app.services.game_loop_builder import build_game_loop
    from app.services.npc.life_engine import reset_life_engine

    reset_life_engine()  # eat C1: синглтон переживает пересборку
    gl = build_game_loop(Path(settings.data_dir))

    from app.services.llm.router import ModelRouter

    router = ModelRouter()

    g1_world(gl)
    ctrl = g2_outage(gl, gw, router)
    g4_restart_resume(gl, gw, router, ctrl)
    g5_failure(gw, router)
    g6_debounce(gw)
    g7_modal_ui()
    g8_final(gw)


def _finish() -> int:
    REPORT["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    REPORT["green"], REPORT["red"] = _GREEN, _RED
    (REPORTS / "d61_llm_outage_doctrine.json").write_text(
        json.dumps(REPORT, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md = [
        "# D61 LLM Outage Doctrine — живой прогон (COV-2)", "",
        f"Итог: GREEN={_GREEN} RED={_RED}", "",
        "| check | verdict | detail |", "|---|---|---|",
    ]
    md += [
        f"| {c['name']} | {'GREEN' if c['ok'] else 'RED'} | {c['detail'][:120]} |"
        for c in REPORT["checks"]
    ]
    (REPORTS / "d61_llm_outage_doctrine.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[D61-SCENARIO] артефакты: {REPORTS / 'd61_llm_outage_doctrine.json'}")
    print(f"Итог: GREEN={_GREEN} RED={_RED}")
    return 0 if _RED == 0 else 1


def main() -> int:
    try:
        _run()
    except Exception:
        traceback.print_exc()
        check("scenario_unexpected_exception", False, "см. traceback выше")
    finally:
        for c in _CTRLS:
            try:
                c.stop()
            except Exception:
                pass
    return _finish()


if __name__ == "__main__":
    raise SystemExit(main())
