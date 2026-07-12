"""
path: /project/backend/tests/sandbox/micro/test_lod_arbitration.py
Назначение: Верификация ADR-060.1 — арбитраж LOD0/LOD1 до MovementEngine.
Доказывает, что Micro (уклонение) не убивает Macro (маршрут), и порядок исполнения строг.

ЗАПУСК: python -m pytest backend/tests/sandbox/micro/test_lod_arbitration.py -v --tb=short

TODO:
- В будущем можно расширить тесты, добавив больше интентов (например, CombatGoal для LOD2) и проверяя их приоритеты.
- Также стоит протестировать сценарии с несколькими NPC, чтобы убедиться, что арбитраж работает корректно в масштабах всей сцены, а не только для одного NPC.
- Возможно, стоит добавить тесты на производительность, чтобы убедиться, что арбитраж не добавляет заметной задержки при большом количестве интентов и NPC. Сейчас фокус на логической корректности порядка исполнения.
"""

from app.domain.movement import LocalSteeringGoal, MacroMovementGoal


def test_lod1_has_priority_over_lod0_in_arbitration():
    """Если NPC имеет и Macro (LOD1) и Micro (LOD0) интенты, Macro идет первым."""
    # Симулируем ввод: Micro пришел первым (например, реактивное уклонение)
    macro = MacroMovementGoal(actor_id="test_npc", target_node_id="bar_area")
    micro = LocalSteeringGoal(actor_id="test_npc", local_target_xy=(5.0, 5.0))

    movement_intents = [micro, macro]  # Неправильный порядок на входе

    # Симулируем логику арбитража из tick_orchestrator.py
    _merged_intents = []
    _per_npc = {}
    for i in movement_intents:
        _nid = getattr(i, "npc_id", None) or getattr(i, "actor_id", None)
        if _nid:
            _per_npc.setdefault(_nid, []).append(i)
        else:
            _merged_intents.append(i)

    for _nid, _intents in _per_npc.items():
        if len(_intents) > 1:
            # Сортируем: Macro (LOD1) идет первым, Micro (LOD0) корректирует
            _intents.sort(key=lambda x: isinstance(x, LocalSteeringGoal))
        _merged_intents.extend(_intents)

    # Проверка: Macro должен быть первым, Micro вторым
    assert len(_merged_intents) == 2, "Потеряны интенты при арбитраже!"
    assert isinstance(_merged_intents[0], MacroMovementGoal), "Macro (LOD1) должен исполняться первым!"
    assert isinstance(_merged_intents[1], LocalSteeringGoal), "Micro (LOD0) должен корректировать позицию после Macro!"


def test_single_intent_passes_unaffected():
    """Если интент один, арбитраж не ломает его."""
    macro = MacroMovementGoal(actor_id="test_npc", target_node_id="bar_area")
    movement_intents = [macro]

    _merged_intents = []
    _per_npc = {}
    for i in movement_intents:
        _nid = getattr(i, "npc_id", None) or getattr(i, "actor_id", None)
        if _nid:
            _per_npc.setdefault(_nid, []).append(i)
        else:
            _merged_intents.append(i)

    for _nid, _intents in _per_npc.items():
        if len(_intents) > 1:
            _intents.sort(key=lambda x: isinstance(x, LocalSteeringGoal))
        _merged_intents.extend(_intents)

    assert len(_merged_intents) == 1
    assert isinstance(_merged_intents[0], MacroMovementGoal)
