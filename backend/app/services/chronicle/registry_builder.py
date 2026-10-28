"""
?????? CanonicalRegistry ??? ConsistencyService (CCH-7, ADR-O-422).

????: backend/app/services/chronicle/registry_builder.py
??????????: ???????????? ????-?????? ?????? ?????? (alias/archetype/secret_known_by).
            ????????? ?? tests/sandbox/scenarios/chronicle_weave_probe.py:226-270 ?
            ?????? ???????? ?????? (?????? ?????? ??????).
???????????: app.services.npc.npc_loader, app.core.config
???????? ????????: build_canonical_registry
"""
from __future__ import annotations

import json
import logging
from typing import Dict, FrozenSet

from app.core.config import BASE_DIR
from app.services.chronicle.consistency_service import CanonicalRegistry

logger = logging.getLogger(__name__)


def build_canonical_registry() -> CanonicalRegistry:
    """?????? ?????? ????: production-?????? ??? ?????????/???? + ???? ????????.

    Read-only. ?????? ??????? ?? ????? ? ??? ????????? (???? ADR-O-422).
    """
    alias: Dict[str, str] = {}
    archetype: Dict[str, str] = {}
    try:
        from app.services.npc.npc_loader import load_npcs_merged

        npcs = load_npcs_merged()
        for raw in npcs:
            npc_id = str(raw["id"])
            archetype[npc_id] = str(raw.get("_archetype") or raw.get("archetype") or "commoner")
            forms = [str(raw.get("name") or "")]
            nf = raw.get("name_forms")
            if isinstance(nf, list):
                forms.extend(str(x) for x in nf)
            elif isinstance(nf, dict):
                forms.extend(str(v) for v in nf.values())
            for f in forms:
                if f.strip():
                    alias[f.strip().lower()] = npc_id
    except Exception as e:
        logger.warning("load_npcs_merged ?????????? (%s) ? ????? individuals ????????", e)
        for path in sorted((BASE_DIR / "config" / "npc" / "individuals").glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            npc_id = str(raw["id"])
            archetype[npc_id] = str(raw.get("_archetype") or raw.get("archetype") or "commoner")
            forms = [str(raw.get("name") or "")]
            nf = raw.get("name_forms")
            if isinstance(nf, list):
                forms.extend(str(x) for x in nf)
            for f in forms:
                if f.strip():
                    alias[f.strip().lower()] = npc_id

    secret_known: Dict[str, FrozenSet[str]] = {}
    ts_path = BASE_DIR / "config" / "canon" / "truth_state_tavern.json"
    if ts_path.is_file():
        ts = json.loads(ts_path.read_text(encoding="utf-8-sig"))
        for s in ts.get("secrets", []):
            holders = set(s.get("initial_holders") or []) | set(s.get("participants") or [])
            secret_known[str(s.get("secret_id"))] = frozenset(holders)

    return CanonicalRegistry(
        alias_to_npc=alias,
        archetype_of=archetype,
        secret_known_by=secret_known,
    )
