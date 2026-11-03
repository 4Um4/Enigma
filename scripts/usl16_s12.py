import pathlib
p = pathlib.Path("docs/audits/ADR-O-437_IMPACT.md")
c = p.read_text(encoding="utf-8-sig")
if "## 12. CanonicalRegistry Bridge" in c:
    print("Section 12 already exists, skipping.")
    raise SystemExit(0)
lines = [
    "",
    "## 12. CanonicalRegistry Bridge (USL-1.5, S410)",
    "",
    "### Architecture",
    "",
    "**Bridge site:** `intent_compressor._resolve_npc_by_name`",
    "**Pattern:** module-level cache (chronicle `decomposition_normalizer.py:73-75`)",
    "",
    "Fallback order: canonical exact match -> stem-based iteration (preserved).",
    "0 feature flags (additive, always active — Master verdict Q4).",
    "",
    "### Cache lifecycle",
    "",
    "| Parameter | Value |",
    "|---|---|",
    "| Registry source | `config/npc/individuals/*.json` (static config) |",
    "| Builder | `build_canonical_registry()` -> `load_npcs_merged()` -> JSON read |",
    "| Mutability | NPC roster + name_forms = config-sourced, NOT runtime-mutable |",
    "| Cache lifecycle | lazy build at first call -> process lifetime |",
    "| Invalidation | NOT NEEDED — registry immutable during game session |",
    "| Precedent | chronicle `decomposition_normalizer.py:73-75` — same pattern |",
    "",
    "Verdict: current implementation acceptable (Master: no code change without proof).",
    "",
    "### USL-1 Section 5.4 proven",
    "",
    "`test_player_and_author_same_resolution`: GREEN.",
    "",
]
with open(p, "a", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("Section 12 appended.")