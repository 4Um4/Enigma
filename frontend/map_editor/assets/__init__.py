"""path: /frontend/map_editor/assets/__init__.py

Назначение: Пакет склада чертежей и ресурсов (ME-1.2, Этап 01).
Зависимости: asset_store.
Основные сущности: реэкспорт AssetStore, AssetStoreError, BlueprintRecord, ResourceRecord.
"""

from .asset_store import AssetStore, AssetStoreError, BlueprintRecord, ResourceRecord

__all__ = ["AssetStore", "AssetStoreError", "BlueprintRecord", "ResourceRecord"]
