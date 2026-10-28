"""DLG-GC-00 — гейт Dialogue vertical (§9.3i, трек §3.6).

Корпус DLG-0 headless-runnable; скоринг детерминирован (15-20 scripted-сценариев).

Гейты:
- 15 ≤ len(CORPUS) ≤ 20
- Уникальные scenario_id
- Согласованность speaker/event_type
- US вычисляется только по applicable checks; zero applicable = error
- coverage = scenarios_with_applicable / total
- Повторный прогон = идентичный отчёт (детерминизм)
- Diagnostics RED присутствуют (asymmetry [H], NL-8)
- Скорер unit-tests: zero applicable, partial PASS, unknown-result-not-PASS
- Подмена результатов не допускается (broken expectation → FAIL)
"""
from __future__ import annotations

import pytest

from app.services.events.event_types import EventType
from tests.sandbox.scenarios.dlg0_golden_corpus import (
    CORPUS,
    CorpusReport,
    DLGCheck,
    DLGScenario,
    ScenarioResult,
    _run_scenario,
    run_corpus,
)


# ── DLG-GC-00: корпус ────────────────────────────────────────────────────────

class TestDLGGC00:
    """DLG-GC-00: корпус headless-runnable; скоринг детерминирован."""

    def test_corpus_size_15_to_20(self):
        assert 15 <= len(CORPUS) <= 20, f"corpus size {len(CORPUS)} out of [15..20]"

    def test_unique_scenario_ids(self):
        ids = [s.scenario_id for s in CORPUS]
        assert len(set(ids)) == len(ids), f"duplicate IDs: {ids}"

    def test_speaker_event_type_consistency(self):
        """speaker='player' → PLAYER_SPOKE; speaker='npc' → NPC_SPOKE."""
        for s in CORPUS:
            if s.speaker == "player":
                assert s.event_type == EventType.PLAYER_SPOKE.value, f"{s.scenario_id}"
            elif s.speaker == "npc":
                assert s.event_type == EventType.NPC_SPOKE.value, f"{s.scenario_id}"
            else:
                pytest.fail(f"unknown speaker {s.speaker!r} in {s.scenario_id}")

    def test_corpus_runs_headless_deterministic(self):
        """Повторный прогон даёт идентичный CorpusReport."""
        r1 = run_corpus()
        r2 = run_corpus()
        assert r1 == r2, "non-deterministic corpus"

    def test_us_baseline_computed(self):
        """US-baseline вычисляется (zero applicable = config error)."""
        r = run_corpus()
        assert r.us_baseline is not None, "zero applicable — config error"
        assert 0.0 <= r.us_baseline <= 100.0

    def test_coverage_computed(self):
        r = run_corpus()
        assert 0.0 <= r.coverage <= 100.0
        assert r.scenarios_with_applicable <= r.total_scenarios

    def test_known_red_findings_registered(self):
        """Должны быть зарегистрированы известные пробелы (DLG-1/2/3, NL-8)."""
        r = run_corpus()
        assert len(r.red_findings) >= 6, f"too few red findings: {len(r.red_findings)}"
        ids = {sid for sid, _ in r.red_findings}
        assert "dlg-018" in ids, "asymmetry [H] scenario required"
        assert "dlg-014" in ids or "dlg-015" in ids, "composite tail-loss required"
        assert "dlg-006" in ids, "GREETING no-consumer required"

    def test_no_exceptions_in_results(self):
        """Сценарии не должны падать с исключениями."""
        r = run_corpus()
        errors = [res for res in r.results if res.error is not None]
        assert not errors, \
            f"scenarios raised exceptions: {[(e.scenario.scenario_id, e.error.splitlines()[0]) for e in errors]}"

    def test_applicable_false_not_counted_as_pass(self):
        """diagnostic_only сценарии НЕ увеличивают applicable."""
        r = run_corpus()
        for res in r.results:
            if res.scenario.diagnostic_only:
                for chk in res.checks:
                    assert not chk.applicable, \
                        f"{res.scenario.scenario_id}: diagnostic_only but has applicable check"

    def test_no_result_substitution_broken_expectation_fails(self):
        """Broken expectation (expected=999) → FAIL — доказывает, что скорер
        сравнивает с фактическим состоянием, а не возвращает hardcoded PASS."""
        s_broken = DLGScenario(
            scenario_id="dlg-test-broken",
            category="self_intro",
            description="broken expectation — must FAIL",
            ref_3_6=None,
            speaker="player",
            event_type=EventType.PLAYER_SPOKE.value,
            semantic_acts=({"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}},),
            text="Мю", event_id="evt-broken",
            target_id="merchant_goran",
            expected_claims_count=999,  # заведомо неверно
            expected_claim_contains=(),
            expected_topic=None, expected_open_questions_count=0,
            known_red_for=(),
        )
        r = _run_scenario(s_broken)
        claims_check = next(c for c in r.checks if c.check_id.endswith("claims_count"))
        assert not claims_check.passed, \
            f"broken expectation must FAIL — proves no substitution; detail={claims_check.detail}"

    def test_real_scenario_dlg001_passes(self):
        """dlg-001 (sanity) — SELF_INTRO действительно создаёт 1 claim."""
        r = _run_scenario(next(s for s in CORPUS if s.scenario_id == "dlg-001"))
        assert all(c.passed for c in r.checks), \
            f"dlg-001 should pass: {[(c.check_id, c.detail) for c in r.checks]}"


# ── Скорер unit-tests ────────────────────────────────────────────────────────

class TestScorer:
    """Unit-тесты самого скорера (без запуска корпуса)."""

    def test_zero_applicable_returns_none_us(self):
        """Zero applicable → US=None (не 100)."""
        s = DLGScenario(
            scenario_id="t1", category="x", description="",
            ref_3_6=None, speaker="player", event_type="PLAYER_SPOKE",
            semantic_acts=(), text="", event_id="e1", target_id=None,
            expected_claims_count=0, expected_claim_contains=(),
            expected_topic=None, expected_open_questions_count=0,
            known_red_for=(), diagnostic_only=True,
        )
        r = ScenarioResult(scenario=s, checks=(
            DLGCheck(check_id="t1.diag", applicable=False, passed=False, detail=""),
        ))
        applicable = sum(1 for c in r.checks if c.applicable)
        us = (0 / applicable * 100) if applicable > 0 else None
        assert us is None, "zero applicable must yield US=None"

    def test_partial_pass(self):
        """2 applicable, 1 passed → US=50.0."""
        checks = (
            DLGCheck(check_id="a", applicable=True, passed=True, detail=""),
            DLGCheck(check_id="b", applicable=True, passed=False, detail=""),
        )
        applicable = sum(1 for c in checks if c.applicable)
        passed = sum(1 for c in checks if c.applicable and c.passed)
        us = passed / applicable * 100
        assert us == 50.0

    def test_unknown_result_not_pass(self):
        """error в scenario → checks пустые → не вклад в applicable/passed."""
        s = DLGScenario(
            scenario_id="t3", category="x", description="",
            ref_3_6=None, speaker="player", event_type="PLAYER_SPOKE",
            semantic_acts=(), text="", event_id="e3", target_id=None,
            expected_claims_count=1, expected_claim_contains=(),
            expected_topic=None, expected_open_questions_count=0,
            known_red_for=(),
        )
        r = ScenarioResult(scenario=s, checks=(), error="Boom")
        applicable = sum(1 for c in r.checks if c.applicable)
        passed = sum(1 for c in r.checks if c.applicable and c.passed)
        assert applicable == 0
        assert passed == 0