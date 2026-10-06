"""path: /project/reports/p0_stage4_analyze.py

Назначение: STAGE 4 — E2-regression на кандидате: воспроизводится ли
    интерференция? Главный канал кандидата — prov-акты (topic-прокси пуст).
    Метрики: prov/topicNZ/SI/AskID/id/FP3; [SLICE]+byte_ok (ORC-ноги);
    A/A внутри рук; resp-дифф ORC vs REF-B на PROV+ (тот же промпт+seed —
    кросс-инстанс детерминизм кандидата ожидает идентичность).
    Сигнатура Qwen2.5 для сравнения: BI: prov 1->0, topicNZ 25->17.
Зависимости: p0_phase1_metrics, p0_rc_baseline.
Запуск: python reports/p0_stage4_analyze.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from p0_phase1_metrics import _build_prompt_map, _metrics, _parse
from p0_rc_baseline import _gold, _load_corpus

_ARMS = [
    ("CAND-BI", "m4_bi_a.txt"),
    ("CAND-ORC", "m4_orc_b.txt"),
    ("CAND-ORC", "m4_orc_a.txt"),
    ("CAND-BI", "m4_bi_b.txt"),
    ("REF-CAND-B", "m2_cand_b.txt"),
    ("REF-CAND-A", "m2_cand_a.txt"),
]


def main() -> None:
    pm = _build_prompt_map()
    prov_texts = [t for cls, t, _ in _load_corpus() if _gold(cls, t) == "PROV"]
    print("=== STAGE 4: E2-REGRESSION НА КАНДИДАТЕ (BI vs ORC-FULL) ===")
    print("Сигнатура Qwen2.5 (сравнение): BI: prov 1->0, topicNZ 25->17; ORC: восстановление.")
    results = {}
    for arm, fname in _ARMS:
        path = Path("reports") / fname
        if not path.is_file():
            print(f"[{arm:11} {fname}] ОТСУТСТВУЕТ")
            continue
        m = _metrics(_parse(path, pm))
        results[fname] = (arm, m)
        sl = m["slice"]
        slice_str = (f"slice(NONE:{sl.get('NONE', 0)}/P:{sl.get('dialogue_provenance', 0)}"
                     f"/I:{sl.get('dialogue_identity', 0)})") if sl else "slice(-)"
        byte_str = "" if m["byte_ok"] is None else f" byte_ok={'OK' if m['byte_ok'] else 'VIOLATION'}"
        print(f"[{arm:11} {fname}] prov={m['prov_rec']}/22 P2={'alive' if m['p2'] else 'dead'} "
              f"id={m['id_rec']}/3 FP3={m['fp3']} SI={m['si']} AskID={m['ask_id']} "
              f"topicNZ={m['topic_nz']} provTOPIC={m['pt']} {slice_str} "
              f"sysU={m['sys_uniq']}{byte_str}")

    for arm in ("CAND-BI", "CAND-ORC"):
        files = [f for a, f in _ARMS if a == arm and f in results]
        if len(files) == 2:
            a1 = results[files[0]][1]["acts_by_text"]
            a2 = results[files[1]][1]["acts_by_text"]
            mism = [t for t in a1 if t in a2 and a1[t] != a2[t]]
            print(f"A/A {arm}: acts-mismatches={len(mism)}")
            for t in mism[:3]:
                print(f"    {t!r}: {a1[t]} vs {a2[t]}")

    if "m4_orc_b.txt" in results and "m2_cand_b.txt" in results:
        ro = results["m4_orc_b.txt"][1]["resp"]
        rb = results["m2_cand_b.txt"][1]["resp"]
        diffs = [t for t in prov_texts if ro.get(t) and rb.get(t) and ro[t] != rb[t]]
        extra = "  <- кросс-инстанс идентичность (тот же промпт+seed)" if not diffs else ""
        print(f"resp-diff ORC vs REF-B на PROV+ (22): {len(diffs)}{extra}")

    def _arm(arm):
        return [m for f, (a, m) in results.items() if a == arm]

    bi, orc, refb = _arm("CAND-BI"), _arm("CAND-ORC"), _arm("REF-CAND-B")
    if bi and orc and refb:
        print("--- СВОД (обе инстанции каждой руки) ---")
        for name, ms in (("CAND-B (ref)", refb), ("CAND-BI", bi), ("CAND-ORC", orc)):
            print(f"{name:13} prov={[m['prov_rec'] for m in ms]}/22 "
                  f"topicNZ={[m['topic_nz'] for m in ms]} SI={[m['si'] for m in ms]} "
                  f"id={[m['id_rec'] for m in ms]}/3 FP3={[m['fp3'] for m in ms]}")
        print("ИТОГО STAGE 4: (a) BI<<B + ORC~=B => интерференция воспроизводится;")
        print("  (b) BI~=B => кандидат нейтрализует композиционную проблему;")
        print("  (c) смешанное => разбор. Вердикт — по развилкам, зарегистрированным до прогона.")


if __name__ == "__main__":
    main()