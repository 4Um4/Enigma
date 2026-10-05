"""path: /project/reports/p0_rb_separation.py

Назначение: P0-3c (SR-1, вердикт Мастера): THRESHOLD-FREE separation
    geometry R-b — распределения косинусных близостей корпуса к якорям
    семейств, ДО любых δ/τ (порядок: геометрия → порог → классификатор).
    Якорь семейства = контент модуля, попадающий в активный промпт:
    enum-tail (если есть) + contrast-block через закрытый loader;
    notes исключены (loader-ignored). Ground truth — ЕДИНЫЙ источник:
    импорт из p0_rc_baseline (аудит P0-1, заморожен Q-1/Q-2). Boundary
    (10) — диагностика, не знаменатель. В этом скрипте НЕТ routing-
    решений и порогов: только геометрия, знаковые тесты, перекрытия.
Зависимости: sentence_transformers (модель запинена P0-3b:
    paraphrase-multilingual-MiniLM-L12-v2, rev e8f8c211226b; офлайн),
    p0_rc_baseline (ground truth + fail-loud гвари), app.services.
    input.semantic_library (read-only loader — прецедент: corpus script).
Основные сущности: _anchor_sections(), _anchor_vec(), _stats(),
    main().
Запуск: $env:HF_HUB_OFFLINE='1'; python reports/p0_rb_separation.py
"""

import sys
from pathlib import Path
from typing import Dict, List

import numpy

_ROOT = Path(__file__).resolve().parents[1]
# read-only доступ к production loader'у (закрытая схема) — прецедент corpus script
sys.path.insert(0, str(_ROOT / "backend"))

# ЕДИНЫЙ источник ground truth (никакой второй истины — вердикт Мастера):
from p0_rc_baseline import _assert_invariants, _gold, _load_corpus

from app.services.input.semantic_library import load_module
from sentence_transformers import SentenceTransformer

_MODEL_ID = "paraphrase-multilingual-MiniLM-L12-v2"
_BOUNDARY = "BOUNDARY"
_GROUPS = ("PROV", "ID", "EMPTY")


def _anchor_sections(module_name: str) -> List[str]:
    """Секции модуля, попадающие в активный промпт: enum-tail (если
    есть) + contrast-block. notes исключены — loader-ignored."""
    m = load_module(module_name)
    sections = [m.enum_tail] if m.enum_tail is not None else []
    sections.append(m.contrast_block)
    return sections


def _anchor_vec(model: SentenceTransformer, sections: List[str]) -> numpy.ndarray:
    """Якорь = L2-нормализованное среднее векторов секций (a priori:
    секции равноправны независимо от длины)."""
    vecs = numpy.asarray(model.encode(sections, normalize_embeddings=True))
    anchor = vecs.mean(axis=0)
    return anchor / numpy.linalg.norm(anchor)


def _stats(a: numpy.ndarray) -> str:
    return (
        f"mean={a.mean():+.3f} min={a.min():+.3f} "
        f"med={numpy.median(a):+.3f} max={a.max():+.3f}"
    )


def main() -> None:
    model = SentenceTransformer(_MODEL_ID)

    entries = _load_corpus()
    _assert_invariants(entries)  # fail-loud: ground truth == аудит P0-1
    texts = [t for _, t, _ in entries]
    golds = [_gold(cls, text) for cls, text, _ in entries]
    idx: Dict[str, List[int]] = {g: [k for k, gd in enumerate(golds) if gd == g] for g in _GROUPS}
    bnd_idx = [k for k, gd in enumerate(golds) if gd == _BOUNDARY]

    # Гварь детерминизма (перезакрепление P0-3b внутри прибора):
    v_a = model.encode(["Кто ты?"], normalize_embeddings=True)[0]
    v_b = model.encode(["Кто ты?"], normalize_embeddings=True)[0]
    assert float(numpy.max(numpy.abs(v_a - v_b))) == 0.0, "недетерминизм энкодера"

    prov_sections = _anchor_sections("dialogue_provenance")
    id_sections = _anchor_sections("dialogue_identity")
    anchor_p = _anchor_vec(model, prov_sections)
    anchor_i = _anchor_vec(model, id_sections)
    anchor_cross = float(anchor_p @ anchor_i)

    vecs = numpy.asarray(model.encode(texts, normalize_embeddings=True))
    sim_p = vecs @ anchor_p
    sim_i = vecs @ anchor_i
    delta = sim_p - sim_i

    print("=== P0-3c: R-b SEPARATION GEOMETRY (threshold-free) ===")
    print(f"model: {_MODEL_ID} (rev e8f8c211226b; offline)")
    print(f"anchor PROV: {len(prov_sections)} секции (enum-tail + contrast-block)")
    print(f"anchor ID: {len(id_sections)} секции (contrast-block)")
    print(f"sim(anchorP, anchorI) = {anchor_cross:+.3f}   <- близость якорей друг к другу")
    print()

    print("--- Сводка по золотым группам ---")
    for g in _GROUPS:
        ii = numpy.asarray(idx[g])
        print(f"{g:6} n={len(ii):2}  simP [{_stats(sim_p[ii])}]")
        print(f"{'':13}      simI [{_stats(sim_i[ii])}]")
        print(f"{'':13}      D    [{_stats(delta[ii])}]  sign(D>0)={int((delta[ii] > 0).sum())}/{len(ii)}")
    print()

    print("--- Знаковые тесты (D>0 = ближе к PROV-анкеру) ---")
    for g in _GROUPS:
        ii = numpy.asarray(idx[g])
        print(f"{g:6}: sign(D>0) = {int((delta[ii] > 0).sum())}/{len(ii)}")
    print()

    print("--- PROV+ построчно (sorted by D) ---")
    for k in sorted(idx["PROV"], key=lambda k: -delta[k]):
        print(f"  D={delta[k]:+.3f}  simP={sim_p[k]:.3f} simI={sim_i[k]:.3f}  {texts[k]!r}")
    print()

    print("--- ID+ (n=3, diagnostic arm) ---")
    for k in idx["ID"]:
        print(f"  D={delta[k]:+.3f}  simP={sim_p[k]:.3f} simI={sim_i[k]:.3f}  {texts[k]!r}")
    print()

    print("--- Boundary (диагностика, НЕ знаменатель; Q-1) ---")
    for k in bnd_idx:
        print(f"  D={delta[k]:+.3f}  simP={sim_p[k]:.3f} simI={sim_i[k]:.3f}  {texts[k]!r}")
    print()

    empty = numpy.asarray(idx["EMPTY"])
    print("--- EMPTY: топ-10 по simP (риск F2: EMPTY->PROV) ---")
    for k in sorted(idx["EMPTY"], key=lambda k: -sim_p[k])[:10]:
        print(f"  simP={sim_p[k]:.3f} simI={sim_i[k]:.3f}  {texts[k]!r}")
    print()
    print("--- EMPTY: топ-10 по simI (риск F4: EMPTY->ID) ---")
    for k in sorted(idx["EMPTY"], key=lambda k: -sim_i[k])[:10]:
        print(f"  simI={sim_i[k]:.3f} simP={sim_p[k]:.3f}  {texts[k]!r}")
    print()

    prov = numpy.asarray(idx["PROV"])
    print("--- Перекрытия распределений (D-ось и simP-ось; порог НЕ выбирается) ---")
    print(f"PROV+ D: [{delta[prov].min():+.3f} .. {delta[prov].max():+.3f}]")
    print(f"EMPTY  D: [{delta[empty].min():+.3f} .. {delta[empty].max():+.3f}]")
    if delta[prov].min() > delta[empty].max():
        print("=> знаково полное разделение (min D PROV+ > max D EMPTY)")
    else:
        above = int((delta[empty] >= delta[prov].min()).sum())
        print(f"=> ПЕРЕКРЫТИЕ: {above} EMPTY выше min D(PROV+)")
    print(
        f"ось simP: max(EMPTY)={sim_p[empty].max():.3f} vs min(PROV+)={sim_p[prov].min():.3f} "
        f"({'разделимо' if sim_p[empty].max() < sim_p[prov].min() else 'ПЕРЕКРЫТИЕ'})"
    )
    print()

    idv = numpy.asarray(idx["ID"])
    print(
        f"ИТОГО P0-3c: sign PROV+ {int((delta[prov] > 0).sum())}/22 | "
        f"EMPTY {int((delta[empty] > 0).sum())}/55 | ID+ {int((delta[idv] > 0).sum())}/3 | "
        f"sim(anchorP,anchorI)={anchor_cross:+.3f} | "
        f"D-range PROV+ [{delta[prov].min():+.3f}..{delta[prov].max():+.3f}] vs "
        f"EMPTY [{delta[empty].min():+.3f}..{delta[empty].max():+.3f}]"
    )


if __name__ == "__main__":
    main()