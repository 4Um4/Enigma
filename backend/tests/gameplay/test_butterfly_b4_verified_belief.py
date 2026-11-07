# path: /project/backend/tests/gameplay/test_butterfly_b4_verified_belief.py
# Назначение: B4 — доказать что Торнин получает verified слух от maid_lusya
#   через production цепочку: COMMUNICATION_CLAIM → membrane → BeliefRevisionEngine → EpistemicStore
# Зависимости: tests.gameplay.harness, app.services.llm.health, app.services.npc.epistemic_store
# Запуск: cd backend; $env:ENIGMA_B4_APPROVED=1; python -m pytest tests/gameplay/test_butterfly_b4_verified_belief.py -v -s
#
# КРИТЕРИЙ ЗАПУСКА (по Мастеру):
#   1. ENIGMA_B4_APPROVED=1 (env var)
#   2. LLM-server :8181 (HTTP /v1/models)
#   3. S3 завершена (вне теста)
#   4. Тихое окно (вне теста)
#   5. Нет конфликтующих WIP-изменений

"""
B4 — verified belief у Торнина.

Production wiring (как B3): ModelRouter, PropositionVerifier, RouterAdapter,
DialogueExecutor, DialogueMaterializer, ThreadPoolExecutor.

НЕ использует: router=None, PassthroughVerifier, SyncPool, ручной belief.

Доказывает 7 критериев:
  1. Люся произносит подтверждённое сообщение (NPC_SPOKE + verifier YES)
  2. COMMUNICATION_CLAIM доставляется Торнину (source=maid_lusya, target=tornin)
  3. Мембрана допускает получение (Торнин как слушатель)
  4. EpistemicStore Торнина: (player, INSULTED, tornin)
  5. Provenance: source_id=maid_lusya, original_source_id=player
  6. Качество: confidence>0, source_type=testimony
  7. Cognition: EpistemicContextResolver возвращает proposition для Торнина

Ограничение: Торнин получает знание только через COMMUNICATION_CLAIM → membrane
→ BeliefRevisionEngine, не напрямую из EpistemicStore Люси.

Provenance схема (археология):
  EpistemicRecord.source_id = claim.speaker_id (перезаписывается свежим)
  EpistemicRecord.source_type = reliability_context.get("source_type", "testimony")
  EpistemicRecord.original_source_id = из записи спикера (G10 fix, сохраняется)

  Для INSULTED: source_type всегда "testimony" (ObservationSubscriber не обрабатывает
  PLAYER_INSULTS — только THEFT и PLAYER_ATTACKED).
"""

from __future__ import annotations

import ast
import copy
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

# sys.path patch — позволяет запускать без `cd backend`
_BACKEND = Path(__file__).parent.parent.parent  # backend/
sys.path.insert(0, str(_BACKEND))
_ROOT = _BACKEND.parent  # Enigma/
sys.path.insert(0, str(_ROOT))

import pytest
from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.butterfly_b4")

_CAMPAIGN = "Open_road"
_VICTIM = "tavern_keeper_tornin"
_WITNESS = "maid_lusya"
_PLAYER = "player"

_B4_REQUIRED_PORT = 8181

# Verifier status classification — exact prefixes from proposition_verifier.py
# L91, L107, L113, L121, L128, L133. Никакого substring matching.
_VERIFIER_STATUS_PREFIXES: tuple = (
    ("verify \u2192 YES (confirmed)", "YES"),
    ("verify \u2192 NO (rejected)", "NO"),
    ("verify \u2192 AMBIGUOUS verdict", "AMBIGUOUS"),
    ("verify: empty text", "EMPTY_TEXT"),
    ("verify: LLM timeout", "TIMEOUT"),
    ("verify: LLM call failed", "ERROR"),
)

_VERIFIER_YES_PREFIX = "verify \u2192 YES (confirmed)"

# B4-LM fix #1: polarity required for complete linkage.
# "player insulted tornin" и "player did NOT insult tornin" имеют одинаковые
# три поля, но противоположный смысл. polarity различает их.
# Если polarity отсутствует в любой из записей — linkage incomplete (не silent match).
_PROPOSITION_KEY_FIELDS = ("subject_id", "predicate", "object_id", "polarity")

# Spies
SPY_SPOKE: List[dict] = []
SPY_CLAIM: List[dict] = []
_GLOBAL_CAPTURE_ORDER: int = 0

_ORIG_DISPOSITIONS: Optional[dict] = None
_SUBSCRIBED_SPIES: List[tuple] = []


def _verifier_msg(record: logging.LogRecord) -> str:
    return record.getMessage()


def _extract_prop_from_verifier_msg(msg: str) -> dict:
    _prefix = "prop="
    _idx = msg.find(_prefix)
    if _idx == -1:
        return {}
    _start = _idx + len(_prefix)
    if _start >= len(msg) or msg[_start] != "{":
        return {}
    _depth = 0
    _end = -1
    for _i in range(_start, len(msg)):
        if msg[_i] == "{":
            _depth += 1
        elif msg[_i] == "}":
            _depth -= 1
            if _depth == 0:
                _end = _i + 1
                break
    if _end == -1:
        return {}
    try:
        _parsed = ast.literal_eval(msg[_start:_end])
        if isinstance(_parsed, dict):
            return _parsed
    except Exception:
        pass
    return {}


def _match_prop(verifier_prop: dict, expected: dict) -> bool:
    if not verifier_prop or not expected:
        return False
    # B4-LM fix #1: polarity обрабатывается специально.
    # Если polarity отсутствует в любой из записей → linkage incomplete → False.
    # Не допускаем silent match на None == None.
    for _f in _PROPOSITION_KEY_FIELDS:
        if _f == "polarity":
            if "polarity" not in verifier_prop or "polarity" not in expected:
                return False  # incomplete linkage
            if verifier_prop["polarity"] != expected["polarity"]:
                return False
        else:
            if verifier_prop.get(_f) != expected.get(_f):
                return False
    return True


# ============================================================================
# TRANSCRIPT CAPTURE HELPERS (B4-LM)
# Эти функции НЕ влияют на assertions; они только собирают и сохраняют
# стенограмму для последующего анализа. Связь claim ↔ verifier — через
# proposition-dict (structured) с polarity, не через текст. Статус verifier —
# по точному prefix match. JSON-сериализация безопасна (default=str + fallback).
# Ограничение: при совпадении proposition у нескольких реплик индивидуальная
# атрибуция невозможна — это явно отмечено в _meta.verifier_linkage_limitations.
# ============================================================================


def _classify_verifier_status(msg: str) -> str:
    """Точная классификация статуса verifier по префиксу сообщения.

    Не использует substring matching — только startswith.
    Возвращает "UNKNOWN" если ни один префикс не подошёл.
    Источник префиксов: proposition_verifier.py L91, L107, L113, L121, L128, L133.
    """
    for _prefix, _status in _VERIFIER_STATUS_PREFIXES:
        if msg.startswith(_prefix):
            return _status
    return "UNKNOWN"


def _collect_verifier_records(caplog_records: list) -> list:
    """Собирает verifier records из caplog.

    Каждая запись: {status, proposition, proposition_parse_ok, level, message}.
    Записи без proposition (parse failed) — proposition={}, proposition_parse_ok=False.
    Такие записи не участвуют в linkage, но попадают в вывод как unattributed.
    """
    _records = []
    for _r in caplog_records:
        if "proposition_verifier" not in _r.name:
            continue
        _msg = _r.getMessage()
        _prop = _extract_prop_from_verifier_msg(_msg)
        _records.append(
            {
                "status": _classify_verifier_status(_msg),
                "proposition": _prop,
                "proposition_parse_ok": bool(_prop),
                "level": _r.levelname,
                "message": _msg,
            }
        )
    return _records


def _link_claims_to_verifier(claims: list, verifier_records: list) -> list:
    """Связывает каждый claim с verifier records по proposition-dict.

    Связь: точное равенство (subject_id, predicate, object_id, polarity).
    B4-LM fix #1: polarity в key. Если polarity отсутствует — linkage_complete=False.
    B4-LM fix #2: bool(_matched) обязателен — empty _matched НЕ является complete.
    B4-LM fix #3: сохраняем сами verifier records (не только статусы) для археологии.
    """
    _by_prop: dict = {}
    for _v in verifier_records:
        _p = _v.get("proposition") or {}
        if not _p:
            continue
        _key = (
            _p.get("subject_id"),
            _p.get("predicate"),
            _p.get("object_id"),
            _p.get("polarity"),
        )
        _by_prop.setdefault(_key, []).append(_v)
    _result = []
    for _c in claims:
        _payload = _c.get("payload", {}) or {}
        _p = _payload.get("proposition") or {}
        _key = (
            _p.get("subject_id"),
            _p.get("predicate"),
            _p.get("object_id"),
            _p.get("polarity"),
        )
        _matched = _by_prop.get(_key, [])
        _claim_has_polarity = "polarity" in _p and _p.get("polarity") is not None
        _all_matched_have_polarity = all(
            "polarity" in (_v.get("proposition") or {}) and (_v.get("proposition") or {}).get("polarity") is not None
            for _v in _matched
        )
        # B4-LM fix #2: bool(_matched) обязателен — empty _matched НЕ является
        # complete linkage, даже если all([]) возвращает True.
        _linkage_complete = _claim_has_polarity and bool(_matched) and _all_matched_have_polarity
        _result.append(
            {
                "claim_capture_order": _c.get("_global_order"),
                "claim_source": _c.get("source"),
                "claim_target_id": _c.get("target_id"),
                "proposition": _p,
                "verifier_records_count": len(_matched),
                "verifier_statuses": sorted({_v["status"] for _v in _matched}),
                "verifier_records": _matched,
                "linkage_complete": _linkage_complete,
                "verifier_linkage_method": "proposition_dict_match_with_polarity",
            }
        )
    return _result


def _safe_json_serialize(obj: Any) -> Any:
    """Рекурсивная конвертация в JSON-безопасную форму.

    Сначала проверяет json.dumps(obj, default=str); если падает — обходит
    рекурсивно и конвертирует проблемные значения в str(obj).
    str/int/float/bool/None проходят как есть. dict/list/tuple обходятся.
    Исходный `text` (str) сохраняется всегда — это базовый тип, не конвертируется.
    """
    try:
        json.dumps(obj, default=str)
        return obj
    except (TypeError, ValueError):
        pass
    if isinstance(obj, dict):
        return {str(_k): _safe_json_serialize(_v) for _k, _v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_json_serialize(_v) for _v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _safe_json_dump(data: dict, path: Path) -> None:
    """Сохраняет JSON: ensure_ascii=False, indent=2, default=str + fallback.

    Родительский каталог создаётся через mkdir(parents=True, exist_ok=True).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    _sanitized = _safe_json_serialize(data)
    with path.open("w", encoding="utf-8") as _f:
        json.dump(_sanitized, _f, ensure_ascii=False, indent=2, default=str)


def _build_transcript(
    *,
    spoke_events: list,
    claim_events: list,
    verifier_records: list,
    victim: str,
    witness: str,
) -> dict:
    """Собирает финальную структуру transcript для JSON-дампа."""
    _tornin_spoke = [_e for _e in spoke_events if _e.get("source") == victim]
    _lusya_to_tornin_spoke = [
        _e for _e in spoke_events if _e.get("source") == witness and _e.get("target_id") == victim
    ]
    _lusya_to_tornin_claims = [
        _c for _c in claim_events if _c.get("source") == witness and _c.get("target_id") == victim
    ]
    return {
        "_meta": {
            "schema_version": "1.0",
            "generated_at": datetime.now(UTC).isoformat(),
            "_global_order_note": "test-internal capture order, not production field",
            "verifier_linkage_method": "proposition_dict_match_with_polarity",
            "verifier_linkage_limitations": (
                "If multiple speeches share the same proposition (including polarity), "
                "individual attribution to a specific speech is not possible from log data. "
                "If polarity is missing in either claim or verifier proposition, "
                "linkage_complete=False — match is recorded but flagged as incomplete."
            ),
            "verifier_status_classification": "exact prefix match on log message",
            "verifier_status_source": ("proposition_verifier.py L91, L107, L113, L121, L128, L133"),
        },
        "spoke_events": spoke_events,
        "claim_events": claim_events,
        "verifier_records": verifier_records,
        "claim_to_verifier_linkage": _link_claims_to_verifier(claim_events, verifier_records),
        "tornin_reactions": {
            "spoke_count": len(_tornin_spoke),
            "spoke_events": _tornin_spoke,
            "disclaimer": (
                "Zero reactions is not a defect by itself. For a reaction, "
                "an NPC needs its own decision, suitable context, and ability to act."
            ),
        },
        "lusya_to_tornin": {
            "spoke_count": len(_lusya_to_tornin_spoke),
            "claim_count": len(_lusya_to_tornin_claims),
            "spoke_events": _lusya_to_tornin_spoke,
            "claim_events": _lusya_to_tornin_claims,
        },
        "hypotheses_for_research": [
            "confidence < REPORT_CONFIDENCE_THRESHOLD (0.25)",
            "cold-start блокировка cognition context resolver",
            "не было адресованного диалога с Торниным (target_id != tornin)",
        ],
        "hypotheses_disclaimer": (
            "Эти гипотезы представлены для последующего исследования и не "
            "являются диагностическими выводами. Нулевое количество реплик "
            "Торнина само по себе не доказывает ни одну из них. Для реакции "
            "нужны собственное решение, подходящий контекст и возможность действовать."
        ),
    }


def _format_transcript_summary(transcript: dict) -> str:
    """Форматирует краткое summary для stdout (не JSON)."""
    _lines = ["=== B4 TRANSCRIPT SUMMARY ==="]
    _lines.append(
        f"spoke_events: {len(transcript['spoke_events'])}, "
        f"claim_events: {len(transcript['claim_events'])}, "
        f"verifier_records: {len(transcript['verifier_records'])}"
    )
    # ALL NPC SPEECH — полный текст для проверки характера мира
    _lines.append("")
    _lines.append("=== ALL NPC SPEECH (полный текст, характер мира) ===")
    for _e in transcript["spoke_events"]:
        _lines.append(
            f"  [#{_e['_global_order']}] "
            f"{_e.get('source')} → {_e.get('target_id')} "
            f"(intent={_e.get('intent_type')}): "
            f"{_e.get('text', '')}"
        )
    _v_statuses: dict = {}
    for _v in transcript["verifier_records"]:
        _s = _v["status"]
        _v_statuses[_s] = _v_statuses.get(_s, 0) + 1
    _lines.append("")
    _lines.append(f"verifier statuses: {_v_statuses}")
    _t = transcript["tornin_reactions"]
    _lines.append("")
    _lines.append(f"TORNIN REACTIONS: {_t['spoke_count']} spoke events")
    for _e in _t["spoke_events"]:
        _lines.append(
            f"  [#{_e['_global_order']}] "
            f"text={_e.get('text', '')!r} "
            f"target={_e.get('target_id')} "
            f"intent={_e.get('intent_type')}"
        )
    _lines.append(f"  disclaimer: {_t['disclaimer']}")
    _l = transcript["lusya_to_tornin"]
    _lines.append("")
    _lines.append(f"LUSYA → TORNIN: {_l['spoke_count']} spoke, {_l['claim_count']} claims")
    for _e in _l["spoke_events"]:
        _lines.append(f"  [#{_e['_global_order']}] text={_e.get('text', '')!r} intent={_e.get('intent_type')}")
    for _c in _l["claim_events"]:
        _lines.append(
            f"  [#{_c['_global_order']}] proposition={_c.get('proposition')} verified_by={_c.get('verified_by')!r}"
        )
    _lines.append("")
    _lines.append("HYPOTHESES (for further research, NOT diagnostics):")
    for _h in transcript["hypotheses_for_research"]:
        _lines.append(f"  - {_h}")
    _lines.append(f"  disclaimer: {transcript['hypotheses_disclaimer']}")
    return "\n".join(_lines)


def _spy_npc_spoke(event: Any) -> None:
    global _GLOBAL_CAPTURE_ORDER
    _pl = getattr(event, "payload", {}) or {}
    _pl_dict: dict = dict(_pl) if isinstance(_pl, dict) else {}
    SPY_SPOKE.append(
        {
            "_global_order": _GLOBAL_CAPTURE_ORDER,
            "source": getattr(event, "source", "?"),
            "target_id": _pl_dict.get("target_id"),
            "text": _pl_dict.get("text", ""),
            "intent_type": _pl_dict.get("intent_type"),
            "payload": _pl_dict,
        }
    )
    _GLOBAL_CAPTURE_ORDER += 1


def _spy_comm_claim(event: Any) -> None:
    global _GLOBAL_CAPTURE_ORDER
    _pl = getattr(event, "payload", {}) or {}
    _pl_dict: dict = dict(_pl) if isinstance(_pl, dict) else {}
    _prop = _pl_dict.get("proposition") or {}
    SPY_CLAIM.append(
        {
            "_global_order": _GLOBAL_CAPTURE_ORDER,
            "source": getattr(event, "source", "?"),
            "target_id": _pl_dict.get("target_id"),
            "proposition": _prop,
            "verified_by": _pl_dict.get("verified_by", "?"),
            "payload": _pl_dict,
        }
    )
    _GLOBAL_CAPTURE_ORDER += 1


def _install_spies() -> None:
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType

    _bus = get_event_bus()
    _bus.subscribe(EventType.NPC_SPOKE, _spy_npc_spoke)
    _bus.subscribe(EventType.COMMUNICATION_CLAIM, _spy_comm_claim)
    _SUBSCRIBED_SPIES.append((EventType.NPC_SPOKE, _spy_npc_spoke))
    _SUBSCRIBED_SPIES.append((EventType.COMMUNICATION_CLAIM, _spy_comm_claim))


def _uninstall_spies() -> None:
    if not _SUBSCRIBED_SPIES:
        return
    try:
        from app.services.events.event_bus import get_event_bus

        _bus = get_event_bus()
        for _et, _handler in _SUBSCRIBED_SPIES:
            try:
                _bus.unsubscribe(_et, _handler)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        _SUBSCRIBED_SPIES.clear()


def _backup_dispositions() -> None:
    global _ORIG_DISPOSITIONS
    from app.domain import epistemic_dispositions as _ed

    _ORIG_DISPOSITIONS = copy.deepcopy(_ed.EPISTEMIC_DISPOSITIONS)


def _restore_dispositions() -> None:
    global _ORIG_DISPOSITIONS
    if _ORIG_DISPOSITIONS is None:
        return
    try:
        from app.domain import epistemic_dispositions as _ed

        _ed.EPISTEMIC_DISPOSITIONS.clear()
        _ed.EPISTEMIC_DISPOSITIONS.update(copy.deepcopy(_ORIG_DISPOSITIONS))
    except Exception:
        pass
    finally:
        _ORIG_DISPOSITIONS = None


def _override_witness_disposition() -> None:
    from app.domain import epistemic_dispositions as _ed

    _ed.EPISTEMIC_DISPOSITIONS["maid"] = {
        "report": 0.0,
        "warn": 0.0,
        "attack": 0.0,
        "spread_rumor": 1.4,
        "talk": 0.8,
        "intimidate": 0.0,
    }


def _check_llm_health_http() -> bool:
    try:
        from app.core.config import settings
        from app.services.llm.health import check_llm_health

        _result = check_llm_health(use_cache=False)
        if _result.get("status") != "online":
            return False
        if settings.llama_cpp_port != _B4_REQUIRED_PORT:
            return False
        _parsed = urlparse(_result.get("url", ""))
        if _parsed.port != _B4_REQUIRED_PORT:
            return False
        return True
    except Exception:
        return False


def _check_b4_approved() -> bool:
    return os.environ.get("ENIGMA_B4_APPROVED") == "1"


def _publish_player_insults(harness, target_id, radius=15.0):
    from app.domain.events import EventDTO
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType

    _event = EventDTO(
        id=uuid4(),
        type=EventType.PLAYER_INSULTS.value,
        source=_PLAYER,
        timestamp=0.0,
        payload={
            "target_id": target_id,
            "action_type": "player_insults",
            "intent_type": "insult",
        },
        visibility="public",
        radius=radius,
        persistence_level="session",
    )
    get_event_bus().publish(_event)


def _read_epistemic_for_agent(harness, agent_id) -> List[dict]:
    """Read EpistemicStore records for specific agent."""
    _store = getattr(harness.game_loop._tick_orch, "_epistemic_store", None)
    if _store is None:
        return []
    return [r for r in _store.to_dict() if r.get("agent_id") == agent_id]


def _resolve_cognition_context(harness, agent_id) -> dict:
    """Resolve EpistemicContext for agent — check if proposition is available."""
    try:
        _resolver = getattr(harness.game_loop._tick_orch, "_epistemic_resolver", None)
        if _resolver is None:
            return {}
        _ctx = _resolver.resolve(agent_id)
        return {
            "has_report_proposition": _ctx.report_proposition is not None,
            "has_claims_about_self": len(_ctx.claims_about_self) > 0,
            "max_confidence": _ctx.max_confidence,
            "report_proposition": (str(_ctx.report_proposition) if _ctx.report_proposition else None),
        }
    except Exception as _e:
        return {"error": str(_e)}


@pytest.fixture(autouse=True)
def _clear_and_restore():
    global _GLOBAL_CAPTURE_ORDER, _ORIG_DISPOSITIONS
    _uninstall_spies()
    _restore_dispositions()
    SPY_SPOKE.clear()
    SPY_CLAIM.clear()
    _SUBSCRIBED_SPIES.clear()
    _ORIG_DISPOSITIONS = None
    _GLOBAL_CAPTURE_ORDER = 0
    yield
    _uninstall_spies()
    _restore_dispositions()
    _GLOBAL_CAPTURE_ORDER = 0


class TestButterflyB4VerifiedBelief:
    """B4: verified belief у Торнина — получает слух через COMMUNICATION_CLAIM."""

    def test_pre_flight(self) -> None:
        if not _check_b4_approved():
            pytest.skip("ENIGMA_B4_APPROVED != 1")
        if not _check_llm_health_http():
            pytest.skip("LLM-server :8181 не отвечает")

    def test_b4_tornin_receives_verified_belief(self, caplog: Any) -> None:
        """B4 — Торнин получает verified слух от maid_lusya.

        7 критериев (по Мастеру):
        1. Речь Люси: NPC_SPOKE + verifier YES
        2. Доставка: COMMUNICATION_CLAIM source=maid_lusya, target=tornin
        3. Мембрана: Торнин как слушатель
        4. Belief: (player, INSULTED, tornin) в EpistemicStore Торнина
        5. Provenance: source_id=maid_lusya, original_source_id=player
        6. Качество: confidence>0, source_type=testimony
        7. Cognition: EpistemicContextResolver возвращает proposition
        """
        # AUTO-START LLM via Host broker (:8182 → spawns llama-server :8181)
        # Pattern from IPT.py: ensure_llm(label=...) — discovery + spawn Host
        # (если мёртв) + POST /ensure (respawn llama-server если мёртв) +
        # heartbeat thread; release_lease регистрируется в atexit ВНУТРИ SDK
        # (app.services.llm.runtime.client.ensure_llm) — НЕ дублируем.
        # Вердикт Мастера: Host broker и llama-server переживают shutdown
        # управляющего процесса (release_lease отпускает lease, процессы НЕ kill).
        try:
            from app.services.llm.runtime.client import ensure_llm

            ensure_llm(label="B4")
        except Exception as _llm_err:
            # Любой отказ (CI без Models LLM/, таймаут Host startup, OSError
            # из Popen, RuntimeError из /ensure) — продолжаем без LLM; pre-flight
            # check ниже пропустит тест. Широкий catch вместо (ModuleNotFoundError,
            # OSError) — Host/SDK поднимает RuntimeError при невозможности lease.
            print(f"⚠️ B4: LLM auto-start failed ({_llm_err!r}). MVP продолжает без LLM.")

        # KILLER_SPIRIT (санкция Мастера): убийца призрачных backend-связок
        # Ланчер умирает, не убив детей (llama-server:8181 + uvicorn:8000).
        # Каждый запуск B4 = гигиена проекта: осиротевшие связки убиваются ДО
        # инвариантов. Деградация канала, не тика: любой отказ уборщика
        # печатается громко и НЕ роняет B4 (L4: без тихих глотаний).
        # Opt-out: env B4_NO_REAPER=1 (CI/спец-прогоны).
        try:
            if os.environ.get("B4_NO_REAPER", "").strip().lower() not in (
                "1",
                "true",
                "yes",
            ):
                from scripts.ghost_reaper import reap as _reap

                _reaper_pre = _reap(dry_run=False)
                print(
                    "[B4] KILLER_SPIRIT старт: убито="
                    f"{len(_reaper_pre.get('killed', []))}, пощажено="
                    f"{len(_reaper_pre.get('spared', []))}, отказов="
                    f"{len(_reaper_pre.get('fault', []))}"
                )
        except Exception as _reaper_exc:  # noqa: BLE001 — канальный отказ, не тика
            print(f"[B4] KILLER_SPIRIT FAULT (не критично): {_reaper_exc!r}")

        # PRE-FLIGHT
        if not _check_b4_approved():
            pytest.skip("ENIGMA_B4_APPROVED != 1")
        if not _check_llm_health_http():
            pytest.skip("LLM-server :8181 не отвечает")

        _h: TavernGameplayHarness | None = None

        try:
            _backup_dispositions()
            _h = TavernGameplayHarness(seed=42, location="tavern")
            _h.new_game()
            _install_spies()
            _override_witness_disposition()

            _h.advance_ticks(2)
            _publish_player_insults(_h, _VICTIM, radius=15.0)

            caplog.clear()
            with caplog.at_level(logging.DEBUG, logger="app.services.cognition.proposition_verifier"):
                _t0 = time.monotonic()
                _h.advance_ticks(10)
                _elapsed = time.monotonic() - _t0
            print(f"[B4] advance_ticks(10): {_elapsed:.1f}s")

            # === КРИТЕРИЙ 1: Речь Люси + verifier YES ===
            # B4-LM fix #1: polarity required for complete linkage.
            # Proposition.polarity — boolean: True для утвердительного,
            # False для отрицания. Контракт ENIGMA.
            _expected_prop = {
                "subject_id": _PLAYER,
                "predicate": "insulted",
                "object_id": _VICTIM,
                "polarity": True,
            }

            _verifier_records = [r for r in caplog.records if "proposition_verifier" in r.name]
            _verifier_yes = [r for r in _verifier_records if _verifier_msg(r).startswith(_VERIFIER_YES_PREFIX)]
            _verifier_yes_for_prop = [
                r
                for r in _verifier_yes
                if _match_prop(_extract_prop_from_verifier_msg(_verifier_msg(r)), _expected_prop)
            ]

            _maid_speech = [s for s in SPY_SPOKE if s["source"] == _WITNESS and s["text"] and s["text"].strip()]

            print(
                f"[CHECK 1] maid_lusya speech: {len(_maid_speech)}, "
                f"verifier YES for prop: {len(_verifier_yes_for_prop)}"
            )

            crit1_speech = len(_maid_speech) > 0
            crit1_verifier_yes = len(_verifier_yes_for_prop) > 0

            # === КРИТЕРИЙ 2: COMMUNICATION_CLAIM доставляется Торнину ===
            _claims_to_tornin = [c for c in SPY_CLAIM if c["target_id"] == _VICTIM]
            _claims_from_maid = [c for c in _claims_to_tornin if c["source"] == _WITNESS]

            print(
                f"[CHECK 2] COMMUNICATION_CLAIM to tornin: {len(_claims_to_tornin)}, "
                f"from maid: {len(_claims_from_maid)}"
            )

            crit2_claim_delivered = len(_claims_from_maid) > 0

            # === КРИТЕРИЙ 3: Мембрана (косвенно — если claim доставлен, мембрана пропустила) ===
            crit3_membrane = crit2_claim_delivered  # COMMUNICATION_CLAIM опубликован → мембрана допустила

            # === КРИТЕРИЙ 4: EpistemicStore Торнина ===
            _tornin_records = _read_epistemic_for_agent(_h, _VICTIM)

            _insulted_records = [
                r
                for r in _tornin_records
                if r.get("proposition", {}).get("predicate") == "insulted"
                and r.get("proposition", {}).get("subject_id") == _PLAYER
                and r.get("proposition", {}).get("object_id") == _VICTIM
            ]

            print(
                f"[CHECK 4] tornin EpistemicStore: {len(_tornin_records)} records, INSULTED: {len(_insulted_records)}"
            )

            crit4_belief = len(_insulted_records) > 0

            # === КРИТЕРИЙ 5: Provenance ===
            crit5_source_id_maid = False
            crit5_original_player = False

            if _insulted_records:
                _rec = _insulted_records[0]
                _src = _rec.get("source_id", "")
                _orig = _rec.get("original_source_id", "")
                print(f"[CHECK 5] source_id={_src!r}, original_source_id={_orig!r}")
                crit5_source_id_maid = _src == _WITNESS
                crit5_original_player = _orig == _PLAYER

            # === КРИТЕРИЙ 6: Качество записи ===
            crit6_confidence = False
            crit6_source_type = False

            if _insulted_records:
                _rec = _insulted_records[0]
                _conf = _rec.get("confidence", 0)
                _st = _rec.get("source_type", "")
                print(f"[CHECK 6] confidence={_conf}, source_type={_st!r}")
                crit6_confidence = _conf > 0
                crit6_source_type = _st == "testimony"

            # === КРИТЕРИЙ 7: Cognition context ===
            _cog = _resolve_cognition_context(_h, _VICTIM)
            print(f"[CHECK 7] cognition: {_cog}")

            crit7_cognition = _cog.get("has_report_proposition", False) or _cog.get("has_claims_about_self", False)

            # === TRANSCRIPT CAPTURE (B4-LM) — всегда, даже при FAIL ===
            # Не влияет на assertions. Сохраняет полную стенограмму для анализа.
            # Связь claim ↔ verifier через proposition-dict (structured) с polarity.
            # Статус verifier по точному prefix match.
            try:
                _verifier_records_b4 = _collect_verifier_records(list(caplog.records))
                _transcript = _build_transcript(
                    spoke_events=list(SPY_SPOKE),
                    claim_events=list(SPY_CLAIM),
                    verifier_records=_verifier_records_b4,
                    victim=_VICTIM,
                    witness=_WITNESS,
                )
                _transcript_path = Path(__file__).parent / "data" / "b4_transcript.json"
                _safe_json_dump(_transcript, _transcript_path)
                print(f"\n[TRANSCRIPT] saved to: {_transcript_path}")
                print(_format_transcript_summary(_transcript))
            except Exception as _transcript_err:
                print(f"\n[TRANSCRIPT ERROR] {_transcript_err!r}")

            # === VERDICT ===
            all_criteria = [
                ("1. maid_lusya speech", crit1_speech),
                ("1. verifier YES for prop", crit1_verifier_yes),
                ("2. COMMUNICATION_CLAIM from maid to tornin", crit2_claim_delivered),
                ("3. membrane (claim delivered)", crit3_membrane),
                ("4. INSULTED in tornin EpistemicStore", crit4_belief),
                ("5. source_id=maid_lusya", crit5_source_id_maid),
                ("5. original_source_id=player", crit5_original_player),
                ("6. confidence>0", crit6_confidence),
                ("6. source_type=testimony", crit6_source_type),
                ("7. cognition context available", crit7_cognition),
            ]

            print(f"\n[VERDICT CHECK] {len(all_criteria)} criteria:")
            for _name, _passed in all_criteria:
                _status = "✅" if _passed else "❌"
                print(f"  {_status} {_name}")

            _all_pass = all(_p for _, _p in all_criteria)

            if _all_pass:
                print("\n[OK] B4 PASS: Торнин получил verified слух от maid_lusya")
                print("  source_id=maid_lusya, original_source_id=player")
                print("  confidence>0, source_type=testimony")
                print("  cognition context: proposition available")
            else:
                _failed = [n for n, p in all_criteria if not p]
                pytest.fail(
                    f"B4 FAIL: {len(_failed)} criteria not met:\n  - " + "\n  - ".join(_failed) + f"\n\nDiagnostics:\n"
                    f"  SPY_SPOKE total: {len(SPY_SPOKE)}\n"
                    f"  SPY_CLAIM total: {len(SPY_CLAIM)}\n"
                    f"  maid_lusya speech: {len(_maid_speech)}\n"
                    f"  verifier YES for prop: {len(_verifier_yes_for_prop)}\n"
                    f"  claims to tornin from maid: {len(_claims_from_maid)}\n"
                    f"  tornin EpistemicStore records: {len(_tornin_records)}\n"
                    f"  INSULTED records: {len(_insulted_records)}\n"
                    f"  cognition: {_cog}"
                )

        finally:
            _uninstall_spies()
            _restore_dispositions()
            if _h is not None:
                try:
                    _h.dispose()
                except Exception:
                    pass

    def test_b4_transcript_json_serialization_synthetic(self, tmp_path: Path) -> None:
        """B4-LM: проверка JSON-сериализации на синтетических типах.

        Не требует ENIGMA_B4_APPROVED и LLM-server — это unit-тест.
        Проверяет что:
          - str/int/float/bool/None сохраняются как есть
          - dict/list проходят рекурсивно
          - datetime/set/object конвертируются в str (default=str + fallback)
          - UTF-8 текст с unicode-символами сохраняется (ensure_ascii=False)
          - файл создаётся и парсится обратно
        """
        _synthetic = {
            "str_field": "Текст с unicode: → ← ✓ ✓",
            "int_field": 42,
            "float_field": 3.14,
            "bool_field": True,
            "none_field": None,
            "list_field": [1, "two", None, {"nested": "dict"}],
            "dict_field": {"key": "value", "nested_dict": {"a": 1}},
            "datetime_field": datetime.now(UTC),
            "set_field": {"a", "b"},
            "nested_with_unserializable": {
                "ok": "fine",
                "bad": object(),
            },
            "payload_simulated": {
                "text": "Open_road оскорбил Tavern_keeper_tornin",
                "target_id": "tavern_keeper_tornin",
                "intent_type": "report_insult",
                "proposition": {
                    "subject_id": "player",
                    "predicate": "insulted",
                    "object_id": "tavern_keeper_tornin",
                    "polarity": True,
                },
            },
        }
        _path = tmp_path / "b4_serialization_test.json"
        _safe_json_dump(_synthetic, _path)
        assert _path.exists(), f"file not created at {_path}"
        with _path.open("r", encoding="utf-8") as _f:
            _loaded = json.load(_f)
        assert _loaded["str_field"] == "Текст с unicode: → ← ✓ ✓"
        assert _loaded["int_field"] == 42
        assert _loaded["bool_field"] is True
        assert _loaded["none_field"] is None
        assert isinstance(_loaded["datetime_field"], str)
        assert isinstance(_loaded["set_field"], str)
        assert isinstance(_loaded["nested_with_unserializable"]["bad"], str)
        assert _loaded["payload_simulated"]["text"] == "Open_road оскорбил Tavern_keeper_tornin"
        print(f"[SERIALIZATION TEST] OK — file at {_path}")
