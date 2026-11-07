"""B3-PROMPT-FORENSICS — перехват полного prompt на границе ModelRouter.

Instrumentation (без подмены): wrap router.request_for_agent для capture
полного prompt перед вызовом LLM. Production-код НЕ меняется.

Запуск: cd backend; python scripts/b3_prompt_forensics.py
Требует: LLM-server на :8181 (ensure_llm)
"""
import sys
import os
import json
import time
import copy
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CAMPAIGN = "Open_road"
VICTIM = "tavern_keeper_tornin"
WITNESS = "maid_lusya"
PLAYER = "player"

CAPTURED = []


def main():
    from app.services.llm.runtime.client import ensure_llm
    from tests.gameplay.harness import TavernGameplayHarness
    from app.domain import epistemic_dispositions as _ed
    from app.domain.events import EventDTO
    from app.services.events.event_bus import get_event_bus
    from app.services.events.event_types import EventType
    from app.services.execution.dialogue_executor import DialogueExecutor

    print("[1] ensure_llm...")
    try:
        ensure_llm(label="B3-FORENSICS")
        print("  LLM lease acquired")
    except Exception as e:
        print(f"  ensure_llm failed: {e}")
        return

    print("[2] Monkey-patch DialogueExecutor for prompt capture...")
    _orig_gen = DialogueExecutor._generate_with_router

    def _instrumented(self, task, req, verdict=None):
        _router = getattr(self, "_router", None)
        if _router is None:
            return _orig_gen(self, task, req, verdict)
        _orig_req = _router.request_for_agent

        def _capture(agent_name, prompt, params=None, system_prompt=None, priority="canonical"):
            CAPTURED.append({
                "agent": agent_name,
                "prompt": prompt,
                "system_prompt": system_prompt,
                "prompt_len": len(prompt) if prompt else 0,
                "tick": getattr(task, "tick", None),
                "owner_id": getattr(task, "owner_id", ""),
                "campaign_id": getattr(task, "campaign_id", ""),
                "intent_type": getattr(req, "intent_type", ""),
                "target_id": getattr(req, "target_id", ""),
                "has_prop": bool(getattr(req, "proposition", None)),
                "prop": getattr(req, "proposition", None),
            })
            return _orig_req(agent_name, prompt, params, system_prompt, priority)

        _router.request_for_agent = _capture
        try:
            return _orig_gen(self, task, req, verdict)
        finally:
            _router.request_for_agent = _orig_req

    DialogueExecutor._generate_with_router = _instrumented

    print("[3] Harness setup...")
    _h = TavernGameplayHarness(seed=42, location="tavern")
    _h.new_game()
    _orig_disp = copy.deepcopy(_ed.EPISTEMIC_DISPOSITIONS)
    _ed.EPISTEMIC_DISPOSITIONS["maid"] = {
        "report": 0.0, "warn": 0.0, "attack": 0.0,
        "spread_rumor": 1.4, "talk": 0.8, "intimidate": 0.0,
    }

    try:
        print("[4] Warmup 2 ticks...")
        _h.advance_ticks(2)

        print("[5] Publish PLAYER_INSULTS...")
        _event = EventDTO(
            id=uuid4(), type=EventType.PLAYER_INSULTS.value,
            source=PLAYER, timestamp=0.0,
            payload={"target_id": VICTIM, "action_type": "player_insults", "intent_type": "insult"},
            visibility="public", radius=15.0, persistence_level="session",
        )
        get_event_bus().publish(_event)

        print("[6] Advance 8 ticks (capturing)...")
        _t0 = time.monotonic()
        _h.advance_ticks(8)
        print(f"  elapsed: {time.monotonic() - _t0:.1f}s")
    finally:
        _ed.EPISTEMIC_DISPOSITIONS.clear()
        _ed.EPISTEMIC_DISPOSITIONS.update(copy.deepcopy(_orig_disp))
        _h.dispose()

    print(f"\n[7] Captured {len(CAPTURED)} prompts total")

    npc = [p for p in CAPTURED if p["agent"] != "verifier" and p["agent"] != "dialogue_extractor"]
    ver = [p for p in CAPTURED if p["agent"] == "verifier"]
    maid_prop = [p for p in npc if p["owner_id"] == WITNESS and p["has_prop"]]

    print(f"  NPC dialogue (agent=npc): {len(npc)}")
    print(f"  Verifier: {len(ver)}")
    print(f"  maid_lusya with proposition: {len(maid_prop)}")

    output = Path("data/b3_prompt_forensics.json")
    with open(output, "w", encoding="utf-8") as f:
        json.dump({"total": len(CAPTURED), "npc": len(npc), "verifier": len(ver),
                   "maid_prop": len(maid_prop), "prompts": CAPTURED}, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved to: {output}")

    print(f"\n{'='*80}")
    print(f"ANALYSIS: maid_lusya prompts with proposition")
    print(f"{'='*80}")

    for i, p in enumerate(maid_prop[:5]):
        prompt = p["prompt"] or ""
        plen = len(prompt)
        has_claim = "[Факт, которым ты делишься]" in prompt
        has_beliefs = "Ты боишься" in prompt or "Ты доверяешь" in prompt or "Ты предан" in prompt or "Ты злишься" in prompt
        has_stm = "[Контекст текущего разговора]" in prompt
        has_cog = "Ты знаешь" in prompt or "ты видел" in prompt or "тебе сообщил" in prompt
        has_target = "Ты обращаешься к" in prompt

        print(f"\n--- maid_lusya [{i+1}] tick={p['tick']} target={p['target_id']} ---")
        print(f"  prompt_len: {plen}")
        print(f"  proposition: {p['prop']}")
        print(f"  has_claim_block: {has_claim}")
        print(f"  has_beliefs: {has_beliefs}")
        print(f"  has_stm: {has_stm}")
        print(f"  has_cognition: {has_cog}")
        print(f"  has_target_addr: {has_target}")

        if has_claim:
            pos = prompt.find("[Факт, которым ты делишься]")
            pct = pos / plen * 100 if plen > 0 else 0
            print(f"  claim_block position: char {pos}/{plen} ({pct:.1f}%)")
            end = prompt.find("\n", pos + 50)
            if end == -1: end = plen
            print(f"  claim_block: {prompt[pos:min(end, pos+250)]}")

        print(f"\n  PROMPT FIRST 400:")
        print(f"  {prompt[:400]}")
        print(f"\n  PROMPT LAST 400:")
        print(f"  {prompt[-400:]}")

    print(f"\n{'='*80}")
    print(f"VERIFIER prompts (confirm proposition)")
    print(f"{'='*80}")
    for i, p in enumerate(ver[:3]):
        prompt = p["prompt"] or ""
        print(f"\n--- verifier [{i+1}] len={len(prompt)} ---")
        print(f"  has 'player': {'player' in prompt}")
        print(f"  has 'tavern_keeper_tornin': {'tavern_keeper_tornin' in prompt}")
        print(f"  has 'субъект: ?': {'субъект: ?' in prompt or 'субъект:  ?' in prompt}")
        print(f"  first 250: {prompt[:250]}")


if __name__ == "__main__":
    main()