"""
path: backend/app/services/world/__init__.py
Назначение: Пакет семантического мира (W-track, ADR-O-371).
    W1 — WorldObjectStore над scene_state["world_objects"].
Зависимости: app.services.world.world_object_store
Основные сущности: WorldObjectStore (реэкспорт)
"""
from app.services.world.world_object_store import WorldObjectStore

__all__ = ["WorldObjectStore"]
