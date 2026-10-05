"""path: /project/reports/p0_phase1_metrics.py

Назначение: анализатор ног SR-1 Phase 1 (oracle isolation). Парсит
    артефакты reports/sr1_*.txt, считает пер-классовые профильные метрики
    по золотым семьям (единый источник p0_rc_baseline) и печатает таблицу
    рук. Механические runtime-проверки (толерансы и вердикт — ВНЕ скрипта):
    (1) обязательное условие Мастера: счёт NONE-срезов == счёт sys_md5
    golden A, PROV-срезов == golden B (пустой срез настоящий, байт-пруф);
    (2) A/A руки ORC-I — построчное совпадение актов.
    Примечание: [SLICE] печатается только на LLM-вызовах: вопросные
    записи всегда slow-path; часть action-записей закрывается fast-path
    (без LLM) — для них среза не существует by construction. Warm-up
    вызов («привет») добавляет +1 NONE/+1 golden A — счётная пара
    остаётся согласованной.
Зависимости: p0_rc_baseline (ground truth), stdlib.
Запуск: python reports/p0_phase1_metrics.py
"""

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from p0_rc_baseline import _gold

_ROOT = Path(__file__).resolve().parents[1]
_REPORTS = Path(__file__).resolve().parent
_MICRO = _ROOT / "backend" / "tests" / "micro"
_MD5_A = hashlib.md5(
    (_MICRO / "golden_production_system_prompt_A.txt").read_text(encoding="utf-8").encode("utf-8")
).hexdigest()
_MD5_B = hashlib.md5(
    (_MICRO / "golden_production_system_prompt_B.txt").read_text(encoding="utf-8").encode("utf-8")
).hexdigest()

_THIRD = ("AB-3RD", "IND-3RD", "GEN-3RD")
_PROV2_TEXT = "Кто сообщил тебе моё имя?"

_ARMS: List[Tuple[str, str]] = [
    ("CTRL-BI", "sr1_p1_bi_a.txt"),
    ("ORC-FULL", "sr1_p1_orcfull_b.txt"),
    ("ORC-FULL", "sr1_p2_orcfull_a.txt"),
    ("CTRL-BI", "sr1_p2_bi_b.txt"),
    ("CTRL-B", "sr1_p3_b_a.txt"),
    ("ORC-B", "sr1_p3_orcb_b.txt"),
    ("ORC-B", "sr1_p4_orcb_a.txt"),
    ("CTRL-B", "sr1_p4_b_b.txt"),
    ("ORC-I", "sr1_p5_orci_a.txt"),
    ("ORC-I", "sr1_p5_orci_b.txt"),
]

_SLICE_RE = re.compile(r"\[SLICE\] router=oracle text='(.*)' family=(None|'[^']*') modules=(\S+)")
_SYS_RE = re.compile(r"sys_md5=([0-9a-f]{32})")
_ENTRY_RE = re.compile(r"^\[(\S+)\] TEXT: '(.*)'\s*$")
_ACTS_RE = re.compile(r"^\s+ACTS: (.*)$")
_ACT_RE = re.compile(r"([A-Z_]+)\(([^)]*)\)")


def _read(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _parse(path: Path) -> Dict[str, object]:
    entries: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    slices: Dict[str, str] = {}
    sys_md5s: List[str] = []
    cur: Optional[Tuple[str, str]] = None
    for line in _read(path).splitlines():
        m = _SLICE_RE.search(line)
        if m:
            slices[m.group(1)] = m.group(3)
            continue
        m = _SYS_RE.search(line)
        if m:
            sys_md5s.append(m.group(1))
            continue
        m = _ENTRY_RE.match(line)
        if m:
            cur = (m.group(1), m.group(2))
            continue
        m = _ACTS_RE.match(line)
        if m and cur is not None:
            entries.append((cur[0], cur[1], _ACT_RE.findall(m.group(1))))
            cur = None
    return {"entries": entries, "slices": slices, "sys": sys_md5s}


def _metrics(parsed: Dict[str, object]) -> Dict[str, object]:
    entries: List[Tuple[str, str, List[Tuple[str, str]]]] = parsed["entries"]
    slices: Dict[str, str] = parsed["slices"]
    sys_md5s: List[str] = parsed["sys"]

    def _acts(text: str) -> List[Tuple[str, str]]:
        for cls, t, acts in entries:
            if t == text:
                return acts
        return []

    prov_rec = sum(
        1 for cls, t, acts in entries
        if _gold(cls, t) == "PROV" and any(a == "ASK_PROVENANCE" for a, _ in acts)
    )
    p2 = any(a == "ASK_PROVENANCE" for a, _ in _acts(_PROV2_TEXT))
    id_rec = sum(
        1 for cls, t, acts in entries
        if _gold(cls, t) == "ID" and any(a == "ASK_IDENTITY" for a, _ in acts)
    )
    fp3 = sum(
        1 for cls, t, acts in entries
        if cls in _THIRD and any(a == "ASK_PROVENANCE" for a, _ in acts)
    )
    si = sum(1 for _, _, acts in entries for a, _ in acts if a == "SELF_INTRODUCTION")
    ask_id = sum(1 for _, _, acts in entries for a, _ in acts if a == "ASK_IDENTITY")
    topic = sum(1 for _, _, acts in entries for a, p in acts if a == "QUESTION" and p.strip())
    bnd_prov = sum(
        1 for cls, t, acts in entries
        if _gold(cls, t) == "BOUNDARY" and any(a == "ASK_PROVENANCE" for a, _ in acts)
    )
    bnd_id = sum(
        1 for cls, t, acts in entries
        if _gold(cls, t) == "BOUNDARY" and any(a == "ASK_IDENTITY" for a, _ in acts)
    )
    slice_counts = Counter(slices.values())
    sys_counts = Counter(sys_md5s)
    byte_ok = (
        slice_counts.get("NONE", 0) == sys_counts.get(_MD5_A, 0)
        and slice_counts.get("dialogue_provenance", 0) == sys_counts.get(_MD5_B, 0)
    )
    return {
        "n": len(entries), "prov_rec": prov_rec, "p2": p2, "id_rec": id_rec,
        "fp3": fp3, "si": si, "ask_id": ask_id, "topic": topic,
        "bnd": (bnd_prov, bnd_id), "slice": dict(slice_counts),
        "sys_uniq": len(sys_counts), "byte_ok": byte_ok,
        "acts_by_text": {t: [a for a, _ in acts] for _, t, acts in entries},
    }


def main() -> None:
    print("=== SR-1 PHASE 1: ORACLE ISOLATION — МЕТРИКИ РУК ===")
    print(f"golden A md5={_MD5_A[:10]} B md5={_MD5_B[:10]}")
    print("легенда: prov=ASK_PROV на PROV+(22) P2=PROV[2] id=ASK_ID на ID+(3) FP3=ASK_PROV на 3RD(9)")
    results: Dict[Tuple[str, str], Dict[str, object]] = {}
    for arm, fname in _ARMS:
        path = _REPORTS / fname
        if not path.is_file():
            print(f"[{arm:8} {fname}] ARTEFACT ОТСУТСТВУЕТ")
            continue
        m = _metrics(_parse(path))
        results[(arm, fname)] = m
        sl = m["slice"]
        slice_str = (
            f"slice(NONE:{sl.get('NONE', 0)}/PROV:{sl.get('dialogue_provenance', 0)}"
            f"/ID:{sl.get('dialogue_identity', 0)})"
            if sl else "slice(-)"
        )
        bnd_p, bnd_i = m["bnd"]
        print(
            f"[{arm:8} {fname}] n={m['n']} prov={m['prov_rec']}/22 "
            f"P2={'alive' if m['p2'] else 'DEAD'} id={m['id_rec']}/3 FP3={m['fp3']} "
            f"SI={m['si']} AskID={m['ask_id']} topic={m['topic']} bnd(p/i)={bnd_p}/{bnd_i} "
            f"{slice_str} sys_uniq={m['sys_uniq']}"
            + (f" byte_ok={'OK' if m['byte_ok'] else 'VIOLATION'}" if sl else "")
        )

    orci = [k for k in results if k[0] == "ORC-I"]
    aa = "-"
    if len(orci) == 2:
        a_map = results[orci[0]]["acts_by_text"]
        b_map = results[orci[1]]["acts_by_text"]
        mism = [t for t in a_map if t in b_map and a_map[t] != b_map[t]]
        aa = str(len(mism))
        print(f"A/A ORC-I: acts-mismatches={len(mism)}")
        for t in mism[:5]:
            print(f"  {t!r}: {a_map[t]} vs {b_map[t]}")

    print("--- СВОД (обе инстанции каждой руки) ---")
    for arm in ("CTRL-BI", "ORC-FULL", "CTRL-B", "ORC-B", "ORC-I"):
        rs = [m for (a, _), m in results.items() if a == arm]
        if rs:
            print(
                f"{arm:8} prov={[m['prov_rec'] for m in rs]}/22 "
                f"P2={[m['p2'] for m in rs]} id={[m['id_rec'] for m in rs]}/3 "
                f"FP3={[m['fp3'] for m in rs]} topic={[m['topic'] for m in rs]} "
                f"AskID={[m['ask_id'] for m in rs]} byte_ok={[m['byte_ok'] for m in rs]}"
            )

    def _sel(arm: str, key: str) -> str:
        return "/".join(str(m[key]) for (a, _), m in results.items() if a == arm)

    print(
        "ИТОГО SR-1-P1: ORC-FULL prov=" + _sel("ORC-FULL", "prov_rec")
        + " P2=" + _sel("ORC-FULL", "p2")
        + " byte_ok=" + _sel("ORC-FULL", "byte_ok")
        + " | CTRL-B prov=" + _sel("CTRL-B", "prov_rec")
        + " | CTRL-BI prov=" + _sel("CTRL-BI", "prov_rec")
        + " P2=" + _sel("CTRL-BI", "p2")
        + " | ORC-I id=" + _sel("ORC-I", "id_rec")
        + " | A/A=" + aa
    )


if __name__ == "__main__":
    main()