# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/SUPERBOX/scenarios/ue4_probe.py
Назначение: S-UE Блок 4 замер — per-act признаки (negated/modality/quoted)
    в ответах LLM после промпт-таблицы + живость comprehension_facts.
Зависимости: intent_compressor, scripts.llm_server_manager
Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.ue4_probe; cd ..
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
    ("NEG-04", "Не бей его."),
    ("QUO-01", "Она сказала мне: «Уходи и больше не возвращайся»."),
    ("QUO-02", "Он сказал мне: «Убей стражника». Что он имел в виду?"),
    ("HYP-01", "А если я предложу ей помочь гильдии, она мне поверит?"),
    ("CON-01", "Привет."),
]


async def main() -> None:
    comp = IntentCompressor(LlamaCppCompressorClient())
    for cid, text in PHRASES:
        f = await comp.compress(text, SCENE)
        acts = [{k: v for k, v in a.items() if k != "params"} for a in f.semantic_acts]
        print(f"[UE4] {cid} {text!r}")
        print(f"      action={f.action.value} facts={f.comprehension_facts}")
        print(f"      acts={acts}")


asyncio.run(main())