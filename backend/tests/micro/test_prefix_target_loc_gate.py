# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/micro/test_prefix_target_loc_gate.py
Назначение: замок фикса S276 (prefix-authoritative target_loc). До фикса
    cross-loc intent с префиксованной целью и location_id == текущей локации
    обходил PERSONAL_ROUTE gate (target_loc не получал значение из префикса
    — переменная-сирота _intent_target_loc) и умирал молчаливым NO_TARGET
    в чужом графе. После фикса: gate видит target_loc != current_loc,
    UNKNOWN-ветка пишет _unknown_route-сигнал, SceneChange не создаётся.
Зависимости: app.services.spatial.movement_engine, app.domain.movement
Основные сущности: test_prefix_target_loc_routes_to_unknown_gate
Запуск: cd backend; python -m pytest tests/micro/test_prefix_target_loc_gate.py -v
"""

from app.domain.movement import MacroMovementGoal, IntentDomain
from app.services.spatial.movement_engine import MovementEngine


def test_prefix_target_loc_routes_to_unknown_gate():
    """Префиксованная cross-loc цель + location_id текущей локации
    обязана попасть в UNKNOWN-гейт (сигнал _unknown_route), не в локальный A*."""
    engine = MovementEngine()
    tick = 42

    # NPC стоит в city_gate; цель — узел tavern (чужая локация)
    npc_positions = {
        "merchant_goran": {
            "npc_id": "merchant_goran",
            "position": "city_gate:gate_road",
            "location_id": "city_gate",
            "local_position": {"x": 7.43, "y": 11.35},
        }
    }

    intent = MacroMovementGoal(
        actor_id="merchant_goran",
        target_node_id="tavern:bar_area",   # префикс чужой локации
        from_node_id="city_gate:gate_road",
        location_id="city_gate",            # генератор ставит ТЕКУЩУЮ локацию (сломанная форма)
        reason="need_driven:shelter_urge=1.00",
        domain=IntentDomain.ROUTINE,
    )

    # Гейт контрактно требует scene_state (без него PERSONAL_ROUTE skip by design):
    # минимальная живая сцена текущей локации.
    scene_state = {"location_id": "city_gate", "npc_positions": npc_positions}
    changes = engine.process_intents([intent], tick, npc_positions=npc_positions, campaign_id="Open_road", scene_state=scene_state)

    # 1) Никаких позиционных SceneChange из чужого графа
    pos_changes = [c for c in changes if getattr(c, "field", "") == "position"]
    assert not pos_changes, f"cross-loc intent просочился в локальный A*: {pos_changes}"

    # 2) UNKNOWN-сигнал записан — причинный носитель для Phase D
    sig = npc_positions["merchant_goran"].get("_unknown_route")
    assert sig is not None, "UNKNOWN-гейт не сработал: сигнал _unknown_route не записан"
    assert sig.get("to") == "tavern", f"сигнал указывает не на ту локацию: {sig}"