"""
path: /project/backend/tests/sandbox/f1a_trade_gate_probe.py
Назначение: Фронт ① TRADE MATERIALIZATION — доказательство F1a (S264-гейт
    activity_state глушит причинный TRADE до WORK-ветки) и F1e (лайвлок
    PROPOSED-заказа: продавец занят → dedup блокирует повторные ORDER).
    Production-only (§5a.2): idle_tick, temp-saves, инъекция ТОЛЬКО входа
    (hunger тела maid_lusya = 80.0 [шкала 0-100, pipeline:689 нормализует],
    позиция = позиция Торнина — прецедент w5_probe). Диагностические
    print-маркеры [GATE-F1A]/[GATE-F1E] в post_decision/work_orders —
    временные, удаляются после вердикта.
Запуск: cd backend; python tests/sandbox/f1a_trade_gate_probe.py
"""
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, ".")
from app.core.config import settings

_d = Path(tempfile.mkdtemp(prefix="f1a_"))
shutil.copytree(settings.data_dir, _d, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("replay.db", "logs"))
settings.data_dir = str(_d)
settings.saves_dir = tempfile.mkdtemp(prefix="f1a_saves_")
os.environ["ACTIVITY_LIFECYCLE_ENABLED"] = "1"
os.environ["DESIRES_ENABLED"] = "1"
os.environ["WORK_ENABLED"] = "1"

logging.basicConfig(level=logging.INFO)
# Глушим шум, но НЕ decision_hub/work_orders (их логи — часть вердикта)
for _n in ("app.services.llm.router", "app.services.llm.provider_manager",
           "app.services.llm.llama_cpp_provider", "app.services.memory",
           "pymorphy3.opencorpora_dict.wrapper"):
    logging.getLogger(_n).setLevel(logging.CRITICAL)

from app.services.economy.work_orders import _ORDERS_KEY
from app.services.game_loop_builder import build_game_loop

gl = build_game_loop(Path(_d))
_s = getattr(gl, "_task_scheduler", None)
_e = getattr(_s, "_executor", None) or getattr(_s, "executor", None)
if _e is not None and hasattr(_e, "_router"):
    _e._router = None  # wall-clock LLM-ретраи = шум зонда (прецедент iron_river_lusya)

LUSYA = "maid_lusya"
TORNIN = "tavern_keeper_tornin"

# Прогрев: сцена лениво поднимается первым тиком
gl.idle_tick("Open_road")

_st = gl._get_life_engine().get_npc_states("Open_road")
_l = next((n for n in _st if n.get("npc_id") == LUSYA or n.get("id") == LUSYA), None)
_t = next((n for n in _st if n.get("npc_id") == TORNIN or n.get("id") == TORNIN), None)
if _l is None or _t is None:
    print(f"[F1A-VERDICT] FAIL: NPC не найдены (lusya={_l is not None}, tornin={_t is not None})")
    sys.exit(2)

# ИНЪЕКЦИЯ ВХОДА (факты тела/мира, §9): голод тела + позиция у продавца
_bs = _l.setdefault("body_state", {})
_bs["hunger"] = 80.0  # шкала 0-100 → pipeline:689 даст 0.8 ≥ NEED_GATE
_l["position"] = _t.get("position")
print(f"[F1A-SEED] lusya hunger=80.0 pos={str(_l.get('position',''))[:30]} "
      f"tornin_pos={str(_t.get('position',''))[:30]}")

def _orders_view():
    _sc = gl.scene_manager.get_scene_state("Open_road", "tavern") or {}
    _o = _sc.get(_ORDERS_KEY) or {}
    return {k: v.get("status", "?") for k, v in _o.items()} if isinstance(_o, dict) else {"<not-dict>": "?"}

for _i in range(12):
    gl.idle_tick("Open_road")
    _st = gl._get_life_engine().get_npc_states("Open_road")
    _l = next((n for n in _st if (n.get("npc_id") or n.get("id")) == LUSYA), {}) or {}
    _t = next((n for n in _st if (n.get("npc_id") or n.get("id")) == TORNIN), {}) or {}
    _lh = (_l.get("body_state") or {}).get("hunger")
    _ln = (_l.get("needs") or {}).get("hunger")
    _lful = next((d.get("last_fulfilled_tick") for d in (_l.get("desires") or [])
                  if d.get("subject_class") == "food"), None)
    _prof = gl._svc.get_or_create_economic_profiles("Open_road")
    _lg = dict(getattr(_prof.get(LUSYA), "goods", {}) or {})
    _tg = dict(getattr(_prof.get(TORNIN), "goods", {}) or {})
    _ts = dict(getattr(_prof.get(TORNIN), "stock_for_sale", {}) or {})
    _lgold = float(getattr(_prof.get(LUSYA), "gold", 0.0) or 0.0)
    _tgold = float(getattr(_prof.get(TORNIN), "gold", 0.0) or 0.0)
    _la = (_l.get("activity_state") or {}).get("activity_type")
    _ta = (_t.get("activity_state") or {}).get("activity_type")
    print(f"[F1A-T{_i+1}] body_hunger={_lh} needs_hunger={_ln} food_fulfilled@{_lful} "
          f"lusya_goods={_lg} lusya_gold={_lgold:.2f} tornin_goods={_tg} "
          f"tornin_stock={_ts} tornin_gold={_tgold:.2f} "
          f"lusya_act={_la} tornin_act={_ta} orders={_orders_view()}")

# DIAG-F1B: capability-карта — желания Люсьи и стоки продавцов (чтение SSOT)
_p = gl._svc.get_or_create_economic_profiles("Open_road")
for _nid in sorted(_p):
    _stock = getattr(_p[_nid], "stock_for_sale", None)
    if isinstance(_stock, dict) and _stock:
        print(f"[F1B-CAP] stock {_nid}: {dict(_stock)}")
print(f"[F1B-CAP] desires lusya: "
      f"{[(d.get('subject_class'), d.get('urgency')) for d in (_l.get('desires') or [])][:6]}")
print(f"[F1B-CAP] GOODS_PRICES keys: {sorted(__import__('app.core.constants', fromlist=['GOODS_PRICES']).GOODS_PRICES.keys())}")

print("[F1A-VERDICT] прогон завершён — разбирай маркеры GATE-F1A/F1E/[WORK] выше")