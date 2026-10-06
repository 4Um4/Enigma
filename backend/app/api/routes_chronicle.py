"""
API Character Chronicle (ADR-O-420, CCH-2).

Файл: backend/app/api/routes_chronicle.py
Назначение: decompose/clarify/draft-цикл. Канонизация и UI — CCH-3.
Зависимости: app.services.chronicle.*, app.core.config
Основные сущности: chronicle_router

ГРАНИЦА: это внеигровой инструмент (layer 4 UI Doctrine). Эндпоинты НЕ входят
в тик-контур; NPCState/ядро не трогают (запрет 10 ADR-O-420).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.config import BASE_DIR
from app.domain.chronicle import SCHEMA_VERSION
from app.services.chronicle.biography_decomposer import BiographyDecomposer
from app.services.chronicle.chronicle_store import (
    ChronicleStore,
    document_from_dict,
    document_to_dict,
)
from fastapi import APIRouter
from pydantic import BaseModel, Field

chronicle_router = APIRouter()

_store: Optional[ChronicleStore] = None
_decomposer: Optional[BiographyDecomposer] = None


def _get_store() -> ChronicleStore:
    global _store
    if _store is None:
        _store = ChronicleStore(
            canonical_dir=BASE_DIR / "config" / "npc" / "chronicles",
            drafts_root=BASE_DIR / "saves",
        )
    return _store


def _get_decomposer() -> BiographyDecomposer:
    global _decomposer
    if _decomposer is None:
        _decomposer = BiographyDecomposer()
    return _decomposer


class DecomposeRequest(BaseModel):
    campaign_id: str = Field(..., min_length=1)
    npc_id: str = Field(..., min_length=1)
    fragment_ord: int = Field(..., ge=0)
    fragment: str = Field(..., min_length=1)


class ClarifyRequest(BaseModel):
    campaign_id: str = Field(..., min_length=1)
    npc_id: str = Field(..., min_length=1)
    fragment_ord: int = Field(..., ge=0)
    question_id: str = Field(..., min_length=1)
    selected_option: str
    selected_value: Optional[str] = None


@chronicle_router.get("/chronicle/npcs")
async def list_chronicles() -> Dict[str, Any]:
    """Список NPC с хрониками (канон + черновики кампании определяются по файлам)."""
    store = _get_store()
    canon = sorted(p.stem for p in store._canonical_dir.glob("*.json"))
    return {"canonical": canon}


@chronicle_router.post("/chronicle/{campaign_id}/{npc_id}/decompose")
async def decompose_fragment(campaign_id: str, npc_id: str, req: DecomposeRequest) -> Dict[str, Any]:
    """FR-2.x: фрагмент → декомпозиция (transient). Не пишет ни канон, ни draft."""
    result = await _get_decomposer().decompose(req.npc_id, req.fragment_ord, req.fragment)
    if not result.ok:
        return {"status": "NOT_DECOMPOSED", "error": result.error, "age_anchors": result.age_anchors or []}
    return {
        "status": "OK",
        "age_anchors": result.age_anchors,
        "items": [
            {
                "kind": i.kind.value,
                "draft_payload": i.draft_payload,
                "confidence": i.confidence,
                "needs_confirmation": i.needs_confirmation,
                "question": None if i.question is None else {
                    "question_id": i.question.question_id,
                    "target_span": i.question.target_span,
                    "options": [o.value for o in i.question.options],
                },
            }
            for i in result.items
        ],
    }


@chronicle_router.get("/chronicle/{campaign_id}/{npc_id}/draft")
async def get_draft(campaign_id: str, npc_id: str) -> Dict[str, Any]:
    doc = _get_store().load_draft(campaign_id, npc_id)
    if doc is None:
        return {"status": "EMPTY"}
    return {"status": "OK", "document": document_to_dict(doc)}


@chronicle_router.put("/chronicle/{campaign_id}/{npc_id}/draft")
async def put_draft(campaign_id: str, npc_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Сохранение черновика (UI конструирует document-dict; валидация store)."""
    doc = document_from_dict({**body, "schema_version": body.get("schema_version", SCHEMA_VERSION)})
    if doc.npc_ref != npc_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="npc_ref не совпадает с {npc_id}")
    path = _get_store().save_draft(doc, campaign_id)
    return {"status": "OK", "path": str(path)}
