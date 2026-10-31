"""ME-2.1 Step C: CatalogIndex — search/filter/tags API on AssetStore.

Query layer, NOT a second storage. Reads blueprint data dicts from
AssetStore and builds an in-memory index for fast search/filter.
Index is rebuilt on refresh() — no persistent storage.

Categories support hierarchy and multiple membership:
- A blueprint has ONE category (string)
- A blueprint has MULTIPLE tags (list of strings)
- Tags can represent hierarchical categories (e.g., "furniture", "furniture/indoor")
- Filter by category is exact match; filter by tags requires ALL tags present
"""

from __future__ import annotations

from typing import Any

from assets.asset_store import AssetStore


class CatalogIndex:
    """Search and filter layer on top of AssetStore."""

    def __init__(self, asset_store: AssetStore) -> None:
        self._store = asset_store
        self._entries: dict[str, dict[str, Any]] = {}
        self._by_category: dict[str, list[str]] = {}
        self._by_tag: dict[str, list[str]] = {}
        self.refresh()

    def refresh(self) -> None:
        """Rebuild index from AssetStore blueprints."""
        self._entries.clear()
        self._by_category.clear()
        self._by_tag.clear()

        for bp_id in self._store.list_blueprints():
            record = self._store.get_blueprint(bp_id)
            if not record or not record.data:
                continue

            data = record.data
            metadata = data.get("metadata", {})
            entry = {
                "blueprint_id": bp_id,
                "label": metadata.get("label", bp_id),
                "tags": list(data.get("tags", [])),
                "category": data.get("category", "misc"),
                "categories": list(data.get("categories", [data.get("category", "misc")])),
                "type": data.get("type", bp_id),
                "sprite": data.get("appearance", {}).get("sprite"),
                "icon": metadata.get("icon", ""),
            }
            self._entries[bp_id] = entry

            # ME-2.1-E: hierarchical categories — index all levels
            for cat in entry["categories"]:
                self._by_category.setdefault(cat, []).append(bp_id)
                # Also index parent (e.g., "furniture" from "furniture/indoor")
                if "/" in cat:
                    parent = cat.split("/")[0]
                    if bp_id not in self._by_category.setdefault(parent, []):
                        self._by_category[parent].append(bp_id)

            for tag in entry["tags"]:
                self._by_tag.setdefault(tag, []).append(bp_id)

    def search(self, query: str) -> list[str]:
        """Search by blueprint_id, label, or tags (case-insensitive).

        Returns sorted list of matching blueprint_ids.
        """
        q = query.lower()
        results = []
        for bp_id, entry in self._entries.items():
            if q in bp_id.lower() or q in entry["label"].lower() or any(q in tag.lower() for tag in entry["tags"]):
                results.append(bp_id)
        return sorted(results)

    def filter(
        self,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> list[str]:
        """Filter by category and/or tags.

        Args:
            category: Exact category match.
            tags: Blueprint must have ALL specified tags.

        Returns sorted list of matching blueprint_ids.
        """
        if category is None and not tags:
            return sorted(self._entries.keys())

        candidates = set(self._entries.keys())

        if category is not None:
            # ME-2.1-E: hierarchical filter — prefix match
            # "furniture" matches "furniture" AND "furniture/indoor"
            cat_ids = set()
            for indexed_cat, bp_ids in self._by_category.items():
                if indexed_cat == category or indexed_cat.startswith(category + "/"):
                    cat_ids.update(bp_ids)
            candidates &= cat_ids

        if tags:
            for tag in tags:
                candidates &= set(self._by_tag.get(tag, []))

        return sorted(candidates)

    def get_preview(self, blueprint_id: str) -> dict[str, Any] | None:
        """Get preview metadata for UI display.

        Returns dict with blueprint_id, label, tags, category, type, sprite, icon.
        Returns None if not found.
        """
        entry = self._entries.get(blueprint_id)
        if entry is None:
            return None
        return dict(entry)

    def list_categories(self) -> list[str]:
        """All unique categories, sorted."""
        return sorted(self._by_category.keys())

    def list_tags(self) -> list[str]:
        """All unique tags, sorted."""
        return sorted(self._by_tag.keys())

    def list_all(self) -> list[str]:
        """All blueprint_ids, sorted."""
        return sorted(self._entries.keys())

    def list_category_tree(self) -> dict[str, list[str]]:
        """Returns {parent: [child_categories]} for hierarchical display.

        Parents without children have empty list.
        """
        tree: dict[str, list[str]] = {}
        for cat in self._by_category:
            if "/" in cat:
                parent, child = cat.split("/", 1)
                if child not in tree.setdefault(parent, []):
                    tree[parent].append(child)
            else:
                tree.setdefault(cat, [])
        return tree

    def get_category_count(self, category: str) -> int:
        """Number of blueprints in a category."""
        return len(self._by_category.get(category, []))

    def get_tag_count(self, tag: str) -> int:
        """Number of blueprints with a tag."""
        return len(self._by_tag.get(tag, []))

    @property
    def count(self) -> int:
        """Number of indexed blueprints."""
        return len(self._entries)
