"""
Путь: backend/app/services/memory/yaml_export.py

Назначение: Дамп EventMemory из SQLite в человекочитаемый YAML (Закон 4.2.2). Не пишет в MemoryProcessor — только читает из SQLite.
Зависимости: yaml (pyyaml), app.services.memory.sqlite_store.SqliteMemoryStore, app.models.npc_state.EventMemory
Основные сущности: export_npc_memories_to_yaml(), export_campaign_to_yaml() 
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Человеческие метки для полей — не технические значения
_STAGE_LABELS: dict = {
    "FRESH": "свежее",
    "CONSOLIDATED": "закрепилось",
    "ABSTRACT": "абстракция",
    "FORGOTTEN": "забыто",
}


def _format_single_memory(d: Dict[str, Any]) -> Dict[str, Any]:
    """Преобразует сырой dict из SQLite в человекочитаемый формат."""
    stage = d.get("stage", "FRESH")
    if isinstance(stage, str):
        stage_label = _STAGE_LABELS.get(stage, stage)
    else:
        stage_label = _STAGE_LABELS.get(stage.value if hasattr(stage, "value") else str(stage), str(stage))

    tags = d.get("tags", ())
    if isinstance(tags, (list, tuple)):
        tags = list(tags)
    else:
        tags = []

    result: Dict[str, Any] = {
        "событие": d.get("event_type", ""),
        "суть": d.get("summary", "") or "(без описания)",
        "важность": round(d.get("importance", 0.0), 2),
        "доступность": round(d.get("accessibility", 0.0), 2),
        "стадия": stage_label,
        "день": d.get("day", 0),
    }

    if tags:
        result["теги"] = tags

    target = d.get("target_id", "")
    if target:
        result["кто_связан"] = target

    emotion = d.get("emotion_tag", "")
    if emotion and emotion != "neutral":
        result["эмоция"] = emotion

    if d.get("is_secret"):
        result["секрет"] = True
        hidden = d.get("hidden_from", ())
        if hidden:
            result["скрыто_от"] = list(hidden) if isinstance(hidden, (list, tuple)) else [hidden]

    if d.get("contract_tag") or d.get("contract_ref"):
        result["обязательство"] = {
            "тип": d.get("contract_tag", ""),
            "реф": d.get("contract_ref", ""),
            "выполнено": bool(d.get("fulfilled", False)),
        }

    if d.get("is_compressed"):
        result["сжатие"] = True
        compressed_from = d.get("compressed_from", ())
        if compressed_from:
            result["из_чего_сжато"] = list(compressed_from) if isinstance(compressed_from, (list, tuple)) else [compressed_from]

    return result


def export_npc_memories_to_yaml(
    store: Any,
    campaign_id: str,
    npc_id: str,
    output_path: Optional[Path] = None,
) -> str:
    """Экспортирует все EventMemory NPC из SQLite в YAML.

    Закон 4.2.2: YAML = snapshot/export, не пишет MemoryProcessor.
    """
    if not hasattr(store, "load_event_memories"):
        logger.warning("[YAML_EXPORT] Store не поддерживает load_event_memories")
        return ""

    raw_list = store.load_event_memories(campaign_id, npc_id)
    if not raw_list:
        logger.info(f"[YAML_EXPORT] Нет данных для {npc_id} в кампании {campaign_id}")
        return ""

    formatted = [_format_single_memory(d) for d in raw_list]

    doc: Dict[str, Any] = {
        "кампания": campaign_id,
        "npc": npc_id,
        "воспоминаний": len(formatted),
        "память": formatted,
    }

    yaml_str = yaml.dump(doc, allow_unicode=True, default_flow_style=False, sort_keys=False)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_str, encoding="utf-8")
        logger.info(f"[YAML_EXPORT] {npc_id}: {len(formatted)} записей → {output_path}")

    return yaml_str


def export_campaign_to_yaml(
    store: Any,
    campaign_id: str,
    output_dir: Path,
    npc_ids: Optional[List[str]] = None,
) -> int:
    """Экспортирует все NPC кампании в отдельные YAML-файлы.

    Возвращает количество экспортированных NPC.
    """
    if not hasattr(store, "load_event_memories"):
        logger.warning("[YAML_EXPORT] Store не поддерживает load_event_memories")
        return 0

    # Если npc_ids не передан — пытаемся извлечь уникальные из SQLite
    if not npc_ids:
        try:
            rows = store._conn.execute(
                "SELECT DISTINCT npc_id FROM event_memories WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchall()
            npc_ids = [r["npc_id"] for r in rows]
        except Exception as e:
            logger.error(f"[YAML_EXPORT] Не удалось получить список NPC: {e}")
            return 0

    exported = 0
    for npc_id in npc_ids:
        out_path = output_dir / f"{npc_id}.yaml"
        yaml_str = export_npc_memories_to_yaml(store, campaign_id, npc_id, out_path)
        if yaml_str:
            exported += 1

    logger.info(f"[YAML_EXPORT] Кампания {campaign_id}: {exported}/{len(npc_ids)} NPC экспортировано")
    return exported