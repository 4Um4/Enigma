"""
Файл: backend/tests/sandbox/system/test_temporal_reconciliation.py
Назначение: Верификация аналитического согласования (Temporal Reconciliation)
Зависимости: app.services.npc.life_engine
Основные сущности: TestTemporalReconciliation

Запуск: pytest -v backend/tests/sandbox/system/test_temporal_reconciliation.py

TODO:
- Добавить тесты для других аспектов психики и состояния тела, если они будут добавлены в будущем.
"""

import pytest
from app.services.npc.life_engine import LifeEngine


class TestTemporalReconciliation:
    """ADR-047: Аналитический декэй вместо ретро-симуляции."""

    def setup_method(self):
        self.engine = LifeEngine()

    def test_zero_elapsed_no_changes(self):
        npc = {"npc_id": "test", "psyche": {"stress": 50.0}, "body_state": {"hunger": 10.0, "fatigue": 10.0}}
        self.engine._npc_cache["camp"] = [npc]

        self.engine.reconcile_state("camp", 0.0)

        assert npc["psyche"]["stress"] == 50.0
        assert npc["body_state"]["hunger"] == 10.0

    def test_stress_exponential_decay(self):
        npc = {"npc_id": "test", "psyche": {"stress": 80.0}, "body_state": {}}
        self.engine._npc_cache["camp"] = [npc]

        # 100 секунд = 10 тиков. decay_rate = 0.05
        # S_t = 0 + (80 - 0) * (1 - 0.05)^10 = 80 * 0.95^10 = 80 * 0.5987 = 47.9
        self.engine.reconcile_state("camp", 100.0)

        assert npc["psyche"]["stress"] < 80.0
        assert npc["psyche"]["stress"] == pytest.approx(47.9, abs=0.5)

    def test_hunger_fatigue_linear_growth(self):
        npc = {"npc_id": "test", "psyche": {}, "body_state": {"hunger": 0.0, "fatigue": 0.0}}
        self.engine._npc_cache["camp"] = [npc]

        # 100 секунд = 10 тиков. rate = 0.1/тик
        # hunger = 0.0 + 0.1 * 10 = 1.0
        self.engine.reconcile_state("camp", 100.0)

        assert npc["body_state"]["hunger"] == pytest.approx(1.0, abs=0.1)
        assert npc["body_state"]["fatigue"] == pytest.approx(1.0, abs=0.1)

    def test_hunger_capped_at_100(self):
        npc = {"npc_id": "test", "psyche": {}, "body_state": {"hunger": 99.9, "fatigue": 0.0}}
        self.engine._npc_cache["camp"] = [npc]

        # Огромное прошедшее время, но голод не должен превысить 100
        self.engine.reconcile_state("camp", 86400.0)

        assert npc["body_state"]["hunger"] == 100.0
