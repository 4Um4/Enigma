"""
Микрокосм Таверны. Детерминированная фикстура без I/O и рандома.

Файл: backend/tests/sandbox/fixtures/tavern_world.py
Назначение: Минимальный детерминированный мир для тестирования Физики Власти.
Зависимости: None
Основные сущности: build_tavern_fixture

TODO:
- В будущем можно расширить фикстуру, добавив больше NPC, сложные локации, или даже динамические события (например, внезапное появление бандитов).
"""

def build_tavern_fixture() -> dict:
    """
    Возвращает минимальный scene_state с двумя сущностями:
    Игрок (источник власти) и Тень (подчиненный).
    """
    return {
        "location_id": "sandbox_tavern",
        "game_time_seconds": 36000, # 10:00
        "active_traversals": {},
        "npc_positions": {
            "player": {
                "position": "main_hall",
                "local_position": {"x": 5.0, "y": 5.0},
                "name": "Венус",
                "npc_id": "player"
            },
            "thief_shadow": {
                "position": "shadow_corner",
                "local_position": {"x": 15.0, "y": 10.0},
                "name": "Тень",
                "npc_id": "thief_shadow",
                # Психика, предрасположенная к подчинению (для первого теста)
                "psyche": {
                    "fear": 0.6,
                    "aggression": 0.1,
                    "willpower": 0.2,
                    "loyalty_true": 0.4
                }
            }
        }
    }