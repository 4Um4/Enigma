# backend/tests/micro/test_recursive_attribution.py
"""
Тесты рекурсивной модели атрибуции убеждений (EPISTEMIC-005).
"""

import pytest
from app.domain.epistemology import Proposition, Predicate, AttributedBelief, EpistemicRecord
from app.services.npc.epistemic_store import EpistemicStore


class TestRecursiveAttribution:
    """Тесты рекурсивной модели атрибуции убеждений (EPISTEMIC-005)."""
    
    def test_first_order_belief(self):
        """Собственное убеждение агента (без атрибуции)."""
        prop = Proposition(subject_id="C", predicate=Predicate.STOLE, object_id="X")
        record = EpistemicRecord(
            agent_id="A",
            proposition=prop,
            confidence=0.8,
            source_id="direct_observation",
            source_claim_id="claim_1",
            first_observed_tick=100,
            last_updated_tick=100,
            attribution_chain=None
        )
        
        assert record.attribution_chain is None
        assert record.proposition == prop
    
    def test_depth_1_attribution(self):
        """Атрибуция глубины 1: A верит, что B верит в X."""
        prop = Proposition(subject_id="C", predicate=Predicate.STOLE, object_id="X")
        chain = AttributedBelief(holder_id="B", content=prop)
        
        record = EpistemicRecord(
            agent_id="A",
            proposition=prop,
            confidence=0.7,
            source_id="B",
            source_claim_id="claim_2",
            first_observed_tick=100,
            last_updated_tick=100,
            attribution_chain=chain
        )
        
        assert record.attribution_chain is not None
        assert record.attribution_chain.holder_id == "B"
        assert record.attribution_chain.content == prop
    
    def test_depth_2_attribution(self):
        """Атрибуция глубины 2: A верит, что B верит, что C верит в X."""
        prop = Proposition(subject_id="D", predicate=Predicate.STOLE, object_id="Y")
        inner_chain = AttributedBelief(holder_id="C", content=prop)
        outer_chain = AttributedBelief(holder_id="B", content=inner_chain)
        
        record = EpistemicRecord(
            agent_id="A",
            proposition=prop,
            confidence=0.6,
            source_id="B",
            source_claim_id="claim_3",
            first_observed_tick=100,
            last_updated_tick=100,
            attribution_chain=outer_chain
        )
        
        assert record.attribution_chain.holder_id == "B"
        assert record.attribution_chain.content.holder_id == "C"
        assert record.attribution_chain.content.content == prop
    
    def test_depth_5_attribution(self):
        """Атрибуция глубины 5: A → B → C → D → E → X."""
        prop = Proposition(subject_id="F", predicate=Predicate.HELPED, object_id="G")
        
        # Строим цепочку снизу вверх
        current = prop
        for holder in ["E", "D", "C", "B"]:
            current = AttributedBelief(holder_id=holder, content=current)
        
        record = EpistemicRecord(
            agent_id="A",
            proposition=prop,
            confidence=0.5,
            source_id="B",
            source_claim_id="claim_4",
            first_observed_tick=100,
            last_updated_tick=100,
            attribution_chain=current
        )
        
        # Проверяем структуру
        chain = record.attribution_chain
        assert chain.holder_id == "B"
        assert chain.content.holder_id == "C"
        assert chain.content.content.holder_id == "D"
        assert chain.content.content.content.holder_id == "E"
        assert chain.content.content.content.content == prop
    
    def test_large_depth_attribution(self):
        """Атрибуция значительной глубины (50 уровней) — проверка отсутствия лимита."""
        prop = Proposition(subject_id="Z", predicate=Predicate.ATTACKED, object_id="W")
        
        # Строим цепочку из 50 уровней
        current = prop
        for i in range(50):
            current = AttributedBelief(holder_id=f"agent_{i}", content=current)
        
        record = EpistemicRecord(
            agent_id="root",
            proposition=prop,
            confidence=0.3,
            source_id="agent_49",
            source_claim_id="claim_5",
            first_observed_tick=100,
            last_updated_tick=100,
            attribution_chain=current
        )
        
        # Проверяем, что цепочка не обрезана
        depth = 0
        chain = record.attribution_chain
        while hasattr(chain, 'content') and isinstance(chain.content, AttributedBelief):
            depth += 1
            chain = chain.content
        assert depth == 49  # 50 уровней минус 1 (последний holder верит в proposition)
    
    def test_round_trip_serialization(self):
        """Round-trip сериализации без потери данных."""
        prop = Proposition(subject_id="C", predicate=Predicate.STOLE, object_id="X")
        inner_chain = AttributedBelief(holder_id="C", content=prop)
        outer_chain = AttributedBelief(holder_id="B", content=inner_chain)
        
        original = EpistemicRecord(
            agent_id="A",
            proposition=prop,
            confidence=0.75,
            source_id="B",
            source_claim_id="claim_6",
            first_observed_tick=100,
            last_updated_tick=150,
            source_type="testimony",
            original_source_id="C",
            seen_claim_ids=("claim_6", "claim_7"),
            attribution_chain=outer_chain
        )
        
        # Сериализация
        data = original.to_dict()
        
        # Десериализация
        restored = EpistemicRecord.from_dict(data)
        
        # Проверка эквивалентности
        assert restored.agent_id == original.agent_id
        assert restored.proposition == original.proposition
        assert restored.confidence == original.confidence
        assert restored.source_id == original.source_id
        assert restored.source_claim_id == original.source_claim_id
        assert restored.first_observed_tick == original.first_observed_tick
        assert restored.last_updated_tick == original.last_updated_tick
        assert restored.source_type == original.source_type
        assert restored.original_source_id == original.original_source_id
        assert restored.seen_claim_ids == original.seen_claim_ids
        assert restored.attribution_chain is not None
        assert restored.attribution_chain.holder_id == "B"
        assert restored.attribution_chain.content.holder_id == "C"
        assert restored.attribution_chain.content.content == prop
    
    def test_backward_compatibility_old_format(self):
        """Десериализация старого формата без attribution_chain."""
        old_data = {
            "agent_id": "A",
            "proposition": {
                "subject_id": "B",
                "predicate": "stole",
                "object_id": "X",
                "polarity": True
            },
            "confidence": 0.8,
            "source_id": "direct",
            "source_claim_id": "claim_old",
            "first_observed_tick": 100,
            "last_updated_tick": 100,
            "source_type": "",
            "original_source_id": "",
            "seen_claim_ids": []
            # Нет ключа "attribution_chain"
        }
        
        record = EpistemicRecord.from_dict(old_data)
        
        assert record.agent_id == "A"
        assert record.proposition.subject_id == "B"
        assert record.confidence == 0.8
        assert record.attribution_chain is None
    
    def test_proposition_chain_mismatch_rejected(self):
        """Несовпадение proposition и содержания цепочки должно быть отклонено."""
        prop_x = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="item")
        prop_y = Proposition(subject_id="Y", predicate=Predicate.STOLE, object_id="item")
        
        # Цепочка описывает prop_y, но proposition = prop_x
        chain = AttributedBelief(holder_id="B", content=prop_y)
        
        with pytest.raises(ValueError, match="invariant violation"):
            EpistemicRecord(
                agent_id="A",
                proposition=prop_x,
                confidence=0.7,
                source_id="B",
                source_claim_id="claim_mismatch",
                first_observed_tick=100,
                last_updated_tick=100,
                attribution_chain=chain
            )
    
    def test_holder_id_repetition_allowed(self):
        """Повторение holder_id в цепочке допустимо."""
        prop = Proposition(subject_id="Z", predicate=Predicate.HELPED, object_id="W")
        
        # B появляется дважды в цепочке
        inner = AttributedBelief(holder_id="B", content=prop)
        outer = AttributedBelief(holder_id="B", content=inner)
        
        # Это должно работать без ошибок
        record = EpistemicRecord(
            agent_id="A",
            proposition=prop,
            confidence=0.6,
            source_id="B",
            source_claim_id="claim_repeat",
            first_observed_tick=100,
            last_updated_tick=100,
            attribution_chain=outer
        )
        
        assert record.attribution_chain.holder_id == "B"
        assert record.attribution_chain.content.holder_id == "B"
    
    def test_structural_cycle_protection(self):
        """Защита от структурного цикла при создании записи (fail-fast)."""
        prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="Y")
        
        # Создаём цепочку
        chain1 = AttributedBelief(holder_id="B", content=prop)
        chain2 = AttributedBelief(holder_id="C", content=chain1)
        
        # Пытаемся создать цикл через object.__setattr__ (обход frozen)
        # Это искусственный сценарий для проверки защиты
        object.__setattr__(chain1, 'content', chain2)
        
        # Создание EpistemicRecord должно упасть, так как __post_init__ 
        # вызывает _get_atomic_content, который обнаруживает цикл.
        with pytest.raises(ValueError, match="Structural cycle detected"):
            EpistemicRecord(
                agent_id="A",
                proposition=prop,
                confidence=0.7,
                source_id="B",
                source_claim_id="claim_cycle",
                first_observed_tick=100,
                last_updated_tick=100,
                attribution_chain=chain2
            )
    def test_two_records_same_proposition_different_chains(self):
        """Две записи с одинаковым proposition, но разными цепочками не перезаписывают друг друга."""
        prop = Proposition(subject_id="X", predicate=Predicate.STOLE, object_id="item")
        
        chain_b = AttributedBelief(holder_id="B", content=prop)
        chain_c = AttributedBelief(holder_id="C", content=prop)
        
        record_ab = EpistemicRecord(
            agent_id="A",
            proposition=prop,
            confidence=0.7,
            source_id="B",
            source_claim_id="claim_ab",
            first_observed_tick=100,
            last_updated_tick=100,
            attribution_chain=chain_b
        )
        
        record_ac = EpistemicRecord(
            agent_id="A",
            proposition=prop,
            confidence=0.6,
            source_id="C",
            source_claim_id="claim_ac",
            first_observed_tick=100,
            last_updated_tick=100,
            attribution_chain=chain_c
        )
        
        store = EpistemicStore()
        store.upsert(record_ab)
        store.upsert(record_ac)
        
        # Обе записи должны сохраниться
        all_records = store.get_all_for_agent("A")
        assert len(all_records) == 2
        
        # Точный поиск должен работать
        found_ab = store.get("A", prop, chain_b)
        assert found_ab is not None
        assert found_ab.attribution_chain.holder_id == "B"
        
        found_ac = store.get("A", prop, chain_c)
        assert found_ac is not None
        assert found_ac.attribution_chain.holder_id == "C"
    
    def test_epistemic_store_no_regression(self):
        """Отсутствие регрессий старого EpistemicStore."""
        prop = Proposition(subject_id="B", predicate=Predicate.STOLE, object_id="X")
        
        record = EpistemicRecord(
            agent_id="A",
            proposition=prop,
            confidence=0.8,
            source_id="direct",
            source_claim_id="claim_old",
            first_observed_tick=100,
            last_updated_tick=100
        )
        
        store = EpistemicStore()
        store.upsert(record)
        
        # Старый API должен работать
        found = store.get("A", prop)
        assert found is not None
        assert found.confidence == 0.8
        
        # Топ-1 по confidence
        top = store.get("A")
        assert top is not None
        assert top == record
        
        # Сериализация/десериализация
        data = store.to_dict()
        restored_store = EpistemicStore.from_dict(data)
        restored_record = restored_store.get("A", prop)
        assert restored_record is not None
        assert restored_record.confidence == 0.8