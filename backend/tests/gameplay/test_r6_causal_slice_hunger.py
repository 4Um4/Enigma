# path: /project/backend/tests/gameplay/test_r6_causal_slice_hunger.py
# Назначение: R6 CAUSAL SLICE 2a (capability) — RED/GREEN сьют.
#   Контрфактический закон CS13 (Мастер Тай): один A, один desired_change,
#   меняется ТОЛЬКО мир → меняется цепочка candidate set → available
#   methods → selected action. НЕ одно число.
#   Граница: SOCIAL-сессия (S262+) владеет target-stage — addressee-
#   интеграция (RH5/2b) сюда НЕ входит.
# Зависимости: pytest, app.domain.desired_change,
#   app.services.economy.profile_factory (фабрика, §13.4),
#   app.services.npc.causal_slice_hunger (RED: отсутствует → ImportError)
# Основные сущности: T1-T4 (пины), W1-W5/W4b (контрфакт), A1-A3 (факторы)
"""
Запуск: cd backend; python -m pytest tests/gameplay/test_r6_causal_slice_hunger.py -v 2>&1 | Select-Object -Last 15; cd ..
"""


from app.domain.desired_change import (
    REASON_NEED,
    STATE_TYPE_RESOURCE,
)
from app.services.economy.profile_factory import create_profile_from_npc
from app.services.npc.causal_slice_hunger import (
    HungerDesiredChangeProducer,
)

A = "begg"  # голодный проситель (общий агент всех контрфактов)


def _profile(npc_id: str, goods=None):
    """Профиль ТОЛЬКО через фабрику (§13.4). Инъекция входа —
    capability-сток как факт мира (прецедент eat_vertical: hunger=0.9).
    TECH_DEBT_NOTE ECON-FACTORY-GOLD-FALSY: profile_factory игнорирует
    gold=0.0 (falsy) — платежеспособность в тестах управляется
    food_price, не полем gold."""
    return create_profile_from_npc(
        npc_data={"id": npc_id, "status_profile": {"wealth": 50}},
        goods=goods or {},
    )


def _resolve(**overrides):
    """Базовый мир W1 + точечные мутации ОДНОЙ переменной (контрфакт)."""
    world = dict(
        who=A,
        hunger=0.8,
        own_profile=_profile(A, goods={}),          # своей еды нет (CS11-ветка закрыта)
        profiles={"merchant": _profile("merchant", goods={"food": 5})},
        distances={"merchant": 3.0},
        rel={"merchant": {"trust": 60.0}},           # шкала SSOT 0-100
        food_price=2.0,
        archetype="commoner",
        will_state="free",
    )
    world.update(overrides)
    return HungerDesiredChangeProducer.resolve(**world)


# ═══ T-группа: пины честности (no-op там, где причины нет) ═══

def test_t1_no_hunger_no_goal():
    """T1: hunger ниже гейта → None (CS1-аналог: причина первична)."""
    assert _resolve(hunger=0.3) is None

def test_t2_own_food_silent():
    """T2: своя еда есть → None (CS11: путь предшественника, не мой)."""
    assert _resolve(own_profile=_profile(A, goods={"food": 2})) is None

def test_t3_capability_vacuum_is_none():
    """T3: много NPC, еды ни у кого → None (CS9: вакуум ≠ ближайший).
    Это production-режим по умолчанию (data-факт круга 4)."""
    world = {
        "who": A, "hunger": 0.8,
        "own_profile": _profile(A, goods={}),
        "profiles": {
            "guard": _profile("guard", goods={"spear": 1}),
            "maid": _profile("maid", goods={"tray": 1}),
        },
        "distances": {"guard": 2.0, "maid": 2.0},
        "rel": {"guard": {"trust": 50.0}, "maid": {"trust": 50.0}},
        "food_price": 2.0, "archetype": "commoner", "will_state": "free",
    }
    assert HungerDesiredChangeProducer.resolve(**world) is None

def test_t4_contract_fields():
    """T4: CS3 различение — target_of_change (A) ≠ addressee (B);
    reason=need; state_type=resource. Первый случай в ENIGMA, где
    контрактное различение не совпадает (срез-1: совпадали)."""
    dc = _resolve()
    assert dc is not None
    assert dc.target_of_change == A
    assert dc.addressee == "merchant"
    assert dc.target_of_change != dc.addressee
    assert dc.reason == REASON_NEED
    assert dc.state_type == STATE_TYPE_RESOURCE


# ═══ W-группа: контрфакты (CS13) — меняется МИР, не агент ═══

def test_w1_merchant_money_trade():
    """W1: торговец со стоком + деньги → addressee=merchant, trade доминирует."""
    dc = _resolve()
    assert dc.addressee == "merchant"
    w = dc.method_weights
    assert w["trade"] > w["request_service"]
    assert w["trade"] > w.get("steal", 0.0)

def test_w2_friend_no_money_request():
    """W2: друга прошу, торговца нет, денег нет → request_service доминирует."""
    dc = _resolve(
        profiles={"friend": _profile("friend", goods={"food": 3})},
        distances={"friend": 4.0},
        rel={"friend": {"trust": 80.0}},
        food_price=100.0,  # выше кошелька (51G) → afford=0, честный ноль
    )
    assert dc is not None
    w = dc.method_weights
    assert w["request_service"] > w["trade"]
    assert w["trade"] < 0.05  # без денег торговля мертва, не «чуть ниже»

def test_w3_nobody_has_food():
    """W3: мир №3 Тай — еда ни у кого → None (синоним T3 на чистом мире)."""
    assert _resolve(profiles={}) is None

def test_w4_enemy_food_commoner_none():
    """W4: еда ТОЛЬКО у врага (trust=-50, ниже hostile -30), A — commoner
    → None: просить страшно, красть не умеет. Наличие capability НЕ равно
    наличие пути. Честное отсутствие цели."""
    dc = _resolve(
        profiles={"enemy": _profile("enemy", goods={"food": 4})},
        distances={"enemy": 3.0},
        rel={"enemy": {"trust": -50.0}},
        food_price=100.0,  # нечем платить врагу в любом смысле
    )
    assert dc is None

def test_w4b_enemy_food_thief_steals():
    """W4b: тот же враг, но A=thief + deceptive → addressee=enemy,
    steal доминирует. Цепочка Тай: «враг имеет еду → слишком боится
    просить → крадёт» — первый росток будущих grievance-срезов."""
    dc = _resolve(
        profiles={"enemy": _profile("enemy", goods={"food": 4})},
        distances={"enemy": 3.0},
        rel={"enemy": {"trust": -50.0}},
        food_price=100.0,
        archetype="thief",
        will_state="deceptive",
    )
    assert dc is not None
    assert dc.addressee == "enemy"
    w = dc.method_weights
    assert w["steal"] > w.get("trade", 0.0)
    assert w["steal"] > w["request_service"]

def test_w5_unreachable_candidate_excluded():
    """W5: сток есть, B недостижим (12м > радиуса) → кандидат исключён → None."""
    assert _resolve(distances={"merchant": 12.0}) is None


# ═══ A-группа: факторная чувствительность (факторы живые, не орнамент) ═══

def test_a1_trust_factor_alive():
    """A1: trust 60 → 0 (деньги те же) → trade-вес падает измеримо."""
    w_high = _resolve().method_weights["trade"]
    w_zero = _resolve(rel={"merchant": {"trust": 0.0}}).method_weights["trade"]
    assert (w_high - w_zero) >= 0.15

def test_a2_gold_factor_kills_trade():
    """A2: не может заплатить при том же мире → trade-вес ≈ 0."""
    dc = _resolve(food_price=100.0)
    assert dc.method_weights["trade"] < 0.05

def test_a3_weights_sum_bounded():
    """A3: CS12 — сумма весов ≤ 1.0 (нет двойного счёта с eco_modifiers)."""
    dc = _resolve(archetype="thief", will_state="deceptive",
                  food_price=100.0)  # afford=0: изоляция trade-фактора
    assert sum(dc.method_weights.values()) <= 1.0


# ═══ A/A-изоляция ═══

def test_aa_noop_projection():
    """A/A: None → to_modifiers == {} (срез аддитивен, мир без причины
    не меняется; зеркально срезу-1)."""
    assert HungerDesiredChangeProducer.to_modifiers(None) == {}