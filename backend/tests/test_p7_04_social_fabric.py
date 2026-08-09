"""
Файл: backend/tests/test_p7_04_social_fabric.py
Назначение: Проверка матрицы отношений и истории дельт.

Запуск: cd backend; python -m pytest tests/test_p7_04_social_fabric.py -v -s; cd ..
"""

import pytest
from app.models.social_fabric import RelationshipSnapshot
from app.services.social.social_fabric_tracker import SocialFabricTracker


class TestP704SocialFabric:
    """P7-04: Тесты матрицы социальной ткани (строгие инварианты)."""

    @pytest.fixture
    def tracker(self) -> SocialFabricTracker:
        t = SocialFabricTracker()
        t.set_baseline("maid_lusya", "player", RelationshipSnapshot(
            source_id="maid_lusya", target_id="player", trust=20.0, fear=10.0, affection=0.0, debt=0.0, respect=10.0
        ))
        return t

    def test_snapshot_validation(self):
        """Инвариант: Невалидные значения отклоняются."""
        with pytest.raises(ValueError):
            RelationshipSnapshot("A", "B", trust=101.0, fear=0.0, affection=0.0, debt=0.0, respect=0.0)
        with pytest.raises(ValueError):
            RelationshipSnapshot("A", "B", trust=0.0, fear=-1.0, affection=0.0, debt=0.0, respect=0.0)
        with pytest.raises(ValueError):
            RelationshipSnapshot("A", "A", trust=0.0, fear=0.0, affection=0.0, debt=0.0, respect=0.0)

    def test_baseline_is_immutable(self, tracker: SocialFabricTracker):
        """V8-MVP-9 FIX: Baseline идемпотентен (перезапись тихо игнорируется)."""
        tracker.set_baseline("maid_lusya", "player", RelationshipSnapshot(
            source_id="maid_lusya", target_id="player", trust=50.0, fear=0.0, affection=0.0, debt=0.0, respect=0.0
        ))
        # Проверяем, что оригинальный baseline не перезаписан
        assert tracker.get_current("maid_lusya", "player").trust == 20.0

    def test_directional_independence(self, tracker: SocialFabricTracker):
        """Инвариант: A->B != B->A."""
        tracker.set_baseline("player", "maid_lusya", RelationshipSnapshot(
            source_id="player", target_id="maid_lusya", trust=80.0, fear=0.0, affection=0.0, debt=0.0, respect=0.0
        ))
        assert tracker.get_current("maid_lusya", "player").trust == 20.0
        assert tracker.get_current("player", "maid_lusya").trust == 80.0

    def test_baseline_isolation_from_current(self, tracker: SocialFabricTracker):
        """Инвариант: Изменения current не затрагивают baseline."""
        tracker.apply_delta(tick=1, source_id="maid_lusya", target_id="player", trust_delta=-30.0, cause="blackmail")
        assert tracker.get_current("maid_lusya", "player").trust == -10.0
        # Проверяем, что baseline не изменился
        assert tracker._baseline[("maid_lusya", "player")].trust == 20.0

    def test_apply_delta_updates_current(self, tracker: SocialFabricTracker):
        """Дельта обновляет текущее состояние."""
        tracker.apply_delta(tick=1, source_id="maid_lusya", target_id="player", trust_delta=-30.0, fear_delta=20.0, cause="blackmail")
        
        snap = tracker.get_current("maid_lusya", "player")
        assert snap.trust == -10.0 # 20 - 30
        assert snap.fear == 30.0   # 10 + 20

    def test_apply_delta_clamps_values(self, tracker: SocialFabricTracker):
        """Значения ограничиваются диапазонами (-100..100, 0..100)."""
        tracker.apply_delta(tick=1, source_id="maid_lusya", target_id="player", trust_delta=-200.0, fear_delta=200.0)
        
        snap = tracker.get_current("maid_lusya", "player")
        assert snap.trust == -100.0
        assert snap.fear == 100.0

    def test_delta_history_recorded(self, tracker: SocialFabricTracker):
        """История изменений сохраняется."""
        tracker.apply_delta(tick=1, source_id="maid_lusya", target_id="player", trust_delta=-10.0, cause="action1")
        tracker.apply_delta(tick=2, source_id="guard_borko", target_id="player", fear_delta=10.0, cause="action2")
        
        all_deltas = tracker.get_all_deltas()
        assert len(all_deltas) == 2
        
        lusya_deltas = tracker.get_deltas_for("maid_lusya", "player")
        assert len(lusya_deltas) == 1
        assert lusya_deltas[0].cause == "action1"