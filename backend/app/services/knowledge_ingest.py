from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import TYPE_CHECKING, Literal

try:
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None

if TYPE_CHECKING:
    from app.services.memory.memory_manager import MemoryManager

KnowledgeKind = Literal["world", "rules", "characters", "npc", "campaign"]


@dataclass
class IngestResult:
    kind: KnowledgeKind
    filename: str
    extracted_chars: int
    entry_id: str
    notes: str


class KnowledgeIngestService:
    """Imports local source text into memory for DM/rules/NPC context.
    
    Зависит от MemoryManager, не от LayeredMemory (Закон 4.1.2).
    """

    def __init__(self, memory: MemoryManager) -> None:
        self._memory = memory

    def _extract_pdf(self, raw: bytes) -> str:
        if PdfReader is None:
            raise RuntimeError("PDF импорт недоступен: установите pypdf.")
        reader = PdfReader(BytesIO(raw))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()

    def _extract_text(self, filename: str, raw: bytes) -> str:
        lower = filename.lower()
        if lower.endswith(".pdf"):
            return self._extract_pdf(raw)
        return raw.decode("utf-8", errors="ignore").strip()

    def ingest(
        self,
        *,
        world_id: str,
        campaign_id: str,
        kind: KnowledgeKind,
        filename: str,
        raw: bytes,
    ) -> IngestResult:
        text = self._extract_text(filename, raw)
        if not text:
            raise RuntimeError("Не удалось извлечь текст из файла.")

        payload = {
            "source_file": filename,
            "kind": kind,
            "text": text[:20000],
            "text_preview": text[:1000],
            "length": len(text),
        }

        if kind in {"world", "rules", "campaign"}:
            entry_id = self._memory.persist_world_canon(
                world_id,
                campaign_id=campaign_id,
                source=filename,
                payload=payload,
            )
            target = "world_canon"
        elif kind == "characters":
            entry_id = self._memory.persist_campaign_data(
                campaign_id,
                {**payload, "tag": "character_source"},
            )
            target = "campaign_memory"
        else:  # npc
            entry_id = self._memory.persist_npc_note(
                campaign_id,
                note=payload["text_preview"],
                source=filename,
            )
            target = "npc_memory"

        return IngestResult(
            kind=kind,
            filename=filename,
            extracted_chars=len(text),
            entry_id=entry_id,
            notes=f"Сохранено в {target}",
        )
