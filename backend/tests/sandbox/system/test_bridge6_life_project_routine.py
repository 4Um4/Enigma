"""
path: /project/backend/tests/sandbox/system/test_bridge6_life_project_routine.py
Назначение: Регрессионный тест для Bridge 6 (LifeProject → schedule mutation).
            Проверяет, что кризис идентичности (LOST/SEARCHING) блокирует расписание,
            а кризисный жизненный проект (revenge) заменяет работу на отдых.
Зависимости: app.services.npc.life_engine, app.models.npc_state
Основные сущности: LifeEngine

Запуск: cd backend; python -m pytest tests/sandbox/system/test_bridge6_life_project_routine.py -v; cd ..
"""
import pytest
from app.models.npc_state import NPCState
from app.services.npc.life_engine import LifeEngine


@pytest.fixture
def life_engine():
    return LifeEngine()

def _make_npc(life_project: str = "family_builder", life_project_state: str = "ACTIVE"):
    return {
        "id": "test_npc",
        "position": "main_hall",
        "location_id": "tavern_silver_wolf",
        "routine": {
            "schedule": {"08:00-20:00": "working", "20:00-08:00": "sleeping"},
            "current": "sleeping",
            "mood": "neutral"
        },
        "activity_map": {
            "resting": {
                "location": "tavern_silver_wolf",
                "position": "fireplace",
                "display": "resting"
            },
            "working": {
                "location": "tavern_silver_wolf",
                "position": "main_hall",
                "display": "working"
            }
        },
        "psyche": {
            "life_project": life_project,
            "life_project_state": life_project_state
        },
        "core_orientation": life_project
    }

def test_lost_state_bypasses_schedule(life_engine):
    """Если NPC в состоянии LOST, он игнорирует расписание (working)."""
    npc = _make_npc(life_project_state="LOST")
    changes, intent = life_engine.update_routine(npc, "12:00", tick=10)
    
    assert changes == [], "LOST state should bypass schedule entirely (no changes)"
    assert intent is None, "LOST state should not generate movement intent"
    assert npc["routine"]["current"] == "sleeping", "Routine should not be mutated to working"

def test_searching_state_bypasses_schedule(life_engine):
    """Если NPC в состоянии SEARCHING, он игнорирует расписание (working)."""
    npc = _make_npc(life_project_state="SEARCHING")
    changes, intent = life_engine.update_routine(npc, "12:00", tick=10)
    
    assert changes == [], "SEARCHING state should bypass schedule entirely (no changes)"
    assert intent is None, "SEARCHING state should not generate movement intent"
    assert npc["routine"]["current"] == "sleeping", "Routine should not be mutated to working"

def test_revenge_project_overrides_working_to_resting(life_engine):
    """Если life_project=revenge, работа (working) заменяется на отдых (resting)."""
    npc = _make_npc(life_project="revenge", life_project_state="ACTIVE")
    changes, intent = life_engine.update_routine(npc, "12:00", tick=10)
    
    # Проверяем, что активность сменилась на resting
    _routine = npc.get("routine", {})
    assert _routine.get("current") == "resting", "Revenge project should fallback working to resting"
    
    # Проверяем, что интент нацелен на отдых
    assert intent is not None, "Intent should be generated for resting"
    assert "resting" in intent.reason, f"Expected resting reason, got {intent.reason}"