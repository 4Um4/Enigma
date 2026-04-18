import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CombatState:
    campaign_id: str
    combat_id: str
    round: int
    order: list[dict[str, Any]]
    turn_index: int
    participants: list[dict[str, Any]]
    log: list[str]


class CombatService:
    """Simple local D&D-like combat flow: initiative, turn order and attack resolution."""

    def __init__(self, root: str = "data/campaigns") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _combat_path(self, campaign_id: str, combat_id: str) -> Path:
        folder = self.root / campaign_id / "combat"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{combat_id}.json"

    def _save(self, state: CombatState) -> CombatState:
        path = self._combat_path(state.campaign_id, state.combat_id)
        path.write_text(
            json.dumps(
                {
                    "campaign_id": state.campaign_id,
                    "combat_id": state.combat_id,
                    "round": state.round,
                    "order": state.order,
                    "turn_index": state.turn_index,
                    "participants": state.participants,
                    "log": state.log,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return state

    def load(self, campaign_id: str, combat_id: str) -> CombatState:
        path = self._combat_path(campaign_id, combat_id)
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return CombatState(**payload)

    def start(self, campaign_id: str, combat_id: str, participants: list[dict[str, Any]]) -> CombatState:
        ordered = sorted(participants, key=lambda p: p.get("initiative", 0), reverse=True)
        state = CombatState(
            campaign_id=campaign_id,
            combat_id=combat_id,
            round=1,
            order=[{"name": p["name"], "initiative": p.get("initiative", 0)} for p in ordered],
            turn_index=0,
            participants=ordered,
            log=["Бой начался. Определён порядок инициативы."],
        )
        return self._save(state)

    def next_turn(self, campaign_id: str, combat_id: str) -> CombatState:
        state = self.load(campaign_id, combat_id)
        state.turn_index += 1
        if state.turn_index >= len(state.order):
            state.turn_index = 0
            state.round += 1
            state.log.append(f"Начался раунд {state.round}.")
        active = state.order[state.turn_index]["name"]
        state.log.append(f"Ход: {active}.")
        return self._save(state)

    def resolve_attack(
        self,
        campaign_id: str,
        combat_id: str,
        attacker: str,
        target: str,
        d20_roll: int,
        attack_bonus: int,
        target_ac: int,
        damage: int,
    ) -> CombatState:
        state = self.load(campaign_id, combat_id)
        total = d20_roll + attack_bonus
        if d20_roll == 20:
            hit = True
            note = "критическое попадание"
            dealt = damage * 2
        else:
            hit = total >= target_ac
            note = "попадание" if hit else "промах"
            dealt = damage if hit else 0

        for p in state.participants:
            if p.get("name") == target:
                hp = int(p.get("hp", 0))
                p["hp"] = max(0, hp - dealt)

        state.log.append(
            f"{attacker} атакует {target}: d20={d20_roll} + {attack_bonus} => {total} vs AC {target_ac} — {note}. Урон: {dealt}."
        )
        return self._save(state)
