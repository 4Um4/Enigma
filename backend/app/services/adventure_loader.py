import json
from pathlib import Path
from typing import Any


class AdventureLoader:
    """Loads pre-written adventures from local filesystem."""

    def __init__(self, campaigns_root: str = "data/campaigns") -> None:
        self.campaigns_root = Path(campaigns_root)
        self.campaigns_root.mkdir(parents=True, exist_ok=True)

    def load_campaign(self, campaign_id: str) -> dict[str, Any]:
        folder = self.campaigns_root / campaign_id
        if not folder.exists():
            return {"campaign_id": campaign_id, "status": "not_found", "files": {}}

        files: dict[str, Any] = {}
        for filename in ("world_lore.txt", "npc.json", "locations.json"):
            path = folder / filename
            if not path.exists():
                continue
            if path.suffix == ".json":
                files[filename] = json.loads(path.read_text(encoding="utf-8"))
            else:
                files[filename] = path.read_text(encoding="utf-8")

        return {"campaign_id": campaign_id, "status": "loaded", "files": files}
