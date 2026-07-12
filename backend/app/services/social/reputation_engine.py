from __future__ import annotations
# backend/app/services/social/reputation_engine.py
"""
Фаза 3.5 — ReputationEngine: репутация NPC в фракциях.

Принципы:
  - ReputationEngine НЕ пишет состояние напрямую. Возвращает дельты.
  - Действия NPC влияют на репутацию его фракции.
  - Репутация модифицирует DecisionHub через репутационные модификаторы.
  - Фракции загружаются из config/world/factions.json.
"""


import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Faction:
    """Статическое описание фракции из конфига."""

    id: str
    name: str
    nature: str  # criminal, law_enforcement, merchant, neutral
    base_reputation: float  # начальная репутация (-100..100)
    npc_members: FrozenSet[str]  # NPC-члены фракции
    npc_debtors: FrozenSet[str]  # NPC-должники фракции
    rivals: FrozenSet[str]  # враждебные фракции
    allies: FrozenSet[str]  # союзные фракции


@dataclass
class FactionState:
    """Динамическое состояние репутации фракции в runtime."""

    faction_id: str
    reputation: float  # текущая репутация (-100..100)
    recent_actions: List[dict] = field(default_factory=list)


# ── Маппинг event_type → влияние на репутацию ────────────────────────────────
EVENT_REPUTATION_IMPACT: Dict[str, Dict[str, float]] = {
    "PLAYER_ATTACKED": {
        "law_enforcement": -15.0,
        "criminal": 5.0,
        "merchant": -10.0,
        "neutral": -5.0,
    },
    "HELP": {
        "law_enforcement": 10.0,
        "criminal": -5.0,
        "merchant": 8.0,
        "neutral": 5.0,
    },
    "THEFT": {
        "law_enforcement": -20.0,
        "criminal": 15.0,
        "merchant": -15.0,
        "neutral": -10.0,
    },
    "INTIMIDATION": {
        "law_enforcement": -10.0,
        "criminal": 8.0,
        "merchant": -8.0,
        "neutral": -3.0,
    },
    "BETRAYAL": {
        "law_enforcement": -25.0,
        "criminal": -15.0,
        "merchant": -20.0,
        "neutral": -15.0,
    },
}

# Пороги репутации для модификаторов DecisionHub
REPUTATION_HATED_THRESHOLD: float = -50.0
REPUTATION_TRUSTED_THRESHOLD: float = 50.0


class ReputationEngine:
    """
    Фасад репутационной системы.

    Контракт:
    - НЕ пишет в NPCState напрямую. Возвращает модификаторы для DecisionHub.
    - Хранит FactionState в RAM.
    - Фракции — статические, загружаются один раз из JSON.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._factions: Dict[str, Faction] = {}
        self._states: Dict[str, FactionState] = {}
        self._npc_to_faction: Dict[str, str] = {}

        if config_path:
            self._load_factions(config_path)
            self._build_npc_index()
            self._init_states()

    def _load_factions(self, config_path: str) -> None:
        """Загружает статические данные фракций из JSON."""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"[REPUTATION] Config not found: {config_path}")
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[REPUTATION] Failed to load {config_path}: {e}")
            return

        for fid, fdata in data.get("factions", {}).items():
            self._factions[fid] = Faction(
                id=fid,
                name=fdata.get("name", fid),
                nature=fdata.get("nature", "neutral"),
                base_reputation=float(fdata.get("base_reputation", 0)),
                npc_members=frozenset(fdata.get("npc_members", [])),
                npc_debtors=frozenset(fdata.get("npc_debtors", [])),
                rivals=frozenset(fdata.get("rivals", [])),
                allies=frozenset(fdata.get("allies", [])),
            )
        logger.info(f"[REPUTATION] Loaded {len(self._factions)} factions")

    def _build_npc_index(self) -> None:
        """Строит обратный индекс npc_id → faction_id."""
        for fid, faction in self._factions.items():
            for npc_id in faction.npc_members:
                self._npc_to_faction[npc_id] = fid
            for npc_id in faction.npc_debtors:
                if npc_id not in self._npc_to_faction:
                    self._npc_to_faction[npc_id] = fid

    def _init_states(self) -> None:
        """Инициализирует runtime-состояние репутации из base_reputation."""
        for fid, faction in self._factions.items():
            self._states[fid] = FactionState(
                faction_id=fid,
                reputation=faction.base_reputation,
            )

    def get_npc_faction(self, npc_id: str) -> Optional[Faction]:
        """Возвращает фракцию NPC или None."""
        fid = self._npc_to_faction.get(npc_id)
        if fid:
            return self._factions.get(fid)
        return None

    def get_faction_reputation(self, faction_id: str) -> float:
        """Текущая репутация фракции."""
        state = self._states.get(faction_id)
        return state.reputation if state else 0.0

    def apply_event_impact(
        self,
        event_type: str,
        actor_npc_id: Optional[str] = None,
        target_npc_id: Optional[str] = None,
    ) -> List[dict]:
        """
        Рассчитывает влияние события на репутацию фракций.
        Возвращает список дельт для применения.
        """
        actor_faction = self.get_npc_faction(actor_npc_id) if actor_npc_id else None
        actor_nature = actor_faction.nature if actor_faction else "neutral"

        impact_rules = EVENT_REPUTATION_IMPACT.get(event_type, {})
        if not impact_rules:
            return []

        deltas: List[dict] = []

        # Влияние на фракцию актёра
        if actor_faction:
            actor_delta = impact_rules.get(actor_nature, 0.0) * 0.5
            if abs(actor_delta) > 0.1:
                deltas.append(
                    {
                        "faction_id": actor_faction.id,
                        "delta": round(actor_delta, 2),
                        "reason": f"{event_type} by member {actor_npc_id}",
                    }
                )

        # Влияние на союзников актёра (ослабленное)
        if actor_faction:
            for ally_id in actor_faction.allies:
                ally_nature = (
                    self._factions[ally_id].nature
                    if ally_id in self._factions
                    else "neutral"
                )
                ally_delta = impact_rules.get(ally_nature, 0.0) * 0.3
                if abs(ally_delta) > 0.1:
                    deltas.append(
                        {
                            "faction_id": ally_id,
                            "delta": round(ally_delta, 2),
                            "reason": f"ally of {actor_faction.id} affected by {event_type}",
                        }
                    )

        return deltas

    def compute_decay(self, decay_rate: float = 0.005) -> List["StateDeltas"]:
        """Чистый расчёт дрейфа reputation → base_reputation.

        НЕ мутирует _states. Возвращает List[StateDeltas] с faction_id.
        Closing drift: если |base - current| < EPSILON → drift = base - current.
        """
        from app.models.state_delta import DeltaDomain, ReputationPayload, StateDeltas

        REPUTATION_DECAY_EPSILON: float = 0.001
        results: List[StateDeltas] = []

        for fid, faction in self._factions.items():
            state = self._states.get(fid)
            if not state:
                continue

            drift = (faction.base_reputation - state.reputation) * decay_rate

            if abs(drift) < 1e-9:
                continue

            # Closing drift: закрываем разрыв вместо forced epsilon
            if (
                abs(faction.base_reputation - state.reputation)
                < REPUTATION_DECAY_EPSILON
            ):
                drift = faction.base_reputation - state.reputation

            results.append(
                StateDeltas(
                    # v1 backward compat (удаляется после миграции StateApplicator)
                    faction_id=fid,
                    reputation_delta=round(drift, 6),
                    # v2 domain-tagged payload
                    domain=DeltaDomain.REPUTATION,
                    target=fid,
                    payload=ReputationPayload(reputation_delta=round(drift, 6)),
                    source="reputation_decay",
                )
            )

        return results

    def apply_deltas(self, deltas: List["StateDeltas"]) -> None:
        """Единственная точка мутации FactionState.
        Вызывается ТОЛЬКО из StateApplicator._apply_faction_delta().

        Принимает List[StateDeltas] с faction_id + reputation_delta.
        """
        from app.models.state_delta import StateDeltas

        for d in deltas:
            if not isinstance(d, StateDeltas):
                # Обратная совместимость: legacy dict-формат от apply_event_impact
                fid = d.get("faction_id") if isinstance(d, dict) else None
                delta_val = d.get("delta", 0.0) if isinstance(d, dict) else 0.0
                reason = d.get("reason", "legacy") if isinstance(d, dict) else "legacy"
                if fid is None:
                    continue
                state = self._states.get(fid)
                if state is None:
                    continue
                new_rep = max(-100.0, min(100.0, state.reputation + delta_val))
                state.reputation = round(new_rep, 2)
                state.recent_actions.append(d)
                if len(state.recent_actions) > 50:
                    state.recent_actions = state.recent_actions[-50:]
                logger.debug(f"[REPUTATION] {fid}: {state.reputation:+.1f} ({reason})")
                continue

            if d.faction_id is None or d.reputation_delta == 0.0:
                continue
            state = self._states.get(d.faction_id)
            if not state:
                continue
            new_rep = max(-100.0, min(100.0, state.reputation + d.reputation_delta))
            state.reputation = round(new_rep, 2)
            state.recent_actions.append(
                {
                    "faction_id": d.faction_id,
                    "delta": d.reputation_delta,
                    "reason": d.source,
                }
            )
            if len(state.recent_actions) > 50:
                state.recent_actions = state.recent_actions[-50:]
            logger.debug(
                f"[REPUTATION] {d.faction_id}: {state.reputation:+.1f} ({d.source})"
            )

    def compute_reputation_modifier(self, npc_id: str) -> Dict[str, float]:
        """
        Вычисляет модификаторы для DecisionHub на основе репутации фракции NPC.
        """
        faction = self.get_npc_faction(npc_id)
        if faction is None:
            return {}

        rep = self.get_faction_reputation(faction.id)
        mods: Dict[str, float] = {}

        if rep <= REPUTATION_HATED_THRESHOLD:
            mods["flee"] = 0.2
            mods["observe"] = 0.15
            mods["attack"] = -0.1
            mods["talk"] = -0.1
        elif rep >= REPUTATION_TRUSTED_THRESHOLD:
            mods["talk"] = 0.15
            mods["warn"] = 0.1
            mods["help"] = 0.1
            mods["trade"] = 0.15
            mods["block_path"] = 0.1
            mods["offer_job"] = 0.1

        # Специфика nature
        if faction.nature == "criminal":
            mods["intimidate"] = mods.get("intimidate", 0.0) + 0.1
            mods["observe"] = mods.get("observe", 0.0) + 0.1
        elif faction.nature == "law_enforcement":
            mods["report"] = mods.get("report", 0.0) + 0.15
            mods["warn"] = mods.get("warn", 0.0) + 0.1
            mods["block_path"] = mods.get("block_path", 0.0) + 0.1

        return mods

    def get_all_faction_states(self) -> Dict[str, Dict[str, Any]]:
        """Сводка всех фракций для debug/UI."""
        return {
            fid: {
                "name": self._factions[fid].name,
                "nature": self._factions[fid].nature,
                "reputation": state.reputation,
                "members": List[Any](self._factions[fid].npc_members),
            }
            for fid, state in self._states.items()
            if fid in self._factions
        }
