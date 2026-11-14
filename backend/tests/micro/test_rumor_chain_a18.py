"""
Интеграционный тест цепочки распространения слухов A18 (Rumor Chain Integration).
Доказывает полный цикл: A → B (усвоение) → B самостоятельно решает рассказать → B → C (доставка с сохранением provenance).
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.epistemology import Proposition, Predicate, EpistemicRecord, ClaimEvent, SpeechAct
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
from app.services.npc.decision_hub import DecisionHub
from app.services.npc.trust_based_reliability_provider import TrustBasedReliabilityProvider
from app.services.memory.relationship_store import RelationshipStore
from app.services.npc.belief_revision_engine import BeliefRevisionEngine
from app.models.npc_state import EmotionTag
from app.services.events.event_types import EventType


def test_rumor_chain_a_to_b_to_c_integration():
    """
    Сценарий:
    1. NPC A рассказывает NPC B, что X оскорбил B.
    2. B усваивает это (source_id=A, original_source_id=A).
    3. B самостоятельно решает рассказать это C (единственный доступный с trust > 0).
    4. B рассказывает C.
    5. C усваивает это (source_id=B, original_source_id=A).
    """
    # 1. Инициализация хранилищ (корректный API)
    store = EpistemicStore()
    rel_store = RelationshipStore(data_dir="test_data")

    # Настраиваем отношения: B доверяет C (trust = 50.0), но не доверяет A (trust = -10.0)
    # API: update(campaign_id, source, target, delta: Dict[str, float])
    rel_store.update("test_campaign", "B", "C", {"trust": 50.0})
    rel_store.update("test_campaign", "B", "A", {"trust": -10.0})
    rel_store.update("test_campaign", "C", "B", {"trust": 50.0})

    # 2. Симуляция: A только что рассказал B про X
    prop = Proposition(subject_id="X", predicate=Predicate.INSULTED, object_id="B")
    record_a_to_b = EpistemicRecord(
        agent_id="B",
        proposition=prop,
        confidence=0.8,
        source_id="A",
        source_claim_id="claim_1",
        first_observed_tick=1,
        last_updated_tick=1,
        original_source_id="A"  # A является первоисточником
    )
    store.upsert(record_a_to_b)

    # Проверка 1: Belief B & Provenance B
    b_record = store.get("B", prop)
    assert b_record is not None, "B должен иметь запись об утверждении"
    assert b_record.source_id == "A", "Непосредственный источник для B должен быть A"
    assert b_record.original_source_id == "A", "Первоисточник должен быть A"

    # 3. Самостоятельное решение B (Independent decision targeting)
    state_b = MagicMock()
    state_b.npc_id = "B"
    state_b.tick_id = 2
    state_b.campaign_id = "test_campaign"
    state_b.relationship_store = rel_store
    state_b.emotion = EmotionTag.NEUTRAL

    # Пространственный запрос: только C находится в радиусе слышимости (5.0 < 10.0)
    # A далеко (999.0), X далеко (999.0)
    spatial_query = MagicMock()
    spatial_query.distance = MagicMock(side_effect=lambda a, b: 5.0 if b == "C" else 999.0)

    resolver = EpistemicContextResolver(store=store)
    epi_ctx_b = resolver.resolve("B")

    # Проверяем, что B видит это как claim_about_self (триггер для spread_rumor)
    assert len(epi_ctx_b.claims_about_self) == 1
    assert epi_ctx_b.claims_about_self[0].predicate == Predicate.INSULTED

    # compute() обычно размещает источники отношений в DecisionHub перед
    # разрешением цели; здесь подготавливаем тот же контекст для прямого вызова.
    hub = DecisionHub()
    hub._rel_store = rel_store
    hub._campaign_id = "test_campaign"
    event = MagicMock()
    event.event_type = EventType.WORLD_TICK
    all_npcs = ["A", "B", "C", "X"]

    # Проверка 2: Independent decision targeting
    # Доказываем: ЕСЛИ B выбирает SPREAD_RUMOR, он адресует его ИМЕННО C,
    # благодаря социальному фильтру (trust > 0) и физической доступности.
    target_for_b = hub._resolve_target(
        intent="spread_rumor",
        event=event,
        state=state_b,
        spatial_query=spatial_query,
        all_npc_ids=all_npcs,
        epistemic_context=epi_ctx_b
    )

    assert target_for_b == "C", f"B должен выбрать C как единственного доступного и доверенного адресата, получено: {target_for_b}"

    # 4. Симуляция: B рассказывает C (B → C Delivery)
    # Эмулируем логику ClaimEventSubscriber при получении речи от B
    # Он читает запись B, чтобы найти original_source_id для multi-hop provenance
    speaker_record = store.get("B", prop)
    speaker_orig = speaker_record.original_source_id if speaker_record else "B"

    # API: ClaimEvent(event_id, claim_id, speaker_id, listener_id, proposition, speech_act, tick)
    claim_event = ClaimEvent(
        event_id="evt_2",
        claim_id="claim_2",
        speaker_id="B",
        listener_id="C",
        proposition=prop,
        speech_act=SpeechAct.ASSERT,
        tick=2
    )

    reliability = TrustBasedReliabilityProvider(rel_store, "test_campaign")
    engine = BeliefRevisionEngine(reliability_provider=reliability)
    c_existing = store.get("C", prop)

    # reliability_context формируется подписчиком именно так:
    reliability_context = {
        "source_type": "testimony",
        "original_source_id": speaker_orig  # Ключевой момент: сохранение первоисточника!
    }

    c_updated = engine.revise("C", claim_event, c_existing, reliability_context=reliability_context)
    store.upsert(c_updated)

    # Проверка 3: Belief C & Provenance C
    c_record = store.get("C", prop)
    assert c_record is not None, "C должен получить запись об утверждении"
    assert c_record.source_id == "B", "Непосредственный источник для C должен быть B (передатчик)"
    assert c_record.original_source_id == "A", "Первоисточник должен сохраниться как A (multi-hop provenance)"

    # Проверка 4: Replay (Детерминизм)
    # Сбросим хранилище и повторим сценарий
    store._records.clear()
    store.upsert(record_a_to_b)

    c_updated_replay = engine.revise("C", claim_event, None, reliability_context=reliability_context)
    store.upsert(c_updated_replay)

    c_record_replay = store.get("C", prop)
    assert c_record_replay.source_id == "B"
    assert c_record_replay.original_source_id == "A"
