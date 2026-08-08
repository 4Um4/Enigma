"""
path: /frontend/visual_casting_repository.py
Назначение: S174. Изолирует PortraitRenderer от файловой системы.
Загружает visual_casting конфиги, выполняет миграцию legacy portrait_config.
Зависимости: json, pathlib, expression_resolver
Основные сущности: VisualCastingRepository
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

from expression_resolver import ExpressionResolver, ExpressionResult

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent / "config" / "npc" / "individuals"

class VisualCastingRepository:
    """Единое хранилище правил визуального кастинга для всех NPC."""

    def __init__(self):
        self._castings: Dict[str, Dict] = {}
        self._resolver = ExpressionResolver()
        self._load_all()

    def _load_all(self):
        """Загружает visual_casting из всех JSON индивидов при старте."""
        if not _CONFIG_DIR.exists():
            return
        for json_file in _CONFIG_DIR.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                npc_id = data.get("id")
                
                v_config = data.get("visual_casting")
                if not v_config:
                    p_config = data.get("portrait_config")
                    if p_config:
                        v_config = self._migrate_legacy(p_config)
                
                if npc_id and v_config:
                    self._castings[npc_id] = v_config
            except Exception:
                continue

    def _migrate_legacy(self, p_config: Dict) -> Dict:
        """Конвертирует старый portrait_config в новый контракт visual_casting."""
        rules = []
        if "shouting" in p_config:
            rules.append({"rule_id": "legacy_shout", "expression_id": "shouting", "priority": 100, "asset": p_config["shouting"], "evidence": [{"field": "delivery_type", "op": "==", "value": "SHOUT"}]})
        if "whispering" in p_config:
            rules.append({"rule_id": "legacy_whisper", "expression_id": "whispering", "priority": 90, "asset": p_config["whispering"], "evidence": [{"field": "delivery_type", "op": "==", "value": "WHISPER"}]})
        if "tense" in p_config:
            rules.append({"rule_id": "legacy_tense", "expression_id": "tense", "priority": 50, "asset": p_config["tense"], "evidence": [{"field": "pose_tense", "op": ">", "value": 0.5}]})
        if "avoiding_gaze" in p_config:
            rules.append({"rule_id": "legacy_gaze", "expression_id": "avoiding_gaze", "priority": 40, "asset": p_config["avoiding_gaze"], "evidence": [{"field": "gaze_avoidance", "op": ">", "value": 0.7}]})

        return {
            "fallback": {"expression_id": "neutral", "asset": p_config.get("neutral")},
            "rules": rules
        }

    def resolve_entity(self, entity) -> ExpressionResult:
        """Разрешает визуальное состояние для сущности."""
        cfg = self._castings.get(getattr(entity, "entity_id", None))
        return self._resolver.resolve(entity, cfg)

    def get_fallback_asset(self, npc_id: str) -> Optional[list]:
        """Возвращает fallback ассет для NPC (для плавного затухания)."""
        cfg = self._castings.get(npc_id)
        if cfg:
            return cfg.get("fallback", {}).get("asset")
        return None