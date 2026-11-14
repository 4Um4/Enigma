"""
Тесты жизненного цикла автономного разговора NPC (NPC Conversation Lifecycle).
Доказывают, что NPC B воспринимает реплику NPC A и выбирает A целью ответа.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.epistemology import Proposition, Predicate, EpistemicContext
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver
from app.services.npc.decision_hub import DecisionHub


def test_epistemic_context_captures_source_id():
    """
    Сценарий: EpistemicContextResolver извлекает source_id из записей.
    Ожидаемое поведение: trigger_source_id и claim_source_id заполнены корректно.
    """
    from app.services.npc.epistemic_store import EpistemicStore, EpistemicRecord
    
    store = EpistemicStore()
    
    # NPC A оскорбил NPC B (высокая уверенность)
    # subject_id = npc_A, object_id = npc_B
    prop_a = Proposition(subject_id="npc_A", predicate=Predicate.INSULTED, object_id="npc_B")
    record_a = EpistemicRecord(
        agent_id="npc_B",
        proposition=prop_a,
        confidence=0.8,
        source_id="npc_A",  # Автор реплики
        source_claim_id="claim_1",
        first_observed_tick=1,
        last_updated_tick=1
    )
    store.upsert(record_a)
    
    # NPC C тоже что-то сказал про B, но в форме "npc_B помог npc_C" (subject_id = npc_B)
    # Это попадет в claims_about_self, так как subj == agent_id
    prop_c = Proposition(subject_id="npc_B", predicate=Predicate.HELPED, object_id="npc_C")
    record_c = EpistemicRecord(
        agent_id="npc_B",
        proposition=prop_c,
        confidence=0.6,  # Выше порога 0.5, но ниже, чем у A (0.8)
        source_id="npc_C",
        source_claim_id="claim_2",
        first_observed_tick=2,
        last_updated_tick=2
    )
    store.upsert(record_c)
    
    # Resolver инициализируется со store
    resolver = EpistemicContextResolver(store=store)
    context = resolver.resolve("npc_B")
    
    # Проверяем, что source_id захвачен для топ-клейма (у которого conf=0.8)
    assert context.claim_source_id == "npc_A", (
        f"Ожидался npc_A как автор топ-клейма (conf=0.8), получен {context.claim_source_id}"
    )
    assert len(context.claims_about_self) == 2, f"Ожидалось 2 клейма о себе, получено {len(context.claims_about_self)}"


def test_decision_hub_targets_speaker_for_talk():
    """
    Сценарий: DecisionHub выбирает цель для интента "talk".
    Ожидаемое поведение: Если есть claim_source_id, он возвращается как target_id.
    """
    hub = DecisionHub()
    
    state = MagicMock()
    state.npc_id = "npc_B"
    
    # Эмуляция контекста, где NPC B знает, что его оскорбил npc_A
    context = EpistemicContext(
        agent_id="npc_B",
        claims_about_self=(),
        claim_source_id="npc_A"
    )
    
    all_npcs = ["npc_A", "npc_B", "npc_C"]
    
    # Проверяем resolve_target для "talk"
    target = hub._resolve_target(
        intent="talk",
        event=MagicMock(event_type="world_tick"),
        state=state,
        all_npc_ids=all_npcs,
        epistemic_context=context
    )
    
    assert target == "npc_A", f"Ожидался npc_A как цель для talk, получен {target}"


def test_decision_hub_rejects_self_as_target():
    """
    Отрицательный сценарий: source_id совпадает с говорящим.
    Ожидаемое поведение: Адресат отклоняется, fallback не должен вернуть self.
    """
    hub = DecisionHub()
    
    state = MagicMock()
    state.npc_id = "npc_B"
    
    # Ошибка в данных: claim_source_id указывает на самого себя
    context = EpistemicContext(
        agent_id="npc_B",
        claims_about_self=(),
        claim_source_id="npc_B"  # Сам себе!
    )
    
    all_npcs = ["npc_A", "npc_B", "npc_C"]
    
    event = MagicMock()
    event.event_type = "world_tick"
    event.actor_id = None  # Явно указываем, что нет actor_id для fallback
    
    target = hub._resolve_target(
        intent="talk",
        event=event,
        state=state,
        all_npc_ids=all_npcs,
        epistemic_context=context
    )
    
    # Должен сработать fallback, но он не должен вернуть "npc_B"
    assert target != "npc_B", f"Адресат не должен быть самим собой, получен {target}"


def test_decision_hub_preserves_warn_subject_id_priority():
    """
    Сценарий: Для интента "warn" приоритет имеет subject_id пропозиции, а не source_id.
    Ожидаемое поведение: Возвращается subject_id, если он валиден.
    """
    hub = DecisionHub()
    
    state = MagicMock()
    state.npc_id = "npc_B"
    
    prop = Proposition(subject_id="npc_C", predicate=Predicate.ATTACKED, object_id="npc_B")
    context = EpistemicContext(
        agent_id="npc_B",
        trigger_proposition=prop,
        trigger_source_id="npc_A"  # npc_A рассказал, что npc_C атаковал
    )
    
    all_npcs = ["npc_A", "npc_B", "npc_C"]
    
    target = hub._resolve_target(
        intent="warn",
        event=MagicMock(event_type="world_tick"),
        state=state,
        all_npc_ids=all_npcs,
        epistemic_context=context
    )
    
    # Приоритет: subject_id (npc_C) > trigger_source_id (npc_A)
    assert target == "npc_C", f"Ожидался npc_C (subject_id) как цель для warn, получен {target}"