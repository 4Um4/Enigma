# -*- coding: utf-8 -*-
"""
backend/npc_name_resolver.py
Конвертация npc_id → отображаемое имя.
Читает config/npc/individuals/ напрямую, без зависимости от app/.

Зачем отделён от scene_state_manager:
  scene_state_manager — агрегат состояния сцены (backend).
  npc_name_resolver — чистая утилита для парсинга текста (frontend).

  path: /backend/npc_name_resolver.py
Назначение: Конвертация npc_id → отображаемое имя. Без зависимости от app/.
Зависимости: json, pathlib, typing
Основные сущности: npc_id_to_display, _NPC_NAME_CACHE
"""

import json
from pathlib import Path
from typing import Dict

# кэш: npc_id → display_name
_NPC_NAME_CACHE: Dict[str, str] = {}
_NPC_NAME_CACHE_LOADED = False

_INDIVIDUALS_DIR = Path(__file__).parent.parent / "config" / "npc" / "individuals"


def _load_npc_names_cache() -> None:
    """Загружает id→name из config/npc/individuals/ один раз."""
    global _NPC_NAME_CACHE_LOADED
    if _NPC_NAME_CACHE_LOADED:
        return
    try:
        if not _INDIVIDUALS_DIR.exists():
            return
        for json_file in _INDIVIDUALS_DIR.glob("*.json"):
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            nid = data.get("id", "")
            name = data.get("name", "")
            if nid and name:
                _NPC_NAME_CACHE[nid] = name
    except Exception as e:
        print(f"[NPC_NAME_RESOLVER] Ошибка загрузки кэша: {e}")
    _NPC_NAME_CACHE_LOADED = True


def npc_id_to_display(npc_id: str) -> str:
    """
    Конвертирует npc_id в отображаемое имя.
    Приоритет: config/npc → эвристика из id.
    """
    _load_npc_names_cache()
    if npc_id in _NPC_NAME_CACHE:
        return _NPC_NAME_CACHE[npc_id]
    # Эвристика: последнее слово id с заглавной буквы
    parts = npc_id.split("_")
    return parts[-1].capitalize() if parts else npc_id