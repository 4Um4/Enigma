# -*- coding: utf-8 -*-
"""S342 H-ID Stage A — гейт D1 (native5), аддендум 3: read-only анализатор.

Единицы §3.2: нога -> {prompt_md5 -> Counter(resp_md5)} (все slow-path вызовы).
Гейты §3.3 (заморожены до прогона):
  INTRA_LEG(leg) = |{p: |set(resp)|>1}|                    -> >0 = det-RED
  seedMismatchAB = |{p in A&B: seedsA(p) != seedsB(p)}|    -> >0 = INVALID
  Shared = uniqPrompts(A) ∩ uniqPrompts(B) (onlyA/onlyB печатаются)
  S* = Shared(cc1_det_v1_t1_a, cc1_det_v1_t1_b) = 90 exact (канон);
  Shared(native5) != S* = INVALID (полное перечисление missing/extra)
  RESP_DIFF_PROMPT = |{p in Shared: multiset(A,p) != multiset(B,p)}| -> гейт 0
  Валидация методики: RESP_DIFF_PROMPT(cc1) == 0 (исторический det-GREEN).
Semantic A/A 90/90 позиционно — ОТДЕЛЬНЫЙ обязательный шаг (не заменяется
det-GREEN; процедура — вторым шагом по формату сводки корпуса).
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"

TRACE_RE = re.compile(
    r"\[DET-TRACE\] prompt_md5=([0-9a-f]{32})\s+sys_md5=([0-9a-f]{32})\s+"
    r"seed=(\d+)\s+resp_md5=([0-9a-f]{32})"
)


def parse_leg(path: Path) -> dict:
    """{prompt: {'resp': Counter, 'seeds': set, 'sys': set}} — все DET-TRACE ноги."""
    if not path.exists():
        print(f"ABSENT: {path.name}")
        sys.exit(2)
    legs: dict = defaultdict(lambda: {"resp": Counter(), "seeds": set(), "sys": set()})
    n = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TRACE_RE.search(line)
        if not m:
            continue
        p, s, seed, r = m.groups()
        legs[p]["resp"][r] += 1
        legs[p]["seeds"].add(int(seed))
        legs[p]["sys"].add(s)
        n += 1
    print(f"  {path.name}: traces={n} uniqPrompts={len(legs)}")
    return dict(legs)


def main() -> int:
    print("=== D1 native5: дет-гейт (адд.3) ===")
    A = parse_leg(REPORTS / "h_id_native5_a.txt")
    B = parse_leg(REPORTS / "h_id_native5_b.txt")
    print("[methodology] frozen-пара cc1 (валидация):")
    CA = parse_leg(REPORTS / "cc1_det_v1_t1_a.txt")
    CB = parse_leg(REPORTS / "cc1_det_v1_t1_b.txt")

    # INTRA_LEG (§3.2): (prompt,seed)->resp детерминирован ВНУТРИ инвокации
    intra = {}
    for name, leg in (("A", A), ("B", B)):
        bad = sorted(p for p, d in leg.items() if len(d["resp"]) > 1)
        intra[name] = bad
        print(f"INTRA_LEG {name}: {len(bad)}" + (f" -> {bad[:5]}" if bad else ""))

    # Seed-диагностика: межножевое (исторически никогда не наблюдалось)
    seed_mm = sorted(p for p in A.keys() & B.keys() if A[p]["seeds"] != B[p]["seeds"])
    print(f"seedMismatchAB: {len(seed_mm)}" + (f" -> {seed_mm[:5]}" if seed_mm else ""))

    # Shared / onlyA / onlyB (полное перечисление)
    shared = A.keys() & B.keys()
    only_a = sorted(A.keys() - B.keys())
    only_b = sorted(B.keys() - A.keys())
    print(f"Shared: {len(shared)} | onlyA={len(only_a)} onlyB={len(only_b)}")
    for tag, lst in (("ONLY_A", only_a), ("ONLY_B", only_b)):
        for p in lst:
            print(f"  {tag}: {p}")

    # Канон S* из frozen-пары + валидация методики
    s_star = CA.keys() & CB.keys()
    cc1_diff = sum(
        1 for p in s_star
        if sorted(CA[p]["resp"].items()) != sorted(CB[p]["resp"].items())
    )
    print(f"[methodology] S*={len(s_star)} | RESP_DIFF_PROMPT(cc1)={cc1_diff} (ожидание 0)")
    if cc1_diff != 0 or len(s_star) != 90:
        print("D1-VERDICT: METHOD-FAIL (cc1 не воспроизводит det-GREEN) — стоп, разбор")
        return 2

    # Условие INVALID: Shared != S* — полное перечисление
    missing = sorted(s_star - shared)
    extra = sorted(shared - s_star)
    print(f"S*-check: missing={len(missing)} extra={len(extra)}")
    for p in missing:
        print(f"  MISSING: {p}")
    for p in extra:
        print(f"  EXTRA: {p}")

    # RESP_DIFF_PROMPT: мультимножества resp_md5, гейт = 0
    diff = sorted(
        p for p in shared
        if sorted(A[p]["resp"].items()) != sorted(B[p]["resp"].items())
    )
    print(f"RESP_DIFF_PROMPT: {len(diff)}")
    for p in diff[:10]:
        print(f"  DIFF {p}: A={dict(A[p]['resp'])} B={dict(B[p]['resp'])}")

    # Диагностика конфигурации: native-нога = golden A един (sys_md5)
    for name, leg in (("A", A), ("B", B)):
        if leg:
            sysset = set().union(*(d["sys"] for d in leg.values()))
            print(f"[diag] sys_md5 uniq({name}): {sorted(sysset)}")

    if seed_mm or missing or extra or only_a or only_b:
        print("D1-VERDICT: INVALID (seedMismatch и/или Shared != S*)")
        return 1
    if intra["A"] or intra["B"] or diff:
        print("D1-VERDICT: det-RED (INTRA_LEG>0 и/или RESP_DIFF_PROMPT>0)")
        return 1
    print("D1-VERDICT: det-GREEN (INTRA_LEG=0; seedMismatchAB=0; Shared=S*=90; RESP_DIFF_PROMPT=0)")
    print("ВНИМАНИЕ: semantic A/A 90/90 — отдельный обязательный шаг, det-GREEN его НЕ заменяет")
    return 0


if __name__ == "__main__":
    sys.exit(main())
