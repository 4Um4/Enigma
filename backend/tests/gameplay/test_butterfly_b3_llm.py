# path: /project/backend/tests/gameplay/test_butterfly_b3_llm.py
# Назначение: B3 — LLM-интеграционный тест production DialogueExecutor + PropositionVerifier.
#   Доказывает семантическую цепочку:
#     Candidate Proposition -> LLM Dialogue -> PropositionVerifier -> COMMUNICATION_CLAIM
#   При отказе verifier: NPC_SPOKE сохраняется, COMMUNICATION_CLAIM не публикуется (fail-closed).
# Зависимости: tests.gameplay.harness, app.services.llm.health, app.services.cognition.proposition_verifier
# Основные сущности: TestButterflyB3LLM
# Запуск: cd backend; $env:ENIGMA_B3_APPROVED=1; python -m pytest tests/gameplay/test_butterfly_b3_llm.py -v -s --timeout=600
#
# КРИТЕРИЙ ЗАПУСКА (4 условия — по Мастеру):
#   1. ENIGMA_B3_APPROVED=1 (env var — технический предохранитель)
#   2. LLM-server отвечает на :8181 (HTTP /v1/models — pre-flight)
#   3. S3 официально завершена (вне теста — ручное подтверждение автора)
#   4. Тихое окно (вне теста — ручное подтверждение Мастера)

"""
B3 — production LLM integration test with semantic chain verification.

НЕ использует: router=None, PassthroughVerifier, SyncPool, ручной belief,
искусственный COMMUNICATION_CLAIM.

ИСПОЛЬЗУЕТ production wiring: ModelRouter, PropositionVerifier через RouterAdapter,
DialogueExecutor с real router, DialogueMaterializer с production verifier,
ThreadPoolExecutor (max_workers=1, production).

Instrumentation (без подмены):
  - pytest caplog — захват логов PropositionVerifier через record.getMessage()
    Точные префиксы из proposition_verifier.py L121,128,133,107,113:
      "verify -> YES (confirmed)" -> YES
      "verify -> NO (rejected)" -> NO
      "verify -> AMBIGUOUS verdict" -> AMBIGUOUS
      "verify: LLM timeout" -> timeout
      "verify: LLM call failed" -> failed
  - JSONL-лог (enigma_audit.jsonl) — бинарное чтение + decode, isolation по offset
    npc_id != "verifier" для dialogue (мягкий фильтр)
    npc_id == "verifier" для verifier calls

Изоляция: _h=None изначально, try/finally, uninstall_spies+restore_dispositions
ПЕРВЫМ в fixture (защита от предыдущего аварийного прогона).

Event correlation (усилено по ревью Мастера):
  EventDTO не имеет correlation_id. materializer создает NPC_SPOKE + COMMUNICATION_CLAIM
  в одном вызове (L91-L128). Связь через:
    - source (speaker_id) — одинаковый
    - target_id — одинаковый
    - _global_order — общий счетчик перехвата (NPC_SPOKE публикуется первым)
    - _single_pair — ровно одна пара (no competing replicas)
  Если несколько конкурирующих реплик maid_lusya->tornin -> не PASS.

Verifier Proposition correlation (финальное усиление):
  _extract_prop_from_verifier_msg() парсит prop=%s через сбалансированный поиск скобок.
  Тип Proposition: dict[str, Any] (proposition_verifier.py L89).
  Источник: post_decision.py L204-L208 — плоский dict, 4 поля.
  ast.literal_eval для безопасного парсинга Python repr.
  _match_prop() сопоставляет subject_id + predicate + object_id.
  _verifier_yes_for_prop / _verifier_no_for_prop — только для ожидаемой Proposition.

Verdicts:
  PASS: 6 условий + single_pair + precedes + verifier_yes_for_prop -> B3 закрыт
  PARTIAL: verifier_rejected_for_prop (NO/AMBIGUOUS без YES) + partial_single_speech
           + claim suppressed + NPC_SPOKE saved -> НЕ закрывает B3 (pytest.xfail)
  FAIL: отсутствует обязательное доказательство

Ограничение (честное): без correlation_id в EventDTO — косвенное доказательство
через единственность пары + порядок публикации.
PRODUCTION-FIX для 100% корреляции — отдельная архитектурная задача.
"""
from __future__ import annotations

import ast
import copy
import json
import logging
import os
import time
from typing import Any, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from tests.gameplay.harness import TavernGameplayHarness

logger = logging.getLogger("gameplay.butterfly_b3_llm")

_CAMPAIGN = "Open_road"
_VICTIM = "tavern_keeper_tornin"
_WITNESS = "maid_lusya"
_PLAYER = "player"

# B3 требует конкретно :8181 (Решение Мастера — фиксация порта)
_B3_REQUIRED_PORT = 8181

# Verifier message prefixes (точные из proposition_verifier.py L121-L136)
_VERIFIER_YES_PREFIX = "verify \u2192 YES (confirmed)"
_VERIFIER_NO_PREFIX = "verify \u2192 NO (rejected)"
_VERIFIER_AMB_PREFIX = "verify \u2192 AMBIGUOUS verdict"
_VERIFIER_TIMEOUT_PREFIX = "verify: LLM timeout"
_VERIFIER_FAILED_PREFIX = "verify: LLM call failed"

# Key fields для сопоставления Proposition
_PROPOSITION_KEY_FIELDS = ("subject_id", "predicate", "object_id")

# Spies
SPY_SPOKE: List[dict] = []
SPY_CLAIM: List[dict] = []

# Global capture order — общий счетчик для SPY_SPOKE и SPY_CLAIM
_GLOBAL_CAPTURE_ORDER: int = 0

# Backup state — None = backup не сделан; dict (даже пустой) = backup сделан
_ORIG_DISPOSITIONS: Optional[dict] = None
_SUBSCRIBED_SPIES: List[tuple] = []


def _verifier_msg(record: logging.LogRecord) -> str:
    """Использовать getMessage() — record.message ненадежен (создается форматтером)."""
    return record.getMessage()


def _extract_prop_from_verifier_msg(msg: str) -> dict:
    """Извлечь proposition dict из verifier log message.
    
    PropositionVerifier.verify(proposition: dict[str, Any], text) — proposition это dict.
    Логирование (proposition_verifier.py L121,128,133,107,113):
      logger.info("verify -> YES (confirmed). prop=%s text_head=%r", proposition, ...)
    
    Тип: dict[str, Any] (L89). Источник: post_decision.py L204-L208 — плоский dict, 4 поля.
    str(dict) -> Python repr -> ast.literal_eval.
    Сбалансированный поиск скобок — надежнее регекса, обрабатывает вложенные dict.
    """
    _prefix = "prop="
    _idx = msg.find(_prefix)
    if _idx == -1:
        return {}
    _start = _idx + len(_prefix)
    if _start >= len(msg) or msg[_start] != "{":
        return {}
    # Сбалансированный поиск закрывающей }
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
    _prop_str = msg[_start:_end]
    try:
        _parsed = ast.literal_eval(_prop_str)
        if isinstance(_parsed, dict):
            return _parsed
    except Exception:
        pass
    return {}


def _match_prop(verifier_prop: dict, expected: dict) -> bool:
    """Сопоставить key fields proposition (subject_id, predicate, object_id)."""
    if not verifier_prop or not expected:
        return False
    return all(
        verifier_prop.get(_f) == expected.get(_f)
        for _f in _PROPOSITION_KEY_FIELDS
    )


def _spy_npc_spoke(event: Any) -> None:
    """Capture NPC_SPOKE. event.source = speaker_id (NPC ID)."""
    global _GLOBAL_CAPTURE_ORDER
    _pl = getattr(event, "payload", {}) or {}
    SPY_SPOKE.append({
        "_global_order": _GLOBAL_CAPTURE_ORDER,
        "source": getattr(event, "source", "?"),
        "target_id": _pl.get("target_id"),
        "text": _pl.get("text", ""),
        "intent_type": _pl.get("intent_type"),
        "topic": _pl.get("topic"),
        "exposure": _pl.get("exposure"),
        "tone": _pl.get("tone"),
    })
    _GLOBAL_CAPTURE_ORDER += 1


def _spy_comm_claim(event: Any) -> None:
    """Capture COMMUNICATION_CLAIM. event.source = speaker_id (тот же что NPC_SPOKE)."""
    global _GLOBAL_CAPTURE_ORDER
    _pl = getattr(event, "payload", {}) or {}
    _prop = _pl.get("proposition") or {}
    SPY_CLAIM.append({
        "_global_order": _GLOBAL_CAPTURE_ORDER,
        "source": getattr(event, "source", "?"),
        "target_id": _pl.get("target_id"),
        "proposition": _prop,
        "verified_by": _pl.get("verified_by", "?"),
    })
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
            except Exception as _e:
                logger.warning(f"[B3] unsubscribe failed for {_et}: {_e}")
    except Exception as _e:
        logger.warning(f"[B3] get_event_bus failed: {_e}")
    finally:
        _SUBSCRIBED_SPIES.clear()


def _backup_dispositions() -> None:
    global _ORIG_DISPOSITIONS
    from app.domain import epistemic_dispositions as _ed
    _ORIG_DISPOSITIONS = copy.deepcopy(_ed.EPISTEMIC_DISPOSITIONS)


def _restore_dispositions() -> None:
    global _ORIG_DISPOSITIONS
    # None = backup не сделан — ничего не делаем
    # dict (даже пустой) = backup сделан — восстанавливаем
    if _ORIG_DISPOSITIONS is None:
        return
    try:
        from app.domain import epistemic_dispositions as _ed
        _ed.EPISTEMIC_DISPOSITIONS.clear()
        _ed.EPISTEMIC_DISPOSITIONS.update(copy.deepcopy(_ORIG_DISPOSITIONS))
    except Exception as _e:
        logger.warning(f"[B3] disposition restore failed: {_e}")
    finally:
        _ORIG_DISPOSITIONS = None


def _override_witness_disposition() -> None:
    """TEST FIXTURE (Решение Мастера 1): maid disposition override.
    
    НЕ proof автономности spread_rumor. Production НЕ меняется (restore в finally).
    """
    from app.domain import epistemic_dispositions as _ed
    _ed.EPISTEMIC_DISPOSITIONS["maid"] = {
        "report": 0.0, "warn": 0.0, "attack": 0.0,
        "spread_rumor": 1.4, "talk": 0.8, "intimidate": 0.0,
    }
    print("[OVERRIDE] maid: spread_rumor=1.4 (TEST FIXTURE — не proof автономности)")


def _check_llm_health_http() -> bool:
    """HTTP health check + обязательный порт 8181."""
    try:
        from app.services.llm.health import check_llm_health
        from app.core.config import settings
        _result = check_llm_health(use_cache=False)
        _status = _result.get("status", "")
        _url = _result.get("url", "")
        _model = _result.get("model", "unknown")
        print(f"[PRE-FLIGHT] LLM health: status={_status} url={_url} model={_model}")
        
        if _status != "online":
            print(f"[PRE-FLIGHT] FAIL: status={_status}")
            return False
        
        # Шаг 1: settings.llama_cpp_port ДОЛЖЕН быть 8181 (требование Мастера)
        if settings.llama_cpp_port != _B3_REQUIRED_PORT:
            print(f"[PRE-FLIGHT] FAIL: settings.llama_cpp_port={settings.llama_cpp_port} "
                  f"!= {_B3_REQUIRED_PORT} (B3 требует именно :{_B3_REQUIRED_PORT})")
            return False
        
        # Шаг 2: URL port должен совпадать с 8181
        _parsed = urlparse(_url)
        if _parsed.port != _B3_REQUIRED_PORT:
            print(f"[PRE-FLIGHT] FAIL: url port={_parsed.port} != {_B3_REQUIRED_PORT}")
            return False
        if _parsed.hostname != "localhost":
            print(f"[PRE-FLIGHT] FAIL: hostname={_parsed.hostname} != localhost")
            return False
        
        return True
    except Exception as _e:
        print(f"[PRE-FLIGHT] LLM health check failed: {_e}")
        return False


def _check_b3_approved() -> bool:
    return os.environ.get("ENIGMA_B3_APPROVED") == "1"


def _check_file_logs_enabled() -> bool:
    try:
        from app.core.log_gate import file_logs_enabled
        return file_logs_enabled()
    except Exception:
        return False


def _get_log_file_path() -> Optional[str]:
    try:
        from app.services.logging_tools import LOG_FILE
        return str(LOG_FILE)
    except Exception:
        return None


def _snapshot_log_size() -> int:
    _path = _get_log_file_path()
    if not _path or not os.path.exists(_path):
        return 0
    try:
        return os.path.getsize(_path)
    except Exception:
        return 0


def _read_jsonl_log_after_offset(offset: int) -> List[dict]:
    """Бинарное чтение + decode (не текстовый seek)."""
    _path = _get_log_file_path()
    if not _path or not os.path.exists(_path):
        return []
    _entries = []
    try:
        with open(_path, "rb") as f:
            f.seek(offset)
            _remaining_bytes = f.read()
        _text = _remaining_bytes.decode("utf-8", errors="replace")
        for _line in _text.splitlines():
            _line = _line.strip()
            if not _line:
                continue
            try:
                _entries.append(json.loads(_line))
            except Exception:
                continue
    except Exception as _e:
        print(f"[JSONL] read failed: {_e}")
    return _entries


def _publish_player_insults(
    harness: TavernGameplayHarness,
    target_id: str,
    radius: float = 15.0,
) -> None:
    from app.domain.events import EventDTO
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType
    _payload = {
        "target_id": target_id,
        "action_type": "player_insults",
        "intent_type": "insult",
    }
    _event = EventDTO(
        id=uuid4(),
        type=EventType.PLAYER_INSULTS.value,
        source=_PLAYER,
        timestamp=0.0,
        payload=_payload,
        visibility="public",
        radius=radius,
        persistence_level="session",
    )
    get_event_bus().publish(_event)
    print(f"[INJECT] PLAYER_INSULTS: source={_PLAYER} target={target_id} radius={radius}")


@pytest.fixture(autouse=True)
def _clear_spies_and_state() -> Any:
    """СНАЧАЛА cleanup от предыдущего прогона, потом clear."""
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


class TestButterflyB3LLM:
    """B3: production LLM integration — semantic chain verification."""
    
    def test_pre_flight_all_conditions(self) -> None:
        """Pre-flight: все условия запуска."""
        if not _check_b3_approved():
            pytest.skip("ENIGMA_B3_APPROVED != 1 — B3 не одобрен")
        if not _check_file_logs_enabled():
            pytest.skip("ENIGMA_DISABLE_FILE_LOGS=1 — JSONL отключён")
        if not _check_llm_health_http():
            pytest.skip("LLM-server не отвечает на :8181/v1/models")
        print("[PRE-FLIGHT] Все условия выполнены")
    
    def test_b3_semantic_chain_player_to_tornin(self, caplog: Any) -> None:
        """B3 — production LLM semantic chain.
        
        VERDICT (по Мастеру):
          PASS: 6 условий + single_pair + precedes + verifier_yes_for_prop -> B3 закрыт
          PARTIAL: verifier_rejected_for_prop + partial_single_speech + claim suppressed
                   -> НЕ закрывает B3 (pytest.xfail)
          FAIL: отсутствует обязательное доказательство
        """
        # PRE-FLIGHT (до создания harness)
        if not _check_b3_approved():
            pytest.skip("ENIGMA_B3_APPROVED != 1 — B3 не одобрен")
        if not _check_file_logs_enabled():
            pytest.skip("ENIGMA_DISABLE_FILE_LOGS=1 — JSONL отключён")
        if not _check_llm_health_http():
            pytest.skip("LLM-server не отвечает на :8181/v1/models")
        
        # SETUP — _h = None изначально, весь setup в try/finally
        _h: Optional[TavernGameplayHarness] = None
        _log_offset = _snapshot_log_size()
        
        try:
            _backup_dispositions()
            _h = TavernGameplayHarness(seed=42, location="tavern")
            _h.new_game()
            _install_spies()
            _override_witness_disposition()
            
            # WARMUP + PUBLISH + ADVANCE
            _h.advance_ticks(2)
            _publish_player_insults(_h, _VICTIM, radius=15.0)
            
            caplog.clear()
            with caplog.at_level(
                logging.DEBUG,
                logger="app.services.cognition.proposition_verifier"
            ):
                _t_start = time.monotonic()
                _h.advance_ticks(8)
                _elapsed = time.monotonic() - _t_start
            print(f"[B3] advance_ticks(8) с production LLM: {_elapsed:.1f}s")
            
            # JSONL (isolation — бинарное чтение после offset)
            _jsonl_entries = _read_jsonl_log_after_offset(_log_offset)
            _dialogue_calls = [
                e for e in _jsonl_entries
                if e.get("agent") == "llm_output" and e.get("npc_id") != "verifier"
            ]
            _verifier_llm_calls = [
                e for e in _jsonl_entries
                if e.get("agent") == "llm_output" and e.get("npc_id") == "verifier"
            ]
            print(f"[CHECK] JSONL (current run): {len(_dialogue_calls)} dialogue calls, "
                  f"{len(_verifier_llm_calls)} verifier LLM calls")
            print(f"[CHECK] JSONL total entries: {len(_jsonl_entries)}")
            for _e in _jsonl_entries[:5]:
                print(f"  JSONL entry: agent={_e.get('agent')} npc_id={_e.get('npc_id')} "
                      f"latency={_e.get('latency')}")
            
            # Ожидаемая Proposition из PLAYER_INSULTS (post_decision.py L204-L208)
            _expected_prop = {
                "subject_id": _PLAYER,
                "predicate": "insulted",
                "object_id": _VICTIM,
            }
            
            # CAPLOG verifier (getMessage() + точные префиксы startswith)
            _verifier_records = [
                r for r in caplog.records
                if "proposition_verifier" in r.name
            ]
            _verifier_yes = [r for r in _verifier_records if _verifier_msg(r).startswith(_VERIFIER_YES_PREFIX)]
            _verifier_no = [r for r in _verifier_records if _verifier_msg(r).startswith(_VERIFIER_NO_PREFIX)]
            _verifier_amb = [r for r in _verifier_records if _verifier_msg(r).startswith(_VERIFIER_AMB_PREFIX)]
            _verifier_timeout = [r for r in _verifier_records if _verifier_msg(r).startswith(_VERIFIER_TIMEOUT_PREFIX)]
            _verifier_failed = [r for r in _verifier_records if _verifier_msg(r).startswith(_VERIFIER_FAILED_PREFIX)]
            _verifier_called = (
                len(_verifier_yes) + len(_verifier_no) + len(_verifier_amb)
                + len(_verifier_timeout) + len(_verifier_failed)
            ) > 0
            
            # Фильтрация verifier records по ожидаемой Proposition
            _verifier_yes_for_prop = [
                r for r in _verifier_yes
                if _match_prop(_extract_prop_from_verifier_msg(_verifier_msg(r)), _expected_prop)
            ]
            _verifier_no_for_prop = [
                r for r in _verifier_no
                if _match_prop(_extract_prop_from_verifier_msg(_verifier_msg(r)), _expected_prop)
            ]
            _verifier_amb_for_prop = [
                r for r in _verifier_amb
                if _match_prop(_extract_prop_from_verifier_msg(_verifier_msg(r)), _expected_prop)
            ]
            _verifier_timeout_for_prop = [
                r for r in _verifier_timeout
                if _match_prop(_extract_prop_from_verifier_msg(_verifier_msg(r)), _expected_prop)
            ]
            _verifier_failed_for_prop = [
                r for r in _verifier_failed
                if _match_prop(_extract_prop_from_verifier_msg(_verifier_msg(r)), _expected_prop)
            ]
            
            # PARTIAL classification (исправление Мастера — YES исключён)
            # Только отрицательные результаты (NO, AMBIGUOUS) — без YES
            _verifier_rejected_for_prop = (
                bool(_verifier_no_for_prop)
                or bool(_verifier_amb_for_prop)
            )
            _verifier_error_for_prop = (
                bool(_verifier_timeout_for_prop)
                or bool(_verifier_failed_for_prop)
            )
            _verifier_partial_ready = (
                _verifier_rejected_for_prop
                or _verifier_error_for_prop
            )
            
            print(f"[CHECK] Verifier caplog: total={len(_verifier_records)}, "
                  f"called={_verifier_called}")
            print(f"[CHECK] Verifier for expected prop ({_PLAYER}, INSULTED, {_VICTIM}): "
                  f"YES={len(_verifier_yes_for_prop)} (PASS path), "
                  f"NO={len(_verifier_no_for_prop)}, AMBIGUOUS={len(_verifier_amb_for_prop)}, "
                  f"timeout={len(_verifier_timeout_for_prop)}, "
                  f"failed={len(_verifier_failed_for_prop)}")
            print(f"[CHECK] PARTIAL-ready: rejected={_verifier_rejected_for_prop}, "
                  f"error={_verifier_error_for_prop}, "
                  f"partial_ready={_verifier_partial_ready}")
            for _r in _verifier_records[:3]:
                print(f"  verifier log: level={_r.levelname} msg={_verifier_msg(_r)[:120]!r}")
            
            # SPY_SPOKE — все maid_lusya -> victim
            print(f"[CHECK] SPY_SPOKE total: {len(SPY_SPOKE)}")
            for s in SPY_SPOKE[:5]:
                _text_head = (s["text"] or "")[:120]
                print(f"  src={s['source']} tgt={s['target_id']} "
                      f"intent={s['intent_type']} order={s['_global_order']} "
                      f"text={_text_head!r}")
            
            _maid_speech_to_victim = [
                s for s in SPY_SPOKE
                if s["source"] == _WITNESS
                and s["target_id"] == _VICTIM
                and s["text"]
                and s["text"].strip()
            ]
            print(f"[CHECK] maid_lusya speech -> {_VICTIM}: {len(_maid_speech_to_victim)}")
            
            # SPY_CLAIM — все maid_lusya -> victim
            print(f"[CHECK] SPY_CLAIM total: {len(SPY_CLAIM)}")
            for c in SPY_CLAIM[:5]:
                _p = c["proposition"]
                print(f"  src={c['source']} tgt={c['target_id']} "
                      f"prop={_p.get('predicate')} verified_by={c['verified_by']} "
                      f"order={c['_global_order']}")
            
            _maid_claim_to_victim = [
                c for c in SPY_CLAIM
                if c["source"] == _WITNESS
                and c["target_id"] == _VICTIM
            ]
            print(f"[CHECK] maid_lusya claim -> {_VICTIM}: {len(_maid_claim_to_victim)}")
            
            # Correlation checks
            _has_competing_speech = len(_maid_speech_to_victim) > 1
            _has_competing_claim = len(_maid_claim_to_victim) > 1
            
            _precedes = False
            if _maid_speech_to_victim and _maid_claim_to_victim:
                _speech_order = _maid_speech_to_victim[0]["_global_order"]
                _claim_order = _maid_claim_to_victim[0]["_global_order"]
                _precedes = _speech_order < _claim_order
                print(f"[CHECK] Order: speech={_speech_order}, claim={_claim_order}, "
                      f"precedes={_precedes}")
            
            _single_pair = (
                len(_maid_speech_to_victim) == 1
                and len(_maid_claim_to_victim) == 1
            )
            if _has_competing_speech or _has_competing_claim:
                print(f"[CHECK] Competing replicas: "
                      f"speech={len(_maid_speech_to_victim)}, "
                      f"claim={len(_maid_claim_to_victim)} — "
                      f"не можем доказать корреляцию")
            
            # 6 CONDITIONS FOR PASS
            _cond1_npc_spoke = len(_maid_speech_to_victim) > 0
            _cond2_comm_claim = len(_maid_claim_to_victim) > 0
            _cond3_verifier_called = _verifier_called
            # Condition 4: verifier YES именно для ожидаемой Proposition
            _cond4_verifier_yes = len(_verifier_yes_for_prop) > 0
            _cond5_correct_prop = False
            if _maid_claim_to_victim:
                _p = _maid_claim_to_victim[0]["proposition"]
                _cond5_correct_prop = (
                    _p.get("predicate") == "insulted"
                    and _p.get("subject_id") == _PLAYER
                    and _p.get("object_id") == _VICTIM
                )
            _cond6_correlated = (
                _maid_speech_to_victim
                and _maid_claim_to_victim
                and _precedes
                and _single_pair
            )
            
            print(f"\n[VERDICT CHECK] 6 conditions:")
            print(f"  1. NPC_SPOKE maid->{_VICTIM}: {_cond1_npc_spoke}")
            print(f"  2. COMMUNICATION_CLAIM maid->{_VICTIM}: {_cond2_comm_claim}")
            print(f"  3. Verifier called (caplog): {_cond3_verifier_called}")
            print(f"  4. Verifier YES for prop: {_cond4_verifier_yes}")
            print(f"  5. Correct prop (player, INSULTED, {_VICTIM}): {_cond5_correct_prop}")
            print(f"  6. Correlated (precedes + single_pair): {_cond6_correlated}")
            
            # VERDICT
            if all([
                _cond1_npc_spoke,
                _cond2_comm_claim,
                _cond3_verifier_called,
                _cond4_verifier_yes,
                _cond5_correct_prop,
                _cond6_correlated,
            ]):
                # PASS: все 6 условий -> B3 закрыт
                _c = _maid_claim_to_victim[0]
                _p = _c["proposition"]
                _text = _maid_speech_to_victim[0]["text"]
                
                print(f"\n[OK] B3 PASS: full semantic chain verified")
                print(f"  Candidate Proposition: ({_p.get('subject_id')}, "
                      f"{_p.get('predicate')}, {_p.get('object_id')})")
                print(f"  -> LLM Dialogue: maid_lusya text_head={_text[:120]!r}")
                print(f"  -> PropositionVerifier: YES (caplog confirmed, "
                      f"{len(_verifier_yes_for_prop)} records)")
                print(f"  -> COMMUNICATION_CLAIM: published, "
                      f"verified_by={_c['verified_by']}")
                print(f"  Correlation: single_pair + precedes (order "
                      f"{_maid_speech_to_victim[0]['_global_order']} < "
                      f"{_maid_claim_to_victim[0]['_global_order']})")
                print(f"  Latency: {_elapsed:.1f}s total")
                print(f"  LLM calls: {len(_dialogue_calls)} dialogue, "
                      f"{len(_verifier_llm_calls)} verifier")
            
            else:
                # PARTIAL correlation: ровно одна речь, ноль claims
                _partial_single_speech = (
                    len(_maid_speech_to_victim) == 1
                    and len(_maid_claim_to_victim) == 0
                )
                
                if (
                    _cond1_npc_spoke
                    and _partial_single_speech
                    and _verifier_partial_ready
                    and not _cond2_comm_claim
                ):
                    # PARTIAL: fail-closed confirmed для конкретной Proposition
                    _text = _maid_speech_to_victim[0]["text"]
                    print(f"\n[B3 PARTIAL] fail-closed confirmed for expected Proposition:")
                    print(f"  NPC_SPOKE published (maid_lusya text: {_text[:120]!r})")
                    print(f"  Single speech (no competing): speech=1, claim=0")
                    print(f"  Verifier for prop ({_PLAYER}, INSULTED, {_VICTIM}): "
                          f"YES={len(_verifier_yes_for_prop)} (excluded), "
                          f"NO={len(_verifier_no_for_prop)}, "
                          f"AMBIGUOUS={len(_verifier_amb_for_prop)}, "
                          f"timeout={len(_verifier_timeout_for_prop)}, "
                          f"failed={len(_verifier_failed_for_prop)}")
                    print(f"  COMMUNICATION_CLAIM suppressed (verifier rejected)")
                    print(f"  Production fail-closed behaviour confirmed")
                    print(f"  B3 НЕ закрыт — требуется PASS для закрытия")
                    pytest.xfail(
                        "B3 PARTIAL: fail-closed confirmed for expected Proposition "
                        f"({_PLAYER}, INSULTED, {_VICTIM}). "
                        f"Single maid_lusya speech, verifier rejected "
                        f"(NO/AMBIGUOUS/timeout/failed), "
                        f"COMMUNICATION_CLAIM suppressed. "
                        "B3 НЕ закрыт — требуется PASS."
                    )
                else:
                    # FAIL
                    _reasons = []
                    if not _cond1_npc_spoke:
                        _reasons.append("maid_lusya не говорила -> victim")
                    if not _cond3_verifier_called:
                        _reasons.append("verifier НЕ был вызван (wiring сломан?)")
                    if _cond1_npc_spoke and _cond3_verifier_called and not _cond2_comm_claim:
                        if not _verifier_partial_ready:
                            _reasons.append(
                                "verifier вызван, но нет отрицательного результата "
                                "для ожидаемой Proposition"
                            )
                    if _has_competing_speech or _has_competing_claim:
                        _reasons.append(
                            f"competing replicas: speech={len(_maid_speech_to_victim)}, "
                            f"claim={len(_maid_claim_to_victim)} — "
                            f"не можем доказать корреляцию"
                        )
                    
                    pytest.fail(
                        f"B3 FAIL: semantic chain broken.\n"
                        f"  Reasons:\n    - " + "\n    - ".join(_reasons) + "\n"
                        f"  Diagnostics:\n"
                        f"    SPY_SPOKE total: {len(SPY_SPOKE)}\n"
                        f"    maid_lusya speech -> {_VICTIM}: {len(_maid_speech_to_victim)}\n"
                        f"    maid_lusya claim -> {_VICTIM}: {len(_maid_claim_to_victim)}\n"
                        f"    verifier caplog: total={len(_verifier_records)}, "
                        f"called={_verifier_called}\n"
                        f"    verifier for prop: "
                        f"YES={len(_verifier_yes_for_prop)}, "
                        f"NO={len(_verifier_no_for_prop)}, "
                        f"AMBIGUOUS={len(_verifier_amb_for_prop)}, "
                        f"timeout={len(_verifier_timeout_for_prop)}, "
                        f"failed={len(_verifier_failed_for_prop)}\n"
                        f"    JSONL: dialogue={len(_dialogue_calls)}, "
                        f"verifier={len(_verifier_llm_calls)}, "
                        f"total={len(_jsonl_entries)}\n"
                        f"    6 conditions: "
                        f"npc_spoke={_cond1_npc_spoke}, claim={_cond2_comm_claim}, "
                        f"verifier_called={_cond3_verifier_called}, "
                        f"verifier_yes={_cond4_verifier_yes}, "
                        f"correct_prop={_cond5_correct_prop}, "
                        f"correlated={_cond6_correlated}"
                    )
            
            # LATENCY (единый timeout)
            assert _elapsed < 540.0, (
                f"B3 FAIL: advance_ticks(8) took {_elapsed:.1f}s > 540s "
                f"(10% запас от pytest --timeout=600)"
            )
        
        finally:
            _uninstall_spies()
            _restore_dispositions()
            if _h is not None:
                try:
                    _h.dispose()
                except Exception as _e:
                    logger.warning(f"[B3] harness dispose failed: {_e}")