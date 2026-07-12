"""
Rule 57 (ADR-130): Schedule НЕ перезаписывает активный reactive traversal.
Traversal = commitment, schedule = suggestion. Если NPC в статусе MOVING,
update_routine ДОЛЖЕН вернуть ([], None), не создавая schedule intent.

Запуск:cd backend; python -m pytest tests/sandbox/movement/ -v --tb=short; cd ..

TODO:

"""

from app.services.npc.life_engine import LifeEngine


def test_movement_lock_blocks_schedule_on_active_traversal():
    """
    Сценарий G1: NPC идёт к игроку (reactive:approach), но наступило время
    смены активности по расписанию. LifeEngine НЕ должен перезаписать транзит.
    """
    engine = LifeEngine()

    # NPC с расписанием в формате dict (time_range → activity)
    # Реальный формат: {"08:00-18:00": "patrol"} — _get_current_activity использует .items()
    npc = {
        "id": "guard_1",  # LifeEngine использует npc.get("id"), не "npc_id" (строка 1225)
        "npc_id": "guard_1",
        "routine": {"current": "sleeping", "schedule": {"08:00-18:00": "patrol"}},
        "location": "barracks",
    }

    # scene_state с активным транзитом (reactive:approach к игроку)
    scene_state_with_lock = {
        "active_traversals": {
            "guard_1": {"status": "MOVING", "target_node": "player", "source_node": "barracks", "progress": 0.4}
        }
    }

    # Вызов update_routine с time="10:00" (внутри диапазона расписания)
    changes, intent = engine.update_routine(npc=npc, current_time="10:00", tick=1, scene_state=scene_state_with_lock)

    # VERDICT: Schedule заблокирован. Нет новых SceneChange и нет schedule intent.
    assert changes == [], f"Movement Lock нарушен! Созданы SceneChange: {changes}"
    assert intent is None, f"Movement Lock нарушен! Создан schedule intent: {intent}"


def test_schedule_allowed_when_no_active_traversal():
    """
    Обратный кейс: если транзита НЕТ, расписание должно работать штатно.
    """
    engine = LifeEngine()

    npc = {
        "id": "guard_1",  # LifeEngine использует npc.get("id"), не "npc_id" (строка 1225)
        "npc_id": "guard_1",
        "routine": {"current": "sleeping", "schedule": {"08:00-18:00": "patrol"}},
        "location": "barracks",
    }

    # scene_state БЕЗ активных транзитов
    scene_state_no_lock = {"active_traversals": {}}

    changes, intent = engine.update_routine(npc=npc, current_time="10:00", tick=1, scene_state=scene_state_no_lock)

    # VERDICT: Расписание отработало (создан intent или changes)
    # Intent может не создаться если location совпадает, но точно не должен быть заблокирован
    assert not (changes == [] and intent is None), "Расписание заблокировано без активного транзита!"
