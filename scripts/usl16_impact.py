import pathlib
p = pathlib.Path("docs/audits/ADR-O-437_IMPACT.md")
c = p.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
ok = 0
for i, (old, new) in enumerate([
    ("> **Статус:** ACTIVE (USL-1.1/1.2/1.3/1.4 GREEN; USL-1.5/1.6 — pending)",
     "> **Статус:** ACTIVE (USL-1.1–1.5 GREEN; USL-1.6 CLOSED — documentation-only closure, S410)"),
    ("| Будущий USL-1.5 (CanonicalRegistry bridge) | pending | USLEntityRef через общий реестр имён |\n| Будущий USL-1.6 (Regression + Activation) | pending | Финальные тесты, флаги, DTO Registry |",
     "| USL-1.5 (CanonicalRegistry bridge) | **CLOSED (S410)** | intent_compressor._resolve_npc_by_name canonical-first via _ensure_registry_cache(); «Орму» автора = «Орму» игрока (§5.4) |\n| USL-1.6 (Regression + Activation) | **CLOSED (S410)** | IPT 54/0/0 + USL pytest 96/96; 0 feature flags; DTO Registry §15; MUTATIONS S410 |"),
    ("| `tests/micro/test_usl_free_assert.py` | 10 | ✅ GREEN (USL-1.4) |\n| **Регрессия claim-контура** | 16 | ✅ GREEN |\n| **Итого** | **98** | ✅ all GREEN |",
     "| `tests/micro/test_usl_free_assert.py` | 10 | ✅ GREEN (USL-1.4) |\n| `tests/micro/test_usl_canonical_bridge.py` | 7 | ✅ GREEN (USL-1.5) |\n| **Регрессия claim-контура** | 16 | ✅ GREEN |\n| **Итого** | **105** | ✅ all GREEN |"),
    ("2. **CanonicalRegistry bridge** (USL-1.5): прокинуть `registry_builder.CanonicalRegistry` в input-контур как опциональный провайдер. Не разрушать fallback-механизмы. Цель: «Орму» автора и «Орму» игрока резолвятся одинаково (USL §5.4).\n3. **Флаги включения** (USL-1.6): по вердикту Мастера Q4 — минимально необходимые, после реализации. Сейчас 0 флагов (additive + 1 правка без флага — байт-идентично default OFF).\n4. **красный baseline** (5 нарушений IPT) — отдельный долг, не чинится в рамках USL (INV-RE-CACHE-ALLOWLIST, INV-FLAG-REGISTRY ×2, INV-SILENT-FAILURE ×3).",
     "2. ~~**CanonicalRegistry bridge** (USL-1.5)~~ ✅ CLOSED (S410): intent_compressor._ensure_registry_cache() + canonical-first _resolve_npc_by_name. §5.4 доказан.\n3. ~~**Флаги включения** (USL-1.6)~~ ✅ CLOSED (S410): 0 feature flags (additive, always active — вердикт Мастера Q4).\n4. ~~**красный baseline** (5 нарушений IPT)~~ ✅ CLOSED (S410): IPT-clearing — 11 fixes → IPT 54/0/0 CRITICAL. INV-SILENT-FAILURE ×3 + INV-RE-CACHE-ALLOWLIST + INV-FLAG-REGISTRY полностью закрыты."),
    ("| `8caefebc` | production | USL-1.4: Free ASSERT path — claim_event_subscriber.py:104-105. 10 новых тестов + 16 регрессий. |",
     "| `8caefebc` | production | USL-1.4: Free ASSERT path — claim_event_subscriber.py:104-105. 10 новых тестов + 16 регрессий. |\n| `<SHA-IPT>` | infrastructure | IPT-clearing: 11 fixes (INV-SILENT-FAILURE ×3 + INV-RE-CACHE-ALLOWLIST + INV-FLAG-REGISTRY). IPT 51→54 passed, 3→0 CRITICAL. |\n| `<SHA-USL-1.5>` | production | USL-1.5: CanonicalRegistry bridge — intent_compressor.py _ensure_registry_cache() + canonical-first _resolve_npc_by_name. 7 новых тестов. |\n| `<SHA-USL-1.6>` | documentation | USL-1.6: IMPACT R3 + DTO Registry §15 + MUTATIONS S410. Documentation-only closure. |"),
]):
    tag = chr(65 + i)
    if old in c:
        c = c.replace(old, new)
        ok += 1
        print(f"Edit {tag}: OK")
    else:
        print(f"Edit {tag}: NOT FOUND")
p.write_text(c, encoding="utf-8")
print(f"Edits A-E: {ok}/5 applied")