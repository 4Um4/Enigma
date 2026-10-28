"""DLG-0 Golden Dialogue Corpus (§3.6, DLG-GC-00).

LLM-free, headless, детерминированный корпус для измерения baseline
диалогового понимания существующего pipeline. Не изменяет production-код.

Контракт:
- PASS-кандидаты вызывают реальный PlayerSpeechActSubscriber.on_player_spoke
  или реальный API DialogueSession, затем проверяют фактическое состояние.
- KNOWN-RED сценарии регистрируют известные пробелы без фиктивного PASS.
- Асимметрия PLAYER/NPC [H] (§3.6 DLG-L1) — диагностическая RED для DLG-1.

Границы трека (без дублирования):
- VerbalizationContext (NL-3) — не трогаем.
- PLAYER_ASKS_WHY (NL-5) — не трогаем.
- NL-8 (NEG-28 числа в реплике) — не наш трек; dlg-020 диагностический.

Запуск:
    cd backend
    python -m tests.sandbox.scenarios.dlg0_golden_corpus
    cd ..

Гейт: DLG-GC-00 (§9.3i).
"""
from __future__ import annotations

import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_BACKEND_ROOT))

from app.domain.events import EventDTO
from app.services.events.event_types import EventType
from app.services.events.player_speech_act_subscriber import PlayerSpeechActSubscriber
from app.services.memory.dialogue_session import DialogueSession


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DLGCheck:
    """Результат одной проверки сценария."""
    check_id: str
    applicable: bool       # False → не считается в US (диагностический)
    passed: bool           # если applicable=False → False (не повышает US)
    detail: str = ""


@dataclass(frozen=True)
class DLGScenario:
    """Спецификация сценария корпуса."""
    scenario_id: str
    category: str
    description: str
    ref_3_6: Optional[str]

    speaker: str            # "player" | "npc"
    event_type: str
    semantic_acts: Tuple[Dict[str, Any], ...]
    text: str
    event_id: str
    target_id: Optional[str]

    expected_claims_count: int
    expected_claim_contains: Tuple[str, ...]
    expected_topic: Optional[str]
    expected_open_questions_count: int

    known_red_for: Tuple[str, ...]
    diagnostic_only: bool = False


@dataclass(frozen=True)
class ScenarioResult:
    scenario: DLGScenario
    checks: Tuple[DLGCheck, ...]
    error: Optional[str] = None


@dataclass
class CorpusReport:
    results: Tuple[ScenarioResult, ...]
    us_baseline: Optional[float]
    total_scenarios: int
    scenarios_with_applicable: int
    coverage: float
    total_applicable: int
    total_passed: int
    by_category: Dict[str, Dict[str, int]]
    red_findings: Tuple[Tuple[str, str], ...]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CorpusReport):
            return NotImplemented
        return (
            self.results == other.results
            and self.us_baseline == other.us_baseline
            and self.total_scenarios == other.total_scenarios
            and self.scenarios_with_applicable == other.scenarios_with_applicable
            and self.coverage == other.coverage
            and self.total_applicable == other.total_applicable
            and self.total_passed == other.total_passed
            and self.by_category == other.by_category
            and self.red_findings == other.red_findings
        )


# ── Session memory (прецедент test_player_self_intro_claim.py) ──────────────

class _SessionMemory:
    """MemoryManager-контракт (прецедент d8p-теста SessionMemory)."""

    def __init__(self) -> None:
        self._sessions: Dict[Tuple[str, str, str], DialogueSession] = {}

    def get_dialogue_session(
        self, campaign_id: str, npc_id: str, partner_id: str = "player"
    ) -> DialogueSession:
        key = (campaign_id, npc_id, partner_id)
        if key not in self._sessions:
            self._sessions[key] = DialogueSession(npc_id=npc_id, partner_id=partner_id)
        return self._sessions[key]


# ── Event factory ───────────────────────────────────────────────────────────

def _spoke_event(
    acts: Tuple[Dict[str, Any], ...],
    event_id: str,
    target_id: Optional[str],
    event_type: str,
    source: str,
) -> EventDTO:
    payload: Dict[str, Any] = {"semantic_acts": list(acts)}
    if target_id is not None:
        payload["target_id"] = target_id
    return EventDTO.create(
        event_type=event_type,
        source=source,
        payload=payload,
        event_id=event_id,
    )


# ── Корпус: 20 сценариев ────────────────────────────────────────────────────

CORPUS: Tuple[DLGScenario, ...] = (
    # ── SELF_INTRODUCTION (PASS-candidates) ──────────────────────────────────
    DLGScenario(
        scenario_id="dlg-001", category="self_intro",
        description="SELF_INTRODUCTION → 1 claim; имя доезжает до prompt-block",
        ref_3_6="DLG-L1", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}},),
        text="Меня зовут Мю", event_id="evt-dlg-001",
        target_id="merchant_goran",
        expected_claims_count=1, expected_claim_contains=("Мю", "представился"),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=(),
    ),
    DLGScenario(
        scenario_id="dlg-002", category="self_intro",
        description="Дубль event_id (два вызова с одним event_id) → 1 claim (идемпотентность)",
        ref_3_6="DLG-L1", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}},),
        text="Меня зовут Мю", event_id="evt-dlg-002",
        target_id="merchant_goran",
        expected_claims_count=1, expected_claim_contains=("Мю",),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=(),
    ),
    DLGScenario(
        scenario_id="dlg-003", category="self_intro",
        description="name пустой → skip, 0 claims",
        ref_3_6=None, speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "SELF_INTRODUCTION", "params": {"name": ""}},),
        text="", event_id="evt-dlg-003",
        target_id="merchant_goran",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=(),
    ),
    DLGScenario(
        scenario_id="dlg-004", category="self_intro",
        description="name >64 chars → skip, 0 claims",
        ref_3_6=None, speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "SELF_INTRODUCTION", "params": {"name": "А" * 65}},),
        text="А" * 65, event_id="evt-dlg-004",
        target_id="merchant_goran",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=(),
    ),
    DLGScenario(
        scenario_id="dlg-005", category="self_intro",
        description="target_id=None → claim не пишется (нет адресата)",
        ref_3_6=None, speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}},),
        text="Меня зовут Мю", event_id="evt-dlg-005",
        target_id=None,
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=(),
    ),
    # ── Другие речевые акты — нет consumer (KNOWN-RED DLG-1) ─────────────────
    DLGScenario(
        scenario_id="dlg-006", category="greeting",
        description="PLAYER GREETING → нет consumer, 0 claims (KNOWN-RED DLG-1)",
        ref_3_6="DLG-L1", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "GREETING", "params": {}},),
        text="Привет!", event_id="evt-dlg-006",
        target_id="merchant_goran",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=("DLG-1",),
    ),
    DLGScenario(
        scenario_id="dlg-007", category="question",
        description="PLAYER QUESTION → нет consumer (KNOWN-RED DLG-1)",
        ref_3_6="DLG-L1", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "QUESTION", "params": {"topic": "weather"}},),
        text="Какая погода?", event_id="evt-dlg-007",
        target_id="merchant_goran",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=("DLG-1",),
    ),
    DLGScenario(
        scenario_id="dlg-008", category="assert",
        description="PLAYER ASSERT → нет consumer (KNOWN-RED DLG-1)",
        ref_3_6="DLG-L1", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "ASSERT", "params": {"claim": "Торнин вор"}},),
        text="Торнин вор", event_id="evt-dlg-008",
        target_id="merchant_goran",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=("DLG-1",),
    ),
    DLGScenario(
        scenario_id="dlg-009", category="order",
        description="PLAYER ORDER → нет consumer (KNOWN-RED DLG-1)",
        ref_3_6="DLG-L1", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "ORDER", "params": {}},),
        text="Встань!", event_id="evt-dlg-009",
        target_id="merchant_goran",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=("DLG-1",),
    ),
    # ── Topic detection (API-level: add_turn, НЕ player-pipeline) ───────────
    DLGScenario(
        scenario_id="dlg-010", category="topic",
        description="API: keyword 'борко' в add_turn → topic=guard_borko (механический _detect_topic)",
        ref_3_6=None, speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=(), text="борко", event_id="evt-dlg-010",
        target_id="guard_borko",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic="guard_borko", expected_open_questions_count=0,
        known_red_for=(),
    ),
    DLGScenario(
        scenario_id="dlg-011", category="topic",
        description="API: смена topic через add_turn (last-write-wins)",
        ref_3_6=None, speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=(), text="торнин", event_id="evt-dlg-011",
        target_id="tavern_keeper_tornin",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic="tavern_keeper", expected_open_questions_count=0,
        known_red_for=(),
    ),
    DLGScenario(
        scenario_id="dlg-012", category="topic",
        description="API: topic persistence через 3 turns (без авто-reset)",
        ref_3_6=None, speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=(), text="борко", event_id="evt-dlg-012",
        target_id="guard_borko",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic="guard_borko", expected_open_questions_count=0,
        known_red_for=(),
    ),
    # ── Multi-act (DLG-L1 идемпотентность / DLG-L3 tail loss) ────────────────
    DLGScenario(
        scenario_id="dlg-013", category="multi_act",
        description="Два SELF_INTRO в одном event (один event_id) → 1 claim (дедуп по event_id)",
        ref_3_6="DLG-L1", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=(
            {"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}},
            {"type": "SELF_INTRODUCTION", "params": {"name": "Второе"}},
        ),
        text="Меня зовут Мю", event_id="evt-dlg-013",
        target_id="merchant_goran",
        expected_claims_count=1, expected_claim_contains=("Мю",),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=(),
    ),
    DLGScenario(
        scenario_id="dlg-014", category="composite",
        description="SELF_INTRO+QUESTION → 1 claim, QUESTION потерян (KNOWN-RED DLG-3)",
        ref_3_6="DLG-L3", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=(
            {"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}},
            {"type": "QUESTION", "params": {"topic": "weather"}},
        ),
        text="Меня зовут Мю. Какая погода?", event_id="evt-dlg-014",
        target_id="merchant_goran",
        expected_claims_count=1, expected_claim_contains=("Мю",),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=("DLG-3",),
    ),
    DLGScenario(
        scenario_id="dlg-015", category="composite",
        description="3 акта → 1 claim, 2 потеряны (KNOWN-RED DLG-3)",
        ref_3_6="DLG-L3", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=(
            {"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}},
            {"type": "QUESTION", "params": {"topic": "weather"}},
            {"type": "ASSERT", "params": {"claim": "Торнин вор"}},
        ),
        text="Меня зовут Мю. Какая погода? Торнин вор.", event_id="evt-dlg-015",
        target_id="merchant_goran",
        expected_claims_count=1, expected_claim_contains=("Мю",),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=("DLG-3",),
    ),
    # ── Repeat guard (DLG-L2 — отсутствует) ──────────────────────────────────
    DLGScenario(
        scenario_id="dlg-016", category="repeat_guard",
        description="2× SELF_INTRO (разные event_id, одно имя) → 2 claims, нет guard (KNOWN-RED DLG-2)",
        ref_3_6="DLG-L2", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "SELF_INTRODUCTION", "params": {"name": "Мю"}},),
        text="Меня зовут Мю", event_id="evt-dlg-016",
        target_id="merchant_goran",
        expected_claims_count=2, expected_claim_contains=("Мю",),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=("DLG-2",),
    ),
    DLGScenario(
        scenario_id="dlg-017", category="correction",
        description="«Меня не так зовут» как ASSERT → нет act CORRECTION, 0 claims (KNOWN-RED DLG-2)",
        ref_3_6="DLG-L2", speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=({"type": "ASSERT", "params": {"claim": "меня не так зовут"}},),
        text="Меня не так зовут", event_id="evt-dlg-017",
        target_id="merchant_goran",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=("DLG-2",),
    ),
    # ── Асимметрия PLAYER/NPC [H] (диагностическая, не в US) ─────────────────
    DLGScenario(
        scenario_id="dlg-018", category="asymmetry",
        description="NPC-путь не имеет semantic-act consumer; PLAYER имеет типизированные semantic_acts [H]",
        ref_3_6="DLG-L1 (асимметрия)", speaker="npc",
        event_type=EventType.NPC_SPOKE.value,
        semantic_acts=(), text="Привет", event_id="evt-dlg-018",
        target_id=None,
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=("DLG-1",), diagnostic_only=True,
    ),
    # ── API-level (не из player-pipeline) ────────────────────────────────────
    DLGScenario(
        scenario_id="dlg-019", category="api",
        description="API: DialogueSession.add_open_question работает (API-level, не end-to-end)",
        ref_3_6=None, speaker="player",
        event_type=EventType.PLAYER_SPOKE.value,
        semantic_acts=(), text="", event_id="evt-dlg-019",
        target_id="merchant_goran",
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=1,
        known_red_for=(),
    ),
    # ── NEG-28 (NL-8, не наш трек; диагностический) ──────────────────────────
    DLGScenario(
        scenario_id="dlg-020", category="neg28",
        description="NPC-реплика с числами — NEG-28 (NL-8, вне трека DLG; диагностический)",
        ref_3_6=None, speaker="npc",
        event_type=EventType.NPC_SPOKE.value,
        semantic_acts=(), text="Мне 25 лет", event_id="evt-dlg-020",
        target_id=None,
        expected_claims_count=0, expected_claim_contains=(),
        expected_topic=None, expected_open_questions_count=0,
        known_red_for=("NL-8",), diagnostic_only=True,
    ),
)


# ── Исполнение сценария ─────────────────────────────────────────────────────

def _run_scenario(scenario: DLGScenario) -> ScenarioResult:
    """Выполняет сценарий против реального pipeline; без подмены результатов."""
    checks: List[DLGCheck] = []
    error: Optional[str] = None

    actual_claims_count = 0
    actual_claim_text = ""
    actual_topic: Optional[str] = None
    actual_open_q_count = 0

    try:
        mem = _SessionMemory()
        campaign_id = "DLG_TEST"
        npc_id = scenario.target_id or "merchant_goran"

        if scenario.category in ("asymmetry", "neg28"):
            # Diagnostic only — нет реального исполнения (наблюдение структурное)
            pass
        elif scenario.category == "topic":
            # API-level: add_turn напрямую (НЕ через player-pipeline)
            session = mem.get_dialogue_session(campaign_id, npc_id, partner_id="player")
            if scenario.scenario_id == "dlg-012":
                session.add_turn(speaker="player", text="борко", tick=1)
                session.add_turn(speaker="player", text="и ещё борко", tick=2)
                session.add_turn(speaker="player", text="нейтральный текст", tick=3)
            else:
                session.add_turn(speaker="player", text=scenario.text, tick=1)
            actual_topic = session.topic
            actual_claims_count = len(session.claims)
            actual_open_q_count = len(session.open_questions)
        elif scenario.category == "api":
            # API-level: add_open_question напрямую
            session = mem.get_dialogue_session(campaign_id, npc_id, partner_id="player")
            session.add_open_question(
                text="кто ты?", asked_by="player",
                addressed_to=npc_id, tick=1,
            )
            actual_topic = session.topic
            actual_claims_count = len(session.claims)
            actual_open_q_count = len(session.open_questions)
        else:
            # player-pipeline: реальный PlayerSpeechActSubscriber
            event = _spoke_event(
                acts=scenario.semantic_acts,
                event_id=scenario.event_id,
                target_id=scenario.target_id,
                event_type=scenario.event_type,
                source="player",
            )
            sub = PlayerSpeechActSubscriber(
                memory_manager=mem,
                campaign_id_provider=lambda: campaign_id,
                tick_provider=lambda: 1,
            )
            if scenario.scenario_id == "dlg-002":
                # Дубль event_id: два вызова с одним event_id → 1 claim (идемпотентность)
                sub.on_player_spoke(event)
                sub.on_player_spoke(event)
            elif scenario.scenario_id == "dlg-016":
                # Два SELF_INTRO с разными event_id → 2 claims (нет guard)
                sub.on_player_spoke(event)
                event2 = _spoke_event(
                    acts=scenario.semantic_acts,
                    event_id=scenario.event_id + "-r2",
                    target_id=scenario.target_id,
                    event_type=scenario.event_type,
                    source="player",
                )
                sub.on_player_spoke(event2)
            else:
                sub.on_player_spoke(event)
            session = mem.get_dialogue_session(campaign_id, npc_id, partner_id="player")
            actual_claims_count = len(session.claims)
            actual_claim_text = session.claims[0].text if session.claims else ""
            actual_topic = session.topic
            actual_open_q_count = len(session.open_questions)

        # ── Сравнение с ожиданиями ────────────────────────────────────────────
        if not scenario.diagnostic_only:
            checks.append(DLGCheck(
                check_id=f"{scenario.scenario_id}.claims_count",
                applicable=True,
                passed=actual_claims_count == scenario.expected_claims_count,
                detail=f"expected={scenario.expected_claims_count}, actual={actual_claims_count}",
            ))
            if scenario.expected_claim_contains:
                all_in = all(s in actual_claim_text for s in scenario.expected_claim_contains)
                checks.append(DLGCheck(
                    check_id=f"{scenario.scenario_id}.claim_text",
                    applicable=True,
                    passed=all_in,
                    detail=f"actual_claim='{actual_claim_text[:80]}'",
                ))
            if scenario.expected_topic is not None:
                checks.append(DLGCheck(
                    check_id=f"{scenario.scenario_id}.topic",
                    applicable=True,
                    passed=actual_topic == scenario.expected_topic,
                    detail=f"expected={scenario.expected_topic}, actual={actual_topic}",
                ))
            if scenario.expected_open_questions_count > 0:
                checks.append(DLGCheck(
                    check_id=f"{scenario.scenario_id}.open_questions",
                    applicable=True,
                    passed=actual_open_q_count == scenario.expected_open_questions_count,
                    detail=f"expected={scenario.expected_open_questions_count}, actual={actual_open_q_count}",
                ))
        else:
            checks.append(DLGCheck(
                check_id=f"{scenario.scenario_id}.diagnostic",
                applicable=False,
                passed=False,
                detail=f"diagnostic observation: {scenario.description}",
            ))

    except Exception as e:
        error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    return ScenarioResult(scenario=scenario, checks=tuple(checks), error=error)


# ── Скорер ──────────────────────────────────────────────────────────────────

def run_corpus() -> CorpusReport:
    """Запуск корпуса; детерминирован (без RNG, без LLM)."""
    results: List[ScenarioResult] = []
    for scenario in CORPUS:
        results.append(_run_scenario(scenario))

    total_applicable = 0
    total_passed = 0
    by_category: Dict[str, Dict[str, int]] = {}
    red_findings: List[Tuple[str, str]] = []

    for r in results:
        cat = r.scenario.category
        if cat not in by_category:
            by_category[cat] = {"applicable": 0, "passed": 0, "total": 0}
        by_category[cat]["total"] += 1

        for chk in r.checks:
            if chk.applicable:
                total_applicable += 1
                by_category[cat]["applicable"] += 1
                if chk.passed:
                    total_passed += 1
                    by_category[cat]["passed"] += 1

        if r.scenario.known_red_for:
            reason = f"KNOWN-RED для {','.join(r.scenario.known_red_for)}"
            if r.scenario.diagnostic_only:
                reason += " (diagnostic-only)"
            red_findings.append((r.scenario.scenario_id, reason))
        if r.error:
            red_findings.append((r.scenario.scenario_id, f"ERROR: {r.error.splitlines()[0]}"))

    scenarios_with_applicable = sum(
        1 for r in results if any(c.applicable for c in r.checks)
    )
    total_scenarios = len(results)
    coverage = (scenarios_with_applicable / total_scenarios * 100) if total_scenarios else 0.0
    us_baseline = (total_passed / total_applicable * 100) if total_applicable > 0 else None

    return CorpusReport(
        results=tuple(results),
        us_baseline=us_baseline,
        total_scenarios=total_scenarios,
        scenarios_with_applicable=scenarios_with_applicable,
        coverage=coverage,
        total_applicable=total_applicable,
        total_passed=total_passed,
        by_category=dict(by_category),
        red_findings=tuple(red_findings),
    )


def format_report(report: CorpusReport) -> str:
    """Human-readable отчёт."""
    lines = [
        "=" * 70,
        "DLG-0 Golden Dialogue Corpus Report",
        "=" * 70,
        "",
        f"Total scenarios:           {report.total_scenarios}",
        f"Scenarios w/ applicable:    {report.scenarios_with_applicable}",
        f"Coverage:                   {report.coverage:.1f}%",
        f"Applicable checks:          {report.total_applicable}",
        f"Passed checks:              {report.total_passed}",
    ]
    if report.us_baseline is not None:
        lines.append(f"US-baseline:                 {report.us_baseline:.1f}/100")
    else:
        lines.append("US-baseline:                 N/A (zero applicable — config error)")
    lines += ["", "By category:"]
    for cat in sorted(report.by_category.keys()):
        s = report.by_category[cat]
        lines.append(
            f"  {cat:15s} total={s['total']:2d}  applicable={s['applicable']:2d}  passed={s['passed']:2d}"
        )
    lines += ["", f"KNOWN-RED findings ({len(report.red_findings)}):"]
    for sid, reason in report.red_findings:
        lines.append(f"  [{sid}] {reason}")
    lines += ["", "Per-scenario detail:"]
    for r in report.results:
        lines.append(f"  {r.scenario.scenario_id} [{r.scenario.category}] {r.scenario.description}")
        if r.error:
            lines.append(f"    ERROR: {r.error.splitlines()[0]}")
        for chk in r.checks:
            mark = "+" if (chk.applicable and chk.passed) else ("x" if chk.applicable else ".")
            lines.append(f"    {mark} {chk.check_id}: {chk.detail}")
    lines.append("=" * 70)
    return "\n".join(lines)


def main() -> None:
    report = run_corpus()
    print(format_report(report))


if __name__ == "__main__":
    main()