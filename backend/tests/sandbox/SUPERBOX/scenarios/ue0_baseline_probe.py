# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/SUPERBOX/scenarios/ue0_baseline_probe.py
Назначение: S-UE ШАГ 0 — измерение текущего pipeline «как есть» (условия 2–5 GO).
    Полный путь: raw → сырой LLM-ответ → IntentSemanticField → резолв →
    ЭМУЛЯЦИЯ readiness (помечена как эмуляция, не реализация) → consumer-исход.
    Таймаут ≠ непонимание: status/latency/attempts записываются раздельно от
    содержательных ошибок. Все результаты попадают в отчёт, включая отказы.
Зависимости: app.services.input.intent_compressor, app.services.game_loop.phase_1_input
Основные сущности: run_baseline, _capture_llm, _emulate_readiness.
Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.ue0_baseline_probe; cd ..
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import sys

# Прецедент semantic_probe_corpus.py:20-23: backend и корень в sys.path —
# иначе scripts.llm_server_manager не импортируется из backend-CWD
_BACKEND_ROOT = Path(__file__).resolve().parents[4]
_ROOT = _BACKEND_ROOT.parent
for _p in (str(_BACKEND_ROOT), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# LLM-обеспечение (прецедент semantic_probe_corpus.py:27-39): поднимает 8181
# при пустом порте; без него slow-path = connection-refused (мерили бы отказ,
# не понимание). KEEP_SERVER=1 — сервер живёт между прогонами.
import atexit

try:
    from scripts.llm_server_manager import kill_llama_server, start_llama_server
    _llm_ok = start_llama_server()
    if os.environ.get("ENIGMA_DET_KEEP_SERVER") != "1":
        atexit.register(kill_llama_server)
except Exception as _e:
    print(f"ВНИМАНИЕ: менеджер LLM недоступен ({_e}); slow-path уйдёт в отказы")
    _llm_ok = False

REPORTS = Path(__file__).resolve().parents[5] / "reports"
REPORT = REPORTS / "ue0_baseline_report.jsonl"

# Условие 2 GO: конфигурация фиксируется ДО прогона в отчёт-шапку
ENV_CONTRACT = {
    "model": os.environ.get("AIDM_LLAMA_CPP_MODEL_PATH", "<default qwen_7b>"),
    "temperature": 0.0,
    "timeout_s": 60.0,
    "retry": "single-attempt (текущий клиент), повторы не добавляются",
    "det_trace": os.environ.get("ENIGMA_DET_TRACE", "OFF"),
    "server_url": os.environ.get("AIDM_LLAMA_CPP_SERVER_URL", "<default 8181>"),
}

# Сетка сцены для резолва (два стражника = REF-01 должен дать кандидатов, не угадывание)
SCENE_CONTEXT = {
    "npc_positions": {
        "guard_gate": {"name": "стражник у ворот", "x": 10.0, "y": 10.0},
        "guard_market": {"name": "стражник на рынке", "x": 40.0, "y": 10.0},
        "tavern_keeper": {"name": "трактирщик", "x": 5.0, "y": 5.0},
        "maid_lusya": {"name": "Люся", "x": 5.0, "y": 6.0},
    },
    "location_id": "tavern",
    "player": {"x": 5.0, "y": 7.0},
}


def _emulate_readiness(field, resolved_target_id: str | None) -> dict:
    """ЭМУЛЯЦИЯ будущей политики (не реализация): помечается в каждом кортеже отчёта.
    Условия GO: SEMANTIC_AMBIGUOUS восстановлен (блокер №1); claim при PARTIAL
    не публикуется вовсе (блокер №5); None-признаки на изменяющих-мир актах =
    недостаточная информация (блокер №2)."""
    emulated = "EMULATED"
    has_acts = bool(field.semantic_acts)
    action = str(getattr(field.action, "value", field.action))
    world_changing = action in ("ATTACK", "STEAL", "THREATEN", "MOVE", "GIVE")
    negated = any(a.get("negated") for a in field.semantic_acts) if field.semantic_acts else None
    ambiguity = str(getattr(field.ambiguity, "value", "CLEAR")) == "AMBIGUOUS"
    if action == "UNCERTAIN":
        readiness, reason = "FAILED", "uncertain-action"
    elif ambiguity:
        readiness, reason = "SEMANTIC_AMBIGUOUS", "llm-ambiguity-flag"
    elif world_changing and resolved_target_id is None:
        readiness, reason = "PARTIAL", "world-changing-no-target"
    elif world_changing and has_acts and negated is None:
        readiness, reason = "PARTIAL", "world-changing-negation-unknown"
    elif world_changing and not has_acts:
        readiness, reason = "PARTIAL", "world-changing-no-acts"
    else:
        readiness, reason = "RESOLVED", "structurally-complete"
    return {
        "readiness": readiness,
        "reason": reason,
        "emulated": emulated,
        "would_execute": readiness == "RESOLVED" and not world_changing,
        "would_execute_world_changing": readiness == "RESOLVED" and world_changing and negated is not True,
        "claim_publish": readiness == "RESOLVED",  # Блокер №5: только RESOLVED
    }


async def _probe_one(case_id, text, compressor) -> dict:
    t0 = time.monotonic()
    llm_status = "not-invoked"
    try:
        # Захват сырого ответа: клиент логирует [DIAG-LLM]; raw-capture через обёртку
        field = await compressor.compress(text, SCENE_CONTEXT)
        llm_status = "ok"
    except Exception as e:
        field = None
        llm_status = f"exception:{type(e).__name__}"
    latency = round(time.monotonic() - t0, 3)

    resolved = None
    consumer_outcome = None
    if field is not None:
        try:
            from app.services.game_loop.phase_1_input import resolve_player_intent
            resolution = resolve_player_intent(
                raw_action=text, action_type="dialogue", target="",
                player_dict=None, scene_context=SCENE_CONTEXT, semantic_field=field,
            )
            params = resolution.original_intent.parameters
            resolved = params.target_id
            consumer_outcome = {
                "semantic_action": params.semantic_action,
                "target_id": params.target_id,
                "proposition": bool(params.proposition_predicate),
                "semantic_acts_count": len(params.semantic_acts),
                "act_types": [str(a.get("type")) for a in params.semantic_acts][:6],
            }
        except Exception as e:
            consumer_outcome = {"error": f"{type(e).__name__}: {e}"}

    field_dump = None
    if field is not None:
        field_dump = {
            "action": str(getattr(field.action, "value", field.action)),
            "speech_act": str(getattr(getattr(field, "speech_act", None), "value", None)),
            "ambiguity": str(getattr(field.ambiguity, "value", None)),
            "semantic_acts": [
                {k: v for k, v in a.items() if k in ("type", "params", "topic", "name")}
                for a in field.semantic_acts
            ][:8],
            "subject_hint": field.subject_hint,
            "proposition": None if not field.proposition else {
                "predicate": str(field.proposition.predicate.value),
                "polarity": field.proposition.polarity,
                "object_id": field.proposition.object_id,
            },
            "condition": field.condition,
        }

    emu = _emulate_readiness(field, resolved) if field is not None else {
        "readiness": "FAILED", "reason": "no-field", "emulated": "EMULATED",
        "would_execute": False, "claim_publish": False,
    }

    return {
        "case_id": case_id,
        "text": text,
        "llm_status": llm_status,          # таймаут/ошибка — технический статус
        "latency_s": latency,
        "attempts": 1,                     # текущий клиент: без повторов
        "field": field_dump,
        "resolved_target_id": resolved,
        "readiness_emulation": emu,
        "consumer_outcome": consumer_outcome,
        "interpretation_error": None,      # содержательная ошибка — заполняется при разборе
    }


async def run_baseline() -> None:
    from app.services.input.intent_compressor import IntentCompressor
    from app.services.input.llm_compressor_client import LlamaCppCompressorClient

    from tests.sandbox.SUPERBOX.scenarios.ue0_baseline_corpus import CORPUS, CONTROL, GOLD

    REPORTS.mkdir(parents=True, exist_ok=True)
    compressor = IntentCompressor(LlamaCppCompressorClient())
    rows = []
    header = {"type": "HEADER", "env_contract": ENV_CONTRACT,
              "note": "readiness = EMULATION будущей политики, не текущая реализация"}
    rows.append(header)

    for case_id, text in CORPUS:
        rows.append(await _probe_one(case_id, text, compressor))
    for case_id, text in CONTROL:
        rows.append(await _probe_one(case_id, text, compressor))

    # Золотая сетка — в конец файла, для последующего сличения (эталон ДО прогона)
    rows.append({"type": "GOLD", "cases": {k: v for k, v in GOLD.items()}})

    REPORT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print(f"[UE0] отчёт: {REPORT} ({len(rows)} строк: 1 header + {len(CORPUS)} корпус + {len(CONTROL)} контроль + 1 gold)")


if __name__ == "__main__":
    asyncio.run(run_baseline())