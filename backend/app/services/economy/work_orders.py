"""
path: /project/backend/app/services/economy/work_orders.py
Назначение: WORK Vertical Slice (ADR-O-391, S256) — минимальная петля
    заказа и расчёта на живом субстрате:
        Intent.TRADE → ORDER(Transaction PROPOSED) → SERVE(Activity)
        → settle: атомарный SSOT-обмен → COMPLETED/FAILED →
        ACTIVITY_OUTCOME обоим → EconomyTracker.record_income.
    Замыкает разрыв «Intent.TRADE — выбор есть, исполнителя нет».
Законы (ADR-O-391):
    L-W1  ORDER — экономическая онтология (Transaction); SERVE —
          поведенческая (ActivityState; владение зеркалится существующим
          reconcile_activity_ownership).
    L-W2  DecisionHub не тронут: ORDER рождается в Фазе 6 из уже
          выбранного интента; SERVE материализуется work-pass Фазы 0.
    L-W3  Обмен атомарен: валидация ДО мутаций; goods и gold движутся
          вместе или не движется ничего.
    L-W4  INV-WORK-PERSIST: мутации — ТОЛЬКО SSOT-профили
          (npc_services.get_or_create_economic_profiles); deepcopy-слой
          тика (pipeline_runner S-143) — read-only.
    L-W5  WORK_ENABLED (default OFF) = no-op: ни заказа, ни SERVE, ни
          economic writes, ни WORK-outcome; состав событий не меняется.
    L-W6  Transaction терминален однократно; повторный settle = no-op.
    L-W7  Захороненный контур AUDIT #6 (TransactionEngine / TradeResolver
          / MarketState / Traveller / EconomicIntent) не воскресает;
          второго pipeline нет; якорь tick_orchestrator:904 не тронут.
Зависимости: app.core.constants (GOODS_PRICES), app.domain.activity,
    app.models.economy (Transaction/TransactionType/TransactionStatus)
Основные сущности: work_enabled, create_order_from_trade_intent,
    run_work_orders_pass, settle_order, fail_order
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from app.core.constants import GOODS_PRICES
from app.domain.activity import ActivityState, ActivityStep, ActivityType, StepKind
from app.models.economy import Transaction, TransactionStatus, TransactionType

logger = logging.getLogger(__name__)

# Флаг вертикали (G2-паттерн; call-time читатель, прецедент DESIRES_ENABLED)
_WORK_ENABLED_ENV = "WORK_ENABLED"

# K канала «давление желания → TRADE» (Шаг-3 Мастера: не перебор — якорь в
# существующей шкале). Прецедент DecisionHub: _direction_intents бустит
# utility как desire × 1.5 — канал при urgency × 1.0 НИЖЕ прецедента.
# Эмпирика сессии: 0.45 проигрывает OFFER_JOB активной фазы (W1 красный);
# 0.9 при urgency 0.9 — единственная доказанная GREEN-величина.
WORK_TRADE_PRESSURE_K: float = 1.0

# Персистентный стор заказов — scene_state (прецедент: pending_tasks)
_ORDERS_KEY = "work_orders"
# Bounded retention: вытесняются только терминальные записи
_ORDERS_CAP = 32

_SERVE_DURATION_TICKS = 2

_TERMINAL = (
    TransactionStatus.COMPLETED.value,
    TransactionStatus.FAILED.value,
    TransactionStatus.REJECTED.value,
)


def work_enabled() -> bool:
    return os.environ.get(_WORK_ENABLED_ENV, "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _order_id(tick: int, buyer: str, seller: str, good: str) -> str:
    """Детерминированный id (INV-REPLAY-DETERMINISM; uuid4 запрещён)."""
    return f"wo_{int(tick)}_{buyer}_{seller}_{good}"


def _profiles_getter(ctx: Any, orchestrator: Any = None) -> Optional[Any]:
    """SSOT-геттер профилей: NpcServices → оркестратор (DI P1.1f-паттерн).

    Юнит-харнессы инъектируют геттер в NpcServices-подобный объект;
    production-путь — проводка game_loop._svc → оркестратор (ADR-O-391).
    Громко при недоступности обоих (INV-SILENT-FAILURE): контур нем, но видно.
    """
    _svc = getattr(ctx, "npc_services", None)
    _getter = getattr(_svc, "get_or_create_economic_profiles", None)
    if _getter is None and orchestrator is not None:
        _getter = getattr(orchestrator, "_economic_profiles_getter", None)
    if _getter is None:
        logger.error(
            "[WORK] economic-profiles getter недоступен (npc_services/оркестратор) — контур нем"
        )
    return _getter


def _get_order(ctx: Any, order_id: str) -> Optional[Dict[str, Any]]:
    orders = ctx.scene_state.get(_ORDERS_KEY)
    if not isinstance(orders, dict):
        return None
    _o = orders.get(order_id)
    return _o if isinstance(_o, dict) else None


def _evict_terminal(orders: Dict[str, Dict[str, Any]]) -> None:
    if len(orders) <= _ORDERS_CAP:
        return
    _terminal = [k for k, v in sorted(orders.items()) if v.get("status") in _TERMINAL]
    for _k in _terminal[: len(orders) - _ORDERS_CAP]:
        del orders[_k]


def create_order_from_trade_intent(
    ctx: Any, *, speaker: str, seller_ref: str, orchestrator: Any = None
) -> Optional[str]:
    """Фаза 6: INTENT→ORDER — единственная точка рождения заказа.

    OFF → None (вызывающий продолжает легаси-путь диалога, L-W5).
    Экономических мутаций НЕТ: заказ = намерение обмена; наличие товара
    и золота проверяет settlement (предмет сделки называется стоком/желанием).
    """
    if not work_enabled():
        return None
    buyer = str(speaker or "").strip()
    _named = str(seller_ref or "").strip()
    if not buyer or _named in ("all", "player") or _named == buyer:
        return None
    getter = _profiles_getter(ctx, orchestrator)
    if getter is None:
        return None
    profiles = getter(ctx.campaign_id)
    if profiles.get(buyer) is None:
        logger.debug(f"[WORK] профиль покупателя не найден: {buyer} — ORDER не рождён")
        return None

    # ADR-O-391 (M2b-фикс, S256): социальный адресат интента
    # (SocialTargetResolver) не обязан быть экономическим контрагентом —
    # ORDER маршрутизируется к продавцу предмета желания. Ключ в
    # stock_for_sale = «продаёт предмет» (0.0 = продано — settlement честно
    # даст FAILED, не тихий отказ). Детерминизм: желания по urgency desc
    # (ties → subject asc), продавцы по id asc; предпочтение названному
    # адресату, если он продаёт. Без RNG.

    def _stock_keys(nid: str) -> set:
        _p = profiles.get(nid)
        _s = getattr(_p, "stock_for_sale", None) if _p is not None else None
        return set(_s.keys()) if isinstance(_s, dict) else set()

    # Дедупликация: один ОТКРЫТЫЙ заказ на покупателя — защита от спама
    # PROPOSED при живом давлении между онсетом и терминалом SERVE.
    _existing = ctx.scene_state.get(_ORDERS_KEY)
    if isinstance(_existing, dict) and any(
        isinstance(o, dict)
        and o.get("actor_id") == buyer
        and o.get("status")
        in (TransactionStatus.PROPOSED.value, TransactionStatus.ACCEPTED.value)
        for o in _existing.values()
    ):
        return None

    _desires = []
    for _n in ctx.all_npcs_raw or []:
        if str(_n.get("npc_id") or _n.get("id") or "") != buyer:
            continue
        for _d in _n.get("desires") or []:
            _subj = str(_d.get("subject_class", "") or "")
            _urg = float(_d.get("urgency", 0.0) or 0.0)
            if _subj in GOODS_PRICES and _urg >= 0.5:
                _desires.append((_urg, _subj, str(_d.get("desire_id", "") or "")))
        break
    _desires.sort(key=lambda t: (-t[0], t[1]))

    seller = ""
    _good = ""
    _desire_id = ""
    for _urg, _subj, _did in _desires:
        _sellers = sorted(
            nid
            for nid in profiles
            if nid not in (buyer, "player") and _subj in _stock_keys(nid)
        )
        if not _sellers:
            continue  # предмет никто не продаёт — пробуем следующее желание
        seller = _named if _named in _sellers else _sellers[0]
        _good, _desire_id = _subj, _did
        break

    if not seller:
        # Давление не назвало продаваемого предмета — легаси-ветка:
        # детерминированный товар из стока названного адресата (если есть)
        _named_keys = _stock_keys(_named)
        if not _named_keys:
            return None
        seller = _named
        _good = sorted(_named_keys)[0]

    _qty = 1.0
    _price = round(float(GOODS_PRICES.get(_good, 1.0)) * _qty, 4)
    _oid = _order_id(ctx.tick_number, buyer, seller, _good)
    _tx = Transaction(
        tx_type=TransactionType.PURCHASE,
        status=TransactionStatus.PROPOSED,
        actor_id=buyer,
        target_id=seller,
        goods={_good: _qty},
        payment=_price,
        reason="trade_intent",
        tick=int(ctx.tick_number),
        causal_note=f"work_order:{_oid}",
    )
    _order = _tx.to_dict()
    _order["order_id"] = _oid
    _order["buyer_desire_id"] = _desire_id
    orders = ctx.scene_state.setdefault(_ORDERS_KEY, {})
    orders[_oid] = _order
    _evict_terminal(orders)
    logger.info(
        f"[WORK] ORDER born: {_oid} goods={_good}x{_qty} "
        f"payment={_price} tick={ctx.tick_number}"
    )
    return _oid


def run_work_orders_pass(ctx: Any, orchestrator: Any) -> None:
    """Фаза 0: ORDER→SERVE — материализация деятельности продавца.

    Тот же персист-контракт, что у конвертера (npc["activity_state"]);
    владение зеркалится существующим reconcile_activity_ownership.
    ACCEPTED без активности → повторная материализация (resume-семантика
    №3: после INTERRUPTED — новая деятельность, не продолжение).
    OFF = no-op без вычислений (L-W5).
    """
    if not work_enabled():
        return
    orders = ctx.scene_state.get(_ORDERS_KEY)
    if not isinstance(orders, dict) or not orders:
        return

    _by_id = {
        str(n.get("npc_id") or n.get("id") or ""): n for n in ctx.all_npcs_raw or []
    }
    for _oid in sorted(orders):
        _o = orders[_oid]
        if _o.get("status") not in (
            TransactionStatus.PROPOSED.value,
            TransactionStatus.ACCEPTED.value,
        ):
            continue
        _seller = str(_o.get("target_id", "") or "")
        _npc = _by_id.get(_seller)
        if _npc is None:
            continue
        if isinstance(_npc.get("activity_state"), dict):
            continue  # занят — заказ ждёт (давление, не потеря)
        _bs = _npc.get("body_state")
        if not isinstance(_bs, dict) or not _bs:
            continue  # §ENIGMA-003: мёртвый/без сознания не обслуживает
        _state = ActivityState(
            activity_id=ActivityState.build_id(
                _seller, ActivityType.SERVE, ctx.tick_number
            ),
            activity_type=ActivityType.SERVE,
            desire_id=f"order:{_oid}",  # ACTIVITY_ONSET_FACT: причина = заказ
            target_ref=_oid,            # адрес цели = заказ (не WorldObject, D6)
            steps=(
                ActivityStep(
                    step_kind=StepKind.BODY_ACTION,
                    action_type="SERVE",
                    target_ref="",
                    duration_ticks=_SERVE_DURATION_TICKS,
                ),
            ),
            started_tick=int(ctx.tick_number),
        )
        _npc["activity_state"] = _state.to_dict()
        _o["status"] = TransactionStatus.ACCEPTED.value
        try:
            from app.services.npc.activity_lifecycle_service import (
                _ACTIVITY_DISPLAY_LABEL,
                _emit_label_change,
            )

            _emit_label_change(
                ctx,
                orchestrator,
                _seller,
                _ACTIVITY_DISPLAY_LABEL.get(ActivityType.SERVE, "serving"),
            )
        except Exception as exc:  # деградация канала видимости, не тика (G2 D5)
            logger.warning(f"[WORK] label emit fault {_seller}: {exc}")
        logger.info(f"[WORK] SERVE onset: {_seller} ← {_oid} tick={ctx.tick_number}")


def settle_order(
    ctx: Any, orchestrator: Any, *, seller_id: str, order_id: str
) -> None:
    """Терминал SERVE (success) = момент исполнения сделки.

    validate → атомарная SSOT-мутация → COMPLETED → outcome обоим →
    record_income. L-W3 (атомарность) / L-W4 (только SSOT) / L-W6 (однократно).
    """
    if not work_enabled():
        return
    _o = _get_order(ctx, order_id)
    if _o is None:
        logger.error(f"[WORK] settle: заказ {order_id} не найден (громко, не тихо)")
        return
    if _o.get("status") != TransactionStatus.ACCEPTED.value:
        logger.debug(f"[WORK] settle: {order_id} status={_o.get('status')} — no-op (L-W6)")
        return
    getter = _profiles_getter(ctx, orchestrator)
    if getter is None:
        _o["status"] = TransactionStatus.FAILED.value
        _o["fail_reason"] = "profiles_unavailable"
        return
    profiles = getter(ctx.campaign_id)
    buyer = str(_o.get("actor_id", "") or "")
    seller = str(_o.get("target_id", "") or "")
    buyer_p = profiles.get(buyer)
    seller_p = profiles.get(seller)
    goods = _o.get("goods") or {}
    payment = round(float(_o.get("payment", 0.0) or 0.0), 4)
    _tick = int(getattr(ctx, "tick_number", 0) or 0)

    # ── Валидация ДО мутаций (L-W3) ──────────────────────────────────
    _fail = ""
    if buyer_p is None or seller_p is None:
        _fail = "profile_missing"
    else:
        for _g, _q in sorted(goods.items()):
            _stock = float(
                getattr(seller_p, "stock_for_sale", {}).get(_g, 0.0) or 0.0
            )
            if _stock < float(_q or 0.0):
                _fail = f"no_stock:{_g}"
                break
        if not _fail and float(getattr(buyer_p, "gold", 0.0) or 0.0) < payment:
            _fail = "no_gold"

    if _fail:
        _o["status"] = TransactionStatus.FAILED.value
        _o["fail_reason"] = _fail
        _publish_outcome_for(
            orchestrator, buyer, _o, success=False, reason=_fail, tick=_tick
        )
        _publish_outcome_for(
            orchestrator, seller, _o, success=False, reason=_fail, tick=_tick
        )
        logger.info(f"[WORK] ORDER failed: {order_id} reason={_fail}")
        return

    # ── Атомарный обмен: ТОЛЬКО SSOT (L-W3/L-W4) ─────────────────────
    for _g, _q in sorted(goods.items()):
        _q = float(_q or 0.0)
        seller_p.stock_for_sale[_g] = round(
            float(seller_p.stock_for_sale.get(_g, 0.0) or 0.0) - _q, 4
        )
        buyer_p.goods[_g] = round(float(buyer_p.goods.get(_g, 0.0) or 0.0) + _q, 4)
    buyer_p.gold = round(float(buyer_p.gold or 0.0) - payment, 4)
    seller_p.gold = round(float(seller_p.gold or 0.0) + payment, 4)
    _o["status"] = TransactionStatus.COMPLETED.value

    # ADR-O-391: терминал обмена гасит давление покупателя («насыщение
    # пишет только терминал», EAT-прецедент) — иначе желание ale=0.9
    # рождает ордер каждый тик и W2 ловит второй settlement. FAILED-путь
    # давления не касается (желание продолжает давить — честно).
    _satisfy_buyer(ctx, buyer, sorted(goods.keys())[0] if goods else "", _tick)

    _tracker = getattr(getattr(ctx, "npc_services", None), "economy_tracker", None)
    if _tracker is None:
        _tracker = getattr(orchestrator, "_economy_tracker", None)
    if _tracker is not None and hasattr(_tracker, "record_income"):
        _tracker.record_income(seller, payment)  # контракт, никогда не вызывавшийся
    else:
        logger.error("[WORK] economy_tracker недоступен — доход не записан (громко)")

    _publish_outcome_for(
        orchestrator, buyer, _o, success=True, reason="transaction_completed", tick=_tick
    )
    _publish_outcome_for(
        orchestrator, seller, _o, success=True, reason="transaction_completed", tick=_tick
    )
    logger.info(f"[WORK] ORDER completed: {order_id} payment={payment}")


def fail_order(ctx: Any, *, order_id: str, reason: str) -> None:
    """Провал SERVE (не сделки): заказ → FAILED без мутаций и событий —
    исход деятельности продавца уже опубликован конвертером (success=False)."""
    if not work_enabled():
        return
    _o = _get_order(ctx, order_id)
    if _o is None or _o.get("status") in _TERMINAL:
        return
    _o["status"] = TransactionStatus.FAILED.value
    _o["fail_reason"] = f"serve_failed:{reason}"
    logger.info(f"[WORK] ORDER failed (serve): {order_id} reason={reason}")


def _satisfy_buyer(ctx: Any, buyer: str, good: str, tick: int) -> None:
    """Терминал обмена гасит давление покупателя (EAT-прецедент).

    Приобретение предмета = исход желания: need-источник обнуляется
    (обратный маппинг _NEED_TO_DESIRE), желание получает
    last_fulfilled_tick. Отказ — деградация канала (давление продолжит
    жить), не краш settlement'а.
    """
    if not good:
        return
    try:
        from app.services.npc.desire_generator import _NEED_TO_DESIRE

        _need_name = next(
            (_n for _n, (_s, _t) in _NEED_TO_DESIRE.items() if _s == good), ""
        )
        for _n in ctx.all_npcs_raw or []:
            if str(_n.get("npc_id") or _n.get("id") or "") != buyer:
                continue
            if _need_name:
                _needs = _n.get("needs")
                if isinstance(_needs, dict) and _need_name in _needs:
                    _needs[_need_name] = 0.0
            for _d in _n.get("desires") or []:
                if isinstance(_d, dict) and _d.get("subject_class") == good:
                    _d["last_fulfilled_tick"] = int(tick)
            break
    except Exception as exc:
        logger.warning(f"[WORK] satisfy_buyer fault {buyer} (degraded): {exc}")


def _publish_outcome_for(
    orchestrator: Any, npc_id: str, order: Dict[str, Any],
    *, success: bool, reason: str, tick: int,
) -> None:
    """Исход сделки обеим сторонам — той же фабрикой EventDTO, что
    _publish_outcome конвертера (строковый event_type — сон-прецедент).
    Наблюдаемость; отказ публикации = деградация канала, не тика."""
    try:
        _bus = orchestrator._get_event_bus()
        if _bus is None:
            return
        from app.domain.events import EventDTO

        _is_buyer = npc_id == order.get("actor_id")
        _bus.publish(
            EventDTO.create(
                event_type="activity_outcome",
                source=npc_id,
                payload={
                    "activity_type": "trade" if _is_buyer else "serve",
                    "desire_id": (
                        order.get("buyer_desire_id", "")
                        if _is_buyer
                        else f"order:{order.get('order_id', '')}"
                    ),
                    "target_ref": (
                        order.get("target_id") if _is_buyer else order.get("actor_id")
                    ),
                    "success": success,
                    "reason": reason,
                    "order_id": order.get("order_id", ""),
                    "payment": order.get("payment", 0.0),
                    "goods": order.get("goods", {}),
                },
                timestamp=float(tick),
            )
        )
    except Exception as exc:
        logger.warning(f"[WORK] outcome event fault {npc_id} (degraded): {exc}")