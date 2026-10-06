"""path: /project/reports/p0_stage3_analyze.py

Назначение: анализ STAGE 3 (4 артефакта m3_*): пер-групповые метрики
    (PVA/PVB/IDP/IDN/NEG/BRD-пары/MULTI/PVX), FP на EMPTY, границы.
    Источник gold — ЕДИНЫЙ: импорт _SUITE из p0_stage3_paraphrase.
Запуск: python reports/p0_stage3_analyze.py
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_stage3_paraphrase import _SUITE

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_phase1_metrics import _build_prompt_map, _parse

_ENTRY_RE = re.compile(r"^\[(\S+)\] TEXT: '(.*)'\s*$")
_ACTS_RE = re.compile(r"^\s+ACTS: (.*)$")
_ACT_RE = re.compile(r"([A-Z_]+)\(([^)]*)\)")

_BRD_PAIRS = [
    ("Что тебе сказали про склад?", "Кто тебе сказал про склад?"),
    ("Когда пришёл корабль?", "От кого ты узнал о корабле?"),
    ("Что тебе известно о наследстве?", "Как тебе стало известно о наследстве?"),
]


def _acts_by_text(path: Path, pm) -> Dict[str, List[str]]:
    parsed = _parse(path, pm)
    return {t: [a for a, _ in acts] for _, t, acts in parsed["entries"]}


def main() -> None:
    pm = _build_prompt_map()
    gold_by_class: Dict[str, List[Tuple[str, str]]] = {}
    for cls, text, gold in _SUITE:
        gold_by_class.setdefault(cls, []).append((text, gold))

    print("=== STAGE 3 ANALYZE (PVA-лексика vs PVB-семантика; decisive) ===")
    for name in ("m3_base_a", "m3_base_b", "m3_cand_a", "m3_cand_b"):
        path = Path("reports") / f"{name}.txt"
        if not path.is_file():
            print(f"[{name}] ARTEFACT ОТСУТСТВУЕТ")
            continue
        acts = _acts_by_text(path, pm)

        def recall(cls, act):
            items = gold_by_class.get(cls, [])
            return sum(1 for t, _ in items if act in acts.get(t, [])), len(items)

        empty_fp = [(c, t) for c, t, g in _SUITE if g == "EMPTY"
                    and "ASK_PROVENANCE" in acts.get(t, [])]
        id_fp = [(c, t) for c, t, g in _SUITE if g == "EMPTY"
                 and "ASK_IDENTITY" in acts.get(t, [])]
        pva, nva = recall("PVA", "ASK_PROVENANCE")
        pvb, nvb = recall("PVB", "ASK_PROVENANCE")
        idp, nidp = recall("IDP", "ASK_IDENTITY")
        idn = sum(1 for t, g in gold_by_class.get("IDN", []) if "ASK_IDENTITY" not in acts.get(t, []))
        pairs_ok = sum(
            1 for a, b in _BRD_PAIRS
            if "ASK_PROVENANCE" in acts.get(b, []) and "ASK_PROVENANCE" not in acts.get(a, [])
        )
        print(
            f"[{name}] PVA={pva}/{nva} PVB={pvb}/{nvb} IDP={idp}/{nidp} "
            f"IDN-∅={idn}/3 BRD-пары={pairs_ok}/3 "
            f"FP(prov на EMPTY)={len(empty_fp)} FP(id на EMPTY)={len(id_fp)}"
        )
        for c, t in empty_fp:
            print(f"    FP: [{c}] {t!r}")
        for c, t in id_fp:
            print(f"    ID-FP: [{c}] {t!r}")
        print("    PVX/BND (диагностика):")
        for cls in ("PVX", "NEGM"):
            for t, g in gold_by_class.get(cls, []):
                if g == "BOUNDARY":
                    print(f"      [{cls}] {t!r} -> {acts.get(t, [])}")

    print("ИТОГО: decisive = PVB(CAND) - PVB(BASE) >= 25 п.п. при FP<=2 (регистрация)")


if __name__ == "__main__":
    main()
