"""
Интеграционные тесты EPISTEMIC-005-07: разделение прямых и атрибутированных убеждений.
"""
import pytest
from app.domain.epistemology import Proposition, Predicate, AttributedBelief, EpistemicRecord, EpistemicContext
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver


class MockReliability:
    def get_reliability(self, observer, source, context=None):
        return 0.8


class TestEpistemicAttributionIntegration:
    """Тесты интеграции атрибутированных убеждений с EpistemicContext и DecisionHub."""
    
    @pytest.fixture
    def store_and_resolver(self):
        store = EpistemicStore()
        resolver = EpistemicContextResolver(store)
        return store, resolver

    def _make_direct_record(self, subject, obj, conf):
        prop = Proposition(subject_id=subject, predicate=Predicate.STOLE, object_id=obj)
        return EpistemicRecord(
            agent_id="npc_a", proposition=prop, confidence=conf,
            source_id="direct", source_claim_id=f"dir_{subject}",
            first_observed_tick=100, last_updated_tick=100,
            attribution_chain=None
        )

    def _make_attributed_record(self, holder, subject, obj, conf):
        prop = Proposition(subject_id=subject, predicate=Predicate.STOLE, object_id=obj)
        chain = AttributedBelief(holder_id=holder, content=prop)
        return EpistemicRecord(
            agent_id="npc_a", proposition=prop, confidence=conf,
            source_id=holder, source_claim_id=f"attr_{holder}_{subject}",
            first_observed_tick=100, last_updated_tick=100,
            attribution_chain=chain
        )

    def test_first_order_belief_works_as_before(self, store_and_resolver):
        """Прямое убеждение продолжает работать как прежде."""
        store, resolver = store_and_resolver
        store.upsert(self._make_direct_record("victim", "item", 0.9))
        
        ctx = resolver.resolve("npc_a")
        
        assert len(ctx.recent_beliefs) == 1
        assert ctx.recent_beliefs[0].is_attributed is False
        assert ctx.recent_beliefs[0].confidence == 0.9
        assert len(ctx.attributed_beliefs) == 0

    def test_attributed_belief_not_in_recent_beliefs(self, store_and_resolver):
        """Атрибутированное убеждение не попадает в recent_beliefs (прямой scoring)."""
        store, resolver = store_and_resolver
        store.upsert(self._make_attributed_record("npc_b", "victim", "item", 0.95))
        
        ctx = resolver.resolve("npc_a")
        
        assert len(ctx.recent_beliefs) == 0, "Атрибуция не должна попадать в recent_beliefs"
        assert len(ctx.attributed_beliefs) == 1
        assert ctx.attributed_beliefs[0].is_attributed is True

    def test_attributed_belief_preserved_in_context(self, store_and_resolver):
        """Атрибутированное убеждение сохраняется в отдельном поле контекста."""
        store, resolver = store_and_resolver
        store.upsert(self._make_attributed_record("npc_b", "victim", "item", 0.8))
        
        ctx = resolver.resolve("npc_a")
        
        assert len(ctx.attributed_beliefs) == 1
        assert ctx.attributed_beliefs[0].subject_id == "victim"
        assert ctx.attributed_beliefs[0].confidence == 0.8

    def test_belief_summary_is_attributed_flag(self, store_and_resolver):
        """BeliefSummary корректно отражает тип записи через is_attributed."""
        store, resolver = store_and_resolver
        store.upsert(self._make_direct_record("victim1", "item1", 0.9))
        store.upsert(self._make_attributed_record("npc_b", "victim2", "item2", 0.8))
        
        ctx = resolver.resolve("npc_a")
        
        assert any(b.is_attributed is False for b in ctx.recent_beliefs)
        assert all(b.is_attributed is True for b in ctx.attributed_beliefs)

    def test_attributed_does_not_displace_direct(self, store_and_resolver):
        """Атрибутированные убеждения с высоким confidence не вытесняют прямые из Top-3."""
        store, resolver = store_and_resolver
        
        # 3 атрибутированных с очень высоким confidence
        store.upsert(self._make_attributed_record("b1", "v1", "i1", 0.99))
        store.upsert(self._make_attributed_record("b2", "v2", "i2", 0.98))
        store.upsert(self._make_attributed_record("b3", "v3", "i3", 0.97))
        
        # 1 прямое с низким confidence
        store.upsert(self._make_direct_record("v_direct", "i_direct", 0.50))
        
        ctx = resolver.resolve("npc_a")
        
        # Прямое убеждение должно быть в recent_beliefs, несмотря на низкий confidence
        assert len(ctx.recent_beliefs) == 1
        assert ctx.recent_beliefs[0].subject_id == "v_direct"
        assert ctx.recent_beliefs[0].is_attributed is False
        
        # Атрибутированные должны быть в отдельном списке
        assert len(ctx.attributed_beliefs) == 3

    def test_mixed_context_processed_correctly(self, store_and_resolver):
        """Смешанный контекст с обоими типами записей обрабатывается корректно."""
        store, resolver = store_and_resolver
        
        store.upsert(self._make_direct_record("v1", "i1", 0.9))
        store.upsert(self._make_direct_record("v2", "i2", 0.8))
        store.upsert(self._make_attributed_record("b1", "v3", "i3", 0.95))
        store.upsert(self._make_attributed_record("b2", "v4", "i4", 0.85))
        
        ctx = resolver.resolve("npc_a")
        
        assert len(ctx.recent_beliefs) == 2
        assert len(ctx.attributed_beliefs) == 2
        assert all(not b.is_attributed for b in ctx.recent_beliefs)
        assert all(b.is_attributed for b in ctx.attributed_beliefs)

    def test_attributed_not_in_trigger_or_report(self, store_and_resolver):
        """Атрибутированное убеждение не становится прямым триггером или репортом."""
        store, resolver = store_and_resolver
        
        # Прямая угроза (должна стать триггером)
        prop_direct = Proposition(subject_id="enemy", predicate=Predicate.ATTACKED, object_id="npc_a")
        rec_direct = EpistemicRecord(
            agent_id="npc_a", proposition=prop_direct, confidence=0.9,
            source_id="direct", source_claim_id="dir_attack",
            first_observed_tick=100, last_updated_tick=100, attribution_chain=None
        )
        store.upsert(rec_direct)
        
        # Атрибутированная угроза (НЕ должна стать триггером)
        prop_attr = Proposition(subject_id="enemy2", predicate=Predicate.ATTACKED, object_id="npc_a")
        chain = AttributedBelief(holder_id="npc_b", content=prop_attr)
        rec_attr = EpistemicRecord(
            agent_id="npc_a", proposition=prop_attr, confidence=0.99, # Выше, чем у прямой!
            source_id="npc_b", source_claim_id="attr_attack",
            first_observed_tick=100, last_updated_tick=100, attribution_chain=chain
        )
        store.upsert(rec_attr)
        
        ctx = resolver.resolve("npc_a")
        
        # Триггером должна стать прямая угроза, несмотря на меньший confidence
        assert ctx.trigger_proposition is not None
        assert ctx.trigger_proposition.subject_id == "enemy"
        
        # Атрибутированная должна остаться только в attributed_beliefs
        assert len(ctx.attributed_beliefs) == 1
        assert ctx.attributed_beliefs[0].subject_id == "enemy2"

    def test_no_regression_for_legacy_tests(self, store_and_resolver):
        """Отсутствие регрессий: контекст без атрибуции работает как раньше."""
        store, resolver = store_and_resolver
        store.upsert(self._make_direct_record("v1", "i1", 0.9))
        store.upsert(self._make_direct_record("v2", "i2", 0.8))
        store.upsert(self._make_direct_record("v3", "i3", 0.7))
        store.upsert(self._make_direct_record("v4", "i4", 0.6))
        
        ctx = resolver.resolve("npc_a")
        
        # Top-3 работает
        assert len(ctx.recent_beliefs) == 3
        assert ctx.recent_beliefs[0].confidence == 0.9
        assert ctx.recent_beliefs[2].confidence == 0.7
        
        # attributed_beliefs пуст
        assert hasattr(ctx, 'attributed_beliefs')
        assert len(ctx.attributed_beliefs) == 0
