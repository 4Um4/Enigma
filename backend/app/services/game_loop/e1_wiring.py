"""
DEGOD ITER5: E1-wiring-функции (перенос из game_loop/__init__.py).
Назначение: E1-wiring (S260) — резолвер темы речи + читатель отношений для decide_disclosure. DEGOD ITER5: перенос из game_loop/init.py (:131–137, :967–1005); функция от зависимостей вместо self.
Зависимости: logging, app.services.input.intent_compressor (лениво)
Основные сущности: _e1_extract_subject, e1_relationship_reader
"""

import logging

logger = logging.getLogger(__name__)


def _e1_extract_subject(topic: str):
    """E1-wiring (S260): канонический P3-резолвер темы речи в SubjectRef
    (extract_subject; обёртка "про {topic}" — паттерн E1-фикстур и
    P7-B-подписчика game_loop:446 — единый механизм, не второй)."""
    from app.services.input.intent_compressor import extract_subject

    return extract_subject(f"про {topic}")


def e1_relationship_reader(
    memory_manager, resolve_npcs_snapshot, campaign_id: str, knower_id: str, recipient_id: str
) -> dict:
    """E1-wiring (S260): читатель отношений для decide_disclosure.

    Источник — SSOT RelationshipStore (V2, RAM-authoritative);
    Vacuum (нет пары knower→recipient) → фолбэк social_stats NPC —
    канонический паттерн tick_utils (M1b.3.3+3.4: «Player-дефолты
    social_stats — фолбэк только при Vacuum в V2»). Возвращает
    {"trust": float, "fear": float} в шкале 0-100 (пороги V1:
    T_REVEAL=50, F_HIGH=60). Fail-open: любая ошибка чтения →
    пустой dict (decide_disclosure даст DENY-лестницу по нулям —
    честное «не знаю отношений», не крах диалога)."""
    try:
        _store = getattr(memory_manager, "_relationships", None) if memory_manager is not None else None
        if _store is not None:
            _rels = _store.get(campaign_id, knower_id) or {}
            _pair = _rels.get(f"{knower_id}→{recipient_id}") or {}
            if _pair:
                return {
                    "trust": float(_pair.get("trust", 0.0)),
                    "fear": float(_pair.get("fear", 0.0)),
                }
        # Vacuum → social_stats NPC (канон tick_utils)
        for _n in resolve_npcs_snapshot(campaign_id) or []:
            if not isinstance(_n, dict):
                continue
            if (_n.get("npc_id") or _n.get("id")) == knower_id:
                _ss = _n.get("social_stats") or {}
                return {
                    "trust": float(_ss.get("trust", 0.0)),
                    "fear": float(_ss.get("fear_of_player", 0.0)),
                }
        return {}
    except Exception as _e:
        logger.warning(f"[E1_WIRING] relationship read failed: {_e}")
        return {}
