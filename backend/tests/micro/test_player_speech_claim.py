# path: /project/backend/tests/micro/test_player_speech_claim.py
# Назначение: G1 (GC-SOCIAL-01, Stage-1.5) — замок симметрии testimony-канала:
#   PLAYER_SPOKE с DM-вектором (ADR-035) → ClaimEvent → belief слышащего NPC
#   (в радиусе); за радиусом — тишина (мембрана); без вектора — no-op
#   (граница Stage-1.5/M2/D: не-понимание). Контроль: предикат и provenance.
# Зависимости: app.services.events.claim_event_subscriber, app.domain.events,
#   app.services.npc.epistemic_store, app.services.npc.belief_revision_engine
# Основные сущности: ClaimEventSubscriber, EpistemicStore(шпион), EventDTO
#
# Запуск: cd backend; python -m pytest tests/micro/test_player_speech_claim.py -v; cd ..
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.events.claim_event_subscriber import ClaimEventSubscriber


class _Store:
    """Шпион под production-контракт on_claim_event (№183):
    get(listener, prop) → engine.revise(listener, claim, existing) → upsert(record)."""

    def __init__(self):
        self.records = []

    def get(self, listener_id, proposition):
        return None  # нет существующего убеждения — чистый путь ревизии

    def upsert(self, record):
        self.records.append(record)


def _sq(npc_positions, distances):
    return SimpleNamespace(_npc_positions=npc_positions, distance=lambda a, b: distances.get((a, b), 999.0))


def _engine(store):
    return SimpleNamespace(
        apply_claim=store.apply_claim,
        # engine-протокол (β-прецедент: apply через listener+store)
        apply=lambda claim, **kw: store.apply_claim(claim),
    )


def _evt(speech, target="merchant_goran", target_id=None, radius=6.0):
    from app.domain.events import EventDTO

    # target_reference — subject клейма (о ком утверждение);
    # target_id — семантический адресат реплики (S198-фоллбек добавляет его
    # слушателем ВНЕ мембраны — №123, дизайн-гарантия детерминизма). Тесты
    # изоляции передают target_id=None, чтобы слушать только геометрию.
    payload = {
        "target_id": target_id,
        "raw_input": "тест",
        "action_type": "dialogue",
        "semantic_action": speech,
        "target_reference": target,
    }
    return EventDTO.create(
        event_type="PLAYER_SPOKE",
        source="player",
        payload=payload,
        radius=radius,
    )


def test_player_speech_claim_in_radius_creates_belief():
    # C2-контроль: ACCUSE с вектором, Люся в 2 м от игрока → belief о target
    store = _Store()
    sub = ClaimEventSubscriber(
        engine=SimpleNamespace(
            revise=lambda listener_id, claim, existing: SimpleNamespace(
                listener_id=listener_id,
                claim=claim,
                proposition=claim.proposition,
            )
        ),
        store=store,
        spatial_query_provider=lambda: _sq(
            {"player": {}, "merchant_goran": {}, "maid_lusya": {}},
            {("player", "merchant_goran"): 3.0, ("player", "maid_lusya"): 2.0},
        ),
    )
    sub.on_player_spoke(_evt("ACCUSE"))  # target_id=None: только геометрия
    assert store.records, "G1: слышащие NPC в радиусе получили ClaimEvent"
    _lst = {r.listener_id for r in store.records}
    assert "maid_lusya" in _lst and "merchant_goran" in _lst, (
        "G1: оба в радиусе (2/3 м) услышали"
    )
    _c = next(r for r in store.records if r.listener_id == "maid_lusya")
    assert _c.proposition.subject_id == "merchant_goran"
    assert _c.proposition.predicate.value == "stole"


def test_player_speech_claim_out_of_radius_silence():
    # C1: ACCUSE, адресат (Люся) сам за радиусом 9 м И присутствует в мире —
    # даже S198-target-фоллбек уважает мембрану для присутствующих (№123:
    # in-positions → can_observe). Форма ACCUSE при этом — subject=Люся.
    store = _Store()
    sub = ClaimEventSubscriber(
        engine=SimpleNamespace(
            revise=lambda listener_id, claim, existing: SimpleNamespace(
                listener_id=listener_id, claim=claim, proposition=claim.proposition
            )
        ),
        store=store,
        spatial_query_provider=lambda: _sq(
            {"player": {}, "maid_lusya": {}},
            {("player", "maid_lusya"): 9.0},
        ),
    )
    sub.on_player_spoke(_evt("ACCUSE", target="maid_lusya", target_id=None))
    assert not store.records, "C1: за радиусом — 0 ClaimEvent (мембрана)"


def test_player_speech_no_vector_noop():
    # C2-контроль: обычный dialogue (без DM-вектора) → no-op: LISTEN-дельты
    # живы, убеждений нет — граница Stage-1.5 (не-понимание)
    from app.domain.events import EventDTO

    store = _Store()
    sub = ClaimEventSubscriber(engine=MagicMock(), store=store)
    evt = EventDTO.create(
        event_type="PLAYER_SPOKE",
        source="player",
        payload={"target_id": "merchant_goran", "raw_input": "привет", "action_type": "dialogue"},
        radius=6.0,
    )
    sub.on_player_spoke(evt)
    assert not store.records, "C2: без вектора — 0 belief"


def test_player_speech_threaten_predicate_and_player_subject():
    # Предикат THREATEN: subject=player (зеркало NPC-фоллбека)
    store = _Store()
    # S202 (№123): predicate=attacked переносит origin на target — дистанции
    # считаются ОТ Горана; словарь симметричен, свидетельница Люся в 3 м.
    sub = ClaimEventSubscriber(
        engine=SimpleNamespace(
            revise=lambda listener_id, claim, existing: SimpleNamespace(
                listener_id=listener_id,
                claim=claim,
                proposition=claim.proposition,
            )
        ),
        store=store,
        spatial_query_provider=lambda: _sq(
            {"player": {}, "merchant_goran": {}, "maid_lusya": {}},
            {
                ("merchant_goran", "player"): 2.0,
                ("merchant_goran", "maid_lusya"): 3.0,
                ("player", "merchant_goran"): 2.0,
                ("player", "maid_lusya"): 3.0,
            },
        ),
    )
    # target_id=Горан: S202 переносит origin на жертву угрозы (predicate=
    # attacked, №123) — дистанции от Горана; Люся-свидетельница в 3 м слышит.
    sub.on_player_spoke(_evt("THREATEN", target_id="merchant_goran"))
    assert store.records, "THREATEN: ClaimEvent создан (origin=target по S202)"
    _c = next(r for r in store.records if r.listener_id == "maid_lusya")
    assert _c.claim.speaker_id == "player"
    assert _c.proposition.subject_id == "player"
    assert _c.proposition.predicate.value == "attacked"