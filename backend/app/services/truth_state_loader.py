"""
Файл: backend/app/services/truth_state_loader.py
Назначение: Загрузка и валидация TruthState из JSON.
Зависимости: json, typing, app.models.truth_state
"""

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Optional, Set

from app.models.truth_state import RelationType, Secret, TruthRelation, TruthState


class TruthStateLoader:
    """Загружает и валидирует TruthState из канонического JSON."""

    @staticmethod
    def load(file_path: Path) -> TruthState:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        if data.get("schema_version") != 1:
            raise ValueError(f"Unsupported schema_version: {data.get('schema_version')}")

        secrets: Dict[str, Secret] = {}
        for s_data in data.get("secrets", []):
            secret = Secret(
                secret_id=s_data["secret_id"],
                npc_id=s_data.get("npc_id", s_data["participants"][0] if "participants" in s_data else ""),
                participants=tuple(s_data.get("participants", [s_data.get("npc_id", "")])),
                category=s_data["category"],
                canonical_truth=s_data["canonical_truth"],
                importance=float(s_data.get("importance", 0.5)),
                initial_holders=tuple(s_data.get("initial_holders", [])),
                discovery_surface=tuple(s_data.get("discovery_surface", []))
            )
            secrets[secret.secret_id] = secret

        relations = []
        for r_data in data.get("relations", []):
            rel = TruthRelation(
                source_secret_id=r_data["source_secret_id"],
                target_secret_id=r_data["target_secret_id"],
                relation_type=RelationType(r_data["relation_type"]),
                strength=float(r_data.get("strength", 1.0))
            )
            relations.append(rel)

        return TruthState(secrets=MappingProxyType(secrets), relations=tuple(relations))

    @staticmethod
    def validate(state: TruthState, known_npcs: Optional[Set[str]] = None) -> None:
        """Структурная валидация. Бросает ValueError при нарушении инвариантов."""
        if not state.secrets:
            raise ValueError("TruthState validation failed: No secrets found.")

        secret_ids = set(state.secrets.keys())

        for secret in state.secrets.values():
            if not (0.0 <= secret.importance <= 1.0):
                raise ValueError(f"Importance out of range for secret '{secret.secret_id}'")
            if known_npcs:
                for p in secret.participants:
                    if p not in known_npcs:
                        raise ValueError(f"Unknown NPC '{p}' in secret '{secret.secret_id}'")

        for rel in state.relations:
            if rel.source_secret_id not in secret_ids:
                raise ValueError(f"Dangling reference: source '{rel.source_secret_id}' not found.")
            if rel.target_secret_id not in secret_ids:
                raise ValueError(f"Dangling reference: target '{rel.target_secret_id}' not found.")
            if rel.source_secret_id == rel.target_secret_id:
                raise ValueError(f"Self-loop detected for secret '{rel.source_secret_id}'.")
            if not (0.0 <= rel.strength <= 1.0):
                raise ValueError(f"Strength out of range for relation '{rel.source_secret_id}' -> '{rel.target_secret_id}'")
