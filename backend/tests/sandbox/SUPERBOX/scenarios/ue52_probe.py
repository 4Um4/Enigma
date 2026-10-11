# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/SUPERBOX/scenarios/ue52_probe.py
Назначение: S-UE Блок 5.2 замер — критерии Мастера: (1) NEG-01/02 достигают
    LLM ([DIAG-LLM] присутствует); (2) различие негации-приказа/негации-
    содержания (ORDER+negated vs polarity); (3) гейт: readiness NEG-кластера
    не-RESOLVED при неразобранной негации. Контроль: CON-группа без LLM.
Зависимости: intent_compressor, phase_1_input, llm_server_manager
Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.ue52_probe; cd ..
"""
from __future__ import annotations

import asyncio
import atexit
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
_ROOT = _BACKEND.parent
for _p in (str(_BACKEND), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.llm_server_manager import kill_llama_server, start_llama_server

_llm_ok = start_llama_server()
if os.environ.get("ENIGMA_DET_KEEP_SERVER") != "1":
    atexit.register(kill_llama_server)

from app.services.game_loop.phase_1_input import compute_intent_readiness, resolve_target_with_candidates
from app.services.input.intent_compressor import IntentCompressor
from app.services.input.llm_compressor_client import LlamaCppCompressorClient

SCENE = {
    "npc_positions": {
        "guard_gate": {"name": "стражник у ворот"},
        "tavern_keeper": {"name": "трактирщик"},
        "maid_lusya": {"name": "Люся"},
    }
}

PHRASES = [
    ("NEG-01", "Не говори ему, что я согласен."),
    ("NEG-02", "Не говори ему, что я не согласен."),
    ("NEG-03", "Скажи ему, что я не согласен."),
    ("CON-01", "Привет."),
    ("CON-05", "Сколько стоит эль?"),
]


async def main() -> None:
    comp = IntentCompressor(LlamaCppCompressorClient())
    for cid, text in PHRASES:
        f = await comp.compress(text, SCENE)
        tid, cands = resolve_target_with_candidates(f, SCENE)
        rdy = compute_intent_readiness(f, tid, cands)
        acts = [{k: v for k, v in a.items() if k != "params"} for a in f.semantic_acts]
        prop = None if not f.proposition else {"polarity": f.proposition.polarity, "obj": f.proposition.object_id}
        print(f"[UE52] {cid} {text!r}")
        print(f"      facts={f.comprehension_facts}")
        print(f"      acts={acts} prop={prop} readiness={rdy}")


asyncio.run(main())