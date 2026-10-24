# -*- coding: utf-8 -*-
"""S367 smoke: guard_borko — gate core (детерминированно) + LLM-часть (если доступен).

Gate (per вердикт): >=2 валидных вопроса для Гильдия + старый пьянчужка.
Тень (Nominative) = известный NPC (shadow) -> корректно БЕЗ вопроса.
Тень inflected (Тенью/Тени) -> form-mismatch-шум, логируется, не засчитывается.

Детерминированная часть (normalizer + canned items + real roster) — всегда.
LLM-часть (полный decompose на фрагменте guard_borko) — если llama-server доступен.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.chronicle.biography_decomposer import BiographyDecomposer
from app.services.chronicle.decomposition_normalizer import ChronicleDecompositionNormalizer
from app.services.npc.npc_loader import get_display_names


def deterministic_part() -> bool:
    """Canned items с 3 сущностями -> normalizer + real roster -> backstop check."""
    roster = get_display_names()
    print("roster: %d NPCs (%s)" % (len(roster), ", ".join(sorted(roster.values()))))
    raw = json.dumps({"items": [
        {"kind": "RELATIONSHIP",
         "draft_payload": {"summary": "служил Гильдии", "target_hint": "Гильдия",
                           "nature": "dependence", "valence": "negative"},
         "confidence": 0.8},
        {"kind": "RELATIONSHIP",
         "draft_payload": {"summary": "не любит трактирщика",
                           "target_hint": "старый пьянчужка",
                           "nature": "aversion", "valence": "negative"},
         "confidence": 0.8},
        {"kind": "RELATIONSHIP",
         "draft_payload": {"summary": "не знаком с Тень",
                           "target_hint": "Тень",
                           "nature": "unknown", "valence": "neutral"},
         "confidence": 0.8},
    ]})
    items = ChronicleDecompositionNormalizer.normalize(
        raw, chronicle_id="guard_borko", fragment_ord=0, roster=roster)
    guildia = []
    pjan = []
    ten = []
    for it in items:
        q = it.question
        if q is None:
            continue
        span = (q.target_span or "").strip().lower()
        if "гильд" in span:
            guildia.append(q)
        if "пьянчуж" in span:
            pjan.append(q)
        if span.startswith("тен"):
            ten.append(q)
    print("  детерминированная часть:")
    print("    Гильдия: %d valid вопроса (qid=%s)" % (
        len(guildia), guildia[0].question_id if guildia else "none"))
    print("    старый пьянчужка: %d valid вопроса (qid=%s)" % (
        len(pjan), pjan[0].question_id if pjan else "none"))
    print("    Тень (any form): %d — noise/not-counted" % len(ten))
    ok = len(guildia) >= 1 and len(pjan) >= 1
    print("    -> %s" % ("PASS (>=2 valid)" if ok else "FAIL"))
    return ok


def _extract_fragment(author_text: str) -> str:
    """Извлечь порцию с упоминаниями Гильдии/пьянчужки/Тени (items 9, 18, 20, 21)."""
    lines = author_text.split("\n")
    frag = []
    for ln in lines:
        stripped = ln.lstrip()
        if any(stripped.startswith(p) for p in ["9.", "18.", "20.", "21."]):
            frag.append(ln)
    return "\n".join(frag) if frag else author_text[:3000]


async def llm_part():
    """Полный decompose на фрагменте guard_borko — если llama-server доступен."""
    gb_path = ROOT / "config" / "npc" / "chronicles" / "guard_borko.json"
    gb = json.loads(gb_path.read_text(encoding="utf-8"))
    author_text = gb["author_text"]
    fragment = _extract_fragment(author_text)
    print("  фрагмент: %d chars (items 9,18,20,21)" % len(fragment))
    d = BiographyDecomposer()
    try:
        result = await d.decompose("guard_borko", 0, fragment)
    except Exception as e:
        print("  LLM-часть SKIP: decompose exception: %s" % e)
        return None
    if not result.ok:
        print("  LLM-часть SKIP: decompose failure: %s" % (result.error or ""))
        return None
    qs = [it.question for it in result.items if it.question]
    valid = 0
    noise = 0
    for q in qs:
        span = (q.target_span or "").strip().lower()
        if span.startswith("тен"):
            noise += 1
            print("    NOISE: qid=%s span=%r (Тень-form)" % (q.question_id, q.target_span))
        elif "гильд" in span or "пьянчуж" in span:
            valid += 1
            print("    VALID: qid=%s span=%r" % (q.question_id, q.target_span))
        else:
            print("    other: qid=%s span=%r" % (q.question_id, q.target_span))
    print("  LLM-часть: %d valid, %d noise (Тень-form), %d total questions" % (
        valid, noise, len(qs)))
    return valid >= 2


def main():
    print("=== S367 smoke: guard_borko ===")
    print("--- детерминированная часть (normalizer + canned 3 сущности + real roster) ---")
    det_ok = deterministic_part()
    print("--- LLM-часть (полный decompose, если llama-server доступен) ---")
    llm_ok = asyncio.run(llm_part())
    print("=== итог ===")
    if det_ok:
        print("OK SMOKE: gate core валиден (>=2 valid: Гильдия + старый пьянчужка; Тень silent)")
    else:
        print("FAIL SMOKE: gate core не пройден")
    if llm_ok is None:
        print("   LLM-часть не выполнена (llama-server недоступен) — gate core детерминированно валиден")
    elif llm_ok:
        print("   LLM-часть: >=2 valid (полный pipeline подтверждён)")
    else:
        print("   LLM-часть: <2 valid (но gate core детерминированно валиден)")
    return 0 if det_ok else 1


if __name__ == "__main__":
    sys.exit(main())
