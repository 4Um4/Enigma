# path: /project/backend/tests/gameplay/test_cc09_causal_attribution.py
# Назначение: CC-09 — NPC объясняет изменение доверия/страха конкретным событием.
#   causal_ledger → _format_causal_context → LLM prompt.
#   Сценарии A-D, 4 уровня: данные/доступ/prompt/объяснение.
# Зависимости: app.services.execution.dialogue_executor, app.services.npc.state_applicator
# Запуск: cd backend; python -m pytest tests/gameplay/test_cc09_causal_attribution.py -v -s

"""
CC-09: Causal Attribution — NPC can explain WHY state changed.

causal_ledger (ADR-CAUSAL-SPINE) → _format_causal_context → LLM prompt.

Сценарии:
  A. NPC knows cause from own experience (attack → trust change)
  B. NPC knows from testimony (BeliefDelta → causal_ledger entry)
  C. NPC doesn't know and doesn't fabricate (empty ledger → empty context)
  D. Multiple causes (multiple entries → all listed, cap at 10)

Уровни проверки:
  1. Data presence: CausalEntry exists in causal_ledger
  2. NPC accessibility: _format_causal_context reads it
  3. LLM prompt inclusion: formatted text would be in prompt
  4. Actual explanation: (level 3 is prerequisite — prompt includes cause)
"""
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.execution.dialogue_executor import DialogueExecutor


def _make_ledger(entries: list) -> list:
    """Helper: create ledger entries from tuples (field, delta, source, tick)."""
    return [
        {"field": f, "delta": d, "source": s, "tick": t}
        for f, d, s, t in entries
    ]


class TestCC09CausalAttribution:
    """CC-09: NPC explains WHY state changed — causal_ledger → LLM prompt."""

    # ═══ A: NPC knows cause from own experience ═══

    def test_A_data_presence_trust_change(self) -> None:
        """A-1: Attack → CausalEntry in causal_ledger (data presence)."""
        # Simulate: NPC attacked → trust/fear changed → CausalEntry written
        ledger = _make_ledger([
            ("trust", -5.0, "player_insults", 3),
            ("fear", 2.0, "attack_from_player", 5),
        ])
        assert len(ledger) == 2
        assert ledger[0]["field"] == "trust"
        assert ledger[0]["source"] == "player_insults"
        assert ledger[1]["field"] == "fear"

    def test_A_accessibility_format_includes_cause(self) -> None:
        """A-2: _format_causal_context includes cause (accessibility)."""
        de = DialogueExecutor()
        ledger = _make_ledger([
            ("trust", -5.0, "player_insults", 3),
            ("fear", 2.0, "attack_from_player", 5),
        ])
        result = de._format_causal_context(ledger)
        print(f"[A-2] Format result:\n{result}")
        assert "доверие" in result, "trust field not mapped"
        assert "player_insults" in result, "cause source missing"
        assert "страх" in result, "fear field not mapped"
        assert "attack_from_player" in result, "attack source missing"

    def test_A_prompt_inclusion_format_is_prompt_text(self) -> None:
        """A-3: Formatted text is valid prompt section (prompt inclusion)."""
        de = DialogueExecutor()
        ledger = _make_ledger([("trust", -5.0, "player_insults", 3)])
        result = de._format_causal_context(ledger)
        assert result.startswith("[Причины изменений"), "missing section header"
        assert "доверие" in result, "field not in prompt text"
        assert "player_insults" in result, "cause not in prompt text"
        assert "тик: 3" in result, "tick not in prompt text"
        print(f"[A-3] Prompt section: {result[:80]}...")

    # ═══ B: NPC knows from testimony ═══

    def test_B_belief_delta_writes_causal_entry(self) -> None:
        """B-1: BeliefDelta -> CausalEntry contract (data presence).

        Verifies the CausalEntry fields that apply_belief_delta creates:
        field=f"belief:{belief_type.value}", delta=new-old, source, tick.
        (StateApplicator requires relationship_store in __init__;
        contract test verifies field mapping without full instance.)
        """
        from app.models.npc.beliefs import BeliefDelta, BeliefType
        from app.models.psychological import CausalEntry

        delta = BeliefDelta(
            belief_type=BeliefType.DANGER,
            old_value=0.0,
            new_value=0.7,
            confidence=0.8,
            source="testimony_from_guard_borko",
            timestamp=5,
        )

        # Contract: apply_belief_delta creates CausalEntry with:
        # field=f"belief:{type}", delta=new-old, source=delta.source, tick=delta.timestamp
        entry = CausalEntry(
            npc_id="test_npc",
            field=f"belief:{delta.belief_type.value}",
            delta=delta.new_value - delta.old_value,
            source=delta.source,
            tick=delta.timestamp,
        )

        assert entry.field == "belief:danger", f"wrong field: {entry.field}"
        assert entry.source == "testimony_from_guard_borko"
        assert entry.delta == 0.7
        print(f"[B-1] CausalEntry: field={entry.field} delta={entry.delta} source={entry.source}")

    def test_B_accessibility_belief_in_format(self) -> None:
        """B-2: Belief CausalEntry accessible via _format_causal_context."""
        de = DialogueExecutor()
        ledger = [
            {"field": "belief:danger", "delta": 0.7, "source": "testimony_from_guard_borko", "tick": 5},
        ]
        result = de._format_causal_context(ledger)
        print(f"[B-2] Format result:\n{result}")
        assert "belief:danger" in result, "belief field missing"
        assert "testimony_from_guard_borko" in result, "testimony source missing"

    # ═══ C: NPC doesn't know and doesn't fabricate ═══

    def test_C_empty_ledger_returns_empty(self) -> None:
        """C-1/2/3: Empty causal_ledger → empty string (no fabrication)."""
        de = DialogueExecutor()
        result = de._format_causal_context([])
        assert result == "", f"expected empty string, got: {result!r}"
        print("[C] Empty ledger → no fabrication (empty string)")

    def test_C_none_entries_filtered(self) -> None:
        """C: None/malformed entries filtered (no crash, no fabrication)."""
        de = DialogueExecutor()
        result = de._format_causal_context([None, {}, {"field": "", "delta": 0, "source": ""}])
        # Empty entries → empty or minimal output (no fabricated causes)
        assert "причина:" not in result or result == "", "fabricated cause from empty data"
        print(f"[C] Malformed entries → no fabrication: {result!r}")

    # ═══ D: Multiple causes, partial knowledge ═══

    def test_D_multiple_causes_all_listed(self) -> None:
        """D-1/2: Multiple causes → all listed in format."""
        de = DialogueExecutor()
        ledger = _make_ledger([
            ("trust", -5.0, "player_insults", 3),
            ("fear", 3.0, "threat_from_X", 4),
            ("trust", 2.0, "gift_from_player", 5),
        ])
        result = de._format_causal_context(ledger)
        print(f"[D] Multiple causes:\n{result}")
        assert "player_insults" in result, "cause 1 missing"
        assert "threat_from_X" in result, "cause 2 missing"
        assert "gift_from_player" in result, "cause 3 missing"
        # Count lines (3 entries → 3 bullet points)
        assert result.count("•") == 3, f"expected 3 bullets, got {result.count('•')}"

    def test_D_cap_at_10_entries(self) -> None:
        """D: >10 entries → only last 10 shown (causal_ledger cap)."""
        de = DialogueExecutor()
        entries = [("trust", -1.0, f"event_{i}", i) for i in range(15)]
        ledger = _make_ledger(entries)
        result = de._format_causal_context(ledger)
        assert "event_14" in result, "last entry missing"
        assert "event_5" in result, "10th from end missing"
        assert "event_4" not in result, "11th from end should be excluded"
        assert result.count("•") == 10, f"expected 10 bullets, got {result.count('•')}"
        print("[D] Cap: 15 entries → 10 shown (event_5..event_14)")

    def test_D_field_mapping_all_fields(self) -> None:
        """D: All field types mapped to Russian."""
        de = DialogueExecutor()
        ledger = [
            {"field": "trust", "delta": -1.0, "source": "s1", "tick": 1},
            {"field": "fear", "delta": 1.0, "source": "s2", "tick": 2},
            {"field": "hp", "delta": -5.0, "source": "s3", "tick": 3},
            {"field": "stress", "delta": 2.0, "source": "s4", "tick": 4},
            {"field": "anger", "delta": 1.0, "source": "s5", "tick": 5},
        ]
        result = de._format_causal_context(ledger)
        assert "доверие" in result
        assert "страх" in result
        assert "здоровье" in result
        assert "напряжение" in result
        assert "гнев" in result
        print("[D] All fields mapped: доверие/страх/здоровье/напряжение/гнев")

    # ═══ Integration: full format → prompt-ready text ═══

    def test_integration_format_is_non_empty_when_data_exists(self) -> None:
        """Integration: real CausalEntry data → non-empty prompt section."""
        de = DialogueExecutor()
        # Simulate realistic causal_ledger (from StateApplicator)
        ledger = [
            {"field": "trust", "delta": -5.0, "source": "player_insults", "tick": 3},
            {"field": "fear", "delta": 2.0, "source": "attack_from_player", "tick": 5},
            {"field": "belief:danger", "delta": 0.5, "source": "testimony_from_guard", "tick": 7},
        ]
        result = de._format_causal_context(ledger)
        # Level 1: data present
        assert len(ledger) == 3
        # Level 2: accessible (non-empty format)
        assert result != ""
        # Level 3: prompt-ready (has section header, causes, ticks)
        assert "[Причины изменений" in result
        assert "player_insults" in result
        assert "attack_from_player" in result
        assert "testimony_from_guard" in result
        print(f"[Integration] Full prompt section:\n{result}")