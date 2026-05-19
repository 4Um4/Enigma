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
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from diagnostics.health_checkers.tick_health import TickHealthReport
from diagnostics.health_checkers.movement_health import MovementHealthReport


@dataclass
class DNASnapshot:
    """Снимок DNA-метрик одной сессии — пишется в dna_history.jsonl."""
    timestamp: str               # ISO-формат
    session_minutes: float       # длительность сессии

    # --- Simulation ---
    SHI: float    # Simulation Health Index 0–100
    NPI: float    # NPC Pipeline Integrity 0–100
    OBI: float    # Obedience Breakthrough Index 0–100

    # --- Architecture ---
    SCF: float    # Spatial Coherence Factor 0.0 / 0.5 / 1.0
    ADR: float    # Architecture Debt Ratio (TODO/ADR_count)
    CVS: float    # Causal Velocity Score (llm_calls/min)

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


@dataclass
class DNADelta:
    """Дельта между текущей и предыдущей сессией."""
    SHI: Optional[float] = None
    NPI: Optional[float] = None
    OBI: Optional[float] = None
    SCF: Optional[float] = None
    ADR: Optional[float] = None
    CVS: Optional[float] = None

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
        return ("↑" if positive == higher_is_better else "↓")


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
        project_root: Optional[str] = None,
    ) -> None:
        self._tick = tick_report
        self._movement = movement_report
        self._started_at = started_at
        self._root = Path(project_root) if project_root else Path(__file__).parent.parent
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
            npc_total=npc_total,
            npc_with_real_coords=npc_real,
            directive_events=self._directive_events,
            obedience_nonzero=self._obedience_nonzero,
            todo_count=todo_count,
            adr_count=adr_count,
            llm_calls=self._tick.llm_calls,
        )

    def _compute_shi(self) -> float:
        """SHI = decisions_nonzero_ticks / total_ticks * 100."""
        if self._tick.total_ticks == 0:
            return 0.0
        return round(self._tick.decisions_nonzero_ticks / self._tick.total_ticks * 100, 1)

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
            1 for s in npcs.values()
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
        1.0 = нет fallback, нет node_not_found
        0.5 = есть spatial_fallback но нет node_not_found
        0.0 = есть node_not_found (пространство разрушено)
        """
        if self._movement.total_node_not_found > 0:
            return 0.0
        if self._movement.spatial_fallback_triggered:
            return 0.5
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

    # ------------------------------------------------------------------
    # Вспомогательные счётчики файловой системы
    # ------------------------------------------------------------------

    def _count_todos(self) -> int:
        """Считает TODO/FIXME/HACK через PowerShell."""
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-ChildItem -Path 'backend/app/','frontend/' -Filter '*.py' -Recurse "
                 "| Select-String -Pattern 'TODO|FIXME|HACK' "
                 "| Measure-Object | Select-Object -ExpandProperty Count"],
                cwd=str(self._root),
                capture_output=True, text=True, timeout=15,
                encoding="utf-8", errors="replace",
            )
            if result.returncode == 0:
                return int(result.stdout.strip())
        except Exception:
            pass
        return -1  # -1 означает "не удалось посчитать"

    def _count_adrs(self) -> int:
        """Считает ADR-записи через grep по файлу."""
        try:
            adr_file = self._root / "docs" / "Tasks" / "ADR (Architecture Decision Records).md"
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
            lines = [l.strip() for l in self._history_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines() if l.strip()]
            # Берём предпоследнюю — последняя только что записана
            if len(lines) < 2:
                return None
            data = json.loads(lines[-2])
            return DNASnapshot(**data)
        except Exception:
            return None

    def compute_delta(self, current: DNASnapshot, previous: Optional[DNASnapshot]) -> DNADelta:
        """Вычисляет разницу метрик между текущей и предыдущей сессией."""
        if previous is None:
            return DNADelta()
        return DNADelta(
            SHI=round(current.SHI - previous.SHI, 1),
            NPI=round(current.NPI - previous.NPI, 1),
            OBI=round(current.OBI - previous.OBI, 1),
            SCF=round(current.SCF - previous.SCF, 1),
            ADR=round(current.ADR - previous.ADR, 2),
            CVS=round(current.CVS - previous.CVS, 2),
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
        npi_interpret = self._interpret_npi(snapshot.NPI, snapshot.npc_with_real_coords, snapshot.npc_total)
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
        adr_interpret = self._interpret_adr(snapshot.ADR, snapshot.todo_count, snapshot.adr_count)
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
            return f"⚠️ {real}/{total} NPC с координатами: spatial pipeline частично сломан"
        if v < 100:
            return f"⚠️ {real}/{total} NPC с координатами: есть потери в traversal"
        return f"✅ {real}/{total} NPC с реальными координатами"

    def _interpret_obi(self, v: float, events: int) -> str:
        if events == 0:
            return "нет директив в сессии — OBI не применим"
        if v == 0:
            return "⛔ 0% обработки: ObediencePressure всегда 0 → Legitimacy Gate мертва"
        if v < 30:
            return f"⚠️ {v:.0f}% директив прошли: слабый отклик NPC на приказы"
        return f"✅ {v:.0f}% директив с ненулевым давлением"

    def _interpret_scf(self, v: float) -> str:
        if v == 0.0:
            return "⛔ РАЗРУШЕНО: узлы не найдены → NPC не могут двигаться"
        if v == 0.5:
            return "⚠️ ДЕГРАДАЦИЯ: location_templates fallback активен"
        return "✅ пространство целостно: граф загружен корректно"

    def _interpret_adr(self, v: float, todo: int, adr: int) -> str:
        if adr == 0:
            return "нет ADR-записей — невозможно оценить"
        if v > 3.0:
            return f"⛔ {todo} TODO / {adr} ADR = долг накапливается быстрее документации"
        if v > 2.0:
            return f"⚠️ {todo} TODO / {adr} ADR = умеренный архитектурный долг"
        return f"✅ {todo} TODO / {adr} ADR = долг под контролем"

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
            return sum(1 for l in self._history_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines() if l.strip())
        except Exception:
            return 0
