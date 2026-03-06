import json
from pathlib import Path

from app.models.schemas import CharacterSheet


class CharacterService:
    """Persist player characters per campaign as local JSON."""

    def __init__(self, root: str = "data/campaigns") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _characters_path(self, campaign_id: str) -> Path:
        campaign_dir = self.root / campaign_id
        campaign_dir.mkdir(parents=True, exist_ok=True)
        return campaign_dir / "characters.json"

    def list_characters(self, campaign_id: str) -> list[CharacterSheet]:
        path = self._characters_path(campaign_id)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [CharacterSheet.model_validate(item) for item in payload]

    def upsert_character(self, campaign_id: str, sheet: CharacterSheet) -> CharacterSheet:
        items = self.list_characters(campaign_id)
        updated: list[CharacterSheet] = []
        replaced = False
        for item in items:
            if item.name == sheet.name:
                updated.append(sheet)
                replaced = True
            else:
                updated.append(item)
        if not replaced:
            updated.append(sheet)

        path = self._characters_path(campaign_id)
        path.write_text(
            json.dumps([item.model_dump() for item in updated], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return sheet
