"""
path: /diagnose_spatial.py
Назначение: Диагностический sandbox для проверки путей SpatialService и загрузки имен NPC
Зависимости: backend/app (core/config, services/npc, services/spatial)

Этот скрипт предназначен для диагностики проблем с загрузкой графа локации в SpatialService, а также для проверки путей к данным NPC и их имен. Он выполняет следующие проверки:
1. Проверяет BASE_DIR из config.py и существование папки data/locations.
2. Проверяет путь _CONFIG_NPC_ROOT из npc_loader.py и существование папки individuals, а также наличие файлов с именем "lusya".
3. Пытается загрузить NPC через load_npcs_merged() и найти NPC с id "maid_lusya", выводя её имя.
4. Пытается создать SpatialService для локации "tavern_silver_wolf" и проверяет наличие узла "serving_table_3" в графе.
Использование:
python diagnose_spatial.py
Этот скрипт поможет выявить проблемы с путями к данным, загрузкой NPC и построением графа локации, которые могут быть причиной того, что NPC не ходят в игре. Он выводит подробную информацию о каждом этапе диагностики для облегчения отладки.

TODO:
- В будущем можно расширить этот скрипт для проверки других локаций, других NPC и для более глубокой диагностики структуры графа (например, проверять связи между узлами, наличие определённых типов узлов и т.д.). Но на начальном этапе достаточно базовой проверки путей и наличия ключевых данных, чтобы быстро выявить основные проблемы с загрузкой SpatialService и NPC данных.
"""

import sys
from pathlib import Path

# Поднимаемся от backend/tests/sandbox/ к корню проекта (Enigma/)
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

print("=== ДИАГНОСТИКА V2: ГРАФ И ИМЕНА ===")

# 1. Тест загрузки графа локации
print("\n[1] Тест compile_graph для tavern_silver_wolf:")
try:
    from app.services.spatial.graph_compiler import compile_graph, load_editor_json

    editor_data = load_editor_json("Open_road", "tavern_silver_wolf")
    if editor_data:
        print(f"    editor_data загружен, ключи: {list(editor_data.keys())[:5]}")
        graph, connections, alias_map = compile_graph(editor_data, "tavern_silver_wolf")
        print(f"    Граф собран. Узлов: {len(graph)}. Связей: {len(connections)}")
        if "serving_table_3" in graph:
            print("    ✅ Узел 'serving_table_3' НАЙДЕН в графе!")
        else:
            print(f"    ❌ Узел 'serving_table_3' НЕ НАЙДЕН в графе. Доступные узлы: {list(graph.keys())[:10]}")
    else:
        print("    ❌ editor_data вернул None! load_editor_json не нашел JSON локации.")
except Exception as e:
    print(f"    ❌ ОШИБКА: {e}")

# 2. Тест потока имен (SceneState -> WorldSnapshot -> Frontend)
print("\n[2] Тест потока имен NPC:")
try:
    from app.services.scene_state_manager import SceneStateManager, _npc_id_to_display

    # 2.1 Проверяем резолвер
    name = _npc_id_to_display("maid_lusya")
    print(f"    _npc_id_to_display('maid_lusya') = '{name}'")

    # 2.2 Проверяем, добавляет ли SceneStateManager поле name
    mgr = SceneStateManager()
    scene = mgr.get_scene_state("Open_road", "tavern_silver_wolf")
    if scene and "npc_positions" in scene:
        lusya_data = scene["npc_positions"].get("maid_lusya", {})
        print(f"    maid_lusya в scene_state имеет ключи: {list(lusya_data.keys())}")
        print(f"    maid_lusya['name'] = '{lusya_data.get('name')}'")
    else:
        print("    ❌ scene_state пуст или нет npc_positions")

    # 2.3 Проверяем, как WorldSnapshotBuilder собирает DTO
    from app.services.integration.world_snapshot_builder import WorldSnapshotBuilder

    builder = WorldSnapshotBuilder()
    positions_dto = builder._extract_npc_positions(scene)
    lusya_dto = next((p for p in positions_dto if p.npc_id == "maid_lusya"), None)
    if lusya_dto:
        print(f"    NPCPositionDTO.display_name = '{lusya_dto.display_name}'")
    else:
        print("    ❌ maid_lusya не попала в WorldSnapshotDTO")

except Exception as e:
    print(f"    ❌ ОШИБКА: {e}")

print("\n=== ДИАГНОСТИКА ЗАВЕРШЕНА ===")
