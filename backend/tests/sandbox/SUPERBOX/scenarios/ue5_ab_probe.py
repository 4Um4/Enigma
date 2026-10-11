# -*- coding: utf-8 -*-
"""path: backend/tests/sandbox/SUPERBOX/scenarios/ue5_ab_probe.py
Назначение: S-UE Блок 5 A/B — дискриминация «примеры задают формат» vs
    «модель неспособна»: 6 фраз, compress при ENIGMA_PERACT_FSHOT OFF и ON
    (env читается в _build_prompts на каждый вызов — оба состояния в одном
    процессе). NEG-01 = in-example (копирование); перенос = остальные фразы.
Зависимости: intent_compressor, llm_server_manager
Запуск: cd backend; python -B -m tests.sandbox.SUPERBOX.scenarios.ue5_ab_probe; cd ..
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
        "guard_market": {"name": "стражник на рынке"},
        "tavern_keeper": {"name": "трактирщик"},
        "maid_lusya": {"name": "Люся"},
    }
}

PHRASES = [
    ("NEG-01", "Не говори ему, что я согласен."),
    ("NEG-02", "Не говори ему, что я не согласен."),
    ("NEG-04", "Не бей его."),
    ("QUO-02", "Он сказал мне: «Убей стражника». Что он имел в виду?"),
    ("HYP-01", "А если я предложу ей помочь гильдии, она мне поверит?"),
    ("CON-01", "Привет."),
]


def _keys(acts: list) -> list:
    return [
        {k: v for k, v in a.items() if k in ("type", "negated", "modality", "quoted", "quoted_speaker_hint")}
        for a in acts
    ]


async def _run(comp, tag: str) -> dict:
    out = {}
    for cid, text in PHRASES:
        f = await comp.compress(text, SCENE)
        out[cid] = _keys(f.semantic_acts)
        print(f"[UE5-{tag}] {cid} acts={out[cid]}")
    return out


async def main() -> None:
    comp = IntentCompressor(LlamaCppCompressorClient())
    os.environ.pop("ENIGMA_PERACT_FSHOT", None)
    off = await _run(comp, "OFF")
    os.environ["ENIGMA_PERACT_FSHOT"] = "1"
    on = await _run(comp, "ON")
    os.environ.pop("ENIGMA_PERACT_FSHOT", None)

    print("=== ДИФФ ===")
    for cid, _ in PHRASES:
        o, n = off[cid], on[cid]
        per_off = any(("negated" in a or "modality" in a or "quoted" in a) for a in o)
        per_on = any(("negated" in a or "modality" in a or "quoted" in a) for a in n)
        delta = "SAME" if o == n else "CHANGED"
        print(f"{cid}: off_peract={per_off} on_peract={per_on} acts={delta}")
        if delta == "CHANGED":
            print(f"   off={o}")
            print(f"   on ={n}")


asyncio.run(main())