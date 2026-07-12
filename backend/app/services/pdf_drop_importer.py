from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.knowledge_ingest import KnowledgeIngestService, KnowledgeKind


@dataclass
class DropImportItem:
    filename: str
    kind: KnowledgeKind
    chars: int
    status: str
    message: str


class PdfDropImporter:
    """Bulk-imports PDF/TXT/MD files from a local drop folder into layered memory."""

    _KIND_KEYWORDS: list[tuple[KnowledgeKind, tuple[str, ...]]] = [
        ("rules", ("rule", "правил", "player", "игрок", "phb", "dmg")),
        ("campaign", ("campaign", "кампан", "adventure", "сценар")),
        ("npc", ("npc", "бестиар", "monster", "монстр")),
        ("characters", ("character", "персонаж", "hero", "герой")),
    ]

    def __init__(self, ingest_service: KnowledgeIngestService) -> None:
        self.ingest_service = ingest_service

    def _detect_kind(self, filename: str) -> KnowledgeKind:
        low = filename.lower()
        for kind, words in self._KIND_KEYWORDS:
            if any(word in low for word in words):
                return kind
        return "world"

    def import_from_folder(
        self, folder: str, *, world_id: str, campaign_id: str
    ) -> list[DropImportItem]:
        root = Path(folder)
        if not root.exists():
            root.mkdir(parents=True, exist_ok=True)
            return []

        results: list[DropImportItem] = []
        for path in sorted(root.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".pdf", ".txt", ".md"}:
                continue

            kind = self._detect_kind(path.name)
            try:
                raw = path.read_bytes()
                outcome = self.ingest_service.ingest(
                    world_id=world_id,
                    campaign_id=campaign_id,
                    kind=kind,
                    filename=path.name,
                    raw=raw,
                )
                results.append(
                    DropImportItem(
                        filename=path.name,
                        kind=kind,
                        chars=outcome.extracted_chars,
                        status="ok",
                        message=outcome.notes,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive runtime path
                results.append(
                    DropImportItem(
                        filename=path.name,
                        kind=kind,
                        chars=0,
                        status="error",
                        message=str(exc),
                    )
                )

        return results
