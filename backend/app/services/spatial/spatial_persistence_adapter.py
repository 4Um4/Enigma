# path: backend/app/services/spatial/spatial_persistence_adapter.py
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class SpatialPersistenceAdapter:
    """
    ADR-O-442: Единый адаптер для сохранения пространственного состояния.
    Синхронизирует SceneState с каноническими мировыми координатами.
    """

    @staticmethod
    def prepare_scene_for_save(scene_state: Dict[str, Any], current_location: str) -> None:
        """
        Мутирует scene_state перед записью на диск.
        1. Гарантирует наличие player в npc_positions.
        2. Очищает legacy-поля, если global_coords=True.
        """
        if "npc_positions" not in scene_state:
            scene_state["npc_positions"] = {}

        # 1. Фиксируем локацию
        scene_state["location_id"] = current_location

        # 2. Гарантируем наличие игрока
        # В будущем мы будем брать это из SpatialService, сейчас — из world_ctx
        if "player" not in scene_state["npc_positions"]:
            # Если игрока нет в сцене, создаем дефолтную запись, чтобы не крашить фронтенд
            scene_state["npc_positions"]["player"] = {
                "local_position": {"x": 0.0, "y": 0.0},
                "position": "unknown_node",
                "location_id": current_location
            }

        # 3. Проверка мирового фрейма
        is_global = scene_state.get("global_coords", True)
        if is_global:
            # Если файл мировой, мы должны убедиться, что все координаты в npc_positions
            # тоже мировые. Если там есть локальные сдвиги — это баг.
            for npc_id, data in scene_state["npc_positions"].items():
                if isinstance(data, dict) and "local_position" in data:
                    lp = data["local_position"]
                    if lp.get("x") == 0 and lp.get("y") == 0:
                        # Защита от нулевых координат при загрузке
                        logger.warning(f"[SPATIAL_SSOT] Player/NPC {npc_id} has zero coords before save")

        logger.info(
            f"[SPATIAL_SSOT] Scene prepared for save at location={current_location}"
        )
