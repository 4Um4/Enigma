"""
path: backend/tests/sandbox/test_time_skip.py
Назначение: Тесты для TimeSkipExecutor, SignificanceDetector и SemanticMilestoneFilter.
Зависимости: pytest, time_skip_executor, domain.tick
Основные сущности: TestSignificanceDetector, TestSemanticMilestoneFilter

Запуск: cd backend; python -m pytest tests/sandbox/test_time_skip.py -v; cd ..
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

import pytest
from app.services.world.time_skip_executor import (
    SignificanceDetector,
    SemanticMilestoneFilter
)
from app.domain.tick import TickResultDTO

@pytest.fixture
def detector():
    return SignificanceDetector()

@pytest.fixture
def milestone_filter():
    return SemanticMilestoneFilter()

def make_dto(events=None):
    return TickResultDTO(status="ok", significant_events=events or [])

def test_npc_death_detected(detector):
    tick = 5
    dto = make_dto()
    prev_npcs = [{"npc_id": "npc1", "body_state": {"life_status": "ALIVE"}}]
    curr_npcs = [{"npc_id": "npc1", "body_state": {"life_status": "DEAD"}}]
    
    result = detector.check(tick, dto, prev_npcs, curr_npcs)
    
    assert result is not None
    assert result.type == "npc_death"
    assert result.tick == tick
    assert result.details["npc_id"] == "npc1"

def test_trauma_event_detected(detector):
    tick = 10
    dto = make_dto()
    prev_npcs = [{"npc_id": "npc2", "psyche": {"identity_integrity": 0.5}}]
    curr_npcs = [{"npc_id": "npc2", "psyche": {"identity_integrity": 0.2}}]
    
    result = detector.check(tick, dto, prev_npcs, curr_npcs)
    
    assert result is not None
    assert result.type == "trauma_event"
    assert result.tick == tick
    assert result.details["prev"] == 0.5
    assert result.details["curr"] == 0.2

def test_no_significant_event(detector):
    tick = 15
    dto = make_dto()
    prev_npcs = [{"npc_id": "npc3", "body_state": {"life_status": "ALIVE"}, "psyche": {"identity_integrity": 0.8}}]
    curr_npcs = [{"npc_id": "npc3", "body_state": {"life_status": "ALIVE"}, "psyche": {"identity_integrity": 0.7}}]
    
    result = detector.check(tick, dto, prev_npcs, curr_npcs)
    
    assert result is None

def test_milestone_drive_formation(milestone_filter):
    tick = 100
    dto = make_dto()
    context = {"child_id": "child1"}
    prev_npcs = [{"npc_id": "child1", "drives": {"control": 0.2}}]
    curr_npcs = [{"npc_id": "child1", "drives": {"control": 0.3}}]
    
    result = milestone_filter.check(tick, dto, prev_npcs, curr_npcs, context)
    
    assert result is not None
    assert result.type == "personality_trait_formed"
    assert result.requires_playback is True
    assert result.details["drive"] == "control"

def test_milestone_no_change(milestone_filter):
    tick = 200
    dto = make_dto()
    context = {"child_id": "child1"}
    prev_npcs = [{"npc_id": "child1", "drives": {"control": 0.2}}]
    curr_npcs = [{"npc_id": "child1", "drives": {"control": 0.22}}]
    
    result = milestone_filter.check(tick, dto, prev_npcs, curr_npcs, context)
    
    assert result is None