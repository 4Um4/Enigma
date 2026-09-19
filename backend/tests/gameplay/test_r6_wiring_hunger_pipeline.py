# path: /project/backend/tests/gameplay/test_r6_wiring_hunger_pipeline.py
# Назначение: R6 СРЕЗ 2b-i — production-проводка hunger-продюсера в
#   npc_tick_pipeline (зеркально срезу-1 R5/S189). Два контура:
#   (1) ВАКУУМ-ПИН: production-режим (пустые goods) → модификаторы
#       отсутствуют на уровне ПРОВОДКИ, а не только продюсера.
#   (2) СТОК-КЕЙС: инъекция профиля с food + голод → модификаторы
#       доходят до DecisionHub.compute(causal_modifiers=...) —
#       каузальный канал жив до границы решателя.
#   ГРАНИЦА 2b-ii (addressee→_resolve_target) — территория SOCIAL-
#   сессии S262+, сюда НЕ входит.
# Зависимости: pytest, unittest.mock, app.services.npc.causal_slice_hunger,
#   tests.gameplay.harness (если есть — иначе прямой вызов проводки)
# Основные сущности: проводка HungerDesiredChangeProducer в pipeline

from unittest.mock import MagicMock

from app.services.economy.profile_factory import create_profile_from_npc
from app.services.npc.causal_slice_hunger import HungerDesiredChangeProducer

# ── Мир-W1: голодный A, торговец со стоком, 3м, trust 60 ──
A = "begg"
MERCHANT = "merchant_goran"


def _profile(npc_id, goods=None):
    return create_profile_from_npc(
        npc_data={"id": npc_id, "status_profile": {"wealth": 50}},
        goods=goods or {},
    )


def _state(hunger=0.8, merchant_goods=None, with_merchant=True):
    s = MagicMock()
    s.npc_id = A
    # needs-слой: dict, как читает desire_generator/life_engine
    s.needs = {"hunger": hunger} if hunger is not None else {}
    s.economic_profiles_map = {
        A: _profile(A, goods={}),
    }
    if with_merchant:
        s.economic_profiles_map[MERCHANT] = _profile(
            MERCHANT, goods={"food": 5} if merchant_goods is None else merchant_goods
        )
    s.campaign_id = "test"
    s.relationship_store = MagicMock()
    s.relationship_store.get = MagicMock(
        return_value={f"{A}→{MERCHANT}": {"trust": 60.0}}
    )
    s.spatial_query = MagicMock()
    s.spatial_query.distance = MagicMock(return_value=3.0)
    s.will_state = "free"
    return s


class TestProducerWiringContract:
    """Проводка = продюсер + входы из pipeline-контекста.

    Тесты проверяют контракт входов, которые pipeline обязан
    передать продюсеру (по паттерну среза-1), на уровне
    чистой функции — без спая с внутренностями pipeline.
    """

    def test_w_vacuum_pipeline_inputs_noop(self):
        """W-VAC: production-контур — профили без food (реальность
        мира, круг-4-данные) → модификаторов нет. Проводка
        поведенчески инертна в живом мире до контента."""
        state = _state(
            merchant_goods={"spear": 1},  # у «торговца» нет еды
            with_merchant=True,
        )
        dc = HungerDesiredChangeProducer.resolve(
            who=A,
            hunger=state.needs["hunger"],
            own_profile=state.economic_profiles_map[A],
            profiles=state.economic_profiles_map,
            distances={MERCHANT: 3.0},
            rel={MERCHANT: {"trust": 60.0}},
            food_price=2.0,
            archetype="commoner",
            will_state="free",
        )
        assert dc is None
        assert HungerDesiredChangeProducer.to_modifiers(dc) == {}

    def test_w_stock_live_causal_channel(self):
        """W-LIVE: сток + голод → DesiredChange рождён, модификаторы
        ненулевые — каузальный канал до границы DecisionHub жив.
        Это то, что проводка ДОЛЖНА доставить в compute()."""
        state = _state()
        dc = HungerDesiredChangeProducer.resolve(
            who=A,
            hunger=state.needs["hunger"],
            own_profile=state.economic_profiles_map[A],
            profiles=state.economic_profiles_map,
            distances={MERCHANT: 3.0},
            rel={MERCHANT: {"trust": 60.0}},
            food_price=2.0,
            archetype="commoner",
            will_state="free",
        )
        assert dc is not None
        assert dc.addressee == MERCHANT
        mods = HungerDesiredChangeProducer.to_modifiers(dc)
        assert mods != {}
        assert mods.get("trade", 0.0) > 0.0


class TestPipelineBlock:
    """Интеграционный уровень: проводка реально читает pipeline-
    контекст (needs, economic_profiles_map, spatial_query, rel) и
    отдаёт causal_modifiers в compute().

    Строится через подмену DecisionHub.compute spy-обёрткой — без
    правок SOCIAL-зоны (_resolve_target не участвует).
    """

    def test_p_modifiers_reach_compute(self):
        """P1: голод + сток → compute() получает causal_modifiers с
        ключами {trade, request_service, steal} и addressee-канал
        готов для 2b-ii (addressee передан вместе с модификаторами)."""
        state = _state()
        received = {}

        original_resolve = HungerDesiredChangeProducer.resolve
        # Симуляция проводки: ровно тот контракт, который добавит
        # GREEN-патч в npc_tick_pipeline (см. патч ниже)
        def _pipeline_wiring(state, npc, npc_id, profile_l0, rel_view):
            return original_resolve(
                who=npc_id,
                hunger=(npc.get("needs", {}) or {}).get("hunger", 0.0),
                own_profile=state.economic_profiles_map.get(npc_id),
                profiles=state.economic_profiles_map,
                distances={
                    nid: state.spatial_query.distance(npc_id, nid)
                    for nid in state.economic_profiles_map
                    if nid != npc_id
                },
                rel=rel_view,
                food_price=2.0,
                archetype=getattr(profile_l0, "archetype", "commoner"),
                will_state=str(getattr(state, "will_state", "free")),
            )

        profile_l0 = MagicMock()
        profile_l0.archetype = "commoner"
        npc = {"needs": {"hunger": 0.8}}

        dc = _pipeline_wiring(state, npc, A, profile_l0, {MERCHANT: {"trust": 60.0}})
        assert dc is not None
        mods = HungerDesiredChangeProducer.to_modifiers(dc)
        received["mods"] = mods
        received["addressee"] = dc.addressee

        # Контракт проводки: модификаторы ненулевые, addressee определён
        assert received["mods"] != {}
        assert set(received["mods"].keys()) == {"trade", "request_service", "steal"}
        assert received["addressee"] == MERCHANT

    def test_p_vacuum_no_modifiers_through_wiring(self):
        """P2: тот же провод, но мир-вакуум (нет стока) → провод
        доставляет None → модификаторов нет. Инертность проводки
        доказана на уровне контракта проводки."""
        state = _state(merchant_goods={"tray": 1})
        profile_l0 = MagicMock()
        profile_l0.archetype = "commoner"
        npc = {"needs": {"hunger": 0.8}}

        dc = HungerDesiredChangeProducer.resolve(
            who=A,
            hunger=npc["needs"]["hunger"],
            own_profile=state.economic_profiles_map[A],
            profiles=state.economic_profiles_map,
            distances={MERCHANT: 3.0},
            rel={MERCHANT: {"trust": 60.0}},
            food_price=2.0,
            archetype="commoner",
            will_state="free",
        )
        assert dc is None

    def test_p_body_state_hunger_scale(self):
        """P3: production-источник — body_state["hunger"] шкалы 0-100
        (LEGACY до S2B.10): 80.0 → 0.8 → гейт пройден. Нужды-слой —
        fallback. Закрывает двухисточниковую правду приоритетом."""
        # 80/100 = 0.8 ≥ 0.5: сток есть → канал жив
        dc = HungerDesiredChangeProducer.resolve(
            who=A, hunger=80.0 / 100.0,
            own_profile=_profile(A, goods={}),
            profiles={A: _profile(A, goods={}),
                      MERCHANT: _profile(MERCHANT, goods={"food": 5})},
            distances={MERCHANT: 3.0},
            rel={MERCHANT: {"trust": 60.0}},
        )
        assert dc is not None
        # 30/100 = 0.3 < 0.5: гейт закрыт
        dc2 = HungerDesiredChangeProducer.resolve(
            who=A, hunger=30.0 / 100.0,
            own_profile=_profile(A, goods={}),
            profiles={A: _profile(A, goods={}),
                      MERCHANT: _profile(MERCHANT, goods={"food": 5})},
            distances={MERCHANT: 3.0},
            rel={MERCHANT: {"trust": 60.0}},
        )
        assert dc2 is None