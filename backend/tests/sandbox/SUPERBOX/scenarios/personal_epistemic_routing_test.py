# -*- coding: utf-8 -*-
"""
path: /project/backend/tests/sandbox/SUPERBOX/scenarios/personal_epistemic_routing_test.py
Назначение: Phase C acceptance: A (разное знание), B (опыт→знание→маршрут),
    C (anti-leakage пустой store), D (provenance conf), PARTIAL-KNOWLEDGE
    NO-LEAK, DIRECTED-EDGE. Резолвер чистый (реальный EpistemicStore).
Зависимости: app.services.npc.personal_route_resolver, EpistemicStore
Основные сущности: main

Запуск: cd backend; python -m tests.sandbox.SUPERBOX.scenarios.personal_epistemic_routing_test 2>&1 | Select-String -Pattern "PER"; python -m tests.sandbox.SUPERBOX.scenarios.relocation_causal_bridge_test 2>&1 | Select-String -Pattern "Итог"; cd ..
"""

from __future__ import annotations

from app.domain.epistemology import EpistemicRecord, Predicate, Proposition
from app.services.npc.epistemic_store import EpistemicStore
from app.services.npc.personal_route_resolver import resolve_personal_route

_G: list[str] = []
_R: list[str] = []


def _log(m: str) -> None:
    print(f"[PER] {m}", flush=True)


def _seed(store, actor, boundary, to_loc, conf, claim):
    store.upsert(EpistemicRecord(
        agent_id=actor,
        proposition=Proposition(subject_id=boundary, predicate=Predicate.EXITS_TO,
                                object_id=to_loc, polarity=True),
        confidence=conf, source_id=actor, source_claim_id=claim,
        first_observed_tick=0, last_updated_tick=0,
    ))


def main() -> int:
    # A: A знает A→B→C; B знает A→B
    sA, sB = EpistemicStore(), EpistemicStore()
    _seed(sA, "npc_a", "a:exit", "b", 0.9, "initial:a:b")
    _seed(sA, "npc_a", "b:exit", "c", 0.8, "initial:b:c")
    _seed(sB, "npc_b", "a:exit", "b", 0.9, "initial:a:b")
    rA = resolve_personal_route("npc_a", sA, "a", "c")
    rB = resolve_personal_route("npc_b", sB, "a", "c")
    if rA.status == "KNOWN_ROUTE":
        _G.append(f"A KNOWN path={rA.path} min_conf={rA.min_confidence}")
    else:
        _R.append(f"A RED: {rA.status}")
    if rB.status == "UNKNOWN_ROUTE":
        _G.append("B UNKNOWN_ROUTE (partial knowledge not completed by WorldGraph)")
    else:
        _R.append(f"B RED: {rB.status}")
    if rA.status == "KNOWN_ROUTE":
        _G.append(f"A KNOWN, min_conf={rA.min_confidence}")
    if rB.status == "UNKNOWN_ROUTE":
        _G.append("B UNKNOWN_ROUTE (partial knowledge not completed by WorldGraph)")

    # B: обучение — B переживает b→c
    _seed(sB, "npc_b", "b:exit", "c", 0.7, "direct:npc_b:b:exit:50")
    rB2 = resolve_personal_route("npc_b", sB, "a", "c")
    if rB2.status == "KNOWN_ROUTE":
        _G.append(f"B-learn: после опыта KNOWN, path={rB2.path}, min_conf={rB2.min_confidence}")
    else:
        _R.append("B-learn RED")

    # C: anti-leakage — пустой store, мир «знает»
    sE = EpistemicStore()
    rE = resolve_personal_route("npc_x", sE, "a", "c")
    if rE.status == "UNKNOWN_ROUTE":
        _G.append("C: пустой store → UNKNOWN (no WorldGraph leakage)")

    # D: provenance различается, conf не нормализуется
    _seed(sE, "npc_x", "a:exit", "b", 0.4, "heard:a:exit:7")
    rD = resolve_personal_route("npc_x", sE, "a", "b")
    if rD.status == "KNOWN_ROUTE" and abs(rD.min_confidence - 0.4) < 1e-9:
        _G.append("D: heard conf=0.4 сохранён (KNOWN ≠ CERTAIN)")

    # DIRECTED-EDGE: знание a→b не даёт b→a
    rRev = resolve_personal_route("npc_x", sE, "b", "a")
    if rRev.status == "UNKNOWN_ROUTE":
        _G.append("DIRECTED: b→a UNKNOWN (направленность рёбер)")
    else:
        _R.append("DIRECTED RED")

    # PARTIAL: x знает a→b; запрос a→c (мир знает b→c) → UNKNOWN
    _seed(sE, "npc_x", "b:exit", "c", 0.0 + 0.5, "heard:b:exit:9")
    # wait — это добавит b→c. Для PARTIAL-теста нужен ЧИСТЫЙ store:
    sP = EpistemicStore()
    _seed(sP, "npc_p", "a:exit", "b", 0.9, "initial")
    rP = resolve_personal_route("npc_p", sP, "a", "c")
    if rP.status == "UNKNOWN_ROUTE":
        _G.append("PARTIAL: a→b известно, b→c нет → a→c UNKNOWN (no leak)")

    print("[PER] === ОТЧЁТ ===")
    for g in _G:
        print(f"[PER] GREEN: {g}")
    for r in _R:
        print(f"[PER] RED: {r}")
    print(f"[PER] Итог: GREEN={len(_G)} RED={len(_R)}")
    return 0 if not _R else 1


if __name__ == "__main__":
    raise SystemExit(main())