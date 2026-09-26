"""
path: /frontend/ui_workbench/editor_board_stub.py
Назначение: Полигон Доски в редакторе карт (Phase 4.1-P). In-memory
    реализация board-контракта (те же 5 методов, что api_client):
    редактор — песочница UX, не SSOT; закрытие редактора сбрасывает
    доску осознанно (демо-данные не пачкают сейвы). Семантика ответов
    и схема id зеркалят routes_board/player_board_service — UI-код
    не различает полигон и игру.
Зависимости: copy (stdlib)
Основные сущности: EditorBoardStub
"""

import copy


class EditorBoardStub:
    """Board-шлюз полигона. Ключи — константы зеркально сервису
    (§12.1); ValueError = громкий отказ (L4), как в production."""

    _K_VER = "version"
    _K_NEXT_CARD = "next_card_id"
    _K_NEXT_HYP = "next_hypothesis_id"
    _K_CARDS = "cards"
    _K_LINKS = "links"
    _K_HYPS = "hypotheses"
    _K_ID = "id"
    _K_REF_TYPE = "ref_type"
    _K_REF_ID = "ref_id"
    _K_POS = "pos"
    _K_FROM = "from"
    _K_TO = "to"
    _K_KIND = "kind"
    _K_TEXT = "text"
    _K_STATUS = "status"

    def __init__(self) -> None:
        self._board = {
            self._K_VER: 1, self._K_NEXT_CARD: 1, self._K_NEXT_HYP: 1,
            self._K_CARDS: [], self._K_LINKS: [], self._K_HYPS: [],
        }

    def get_board(self, campaign_id: str) -> dict:
        return copy.deepcopy(self._board)

    def board_card_add(self, campaign_id: str, ref_type: str, ref_id: str,
                       pos: list | None = None) -> dict:
        if not ref_id:
            raise ValueError("[BOARD-STUB] ADD_CARD без ref_id запрещён")
        if ref_type == "hypothesis" and not any(
                h[self._K_ID] == ref_id for h in self._board[self._K_HYPS]):
            raise ValueError(f"[BOARD-STUB] Гипотеза {ref_id} не существует")
        _cid = f"board-card-{self._board[self._K_NEXT_CARD]:03d}"
        self._board[self._K_NEXT_CARD] += 1
        _card = {self._K_ID: _cid, self._K_REF_TYPE: ref_type,
                 self._K_REF_ID: ref_id}
        if pos is not None:
            _card[self._K_POS] = [float(pos[0]), float(pos[1])]
        self._board[self._K_CARDS].append(_card)
        return {"status": "ok", "card_id": _cid}

    def board_card_move(self, campaign_id: str, card_id: str, pos: list) -> dict:
        for _c in self._board[self._K_CARDS]:
            if _c[self._K_ID] == card_id:
                _c[self._K_POS] = [float(pos[0]), float(pos[1])]
                return {"status": "ok"}
        raise ValueError(f"[BOARD-STUB] Карточка {card_id} не существует")

    def board_card_remove(self, campaign_id: str, card_id: str) -> dict:
        _before = len(self._board[self._K_CARDS])
        self._board[self._K_CARDS] = [
            c for c in self._board[self._K_CARDS] if c[self._K_ID] != card_id]
        if len(self._board[self._K_CARDS]) == _before:
            raise ValueError(f"[BOARD-STUB] Карточка {card_id} не существует")
        self._board[self._K_LINKS] = [
            l for l in self._board[self._K_LINKS]
            if l.get(self._K_FROM) != card_id and l.get(self._K_TO) != card_id]
        return {"status": "ok"}

    def board_link(self, campaign_id: str, from_id: str, to_id: str,
                   kind: str, unlink_op: bool = False) -> dict:
        if not unlink_op:
            for _l in self._board[self._K_LINKS]:
                if (_l[self._K_FROM] == from_id and _l[self._K_TO] == to_id
                        and _l[self._K_KIND] == kind):
                    return {"status": "ok", "result": "noop"}
            self._board[self._K_LINKS].append(
                {self._K_FROM: from_id, self._K_TO: to_id, self._K_KIND: kind})
            return {"status": "ok", "result": "linked"}
        _before = len(self._board[self._K_LINKS])
        self._board[self._K_LINKS] = [
            l for l in self._board[self._K_LINKS]
            if not (l[self._K_FROM] == from_id and l[self._K_TO] == to_id
                    and l[self._K_KIND] == kind)]
        return {"status": "ok", "result":
                "unlinked" if len(self._board[self._K_LINKS]) < _before else "noop"}

    def board_hypothesis(self, campaign_id: str, op: str, hyp_id: str | None = None,
                         text: str | None = None, status: str | None = None) -> dict:
        if op == "create":
            if text is None or not text.strip():
                raise ValueError("[BOARD-STUB] Гипотеза без текста запрещена")
            _hid = f"hyp-{self._board[self._K_NEXT_HYP]:03d}"
            self._board[self._K_NEXT_HYP] += 1
            self._board[self._K_HYPS].append(
                {self._K_ID: _hid, self._K_TEXT: text, self._K_STATUS: "open"})
            return {"status": "ok", "hypothesis_id": _hid}
        if op == "edit":
            for _h in self._board[self._K_HYPS]:
                if _h[self._K_ID] == hyp_id:
                    if text is not None:
                        _h[self._K_TEXT] = text
                    if status is not None:
                        _h[self._K_STATUS] = status
                    return {"status": "ok"}
            raise ValueError(f"[BOARD-STUB] Гипотеза {hyp_id} не существует")
        # delete — каскад зеркально production
        _before = len(self._board[self._K_HYPS])
        self._board[self._K_HYPS] = [
            h for h in self._board[self._K_HYPS] if h[self._K_ID] != hyp_id]
        if len(self._board[self._K_HYPS]) == _before:
            raise ValueError(f"[BOARD-STUB] Гипотеза {hyp_id} не существует")
        _doomed = {c[self._K_ID] for c in self._board[self._K_CARDS]
                   if c.get(self._K_REF_TYPE) == "hypothesis"
                   and c.get(self._K_REF_ID) == hyp_id}
        self._board[self._K_CARDS] = [
            c for c in self._board[self._K_CARDS]
            if c[self._K_ID] not in _doomed]
        self._board[self._K_LINKS] = [
            l for l in self._board[self._K_LINKS]
            if l[self._K_FROM] not in _doomed and l[self._K_TO] not in _doomed]
        return {"status": "ok"}