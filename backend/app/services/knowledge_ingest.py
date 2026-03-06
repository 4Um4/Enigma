from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from app.services.memory import LayeredMemory

try:
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover
    PdfReader = None

KnowledgeKind = Literal["world", "rules", "characters", "npc", "campaign"]


@dataclass
class IngestResult:
    kind: KnowledgeKind
    filename: str
    extracted_chars: int
    entry_id: str
    notes: str


class KnowledgeIngestService:
    """Imports local source text (TXT/MD/PDF) into layered memory for DM/rules/NPC context."""

    def __init__(self, memory: LayeredMemory) -> None:
        self.memory = memory

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
            entry_id = self.memory.write_world_canon(world_id, payload)
            target = "world_canon"
        elif kind == "characters":
            entry_id = self.memory.write_campaign_memory(campaign_id, {**payload, "tag": "character_source"})
            target = "campaign_memory"
        else:  # npc
            entry_id = self.memory.write_npc_memory(campaign_id, {"note": payload["text_preview"], "source": filename})
            target = "npc_memory"

        return IngestResult(
            kind=kind,
            filename=filename,
            extracted_chars=len(text),
            entry_id=entry_id,
            notes=f"Сохранено в {target}",
        )
