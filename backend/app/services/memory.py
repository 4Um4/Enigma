import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


class JsonMemoryStore:
    """Local JSONL storage backend with explicit memory layer separation and read cache."""

    def __init__(self, root: str = "data") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._recent_cache: dict[tuple[str, int], list[dict[str, Any]]] = {}

    def _collection_path(self, collection: str) -> Path:
        return self.root / f"{collection}.jsonl"

    def append(self, collection: str, payload: dict[str, Any]) -> str:
        entry_id = str(uuid4())
        line = {"id": entry_id, "timestamp": datetime.now(timezone.utc).isoformat(), **payload}
        path = self._collection_path(collection)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

        cache_keys = [k for k in self._recent_cache if k[0] == collection]
        for key in cache_keys:
            self._recent_cache.pop(key, None)
        return entry_id

    def recent(self, collection: str, limit: int = 25) -> list[dict[str, Any]]:
        cache_key = (collection, limit)
        if cache_key in self._recent_cache:
            return self._recent_cache[cache_key]

        path = self._collection_path(collection)
        if not path.exists():
            return []

        tail = deque(maxlen=limit)
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if raw:
                    tail.append(json.loads(raw))

        result = list(tail)
        self._recent_cache[cache_key] = result
        return result


class LayeredMemory:
    """Three-layer campaign memory: world canon, campaign memory, session memory."""

    def __init__(self, store: JsonMemoryStore) -> None:
        self.store = store

    def write_world_canon(self, world_id: str, payload: dict[str, Any]) -> str:
        return self.store.append(f"world_canon_{world_id}", payload)

    def read_world_canon(self, world_id: str, limit: int = 25) -> list[dict[str, Any]]:
        return self.store.recent(f"world_canon_{world_id}", limit=limit)

    def write_campaign_memory(self, campaign_id: str, payload: dict[str, Any]) -> str:
        return self.store.append(f"campaign_memory_{campaign_id}", payload)

    def read_campaign_memory(self, campaign_id: str, limit: int = 25) -> list[dict[str, Any]]:
        return self.store.recent(f"campaign_memory_{campaign_id}", limit=limit)

    def write_session_memory(self, campaign_id: str, payload: dict[str, Any]) -> str:
        return self.store.append(f"session_memory_{campaign_id}", payload)

    def read_session_memory(self, campaign_id: str, limit: int = 25) -> list[dict[str, Any]]:
        return self.store.recent(f"session_memory_{campaign_id}", limit=limit)


    def write_npc_memory(self, campaign_id: str, payload: dict[str, Any]) -> str:
        return self.store.append(f"npc_memory_{campaign_id}", payload)

    def read_npc_memory(self, campaign_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.recent(f"npc_memory_{campaign_id}", limit=limit)

    def build_context(self, world_id: str, campaign_id: str, session_limit: int = 15) -> dict[str, Any]:
        return {
            "world_canon": self.read_world_canon(world_id, limit=10),
            "campaign_memory": self.read_campaign_memory(campaign_id, limit=20),
            "session_memory": self.read_session_memory(campaign_id, limit=session_limit),
            "npc_memory": self.read_npc_memory(campaign_id, limit=20),
        }

    def build_dynamic_context(self, world_id: str, campaign_id: str, session_limit: int = 15) -> dict[str, Any]:
        """Alias for orchestration layer: explicit context assembly before each turn."""
        return self.build_context(world_id, campaign_id, session_limit=session_limit)
