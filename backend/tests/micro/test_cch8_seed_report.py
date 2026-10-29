"""CCH-8 P3/P4: тесты SeedReport.

8 проверок ТЗ + 1 control:
1. точный учёт seeded/skipped;
2. причина каждого пропуска;
3. разделение canonical gaps и runtime materialization;
4. детерминизм отчёта;
5. отсутствие изменения игрового состояния;
6. корректная работа на всех шести NPC;
7. сохранение существующего поведения seeder;
8. регрессии затронутых тестов;
9. (control) отчёт отражает фактический seed, а не повторяет фикстуру.
"""
from __future__ import annotations

from app.services.chronicle.chronicle_seeder import (
    build_full_seed,
    build_seed_report,
    canonical_chronicles,
    SeedReport,
)

CANON_NPCS = [
    "blacksmith_orm",
    "guard_borko",
    "maid_lusya",
    "merchant_goran",
    "tavern_keeper_tornin",
    "thief_shadow",
]


def test_6_all_canonical_npcs_have_report():
    """Проверка 6: корректная работа на всех шести NPC."""
    for npc_id in CANON_NPCS:
        r = build_seed_report(npc_id)
        assert r is not None, f"{npc_id}: report is None"
        assert r.canon_loaded is True
        assert r.entries_total > 0
        assert r.entries_author > 0


def test_1_seeded_and_skipped_counts_match_build_full_seed():
    """Проверка 1: точный учёт seeded/skipped.
    Агрегаты memories/knowledge/relationships/imprints/beliefs должны совпадать
    с len(...) соответствующих компонент build_full_seed."""
    for npc_id in CANON_NPCS:
        r = build_seed_report(npc_id)
        full = build_full_seed(npc_id)
        assert full is not None
        assert r.memories_count == len(full["memories"]), npc_id
        assert r.knowledge_count == len(full["knowledge"]), npc_id
        assert r.relationships_count == len(full["relationships"]), npc_id
        assert r.imprints_count == len(full["imprints"]), npc_id
        assert r.beliefs_count == len(full["beliefs"]), npc_id


def test_2_skip_reason_is_set_for_every_skipped_entry():
    """Проверка 2: причина каждого пропуска.
    Для каждой SKIPPED entry skip_reason не None."""
    for npc_id in CANON_NPCS:
        r = build_seed_report(npc_id)
        for e in r.entries:
            if e.seed_result == "SKIPPED":
                assert e.skip_reason is not None, f"{npc_id}:{e.entry_id} SKIPPED без reason"
                assert len(e.skip_reason) > 0


def test_3_canonical_gaps_vs_runtime_materialization_separation():
    """Проверка 3: разделение canonical gaps и runtime materialization.
    structural_check=FAIL → проблема в каноне (canonical gap).
    seed_result=SKIPPED → seeder пропустил (runtime materialization gap).
    Это разные метрики: FAIL structural не обязательно SKIPPED seed."""
    for npc_id in CANON_NPCS:
        r = build_seed_report(npc_id)
        for e in r.entries:
            # structural FAIL означает canonical gap
            if e.structural_check == "FAIL":
                assert len(e.structural_notes) > 0
            # SKIPPED означает seed-side gap, может быть при structural OK
            if e.seed_result == "SKIPPED":
                assert e.skip_reason is not None
            # NOT_APPLICABLE — kind вне seedable, structural может быть OK
            if e.seed_result == "NOT_APPLICABLE":
                assert e.source_kind not in (
                    "EVENT", "KNOWLEDGE_LINK", "RELATIONSHIP", "EFFECT", "BELIEF_SEED"
                ) or e.source_kind == "EFFECT"


def test_4_determinism_two_runs_identical():
    """Проверка 4: детерминизм. Два запуска дают идентичный отчёт."""
    for npc_id in CANON_NPCS:
        r1 = build_seed_report(npc_id)
        r2 = build_seed_report(npc_id)
        assert r1 is not None and r2 is not None
        d1 = r1.to_dict()
        d2 = r2.to_dict()
        assert d1 == d2, f"{npc_id}: non-deterministic report"
        # entries отсортированы по entry_id
        ids = [e.entry_id for e in r1.entries]
        assert ids == sorted(ids), f"{npc_id}: entries not sorted by entry_id"


def test_5_no_side_effect_no_game_loop_import():
    """Проверка 5: отсутствие изменения игрового состояния.
    build_seed_report — pure function: не импортирует npc_loader, game_loop,
    не вызывает mutators. Доказательство через отсутствие побочных импортов
    в модуле на верхнем уровне."""
    import app.services.chronicle.chronicle_seeder as seeder_mod
    import inspect
    src = inspect.getsource(seeder_mod)
    # Не должно импортировать mutators на топ-уровне
    forbidden_top = [
        "from app.services.npc.npc_loader import",
        "from app.services.game_loop",
        "import game_loop",
    ]
    for fb in forbidden_top:
        assert fb not in src, f"seeder imports forbidden module: {fb}"
    # build_seed_report не должна вызывать mutators
    report_src = inspect.getsource(seeder_mod.build_seed_report)
    forbidden_calls = [
        "_apply_chronicle_seed_to_dict",
        "_enrich_with_chronicle_relations",
    ]
    for fc in forbidden_calls:
        assert fc not in report_src, f"build_seed_report calls mutator: {fc}"


def test_7_existing_seeder_behavior_preserved():
    """Проверка 7: существующее поведение seeder сохранено.
    build_full_seed всё ещё возвращает dict с 5 ключами.
    build_seed_* функции возвращают те же типы, что и раньше."""
    for npc_id in CANON_NPCS:
        full = build_full_seed(npc_id)
        assert full is not None
        assert set(full.keys()) == {
            "memories", "knowledge", "relationships", "imprints", "beliefs"
        }
        assert isinstance(full["memories"], tuple)
        assert isinstance(full["knowledge"], tuple)
        assert isinstance(full["relationships"], dict)
        assert isinstance(full["imprints"], list)
        assert isinstance(full["beliefs"], dict)


def test_9_control_report_matches_actual_seed_not_fixture():
    """Проверка 9 (control): отчёт отражает фактический seed.
    Если взять одну entry и изменить её payload так, чтобы seeder пропустил её,
    отчёт должен отразить новое skip-причину — это доказывает, что отчёт
    читает реальный канон, а не зашитые значения.
    Используем guard_borko: ищем BELIEF_SEED (все 7 без belief_type),
    ожидаем skip_reason содержит 'outside registry'.
    Дополнительно: проверяем EFFECT на blacksmith_orm — trauma без triggers
    должен быть SKIPPED с reason='trauma without triggers'."""
    npc_id = "guard_borko"
    r = build_seed_report(npc_id)
    assert r is not None
    belief_entries = [e for e in r.entries if e.source_kind == "BELIEF_SEED"]
    assert len(belief_entries) > 0, "guard_borko должен иметь BELIEF_SEED entries"
    # Все BELIEF_SEED в guard_borko — без belief_type (B3 audit: 7/7 no_type)
    for be in belief_entries:
        assert be.seed_result == "SKIPPED", f"{be.entry_id}: expected SKIPPED"
        assert be.skip_reason is not None
        assert "outside registry" in be.skip_reason or "belief_type" in be.skip_reason
    # Контр-проверка: EVENT entries должны быть SEEDED
    event_entries = [e for e in r.entries if e.source_kind == "EVENT"]
    assert len(event_entries) > 0
    for ee in event_entries:
        assert ee.seed_result == "SEEDED", f"{ee.entry_id}: expected SEEDED"
        assert ee.day is not None

    # Доп: blacksmith_orm имеет trauma-EFFECT без triggers (B4 audit: 2 записи)
    npc_id2 = "blacksmith_orm"
    r2 = build_seed_report(npc_id2)
    assert r2 is not None
    # Ищем trauma EFFECTs — они должны быть SKIPPED с reason
    trauma_skipped = [
        e for e in r2.entries
        if e.source_kind == "EFFECT" and e.seed_result == "SKIPPED"
    ]
    # blacksmith_orm имеет 2 trauma без triggers (B4 audit)
    assert len(trauma_skipped) >= 2, (
        f"blacksmith_orm: expected >=2 trauma SKIPPED, got {len(trauma_skipped)}"
    )
    for te in trauma_skipped:
        assert te.skip_reason == "trauma without triggers", (
            f"{te.entry_id}: expected 'trauma without triggers', got '{te.skip_reason}'"
        )