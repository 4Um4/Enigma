"""
path: diagnostics/dna_metrics.py
Назначение: Вычисляет DNA-метрики проекта ENIGMA из данных текущей и прошлых сессий.
            Все метрики вычисляются автоматически — без участия человека.
            Результат пишется в reports/dna_history.jsonl и вставляется в LAST_SESSION.md.

Метрики:
    SHI  — Simulation Health Index:     % тиков с decisions > 0
    NPI  — NPC Pipeline Integrity:      % NPC достигших финальных координат (не None, не 0,0)
    OBI  — Obedience Breakthrough Index: % директив где ObediencePressure > 0
    SCF  — Spatial Coherence Factor:    целостность пространства (0.0 / 0.5 / 1.0)
    ADR  — Architecture Debt Ratio:     TODO_count / ADR_count (рост = долг накапливается)
    CVS  — Causal Velocity Score:       LLM-вызовов в минуту сессии

Зависимости: diagnostics.health_checkers.tick_health,
             diagnostics.health_checkers.movement_health
Основные сущности: DNAMetrics, DNASnapshot, DNAComputer
"""

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from diagnostics.health_checkers.movement_health import MovementHealthReport
from diagnostics.health_checkers.tick_health import TickHealthReport


@dataclass
class DNASnapshot:
    """Снимок DNA-метрик одной сессии — пишется в dna_history.jsonl."""

    timestamp: str  # ISO-формат
    session_minutes: float  # длительность сессии

    # --- Simulation ---
    SHI: float  # Simulation Health Index 0–100
    NPI: float  # NPC Pipeline Integrity 0–100
    OBI: float  # Obedience Breakthrough Index 0–100

    # --- Architecture ---
    SCF: float  # Spatial Coherence Factor 0.0 / 0.5 / 1.0
    ADR: float  # Architecture Debt Ratio (TODO/ADR_count)
    CVS: float  # Causal Velocity Score (llm_calls/min)

    # --- Raw counts для воспроизводимости ---
    total_ticks: int
    decisions_nonzero: int
    npc_total: int
    npc_with_real_coords: int
    directive_events: int
    obedience_nonzero: int
    todo_count: int
    adr_count: int
    llm_calls: int
    llm_pool_fails: int = 0  # Провалы пула моделей
    # Инвариант 3: пред-шинные отказы
    prebus_failures: int = (
        0  # pipeline_critical + causality_crash + phase8_crash + tick_orch_error
    )
    # --- New DNA Metrics (Tracebacks, Beliefs, Breaks, Needs) ---
    total_tracebacks: int = 0
    attribute_errors: int = 0
    type_errors: int = 0
    finalize_errors: int = 0
    beliefs_crystallized: int = 0
    BCI: float = 0.0  # Belief Crystallization Index = beliefs / total_ticks
    break_progress_events: int = 0
    will_broken_transitions: int = 0
    BPI: float = 0.0  # Break Progress Index = events / total_npc_ticks
    need_urgent_events: int = 0
    need_critical_events: int = 0
    NEI: float = 0.0  # Need Urgency Index
    affect_decay_fails: int = 0  # affect_decay_fail count
    invariant_violations: int = 0  # Количество CRITICAL нарушений инвариантов
    invariant_warning_count: int = 0  # Количество WARNING нарушений инвариантов
    llm_pool_fails: int = 0  # Провалы пула моделей LLM
    DRI: float = 100.0  # Direct Response Integrity (100% - fail_rate)
    failed_dialogues: int = 0  # Провалы исполнения диалогов
    DPI: float = 100.0  # Dialogue Pipeline Integrity (100% - fail_rate)


@dataclass
class DNADelta:
    """Дельта между текущей и предыдущей сессией."""

    SHI: Optional[float] = None
    NPI: Optional[float] = None
    OBI: Optional[float] = None
    SCF: Optional[float] = None
    ADR: Optional[float] = None
    CVS: Optional[float] = None
    DRI: Optional[float] = None  # Direct Response Integrity
    DPI: Optional[float] = None  # Dialogue Pipeline Integrity
    PFI: Optional[float] = None  # Инвариант 3: Pre-Bus Failure Index
    INV_V: Optional[int] = None  # Invariant Violations (CRITICAL)
    INV_W: Optional[int] = None  # Invariant Warnings

    def format_field(self, name: str) -> str:
        """Форматирует одно поле дельты для LLM-отчёта."""
        v = getattr(self, name)
        if v is None:
            return "первая сессия"
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.1f}"

    def trend_icon(self, name: str, higher_is_better: bool = True) -> str:
        """Иконка тренда: ↑↓→ в зависимости от знака и направления."""
        v = getattr(self, name)
        if v is None:
            return "•"
        if abs(v) < 0.5:
            return "→"
        positive = v > 0
        return "↑" if positive == higher_is_better else "↓"


class DNAComputer:
    """
    Вычисляет DNA-метрики из данных health-checker-ов и файловой системы.
    Читает историю из dna_history.jsonl для вычисления дельт.
    """

    def __init__(
        self,
        tick_report: TickHealthReport,
        movement_report: MovementHealthReport,
        started_at: datetime,
        invariant_violations: Optional[list] = None,
        project_root: Optional[str] = None,
    ) -> None:
        self._tick = tick_report
        self._movement = movement_report
        self._started_at = started_at
        self._invariant_violations = invariant_violations or []
        self._root = (
            Path(project_root) if project_root else Path(__file__).parent.parent
        )
        self._history_path = self._root / "reports" / "dna_history.jsonl"

        # Накопленные данные директив (заполняются через on_* методы)
        self._directive_events: int = 0
        self._obedience_nonzero: int = 0

    # ------------------------------------------------------------------
    # Точки входа от CausalObserver (вызываются при парсинге лога)
    # ------------------------------------------------------------------

    def on_directive(self, obedience_pressure: float) -> None:
        """Вызывается при каждом [DIRECTIVE_INTERPRET]."""
        self._directive_events += 1
        if obedience_pressure > 0.0:
            self._obedience_nonzero += 1

    # ------------------------------------------------------------------
    # Вычисление снимка
    # ------------------------------------------------------------------

    def compute(self) -> DNASnapshot:
        """Вычисляет все метрики и возвращает DNASnapshot."""
        session_minutes = max(
            (datetime.now() - self._started_at).total_seconds() / 60.0,
            0.1,  # защита от деления на ноль при очень коротких сессиях
        )

        shi = self._compute_shi()
        npi, npc_total, npc_real = self._compute_npi()
        obi = self._compute_obi()
        scf = self._compute_scf()
        adr_val, todo_count, adr_count = self._compute_adr()
        cvs = self._compute_cvs(session_minutes)

        # Инвариант 3: Подсчёт пред-шинных отказов
        _prebus = (
            self._tick.pipeline_critical_count
            + self._tick.causality_crash_count
            + self._tick.phase8_crash_count
            + self._tick.tick_orch_error_count
        )

        # INV-DEF: Подсчёт нарушений инвариантов
        _inv_violations = sum(
            1 for v in self._invariant_violations if v.severity == "CRITICAL"
        )
        _inv_warnings = sum(
            1 for v in self._invariant_violations if v.severity == "WARNING"
        )

        # NEW DNA Metrics calculation
        _ticks = self._tick.total_ticks
        if _ticks > 0:
            _bci = round(self._tick.beliefs_crystallized / _ticks, 2)
            _bpi = round(self._tick.break_progress_events / _ticks, 2)
            _nei = round(self._tick.need_urgent_events / _ticks, 2)
        else:
            _bci = 0.0
            _bpi = 0.0
            _nei = 0.0

        return DNASnapshot(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            session_minutes=round(session_minutes, 1),
            SHI=shi,
            NPI=npi,
            OBI=obi,
            SCF=scf,
            ADR=adr_val,
            CVS=cvs,
            total_ticks=self._tick.total_ticks,
            decisions_nonzero=self._tick.decisions_nonzero_ticks,
            total_tracebacks=self._tick.total_tracebacks,
            attribute_errors=self._tick.attribute_errors,
            type_errors=self._tick.type_errors,
            finalize_errors=self._tick.finalize_errors,
            beliefs_crystallized=self._tick.beliefs_crystallized,
            BCI=_bci,
            break_progress_events=self._tick.break_progress_events,
            will_broken_transitions=self._tick.will_broken_transitions,
            BPI=_bpi,
            need_urgent_events=self._tick.need_urgent_events,
            need_critical_events=self._tick.need_critical_events,
            NEI=_nei,
            npc_total=npc_total,
            npc_with_real_coords=npc_real,
            directive_events=self._directive_events,
            obedience_nonzero=self._obedience_nonzero,
            todo_count=todo_count,
            adr_count=adr_count,
            llm_calls=self._tick.llm_calls,
            # Инвариант 3: Наблюдаемость отказа
            prebus_failures=_prebus,
            affect_decay_fails=self._tick.affect_decay_fail_count,
            # INV-DEF: Invariant Defense System метрики
            invariant_violations=_inv_violations,
            invariant_warning_count=_inv_warnings,
            llm_pool_fails=self._tick.llm_pool_fail_count,
            DRI=self._compute_dri(),
            failed_dialogues=self._tick.failed_dialogues,
            DPI=self._compute_dpi(),
        )

    def _compute_shi(self) -> float:
        """SHI = total_decisions / total_ticks * 100 (capped at 100).
        Основан на реальных решениях NPC ([DECISION_HUB]/[DECISION_SCORE]),
        а не на [R3_DIRECT] который может показывать 0 даже при работающих NPC."""
        if self._tick.total_ticks == 0:
            return 0.0
        if self._tick.total_decisions == 0:
            return 0.0
        return round(
            min(self._tick.total_decisions / self._tick.total_ticks * 100, 100.0), 1
        )

    def _compute_npi(self) -> tuple[float, int, int]:
        """
        NPI = npc_with_real_coords / total_npc * 100.
        'Реальные координаты' = не None И не (0.0, 0.0) — нулёвка означает не-инициализированные.
        """
        npcs = self._movement.npcs
        if not npcs:
            return 0.0, 0, 0
        total = len(npcs)
        real = sum(
            1
            for s in npcs.values()
            if s.coord_x is not None and (s.coord_x != 0.0 or s.coord_y != 0.0)
        )
        return round(real / total * 100, 1), total, real

    def _compute_obi(self) -> float:
        """OBI = obedience_nonzero / directive_events * 100."""
        if self._directive_events == 0:
            return 0.0
        return round(self._obedience_nonzero / self._directive_events * 100, 1)

    def _compute_scf(self) -> float:
        """
        SCF — ступенчатая оценка пространственной целостности:
        1.0 = editor JSON найден И нет node_not_found (пространство целостно)
        0.5 = spatial_fallback но editor JSON найден (legacy fallback некритичен)
        0.3 = spatial_fallback без editor JSON (пространство деградировано)
        0.0 = есть node_not_found (пространство разрушено)
        """
        if self._movement.total_node_not_found > 0:
            return 0.0
        if self._movement.spatial_fallback_triggered:
            # Если editor JSON найден — fallback location_templates.json некритичен
            if self._movement.editor_json_locations:
                return 1.0
            return 0.3
        return 1.0

    def _compute_adr(self) -> tuple[float, int, int]:
        """
        ADR = todo_count / adr_count.
        todo_count — через PowerShell Select-String.
        adr_count — через grep "^### ADR-" в ADR.md.
        """
        todo_count = self._count_todos()
        adr_count = self._count_adrs()
        if adr_count == 0:
            return 0.0, todo_count, adr_count
        return round(todo_count / adr_count, 2), todo_count, adr_count

    def _compute_cvs(self, session_minutes: float) -> float:
        """CVS = llm_calls / session_minutes."""
        return round(self._tick.llm_calls / session_minutes, 2)

    def _compute_dri(self) -> float:
        """DRI = 100 - (llm_pool_fails / llm_calls * 100).
        Если вызовов не было — 100% (проблем нет).
        """
        if self._tick.llm_calls == 0:
            return 100.0
        fail_rate = (self._tick.llm_pool_fail_count / self._tick.llm_calls) * 100
        return round(max(0.0, 100.0 - fail_rate), 1)

    def _compute_dpi(self) -> float:
        """DPI = 100 - (failed_dialogues / total_decisions * 100).
        Если решений не было — 100%.
        """
        total_decisions = self._tick.total_decisions
        if total_decisions == 0:
            return 100.0
        fail_rate = (self._tick.failed_dialogues / total_decisions) * 100
        return round(max(0.0, 100.0 - fail_rate), 1)

    # ------------------------------------------------------------------
    # Вспомогательные счётчики файловой системы
    # ------------------------------------------------------------------

    def _count_todos(self) -> int:
        """Считает TODO/FIXME/HACK. PowerShell на Windows, grep на Linux/macOS."""
        import sys
        # Попытка 1: PowerShell (Windows)
        if sys.platform == "win32":
            try:
                result = subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        "Get-ChildItem -Path 'backend/app/','frontend/' -Filter '*.py' -Recurse "
                        "| Select-String -Pattern 'TODO|FIXME|HACK' "
                        "| Measure-Object | Select-Object -ExpandProperty Count",
                    ],
                    cwd=str(self._root),
                    capture_output=True,
                    text=True,
                    timeout=15,
                    encoding="utf-8",
                    errors="replace",
                )
                if result.returncode == 0:
                    return int(result.stdout.strip())
            except Exception:
                pass

        # Попытка 2: grep (Linux/macOS)
        try:
            result = subprocess.run(
                ["grep", "-rE", "TODO|FIXME|HACK", "backend/app/", "frontend/", "--include=*.py"],
                cwd=str(self._root), capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                return len(result.stdout.splitlines())
        except Exception:
            pass

        return -1  # -1 означает "не удалось посчитать"

    def _count_adrs(self) -> int:
        """Считает ADR-записи через grep по файлу."""
        try:
            adr_file = (
                self._root / "docs" / "Tasks" / "ADR (Architecture Decision Records).md"
            )
            if not adr_file.exists():
                return 0
            text = adr_file.read_text(encoding="utf-8", errors="replace")
            return sum(1 for line in text.splitlines() if line.startswith("### ADR-"))
        except Exception:
            return 0

    # ------------------------------------------------------------------
    # История и дельта
    # ------------------------------------------------------------------

    def save(self, snapshot: DNASnapshot) -> None:
        """Дописывает снимок в dna_history.jsonl."""
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(snapshot), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def load_previous(self) -> Optional[DNASnapshot]:
        """Читает предпоследнюю запись из dna_history.jsonl (не текущую)."""
        try:
            if not self._history_path.exists():
                return None
            lines = [
                l.strip()
                for l in self._history_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if l.strip()
            ]
            # Берём предпоследнюю — последняя только что записана
            if len(lines) < 2:
                return None
            data = json.loads(lines[-2])
            return DNASnapshot(**data)
        except Exception:
            return None

    def compute_delta(
        self, current: DNASnapshot, previous: Optional[DNASnapshot]
    ) -> DNADelta:
        """Вычисляет разницу метрик между текущей и предыдущей сессией."""
        if previous is None:
            return DNADelta()
        # Инвариант 3: PFI delta
        _pfi_curr = current.prebus_failures / max(current.total_ticks, 1) * 100
        _pfi_prev = previous.prebus_failures / max(previous.total_ticks, 1) * 100
        
        _dri_curr = getattr(current, "DRI", 100.0) or 100.0
        _dri_prev = getattr(previous, "DRI", 100.0) or 100.0
        
        _dpi_curr = getattr(current, "DPI", 100.0) or 100.0
        _dpi_prev = getattr(previous, "DPI", 100.0) or 100.0

        return DNADelta(
            SHI=round(current.SHI - previous.SHI, 1),
            NPI=round(current.NPI - previous.NPI, 1),
            OBI=round(current.OBI - previous.OBI, 1),
            SCF=round(current.SCF - previous.SCF, 1),
            ADR=round(current.ADR - previous.ADR, 2),
            CVS=round(current.CVS - previous.CVS, 2),
            PFI=round(_pfi_curr - _pfi_prev, 1),
            DRI=round(_dri_curr - _dri_prev, 1),
            DPI=round(_dpi_curr - _dpi_prev, 1),
        )

    # ------------------------------------------------------------------
    # Рендер секции для LAST_SESSION.md
    # ------------------------------------------------------------------

    def render_section(self, snapshot: DNASnapshot, delta: DNADelta) -> str:
        """
        Рендерит секцию DNA для вставки в LAST_SESSION.md.
        Формат оптимизирован для LLM: факты, дельты, интерпретация.
        """
        lines = [
            "## DNA — МЕТРИКИ ЗДОРОВЬЯ СИСТЕМЫ",
            "",
            f"_Сессия: {snapshot.session_minutes} мин | "
            f"Тиков: {snapshot.total_ticks} | "
            f"LLM-вызовов: {snapshot.llm_calls}_",
            "",
            "| Метрика | Значение | Δ от прошлой | Интерпретация для LLM |",
            "|---------|----------|--------------|----------------------|",
        ]

        # SHI
        shi_icon = delta.trend_icon("SHI", higher_is_better=True)
        shi_interpret = self._interpret_shi(snapshot.SHI)
        lines.append(
            f"| **SHI** (Simulation Health) | {snapshot.SHI:.0f}% | "
            f"{shi_icon} {delta.format_field('SHI')}% | {shi_interpret} |"
        )

        # NPI
        npi_icon = delta.trend_icon("NPI", higher_is_better=True)
        npi_interpret = self._interpret_npi(
            snapshot.NPI, snapshot.npc_with_real_coords, snapshot.npc_total
        )
        lines.append(
            f"| **NPI** (NPC Pipeline) | {snapshot.NPI:.0f}% | "
            f"{npi_icon} {delta.format_field('NPI')}% | {npi_interpret} |"
        )

        # OBI
        obi_icon = delta.trend_icon("OBI", higher_is_better=True)
        obi_interpret = self._interpret_obi(snapshot.OBI, snapshot.directive_events)
        lines.append(
            f"| **OBI** (Obedience) | {snapshot.OBI:.0f}% | "
            f"{obi_icon} {delta.format_field('OBI')}% | {obi_interpret} |"
        )

        # SCF
        scf_icon = delta.trend_icon("SCF", higher_is_better=True)
        scf_interpret = self._interpret_scf(snapshot.SCF)
        lines.append(
            f"| **SCF** (Spatial Coherence) | {snapshot.SCF:.1f} | "
            f"{scf_icon} {delta.format_field('SCF')} | {scf_interpret} |"
        )

        # ADR
        adr_icon = delta.trend_icon("ADR", higher_is_better=False)
        adr_interpret = self._interpret_adr(
            snapshot.ADR, snapshot.todo_count, snapshot.adr_count
        )
        lines.append(
            f"| **ADR** (Debt Ratio) | {snapshot.ADR:.2f} | "
            f"{adr_icon} {delta.format_field('ADR')} | {adr_interpret} |"
        )

        # CVS
        cvs_icon = delta.trend_icon("CVS", higher_is_better=True)
        cvs_interpret = self._interpret_cvs(snapshot.CVS)
        lines.append(
            f"| **CVS** (Causal Velocity) | {snapshot.CVS:.2f}/мин | "
            f"{cvs_icon} {delta.format_field('CVS')} | {cvs_interpret} |"
        )

        # Инвариант 3: PFI — Pre-Bus Failure Index
        _pfi_val = snapshot.prebus_failures / max(snapshot.total_ticks, 1) * 100
        pfi_icon = delta.trend_icon("PFI", higher_is_better=False)
        pfi_interpret = self._interpret_pfi(
            _pfi_val, snapshot.prebus_failures, snapshot.affect_decay_fails
        )
        lines.append(
            f"| **PFI** (Pre-Bus Failure) | {_pfi_val:.0f}% | "
            f"{pfi_icon} {delta.format_field('PFI')}% | {pfi_interpret} |"
        )

        # --- New DNA Metrics: Tracebacks, Beliefs, Breaks, Needs ---
        _tb_interpret = "✅ норма" if snapshot.total_tracebacks == 0 else "⚠️ КРИТИЧНО: невидимые регрессии (Tracebacks)"
        lines.append(
            f"| **Tracebacks** | {snapshot.total_tracebacks} (AttrErr={snapshot.attribute_errors}, TypeErr={snapshot.type_errors}) | → | {_tb_interpret} |"
        )
        
        _bci_interpret = "✅ Убеждения формируются" if snapshot.BCI > 0 else "⚠️ Память не кристаллизуется (BCI=0)"
        lines.append(
            f"| **BCI** (Belief Crystallization) | {snapshot.beliefs_crystallized} (idx={snapshot.BCI:.2f}) | → | {_bci_interpret} |"
        )
        
        _bpi_interpret = "✅ Давление доходит" if snapshot.BPI > 0 else "⚠️ NPC не ломаются (BPI=0)"
        lines.append(
            f"| **BPI** (Break Progress) | {snapshot.break_progress_events} (broken={snapshot.will_broken_transitions}) | → | {_bpi_interpret} |"
        )
        
        _nei_interpret = "✅ NPC нуждаются" if snapshot.NEI > 0 else "⚠️ NPC слишком комфортны (NEI=0)"
        lines.append(
            f"| **NEI** (Need Urgency) | {snapshot.need_urgent_events} (critical={snapshot.need_critical_events}) | → | {_nei_interpret} |"
        )

        # DRI: Direct Response Integrity
        dri_icon = delta.trend_icon("DRI", higher_is_better=True)
        dri_interpret = self._interpret_dri(snapshot.DRI, snapshot.llm_pool_fails)
        lines.append(
            f"| **DRI** (Response Integrity) | {snapshot.DRI:.0f}% | "
            f"{dri_icon} {delta.format_field('DRI')}% | {dri_interpret} |"
        )

        # DPI: Dialogue Pipeline Integrity
        dpi_icon = delta.trend_icon("DPI", higher_is_better=True)
        dpi_interpret = self._interpret_dpi(snapshot.DPI, snapshot.failed_dialogues)
        lines.append(
            f"| **DPI** (Dialogue Pipeline) | {snapshot.DPI:.0f}% | "
            f"{dpi_icon} {delta.format_field('DPI')}% | {dpi_interpret} |"
        )

        # Системные предупреждения для LLM
        warnings = self._generate_warnings(snapshot, delta)
        if warnings:
            lines.append("")
            lines.append("**Системные сигналы (требуют внимания):**")
            for w in warnings:
                lines.append(f"- {w}")

        lines.append("")
        lines.append(
            f"_История: `reports/dna_history.jsonl` — {self._count_history_entries()} записей_"
        )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Интерпретации для LLM
    # ------------------------------------------------------------------

    def _interpret_shi(self, v: float) -> str:
        if v == 0:
            return "⛔ МЕРТВА: решений нет. Проверь DecisionHub.compute()"
        if v < 20:
            return "⚠️ критически низко: NPC почти не реагируют на события"
        if v < 50:
            return "⚠️ ниже нормы: часть NPC игнорирует события"
        return "✅ норма: NPC активно принимают решения"

    def _interpret_npi(self, v: float, real: int, total: int) -> str:
        if total == 0:
            return "нет данных о NPC"
        if v == 0:
            return f"⛔ 0/{total} NPC имеют координаты: traversal полностью сломан"
        if v < 50:
            return (
                f"⚠️ {real}/{total} NPC с координатами: spatial pipeline частично сломан"
            )
        if v < 100:
            return f"⚠️ {real}/{total} NPC с координатами: есть потери в traversal"
        return f"✅ {real}/{total} NPC с реальными координатами"

    def _interpret_obi(self, v: float, events: int) -> str:
        if events == 0:
            return "нет директив в сессии — OBI не применим"
        if v == 0:
            return (
                "⛔ 0% обработки: ObediencePressure всегда 0 → Legitimacy Gate мертва"
            )
        if v < 30:
            return f"⚠️ {v:.0f}% директив прошли: слабый отклик NPC на приказы"
        return f"✅ {v:.0f}% директив с ненулевым давлением"

    def _interpret_scf(self, v: float) -> str:
        if v == 0.0:
            return "⛔ РАЗРУШЕНО: узлы не найдены → NPC не могут двигаться"
        if v == 0.5:
            return "⚠️ ДЕГРАДАЦИЯ: location_templates fallback активен"
        return "✅ пространство целостно: граф загружен корректно"

    def _interpret_pfi(self, v: float, prebus: int, decay_fails: int) -> str:
        """Инвариант 3: Интерпретация Pre-Bus Failure Index."""
        if prebus == 0 and decay_fails == 0:
            return "✅ норма: пред-шинных отказов нет — CDS видит всё"
        if prebus == 0:
            return f"⚠️ {decay_fails} сбоев affective decay — эмоции могут застревать"
        if v < 20:
            return f"⚠️ {prebus} пред-шинных отказов — CDS слеп к части крахов"
        return f"⛔ {prebus} пред-шинных отказов — pipeline молча умирает, CDS слеп"

    def _interpret_adr(self, v: float, todo: int, adr: int) -> str:
        if adr == 0:
            return "нет ADR-записей — невозможно оценить"
        if v > 3.0:
            return (
                f"⛔ {todo} TODO / {adr} ADR = долг накапливается быстрее документации"
            )
        if v > 2.0:
            return f"⚠️ {todo} TODO / {adr} ADR = умеренный архитектурный долг"
        return f"✅ {todo} TODO / {adr} ADR = долг под контролем"

    def _interpret_dri(self, v: float, fails: int) -> str:
        if v < 50:
            return f"🔴 КРИТИЧНО: LLM не отвечает на {100-v:.0f}% запросов ({fails} провалов)"
        if v < 90:
            return f"⚠️ Деградация: {fails} провалов LLM. Ответы нестабильны"
        return "✅ LLM отвечает на все запросы"

    def _interpret_dpi(self, v: float, fails: int) -> str:
        if v < 50:
            return f"🔴 КРИТИЧНО: {fails} диалогов упали в TaskScheduler"
        if v < 90:
            return f"⚠️ Деградация: {fails} диалогов не исполнены"
        return "✅ Конвейер диалогов стабилен"

    def _interpret_cvs(self, v: float) -> str:
        if v == 0:
            return "LLM не вызывалась: сессия без действий игрока"
        if v < 0.5:
            return f"⚠️ {v:.2f}/мин: редкие взаимодействия или медленный LLM"
        return f"✅ {v:.2f}/мин: активная сессия"

    def _generate_warnings(self, snap: DNASnapshot, delta: DNADelta) -> list:
        """Генерирует список предупреждений для LLM на основе паттернов."""
        warnings = []

        # ADR растёт — долг накапливается
        if delta.ADR is not None and delta.ADR > 0.5:
            warnings.append(
                f"ADR вырос на {delta.ADR:+.2f}: TODO добавляются быстрее чем закрываются ADR"
            )

        # NPI упал — traversal деградировал
        if delta.NPI is not None and delta.NPI < -20:
            warnings.append(
                f"NPI упал на {delta.NPI:.0f}%: spatial pipeline деградировал между сессиями"
            )

        # SCF упал с 1.0 до 0.0 — критическая регрессия пространства
        if delta.SCF is not None and delta.SCF < -0.4:
            warnings.append(
                "SCF упал с 1.0 до 0.0: spatial fallback + node_not_found = регрессия spatial слоя"
            )

        # SHI низкий при ненулевых LLM-вызовах
        if snap.SHI < 10 and snap.llm_calls > 0:
            warnings.append(
                "SHI=0% при активных LLM-вызовах: игрок взаимодействует но NPC не решают — "
                "разрыв между R3_DIRECT и DecisionHub"
            )

        # OBI=0% при наличии директив — Legitimacy Gate сломана
        if snap.OBI == 0.0 and snap.directive_events > 0:
            warnings.append(
                f"OBI=0% при {snap.directive_events} директивах: "
                "ObediencePressure всегда 0 → проверь DirectiveInterpretationSubscriber"
            )

        return warnings

    def _count_history_entries(self) -> int:
        """Считает количество записей в dna_history.jsonl."""
        try:
            if not self._history_path.exists():
                return 0
            return sum(
                1
                for l in self._history_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                if l.strip()
            )
        except Exception:
            return 0
