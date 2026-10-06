"""path: /project/reports/p0_phase1_metrics.py

Назначение: SR-1 Phase 1 analyzer v2 (после диагностики слоёв):
    (1) Канонический topic-канал Э2 = prov_topic (СВОДКА-строки; калибровка
        на старых ногах: OLD-B=4, OLD-BI=1 — числители handoff «4/25 -> 1/26»);
    (2) финальные акты (ACTS): prov/P2/id/FP3/SI/AskID/topicNZ/bnd;
    (3) byte: построчные [SLICE] vs sys_md5 (byte_ok; v1-баг dict-подсчёта
        исправлен; 96 вызовов = 90+1 warm-up+5 double-call = паритет старых
        ног); CTRL-руки — проверка sys-однородности (CTRL-B: все = golden B);
    (4) resp: resp_md5 по prompt_md5; карта prompt_md5->фраза строится из
        ORC-ног ([SLICE] предшествует своему DET-TRACE; user-prompt не
        зависит от состояния — доказано диагностикой). Сравнения ТОЛЬКО
        внутри пар (same-instance; кросс-инстанс = шум).
    P2 (финальный слой) всюду dead, включая старые ноги: колонка «PROV[2]
    жив» handoff на этом слое не воспроизводится — помечено как non-canon.
Зависимости: p0_rc_baseline, stdlib.
Запуск: python reports/p0_phase1_metrics.py [--old]
"""

import hashlib
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from p0_rc_baseline import _gold, _load_corpus

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
_OLD_ARMS: List[Tuple[str, str]] = [
    ("OLD-B", "e2r_b2bi_a.txt"),
    ("OLD-BI", "e2r_b2bi_b.txt"),
    ("OLD-A", "e2r_i2a_b.txt"),
    ("OLD-A", "e2r_a2i_a.txt"),
]
_PAIRS = [
    ("P1 BI-vs-ORCFULL", "sr1_p1_bi_a.txt", "sr1_p1_orcfull_b.txt"),
    ("P2 ORCFULL-vs-BI", "sr1_p2_orcfull_a.txt", "sr1_p2_bi_b.txt"),
    ("P3 B-vs-ORCB", "sr1_p3_b_a.txt", "sr1_p3_orcb_b.txt"),
    ("P4 ORCB-vs-B", "sr1_p4_orcb_a.txt", "sr1_p4_b_b.txt"),
    ("P5 ORCI-vs-ORCI", "sr1_p5_orci_a.txt", "sr1_p5_orci_b.txt"),
]
_ORC_FILES = [
    "sr1_p1_orcfull_b.txt", "sr1_p2_orcfull_a.txt", "sr1_p3_orcb_b.txt",
    "sr1_p4_orcb_a.txt", "sr1_p5_orci_a.txt", "sr1_p5_orci_b.txt",
]

_SLICE_RE = re.compile(r"\[SLICE\] router=oracle text='(.*)' family=(None|'[^']*') modules=(\S+)")
_TRACE_RE = re.compile(
    r"\[DET-TRACE\] prompt_md5=([0-9a-f]{32})(?: sys_md5=([0-9a-f]{32}))? seed=\d+ resp_md5=([0-9a-f]{32})"
)
_ENTRY_RE = re.compile(r"^\[(\S+)\] TEXT: '(.*)'\s*$")
_ACTS_RE = re.compile(r"^\s+ACTS: (.*)$")
_ACT_RE = re.compile(r"([A-Z_]+)\(([^)]*)\)")
_SUMMARY_RE = re.compile(r"^\[(\S+)\] '(.*)' -> action=\S+ acts=\[[^\]]*\] prov_topic=(True|False)")


def _read(path: Path) -> str:
    # PS 5.1 '>'-редирект пишет UTF-16LE (BOM FF FE); cmd '>' — ANSI.
    # BOM-сниф ДО цепочки: UTF-16-моджибейк декодируется cp1251 БЕЗ ошибки
    # (NUL валиден) — регексы молча умирают при «зелёных» PS-грепах
    # (Select-String читает UTF-16 сам). Обратно совместимо: старые
    # cmd-артефакты BOM не имеют.
    raw = path.read_bytes()
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16")
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig")
    for enc in ("utf-8", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _build_prompt_map() -> Dict[str, str]:
    """prompt_md5 -> фраза. Источник — только ORC-ноги: [SLICE] предшествует
    своему DET-TRACE (доказано); user-prompt не зависит от состояния →
    карта применима ко всем ногам, включая старые e2r и CTRL."""
    mapping: Dict[str, str] = {}
    for name in _ORC_FILES:
        path = _REPORTS / name
        if not path.is_file():
            continue
        pending: Optional[str] = None
        for line in _read(path).splitlines():
            m = _SLICE_RE.search(line)
            if m:
                pending = m.group(1)
                continue
            m = _TRACE_RE.search(line)
            if m:
                if pending is not None:
                    mapping[m.group(1)] = pending
                    pending = None
                continue
    return mapping


def _parse(path: Path, prompt_map: Dict[str, str]) -> Dict[str, object]:
    entries: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    slice_modules: List[str] = []
    sys_md5s: List[str] = []
    resp_by_text: Dict[str, str] = {}
    prov_topic: Dict[str, bool] = {}
    cur: Optional[Tuple[str, str]] = None
    for line in _read(path).splitlines():
        m = _SLICE_RE.search(line)
        if m:
            slice_modules.append(m.group(3))
            continue
        m = _TRACE_RE.search(line)
        if m:
            if m.group(2):
                sys_md5s.append(m.group(2))
            text = prompt_map.get(m.group(1))
            if text is not None:
                resp_by_text[text] = m.group(3)
            continue
        m = _SUMMARY_RE.match(line)
        if m:
            prov_topic[m.group(2)] = m.group(3) == "True"
            continue
        m = _ENTRY_RE.match(line)
        if m:
            cur = (m.group(1), m.group(2))
            continue
        m = _ACTS_RE.match(line)
        if m and cur is not None:
            entries.append((cur[0], cur[1], _ACT_RE.findall(m.group(1))))
            cur = None
    return {
        "entries": entries, "slices": slice_modules, "sys": sys_md5s,
        "resp": resp_by_text, "prov_topic": prov_topic,
    }


def _metrics(parsed: Dict[str, object]) -> Dict[str, object]:
    entries: List[Tuple[str, str, List[Tuple[str, str]]]] = parsed["entries"]
    slices: List[str] = parsed["slices"]
    sys_md5s: List[str] = parsed["sys"]
    prov_topic: Dict[str, bool] = parsed["prov_topic"]

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
    topic_nz = sum(1 for _, _, acts in entries for a, p in acts if a == "QUESTION" and p.strip())
    pt_true = [t for t, v in prov_topic.items() if v]
    slice_counts = Counter(slices)
    sys_counts = Counter(sys_md5s)
    byte_ok = None
    if slices:
        byte_ok = (
            slice_counts.get("NONE", 0) == sys_counts.get(_MD5_A, 0)
            and slice_counts.get("dialogue_provenance", 0) == sys_counts.get(_MD5_B, 0)
            and len(slices) == len(sys_md5s)
        )
    return {
        "n": len(entries), "prov_rec": prov_rec, "p2": p2, "id_rec": id_rec,
        "fp3": fp3, "si": si, "ask_id": ask_id, "topic_nz": topic_nz,
        "pt": len(pt_true), "pt_list": pt_true,
        "slice": dict(slice_counts), "sys_uniq": len(sys_counts),
        "sys_all_B": bool(sys_md5s) and set(sys_counts) == {_MD5_B},
        "byte_ok": byte_ok, "resp": parsed["resp"],
        # v1-поле, потерянное в v2-рерайте (урок: при рерайте прибора — дифф
        # его API против потребителей): A/A и кросс-сравнения актов
        "acts_by_text": {t: [a for a, _ in acts] for _, t, acts in entries},
    }


def main() -> None:
    old_mode = "--old" in sys.argv
    prompt_map = _build_prompt_map()
    corpus = _load_corpus()
    prov_texts = [t for cls, t, _ in corpus if _gold(cls, t) == "PROV"]
    id_texts = [t for cls, t, _ in corpus if _gold(cls, t) == "ID"]

    arms = _OLD_ARMS if old_mode else _ARMS
    title = "SR-1 PHASE 1 ANALYZER v2"
    if old_mode:
        title += " [КАЛИБРОВКА: старые ноги; ожидание OLD-B provTOPIC=4, OLD-BI=1]"
    print(f"=== {title} ===")
    results: Dict[str, Tuple[str, Dict[str, object]]] = {}
    for arm, fname in arms:
        path = _REPORTS / fname
        if not path.is_file():
            print(f"[{arm:8} {fname}] ARTEFACT ОТСУТСТВУЕТ")
            continue
        m = _metrics(_parse(path, prompt_map))
        results[fname] = (arm, m)
        sl = m["slice"]
        slice_str = (
            f"slice(NONE:{sl.get('NONE', 0)}/P:{sl.get('dialogue_provenance', 0)}"
            f"/I:{sl.get('dialogue_identity', 0)})" if sl else "slice(-)"
        )
        byte_str = "" if m["byte_ok"] is None else f" byte_ok={'OK' if m['byte_ok'] else 'VIOLATION'}"
        sysb = " sysALLB" if m["sys_all_B"] else ""
        print(
            f"[{arm:8} {fname}] n={m['n']} prov={m['prov_rec']}/22 "
            f"P2={'alive' if m['p2'] else 'dead(non-canon)'} id={m['id_rec']}/3 "
            f"FP3={m['fp3']} SI={m['si']} AskID={m['ask_id']} "
            f"topicNZ={m['topic_nz']} provTOPIC={m['pt']} {slice_str} "
            f"sysU={m['sys_uniq']}{sysb}{byte_str}"
        )
        for t in m["pt_list"]:
            print(f"    provTOPIC+: {t!r}")

    if old_mode:
        return

    print("--- resp-диффы ВНУТРИ пар (same-instance; PROV+/ID+) ---")
    for tag, fa, fb in _PAIRS:
        if fa not in results or fb not in results:
            continue
        ra = results[fa][1]["resp"]
        rb = results[fb][1]["resp"]
        for label, texts in (("PROV+", prov_texts), ("ID+", id_texts)):
            diffs = [t for t in texts if ra.get(t) and rb.get(t) and ra[t] != rb[t]]
            print(f"{tag:18} {label:5}: resp-diff {len(diffs)}/{len(texts)}")

    def _sel(arm: str, key: str) -> str:
        return "/".join(str(m[key]) for f, (a, m) in results.items() if a == arm)

    print("--- СВОД (обе инстанции каждой руки) ---")
    for arm in ("CTRL-BI", "ORC-FULL", "CTRL-B", "ORC-B", "ORC-I"):
        if any(a == arm for _, (a, _) in results.items()):
            print(
                f"{arm:8} prov={_sel(arm, 'prov_rec')}/22 provTOPIC={_sel(arm, 'pt')} "
                f"topicNZ={_sel(arm, 'topic_nz')} SI={_sel(arm, 'si')} "
                f"AskID={_sel(arm, 'ask_id')} byte_ok={_sel(arm, 'byte_ok')}"
            )
    print(
        "ИТОГО SR-1-P1: provTOPIC ORC-FULL=" + _sel("ORC-FULL", "pt")
        + " | CTRL-B=" + _sel("CTRL-B", "pt")
        + " | CTRL-BI=" + _sel("CTRL-BI", "pt")
        + " | prov " + _sel("ORC-FULL", "prov_rec") + "/" + _sel("CTRL-B", "prov_rec")
        + "/" + _sel("CTRL-BI", "prov_rec")
        + " | byte_ok=" + _sel("ORC-FULL", "byte_ok")
        + " | калибровка: python reports/p0_phase1_metrics.py --old"
    )


if __name__ == "__main__":
    main()
