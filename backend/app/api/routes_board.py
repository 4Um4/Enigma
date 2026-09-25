"""
path: /project/backend/app/api/routes_board.py
Назначение: REST Investigation Board (Phase 4 MVI). GET — состояние
    организации (cards/links/hypotheses, БЕЗ резолва материала — вердикт
    В1: ref_id opaque, резолв = ответственность presentation/client layer).
    POST-эндпоинты маршрутизируют закрытый список операций ТЗ §3 в чистые
    функции PlayerBoardService через mutate() (одна операция = одна
    мутация файла). ValueError операции → HTTP 422 (громкий отказ, L4).
    Board НЕ знает эпистемику: ни одного импорта из epistemic/Predicate.
Зависимости: fastapi, pydantic, app.services.player_board_service
Основные сущности: board_router, CardOpRequest, player_board_service
"""
from __future__ import annotations

from typing import List, Literal, Optional

from app.core.config import settings
from app.services.player_board_service import (
    PlayerBoardService,
    add_card,
    create_hypothesis,
    delete_hypothesis,
    edit_hypothesis,
    link,
    move_card,
    remove_card,
    unlink,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

board_router = APIRouter(tags=["board"])

# Прецедент routes.py:50 — CharacterService(root=str(settings.saves_dir))
player_board_service = PlayerBoardService(root=str(settings.saves_dir))

_POS_LEN = 2


class CardAddPayload(BaseModel):
    op: Literal["add"]
    ref_type: str
    ref_id: str
    pos: Optional[List[float]] = Field(default=None)


class CardMovePayload(BaseModel):
    op: Literal["move"]
    card_id: str
    pos: List[float]


class CardRemovePayload(BaseModel):
    op: Literal["remove"]
    card_id: str


class LinkOpPayload(BaseModel):
    # Ключи from/to — зарезервированное слово Python: JSON-схема доски
    # использует "from"/"to", поля модели named from_id/to_id с alias.
    # Клиент шлёт "from"/"to" (валидация Pydantic v2 по alias — default).
    op: Literal["link", "unlink"]
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    kind: str


CardOp = CardAddPayload | CardMovePayload | CardRemovePayload


def _validate_campaign(campaign_id: str) -> None:
    # campaign_id становится именем каталога под saves/ — traversal-защита
    if not campaign_id or "/" in campaign_id or "\\" in campaign_id or ".." in campaign_id:
        raise HTTPException(status_code=400, detail="Invalid campaign_id")


@board_router.get("/board/{campaign_id}")
def get_board(campaign_id: str) -> dict:
    """Состояние организации доски. Материал карточек НЕ резолвится:
    клиент джойнит ref_id против dialog_journal / player_beliefs (M7)."""
    _validate_campaign(campaign_id)
    return player_board_service.load_board(campaign_id)


@board_router.post("/board/{campaign_id}/cards")
def post_cards(campaign_id: str, payload: CardOp) -> dict:
    """ADD_CARD / MOVE_CARD / REMOVE_CARD — закрытый список ТЗ §3.
    ValueError чистой операции → 422, файл не мутирует (нет частичных
    коммитов — контракт mutate())."""
    _validate_campaign(campaign_id)
    try:
        if isinstance(payload, CardAddPayload):
            _pos = tuple(payload.pos) if payload.pos is not None else None
            if _pos is not None and len(_pos) != _POS_LEN:
                raise ValueError("[BOARD] pos обязан быть [x, y]")
            _card_id = player_board_service.mutate(
                campaign_id,
                lambda b: add_card(b, payload.ref_type, payload.ref_id, pos=_pos),
            )
            return {"status": "ok", "card_id": _card_id}
        if isinstance(payload, CardMovePayload):
            if len(payload.pos) != _POS_LEN:
                raise ValueError("[BOARD] pos обязан быть [x, y]")
            player_board_service.mutate(
                campaign_id,
                lambda b: move_card(b, payload.card_id, tuple(payload.pos)),
            )
            return {"status": "ok"}
        # CardRemovePayload
        player_board_service.mutate(
            campaign_id,
            lambda b: remove_card(b, payload.card_id),
        )
        return {"status": "ok"}
    except ValueError as _e:
        raise HTTPException(status_code=422, detail=str(_e)) from _e


class HypOpPayload(BaseModel):
    op: Literal["create", "edit", "delete"]
    hyp_id: Optional[str] = None
    text: Optional[str] = None
    status: Optional[str] = None


@board_router.post("/board/{campaign_id}/hypotheses")
def post_hypotheses(campaign_id: str, payload: HypOpPayload) -> dict:
    """CREATE_HYPOTHESIS / EDIT_HYPOTHESIS / DELETE_HYPOTHESIS — закрытый
    список ТЗ §3. DELETE каскадный (вердикт Мастера): гипотеза + все
    карточки-указатели + инцидентные рёбра, инвариант целостности
    СОБСТВЕННОГО файла; за пределами board_state.json не трогает ничего
    по построению. Текст гипотезы — свободный (BoardHypothesis.text,
    НЕ subject/predicate/object — табу §5)."""
    _validate_campaign(campaign_id)
    try:
        if payload.op == "create":
            if payload.text is None:
                raise ValueError("[BOARD] CREATE без text запрещён")
            _hyp_id = player_board_service.mutate(
                campaign_id,
                lambda b: create_hypothesis(b, payload.text),
            )
            return {"status": "ok", "hypothesis_id": _hyp_id}
        if payload.op == "edit":
            if not payload.hyp_id:
                raise ValueError("[BOARD] EDIT без hyp_id запрещён")
            player_board_service.mutate(
                campaign_id,
                lambda b: edit_hypothesis(
                    b, payload.hyp_id,
                    text=payload.text, status=payload.status,
                ),
            )
            return {"status": "ok"}
        # delete
        if not payload.hyp_id:
            raise ValueError("[BOARD] DELETE без hyp_id запрещён")
        player_board_service.mutate(
            campaign_id,
            lambda b: delete_hypothesis(b, payload.hyp_id),
        )
        return {"status": "ok"}
    except ValueError as _e:
        raise HTTPException(status_code=422, detail=str(_e)) from _e


@board_router.post("/board/{campaign_id}/links")
def post_links(campaign_id: str, payload: LinkOpPayload) -> dict:
    """LINK (idempotent: повторный клик → 'noop', без дубля ребра) /
    UNLINK (тройка from+to+kind; отсутствие ребра — безопасный no-op).
    Контракт операций утверждён Мастером (Phase 4, вердикты 1-3)."""
    _validate_campaign(campaign_id)
    try:
        _result = player_board_service.mutate(
            campaign_id,
            lambda b: (
                link(b, payload.from_id, payload.to_id, payload.kind)
                if payload.op == "link"
                else unlink(b, payload.from_id, payload.to_id, payload.kind)
            ),
        )
        return {"status": "ok", "result": _result}
    except ValueError as _e:
        raise HTTPException(status_code=422, detail=str(_e)) from _e
