"""
path: /project/backend/app/services/player_board_service.py
Назначение: Investigation Board (Phase 4 MVI) — presentation-persistence.
    Единственный писатель файла saves/<campaign>/board_state.json.
    Board хранит ТОЛЬКО организацию ссылок (ref_type + ref_id), не знание:
    резолв материала — работа presentation layer / клиента. Board не знает,
    что является истиной, и МОЖЕТ ОШИБАТЬСЯ — это его нормальное состояние
    («Горан — вор» + три ложных свидетельства хранятся спокойно).
Зависимости: json, os, re, threading, pathlib, typing — ТОЛЬКО stdlib.
    Запрещённые зависимости (ТЗ Phase 4 §5, enforcement ниже — их здесь
    физически нет, ни одного импорта из app.): epistemic_store,
    player_beliefs, Predicate, TruthState, ACCUSE, LLM, EventBus,
    мутация Journal. event_id для ref_type=journal здесь НЕ
    интерпретируется — это opaque reference.
Основные сущности: PlayerBoardService (write-path), чистые операции
    над BoardState (add/remove/move/link/unlink/hypotheses).
"""
import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── Ключи — константы, не строки (Устав §12.1) ──────────────────
_KEY_VERSION = "version"
_KEY_NEXT_CARD = "next_card_id"
_KEY_NEXT_HYP = "next_hypothesis_id"
_KEY_CARDS = "cards"
_KEY_LINKS = "links"
_KEY_HYPOTHESES = "hypotheses"
_KEY_ID = "id"
_KEY_REF_TYPE = "ref_type"
_KEY_REF_ID = "ref_id"
_KEY_POS = "pos"
_KEY_FROM = "from"
_KEY_TO = "to"
_KEY_KIND = "kind"
_KEY_TEXT = "text"
_KEY_STATUS = "status"

_BOARD_FILENAME = "board_state.json"
_CARD_PREFIX = "board-card-"
_HYP_PREFIX = "hyp-"
_ID_MIN_WIDTH = 3

# Схема принимает все 4 ref_type (вердикт Мастера: формат файла стабилен);
# MVI реально резолвятся journal+hypothesis, claim/belief — persisted
# opaque-ссылки, клиент рендерит серыми. Сервер резолвом не занимается.
VALID_REF_TYPES = frozenset({"journal", "claim", "belief", "hypothesis"})
# user-authored relation: «игрок считает, что A поддерживает B» —
# НЕ объективная семантика (ТЗ §2)
VALID_LINK_KINDS = frozenset({"PLAYER_SUPPORTS", "PLAYER_CONTRADICTS"})

_CARD_ID_RE = re.compile(r"^board-card-(\d+)$")
_HYP_ID_RE = re.compile(r"^hyp-(\d+)$")

_SCHEMA_VERSION = 1


def _empty_board() -> Dict[str, Any]:
    return {
        _KEY_VERSION: _SCHEMA_VERSION,
        _KEY_NEXT_CARD: 1,
        _KEY_NEXT_HYP: 1,
        _KEY_CARDS: [],
        _KEY_LINKS: [],
        _KEY_HYPOTHESES: [],
    }


# ── Self-repair счётчиков: ТОЛЬКО вверх (вердикт Мастера) ───────
# Отказ от uuid4 означает: монотонность — единственная защита от
# коллизии id при ручной правке/повреждении файла. Переиспользование
# существующего ID запрещено всегда.

def _repair_counters(board: Dict[str, Any]) -> None:
    declared_card = int(board.get(_KEY_NEXT_CARD, 1))
    declared_hyp = int(board.get(_KEY_NEXT_HYP, 1))
    max_card = 0
    for _c in board.get(_KEY_CARDS, []):
        _m = _CARD_ID_RE.match(str(_c.get(_KEY_ID, "")))
        if _m:
            max_card = max(max_card, int(_m.group(1)))
    max_hyp = 0
    for _h in board.get(_KEY_HYPOTHESES, []):
        _m = _HYP_ID_RE.match(str(_h.get(_KEY_ID, "")))
        if _m:
            max_hyp = max(max_hyp, int(_m.group(1)))
    board[_KEY_NEXT_CARD] = max(declared_card, max_card + 1)
    board[_KEY_NEXT_HYP] = max(declared_hyp, max_hyp + 1)


def _allocate_id(
    board: Dict[str, Any], counter_key: str, prefix: str,
    collection_key: str,
) -> str:
    """Выдаёт следующий свободный id. While-цикл = защита от дублей
    при ручном JSON: счетчик после repair уже > max, но дубли внутри
    коллекции (два board-card-001 руками) не должны порождать третий."""
    existing = {
        str(_c.get(_KEY_ID, "")) for _c in board.get(collection_key, [])
    }
    _n = int(board.get(counter_key, 1))
    while f"{prefix}{_n:0{_ID_MIN_WIDTH}d}" in existing:
        _n += 1
    board[counter_key] = _n + 1
    return f"{prefix}{_n:0{_ID_MIN_WIDTH}d}"


def _find_card(board: Dict[str, Any], card_id: str) -> Optional[Dict[str, Any]]:
    for _c in board.get(_KEY_CARDS, []):
        if str(_c.get(_KEY_ID, "")) == card_id:
            return _c
    return None


def _hyp_exists(board: Dict[str, Any], hyp_id: str) -> bool:
    return any(
        str(_h.get(_KEY_ID, "")) == hyp_id
        for _h in board.get(_KEY_HYPOTHESES, [])
    )


# ══ ЧИСТЫЕ ОПЕРАЦИИ над BoardState (мутируют board, без I/O) ════
# Нарушение контракта = громкий ValueError (L4: никаких тихих отказов).
# Каждая операция из закрытого списка ТЗ §3 — одна функция.

def add_card(
    board: Dict[str, Any], ref_type: str, ref_id: str,
    pos: Optional[Tuple[float, float]] = None,
) -> str:
    """ADD_CARD. Возвращает новый card_id."""
    if ref_type not in VALID_REF_TYPES:
        raise ValueError(f"[BOARD] Недопустимый ref_type: {ref_type}")
    if not ref_id:
        raise ValueError("[BOARD] ADD_CARD без ref_id запрещён")
    if ref_type == "hypothesis" and not _hyp_exists(board, ref_id):
        # Инвариант целостности СОБСТВЕННОГО файла: указатель на
        # несуществующую гипотезу внутри доски недопустим с рождения
        raise ValueError(f"[BOARD] Гипотеза {ref_id} не существует")
    _card_id = _allocate_id(board, _KEY_NEXT_CARD, _CARD_PREFIX, _KEY_CARDS)
    _card: Dict[str, Any] = {
        _KEY_ID: _card_id,
        _KEY_REF_TYPE: ref_type,
        _KEY_REF_ID: ref_id,
    }
    if pos is not None:
        _card[_KEY_POS] = [float(pos[0]), float(pos[1])]
    board[_KEY_CARDS].append(_card)
    return _card_id


def remove_card(board: Dict[str, Any], card_id: str) -> None:
    """REMOVE_CARD + рёбра, инцидентные карточке. Висячее ребро на
    несуществующую карточку — та же битая ссылка, что card→hyp:
    инвариант целостности собственного файла."""
    _before = len(board.get(_KEY_CARDS, []))
    board[_KEY_CARDS] = [
        _c for _c in board.get(_KEY_CARDS, [])
        if str(_c.get(_KEY_ID, "")) != card_id
    ]
    if len(board[_KEY_CARDS]) == _before:
        raise ValueError(f"[BOARD] Карточка {card_id} не существует")
    board[_KEY_LINKS] = [
        _l for _l in board.get(_KEY_LINKS, [])
        if _l.get(_KEY_FROM) != card_id and _l.get(_KEY_TO) != card_id
    ]


def move_card(
    board: Dict[str, Any], card_id: str, pos: Tuple[float, float],
) -> None:
    """MOVE_CARD: координаты на «столе» (вердикт В2)."""
    _card = _find_card(board, card_id)
    if _card is None:
        raise ValueError(f"[BOARD] Карточка {card_id} не существует")
    _card[_KEY_POS] = [float(pos[0]), float(pos[1])]


def link(board: Dict[str, Any], from_id: str, to_id: str, kind: str) -> str:
    """LINK. Idempotent (вердикт Мастера): повторный клик не ломает
    состояние — существующее ребро возвращается как no-op."""
    if kind not in VALID_LINK_KINDS:
        raise ValueError(f"[BOARD] Недопустимый kind: {kind}")
    if _find_card(board, from_id) is None:
        raise ValueError(f"[BOARD] Карточка {from_id} не существует")
    if _find_card(board, to_id) is None:
        raise ValueError(f"[BOARD] Карточка {to_id} не существует")
    for _l in board.get(_KEY_LINKS, []):
        if (
            _l.get(_KEY_FROM) == from_id
            and _l.get(_KEY_TO) == to_id
            and _l.get(_KEY_KIND) == kind
        ):
            return "noop"
    board[_KEY_LINKS].append(
        {_KEY_FROM: from_id, _KEY_TO: to_id, _KEY_KIND: kind}
    )
    return "linked"


def unlink(board: Dict[str, Any], from_id: str, to_id: str, kind: str) -> str:
    """UNLINK тройкой (from, to, kind) — вердикт Мастера. Отсутствие
    ребра — безопасный no-op, не ошибка."""
    _before = len(board.get(_KEY_LINKS, []))
    board[_KEY_LINKS] = [
        _l for _l in board.get(_KEY_LINKS, [])
        if not (
            _l.get(_KEY_FROM) == from_id
            and _l.get(_KEY_TO) == to_id
            and _l.get(_KEY_KIND) == kind
        )
    ]
    return "unlinked" if len(board[_KEY_LINKS]) < _before else "noop"


def create_hypothesis(board: Dict[str, Any], text: str) -> str:
    """CREATE_HYPOTHESIS. Текст — свободный (BoardHypothesis.text,
    НЕ subject/predicate/object — табу §5)."""
    if not text or not text.strip():
        raise ValueError("[BOARD] Гипотеза без текста запрещена")
    _hyp_id = _allocate_id(board, _KEY_NEXT_HYP, _HYP_PREFIX, _KEY_HYPOTHESES)
    board[_KEY_HYPOTHESES].append(
        {_KEY_ID: _hyp_id, _KEY_TEXT: text, _KEY_STATUS: "open"}
    )
    return _hyp_id


def edit_hypothesis(
    board: Dict[str, Any], hyp_id: str,
    text: Optional[str] = None, status: Optional[str] = None,
) -> None:
    """EDIT_HYPOTHESIS. Множество статусов НЕ ограничиваем: единственный
    засвидетельствованный ТЗ статус — «open»; вводить enum без второго
    кейса — преждевременная генерализация (§ENIGMA-002)."""
    for _h in board.get(_KEY_HYPOTHESES, []):
        if str(_h.get(_KEY_ID, "")) == hyp_id:
            if text is not None:
                if not text.strip():
                    raise ValueError("[BOARD] Гипотеза без текста запрещена")
                _h[_KEY_TEXT] = text
            if status is not None:
                _h[_KEY_STATUS] = status
            return
    raise ValueError(f"[BOARD] Гипотеза {hyp_id} не существует")


def delete_hypothesis(board: Dict[str, Any], hyp_id: str) -> None:
    """DELETE_HYPOTHESIS — каскад (вердикт Мастера, инвариант
    целостности собственного файла): гипотеза + все карточки-указатели
    на неё + все рёбра этих карточек. Каскад не трогает ничего ВНЕ
    board_state.json по построению (функция видит только board)."""
    _before = len(board.get(_KEY_HYPOTHESES, []))
    board[_KEY_HYPOTHESES] = [
        _h for _h in board.get(_KEY_HYPOTHESES, [])
        if str(_h.get(_KEY_ID, "")) != hyp_id
    ]
    if len(board[_KEY_HYPOTHESES]) == _before:
        raise ValueError(f"[BOARD] Гипотеза {hyp_id} не существует")
    _doomed = {
        str(_c.get(_KEY_ID, ""))
        for _c in board.get(_KEY_CARDS, [])
        if _c.get(_KEY_REF_TYPE) == "hypothesis"
        and _c.get(_KEY_REF_ID) == hyp_id
    }
    board[_KEY_CARDS] = [
        _c for _c in board.get(_KEY_CARDS, [])
        if str(_c.get(_KEY_ID, "")) not in _doomed
    ]
    board[_KEY_LINKS] = [
        _l for _l in board.get(_KEY_LINKS, [])
        if _l.get(_KEY_FROM) not in _doomed and _l.get(_KEY_TO) not in _doomed
    ]


# ══ WRITE-PATH (единственный писатель файла) ════════════════════

class PlayerBoardService:
    """Владелец board_state.json. Lock per campaign: операции приходят
    из REST-потока (двойной клик реален) — сериализация обязательна.
    tmp + os.replace: обрыв записи не оставляет битую доску (осознанное
    отклонение от прецедента _persist_journal — доска мутируется
    пользовательскими операциями чаще журнала)."""

    def __init__(self, root: str = "saves") -> None:
        self.root = Path(root)
        self._locks: Dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, campaign_id: str) -> threading.Lock:
        with self._locks_guard:
            if campaign_id not in self._locks:
                self._locks[campaign_id] = threading.Lock()
            return self._locks[campaign_id]

    def _board_path(self, campaign_id: str) -> Path:
        return self.root / campaign_id / _BOARD_FILENAME

    def _ensure_campaign_dir(self, campaign_id: str) -> None:
        self._board_path(campaign_id).parent.mkdir(parents=True, exist_ok=True)

    def load_board(self, campaign_id: str) -> Dict[str, Any]:
        """M7-совместимость (гейт №4): файла нет / JSON без board-полей →
        пустая доска, без миграции. Неизвестные поля СОХРАНЯЮТСЯ
        (forward-compat). Битый JSON → громкий ValueError (L4: тихий
        re-init уничтожил бы игроку расследование молча)."""
        _path = self._board_path(campaign_id)
        if not _path.exists():
            return _empty_board()
        try:
            _data = json.loads(_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as _e:
            raise ValueError(
                f"[BOARD] Повреждённый {_path}: {_e}"
            ) from _e
        if not isinstance(_data, dict):
            raise ValueError(f"[BOARD] {_path}: корень не dict")
        _board = _empty_board()
        _board.update(_data)
        _repair_counters(_board)
        return _board

    def save_board_atomic(self, campaign_id: str, board: Dict[str, Any]) -> None:
        self._ensure_campaign_dir(campaign_id)
        _path = self._board_path(campaign_id)
        _tmp = _path.with_name(_path.name + ".tmp")
        _tmp.write_text(
            json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(_tmp, _path)

    def mutate(
        self, campaign_id: str,
        operation: Callable[[Dict[str, Any]], Any],
    ) -> Any:
        """Единственный write-path: lock → load → чистая операция →
        atomic save. Каждая операция = одна мутация файла (ТЗ §3).
        ValueError из операции → файл НЕ пишется (нет частичных коммитов)."""
        with self._lock_for(campaign_id):
            _board = self.load_board(campaign_id)
            _result = operation(_board)
            self.save_board_atomic(campaign_id, _board)
            return _result