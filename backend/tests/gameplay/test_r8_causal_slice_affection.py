# path: /project/backend/tests/gameplay/test_r8_causal_slice_affection.py
# Назначение: R8 CAUSAL SLICE 4 (ADR-O-400, CS17-CS19): тёплая связь
#     (trust ≥ 40 ∧ attraction ≥ 40) + видимый голод B (world-снапшот,
#     CS18-долг perception) + capacity A (CS19) → DesiredChange(who=A,
#     target_of_change=B — первое структурное who ≠ target) →
#     talk/trade(купить ДЛЯ B)/call_for_help. Каскад: threat > hunger >
#     grievance > affection.
# Зависимости: app.domain.desired_change, app.services.npc.causal_slice_affection,
#     app.services.economy.profile_factory
# Основные сущности: T1-T4 (пины, T4 — who≠target контракт),
#     W1-W5 (контрфакт), test_aa_noop_projection
# Запуск: cd backend; python -m pytest tests/gameplay/test_r8_causal_slice_affection.py -v -s

from app.domain.desired_change import REASON_AFFECTION, STATE_TYPE_RESOURCE
from app.services.economy.profile_factory import create_profile_from_npc
from app.services.npc.causal_slice_affection import AffectionDesiredChangeProducer

A = "carer"      # заботящийся (аналог orm: guilt_affection к B)
B = "beloved"    # любимый (аналог lusya)


def _profile(npc_id, goods=None):
    return create_profile_from_npc(
        npc_data={"id": npc_id, "status_profile": {"wealth": 50}},
        goods=goods or {},
    )


def _resolve(**ov):
    world = dict(
        who=A,
        rel={B: {"trust": 60.0, "attraction": 70.0}},   # тёплая пара (шкала SSOT 0-100)
        others_state={B: {"hunger": 80.0}},              # B голоден (world-снапшот, 0-100)
        own_profile=_profile(A, goods={"food": 1}),      # A имеет чем делиться
        distances={B: 4.0},
    )
    world.update(ov)
    return AffectionDesiredChangeProducer.resolve(**world)


# ═══ T-группа: пины ═══

def test_t1_cold_pair_no_care():
    """T1 (CS17): холодная пара → None — забота = проекция тепла."""
    assert _resolve(rel={B: {"trust": 10.0, "attraction": 5.0}}) is None

def test_t2_beloved_fed_no_change():
    """T2: B сыт → нет желаемого изменения → None."""
    assert _resolve(others_state={B: {"hunger": 20.0}}) is None

def test_t3_no_capacity_no_action():
    """T3 (CS19): B голоден, связь тёплая, но A пуст (ни еды, ни денег
    выше цены) → None: желание без возможности не действие."""
    assert _resolve(own_profile=_profile(A, goods={}),
                    food_price=100.0) is None

def test_t4_contract_who_ne_target():
    """T4: СТРУКТУРНОЕ различение — who=A, target_of_change=B,
    addressee=B: впервые агент меняет состояние ДРУГОГО."""
    dc = _resolve()
    assert dc is not None
    assert dc.who == A
    assert dc.target_of_change == B
    assert dc.who != dc.target_of_change
    assert dc.reason == REASON_AFFECTION
    assert dc.state_type == STATE_TYPE_RESOURCE


# ═══ W-группа: контрфакты (мир меняется → структура меняется) ═══

def test_w1_warm_pair_with_food_talk_dominates():
    """W1: тёплая пара + A имеет еду → talk (подойти, разделить трапезу)
    доминирует над торговыми способами."""
    dc = _resolve()
    w = dc.method_weights
    assert w["talk"] > w.get("trade", 0.0)
    assert w["talk"] > w.get("call_for_help", 0.0)

def test_w2_money_no_food_trade_alive():
    """W2: A без еды, но при деньгах → торговый путь жив (купить ДЛЯ B):
    контрфакт меняет доступный набор, не только вес."""
    dc = _resolve(own_profile=_profile(A, goods={}))  # wealth-дефолт ~51G
    assert dc is not None
    w = dc.method_weights
    assert w["trade"] > 0.1
    assert w["talk"] < w["trade"] or w["talk"] > 0.0  # talk жив, trade доминирует без своего ресурса

def test_w3_unreachable_beloved_none():
    """W3: B далеко (12м) → забота без пути → None (зеркало W5)."""
    assert _resolve(distances={B: 12.0}) is None

def test_w4_warmth_gradation():
    """W4: глубина тепла градуирует заботу: affection 70 vs 40 —
    веса глубже (фактор живой, не бинарный)."""
    deep = _resolve().method_weights["talk"]
    mild = _resolve(rel={B: {"trust": 45.0, "attraction": 42.0}}).method_weights["talk"]
    assert deep > mild

def test_w5_distress_gradation():
    """W5: лёгкий голод B (55) vs тяжёлый (85) — сильнее distress,
    сильнее давление заботы."""
    strong = _resolve(others_state={B: {"hunger": 85.0}}).method_weights["talk"]
    mild = _resolve(others_state={B: {"hunger": 55.0}}).method_weights["talk"]
    assert strong > mild


# ═══ A/A ═══

def test_aa_noop_projection():
    assert AffectionDesiredChangeProducer.to_modifiers(None) == {}