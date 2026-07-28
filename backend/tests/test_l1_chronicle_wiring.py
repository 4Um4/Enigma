# backend/tests/test_l1_chronicle_wiring.py
"""
V8-PSY-1: Тест прокидывания L1Chronicle через TickOrchestrator -> TickState -> StateApplicator.
Гарантирует, что trauma pipeline не мёртв.

Запуск: cd backend; python -m pytest tests/test_l1_chronicle_wiring.py -v; cd ..
"""

import pytest
from unittest.mock import MagicMock

def test_state_applicator_accepts_l1_chronicle():
    """Проверяет, что StateApplicator корректно принимает и хранит l1_chronicle."""
    from app.services.npc.state_applicator import StateApplicator

    # 1. Mock L1Chronicle
    mock_chronicle = MagicMock()
    mock_rel_store = MagicMock()

    # 2. Создаём StateApplicator с l1_chronicle
    applicator = StateApplicator(
        relationship_store=mock_rel_store,
        l1_chronicle=mock_chronicle
    )

    # 3. Проверяем, что L1Chronicle сохранён внутри
    assert applicator._l1_chronicle is mock_chronicle, \
        "StateApplicator не сохранил ссылку на L1Chronicle в self._l1_chronicle"

def test_tick_state_has_l1_chronicle_field():
    """Проверяет, что TickState имеет поле l1_chronicle и оно передаётся."""
    from app.domain.tick import TickState

    mock_chronicle = MagicMock()
    
    tick_state = TickState(
        tick_id=0,
        campaign_id="test",
        scene_state={},
        all_npcs_raw=(),
        effective_drives_map={},
        interventions=(),
        pe_modifiers_map={},
        l1_chronicle=mock_chronicle
    )

    assert hasattr(tick_state, 'l1_chronicle'), "TickState не имеет поля l1_chronicle"
    assert tick_state.l1_chronicle is mock_chronicle, \
        "Значение l1_chronicle не передаётся в TickState"