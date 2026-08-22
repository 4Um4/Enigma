"""
SUPERBOX-DISPOSITIONS (S211, слой 3): характеры вместо монокультуры.

  [D1] guard + belief(threat, conf=0.9) → report=1.26 > warn=0.45 → REPORT доминирует
  [D2] maid + тот же belief → spread_rumor=1.17 — максимум её словаря
  [D3] merchant + тот же belief → warn=1.26 — паритет с прежним поведением Goran
  [D4] thief + belief → report-модификатора НЕТ ВООБЩЕ (молчание преступника)
  [D5] Обратная совместимость: to_modifiers(ctx) без архетипа — байт-в-байт
       легаси-словарь (warn == attack == 1.35, block_path == 0.675)
  [D6] Три агента, один belief, три РАЗНЫХ словаря модификаторов —
       детерминизм внутри архетипа (D6b: два guard'а идентичны)

Запуск: python backend/tests/sandbox/SUPERBOX/scenarios/epistemic_dispositions_test.py
"""
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.epistemology import EpistemicContext, Predicate, Proposition
from app.services.npc.epistemic_context_resolver import EpistemicContextResolver

THREAT_CTX = EpistemicContext(
    agent_id="x",
    perceived_threats=("thief_shadow",),
    perceived_violations=1,
    max_confidence=0.9,
    trigger_proposition=Proposition(
        subject_id="thief_shadow", predicate=Predicate.STOLE,
        object_id="gold", polarity=True),
)


def main() -> int:
    print("=" * 64)
    print("SUPERBOX-DISPOSITIONS: характеры вместо монокультуры WARN (S211)")
    print("=" * 64)
    ok = True
    to_mod = EpistemicContextResolver.to_modifiers

    # ── D1: guard → REPORT ───────────────────────────────────────────
    m_guard = to_mod(THREAT_CTX, archetype="guard")
    d1 = m_guard.get("report", 0) > m_guard.get("warn", 0) and m_guard["report"] == round(0.9 * 1.5 * 1.4, 4)
    print(f"[D1] guard: report={m_guard.get('report')} > warn={m_guard.get('warn')} "
          f"— {'✅' if d1 else '❌'}")
    ok = ok and d1

    # ── D2: maid → SPREAD_RUMOR ──────────────────────────────────────
    m_maid = to_mod(THREAT_CTX, archetype="maid")
    d2 = (m_maid.get("spread_rumor", 0) == max(m_maid.values())
          and "report" not in m_maid or m_maid.get("report", 0) < 0.2)
    # maid report=0.1: в словарь попадёт (round(0.9*1.5*0.1)>0) — проверяем
    # доминирование слуха, не отсутствие ключа:
    d2 = m_maid.get("spread_rumor", 0) == max(m_maid.values())
    print(f"[D2] maid: spread_rumor={m_maid.get('spread_rumor')} — максимум её профиля "
          f"— {'✅' if d2 else '❌'}")
    ok = ok and d2

    # ── D3: merchant → WARN (паритет с Goran-эрой) ───────────────────
    m_merch = to_mod(THREAT_CTX, archetype="merchant")
    d3 = m_merch.get("warn") == round(0.9 * 1.5 * 1.4, 4) and m_merch["warn"] == max(m_merch.values())
    print(f"[D3] merchant: warn={m_merch.get('warn')} — паритет прежнему Goran "
          f"— {'✅' if d3 else '❌'}")
    ok = ok and d3

    # ── D4: thief → молчание ─────────────────────────────────────────
    m_thief = to_mod(THREAT_CTX, archetype="thief")
    d4 = m_thief.get("report", 99) == 99  # ключа нет вовсе (вес 0.0 отфильтрован)
    print(f"[D4] thief: report-модификатор отсутствует (молчание) — "
          f"{'✅' if d4 else '❌'}")
    ok = ok and d4

    # ── D5: обратная совместимость ───────────────────────────────────
    m_legacy = to_mod(THREAT_CTX)  # без архетипа
    d5 = (m_legacy.get("warn") == 1.35 and m_legacy.get("attack") == 1.35
          and m_legacy.get("block_path") == 0.675
          and "report" not in m_legacy and "spread_rumor" not in m_legacy)
    print(f"[D5] Легаси без архетипа: warn=attack={m_legacy.get('warn')}, "
          f"block_path={m_legacy.get('block_path')} — "
          f"{'✅' if d5 else '❌'} (байт-в-байт S198)")
    ok = ok and d5

    # ── D6: разнообразие + детерминизм ───────────────────────────────
    dicts = {a: to_mod(THREAT_CTX, archetype=a)
             for a in ("guard", "maid", "merchant", "tavern_keeper")}
    d6a = len({tuple(sorted(d.items())) for d in dicts.values()}) == 4
    d6b = to_mod(THREAT_CTX, archetype="guard") == m_guard  # два вызова — идентично
    print(f"[D6] 4 архетипа → 4 разных словаря: {d6a}; "
          f"повтор guard идентичен (детерминизм): {d6b} — "
          f"{'✅' if (d6a and d6b) else '❌'}")
    ok = ok and d6a and d6b

    print("=" * 64)
    print("🎉 ХАРАКТЕРЫ ДОКАЗАНЫ: один belief — разные поступки по натуре."
          if ok else "❌ ТЕСТ С ОШИБКАМИ")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())