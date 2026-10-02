"""
path: /project/backend/tests/gameplay/test_f1_trade_materialization.py
Назначение: Регрессия ① TRADE MATERIALIZATION (ADR-O-412): полная петля
    NEED→DESIRE→TRADE→ORDER→SERVE→settlement→физическая передача.
    Ассерты = 6 приёмочных фактов β-Stage 1 (приказ Мастера) + константа
    V6 (settlement не трогает body_state). Production-only (§5a.2):
    idle_tick, temp-saves, инъекция только фактов тела/мира (hunger=80
    тела Люсьи, позиция у Торнина). Система может проматывать тики —
    ассерты по факту события, не по фиксированному тику.
Зависимости: game_loop_builder, work_orders (_ORDERS_KEY), harness-паттерн temp-saves
Основные сущности: test_trade_materialization_full_loop
Запуск: cd backend; python -m pytest tests/gameplay/test_f1_trade_materialization.py -v
"""
import os
import shutil
import tempfile
from pathlib import Path

import pytest

_CAMPAIGN = "Open_road"
LUSYA = "maid_lusya"
TORNIN = "tavern_keeper_tornin"
_MAX_TICKS = 24


@pytest.fixture()
def world():
    _tmp = Path(tempfile.mkdtemp(prefix="f1_reg_"))
    from app.core.config import settings
    shutil.copytree(settings.data_dir, _tmp, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("replay.db", "logs"))
    settings.data_dir = str(_tmp)
    settings.saves_dir = tempfile.mkdtemp(prefix="f1_reg_saves_")
    os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
    os.environ["DESIRES_ENABLED"] = "1"
    os.environ["WORK_ENABLED"] = "1"
    from app.services.events.event_bus import get_event_bus
    get_event_bus().clear()
    from app.services.game_loop_builder import build_game_loop
    gl = build_game_loop(_tmp)
    _s = getattr(gl, "_task_scheduler", None)
    _e = getattr(_s, "_executor", None) or getattr(_s, "executor", None)
    if _e is not None and hasattr(_e, "_router"):
        _e._router = None  # wall-clock LLM-ретраи — шум
    gl.idle_tick(_CAMPAIGN)  # прогрев сцены
    yield gl
    shutil.rmtree(_tmp, ignore_errors=True)


def _npc(gl, nid):
    _st = gl._get_life_engine().get_npc_states(_CAMPAIGN)
    return next((n for n in _st if (n.get("npc_id") or n.get("id")) == nid), {}) or {}


from app.services.economy.work_orders import _ORDERS_KEY


def _orders(gl):
    _sc = gl.scene_manager.get_scene_state(_CAMPAIGN, "tavern") or {}
    return _sc.get(_ORDERS_KEY) or {}


def test_trade_materialization_full_loop(world):
    gl = world
    _l = _npc(gl, LUSYA)
    _t = _npc(gl, TORNIN)
    assert _l and _t, "NPC не найдены"
    _l.setdefault("body_state", {})["hunger"] = 80.0  # инъекция входа: факт тела
    _l["position"] = _t.get("position")               # инъекция входа: позиция
    _prof = gl._svc.get_or_create_economic_profiles(_CAMPAIGN)
    _gold_l0 = float(getattr(_prof.get(LUSYA), "gold", 0.0) or 0.0)
    _gold_t0 = float(getattr(_prof.get(TORNIN), "gold", 0.0) or 0.0)

    _completed = None
    for _ in range(_MAX_TICKS):
        gl.idle_tick(_CAMPAIGN)
        _o = _orders(gl)
        _done = [v for v in _o.values() if isinstance(v, dict)
                 and v.get("actor_id") == LUSYA and v.get("status") == "completed"]
        if _done:
            _completed = _done[0]
            break
    assert _completed is not None, f"за {_MAX_TICKS} тиков сделка Люсьи не состоялась"

    # V1/V3: сток продавца обнулён ровно на количество заказа
    assert float(getattr(_prof.get(TORNIN), "stock_for_sale", {}).get("food", 0.0)) == 0.0
    # V2/V3: вещь у покупателя
    assert float(getattr(_prof.get(LUSYA), "goods", {}).get("food", 0.0)) == 1.0
    # V4: платёж синхронен
    _pay = float(_completed.get("payment", 0.0) or 0.0)
    assert abs(float(getattr(_prof.get(LUSYA), "gold", 0.0)) - (_gold_l0 - _pay)) < 1e-6
    assert abs(float(getattr(_prof.get(TORNIN), "gold", 0.0)) - (_gold_t0 + _pay)) < 1e-6
    # V6 (константа ADR-O-412): settlement не трогает тело
    assert float((_npc(gl, LUSYA).get("body_state") or {}).get("hunger", 0.0)) == 80.0