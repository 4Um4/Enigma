"""
path: diagnostics/report_renderer.py
Назначение: Рендерит LAST_SESSION.md из данных health-checkers и git-reader.
            Формат оптимизирован для LLM-чтения: конкретные факты, готовые команды.
Зависимости: diagnostics.health_checkers.tick_health,
             diagnostics.health_checkers.movement_health,
             diagnostics.git_reader
Основные сущности: ReportRenderer
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from diagnostics.dna_metrics import DNAComputer
from diagnostics.git_reader import GitInfo, GitReader
from diagnostics.health_checkers.movement_health import MovementHealthReport
from diagnostics.health_checkers.tick_health import TickHealthReport


class ReportRenderer:
    """
    Принимает готовые report-объекты и рендерит markdown.
    Чтение git/mutations происходит здесь — один раз при сборке отчёта.
    """

    def __init__(
        self,
        tick_report: TickHealthReport,
        movement_report: MovementHealthReport,
        dna_computer: Optional[DNAComputer] = None,
        invariant_violations: Optional[list] = None,
        started_at: Optional[datetime] = None,
        project_root: Optional[str] = None,
    ) -> None:
        self._tick = tick_report
        self._movement = movement_report
        self._dna = dna_computer
        self._invariant_violations = invariant_violations or []
        self._started_at = started_at or datetime.now()
        self._git: GitInfo = GitReader(project_root).read()

    def write(self, output_path: str) -> None:
        """Записывает отчёт в output_path и его копию в reports/history/."""
        content = self._render()
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")

        # Архивная копия
        history_dir = out.parent / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        stamp = self._started_at.strftime("%Y-%m-%d_%H-%M")
        archive = history_dir / f"{stamp}.md"
        archive.write_text(content, encoding="utf-8")

        print(f"[CDS] Отчёт записан: {out}")

    # ------------------------------------------------------------------
    # Рендер
    # ------------------------------------------------------------------

    def _section_red_invariants(self) -> str:
        if not self._invariant_violations:
            return (
                "## 🟢 КРАСНЫЕ ИНВАРИАНТЫ — ТИХИЕ ДЕГРАДАЦИИ\n\n"
                "_Не обнаружено — игра жива._\n\n"
                "**Источники проверки:**\n"
                "- Runtime: `SimulationIntegrityError` в pipeline (не сработал)\n"
                "- Post-mortem: `InvariantHealthChecker` в CausalObserver (не нашёл)\n"
                "- Слой ДО: `python backend/tests/IPT.py` (запускается LLM до коммита)"
            )

        critical = [v for v in self._invariant_violations if v.severity == "CRITICAL"]
        warnings = [v for v in self._invariant_violations if v.severity == "WARNING"]

        blocks = []
        if critical:
            blocks.append("### 🔴 CRITICAL — чинить ПЕРВЫМ, до любой новой фичи")
            for v in critical:
                blocks.append(self._render_violation(v))
        if warnings:
            blocks.append("### 🟡 WARNING — можно работать, но записать в долг")
            for v in warnings:
                blocks.append(self._render_violation(v))

        return "## 🔴 КРАСНЫЕ ИНВАРИАНТЫ — ТИХИЕ ДЕГРАДАЦИИ\n\n" + "\n\n".join(blocks)

    def _render_violation(self, v) -> str:
        source_icon = "⚡" if v.source == "RUNTIME" else "📈"
        files_block = "\n".join(f"  - `{f}`" for f in v.suspect_files)
        ps_block = ""
        if v.powershell_check:
            ps_block = f"\n\n**PowerShell для проверки:**\n```powershell\n{v.powershell_check}\n```"

        return (
            f"#### {source_icon} {v.invariant_id} [{v.source}]\n\n"
            f"**Симптом:** {v.message}\n\n"
            f"**Подозреваемые файлы (проверить в порядке очерёдности):**\n"
            f"{files_block}{ps_block}"
        )

    def _render(self) -> str:
        ts = self._started_at.strftime("%Y-%m-%d %H:%M")
        sections = [
            self._header(ts),
            self._section_identification(),
            self._section_dna(),
            self._section_red_invariants(),
            self._section_architect1(),
            self._section_architect2(),
            self._section_architect3(),
        ]
        return "\n\n".join(sections)

    def _section_dna(self) -> str:
        """Секция DNA — вычисляется и сохраняется в историю."""
        if self._dna is None:
            return "## DNA — МЕТРИКИ\n\n_(DNAComputer не инициализирован)_"
        try:
            snap = self._dna.compute()
            prev = self._dna.load_previous()
            self._dna.save(snap)  # пишем ПОСЛЕ load_previous
            delta = self._dna.compute_delta(snap, prev)
            return self._dna.render_section(snap, delta)
        except Exception as exc:
            return f"## DNA — МЕТРИКИ\n\n_(ошибка вычисления: {exc})_"

    def _header(self, ts: str) -> str:
        campaign = self._tick.player_campaign or "?"
        player = self._tick.player_name or "?"
        return f"# ENIGMA Session State — {ts}\n\nКампания: `{campaign}` | Игрок: `{player}`"

    def _section_identification(self) -> str:
        return """\
## ИДЕНТИФИКАЦИЯ АРХИТЕКТОРА

Прочитай эту секцию первой. Определи кто ты по задаче сессии:

- Если ты работаешь с Python-кодом, патчами, архитектурой, багами → **Архитектор #1 или #3**
- Если ты работаешь с UI, pygame, рендерингом, визуальными элементами → **Архитектор #2**
- Если ты работаешь с NPC-поведением, тиками, давлением, решениями → **Архитектор #3**

Прочитай свою секцию (#1, #2 или #3). У других архитекторов читай только строку "Сейчас делает:" — чтобы не конфликтовать по файлам.

---"""

    def _section_architect1(self) -> str:
        commits = (
            "\n".join(f"  - {c}" for c in self._git.recent_commits)
            or "  - (нет данных)"
        )
        mutations = (
            "\n".join(f"  - {m}" for m in self._git.mutations_last)
            or "  - (нет данных)"
        )
        todos = (
            "\n".join(f"  - {f}" for f in self._git.todo_files) or "  - (не найдено)"
        )

        spatial_warn = ""
        if self._movement.spatial_fallback_triggered:
            spatial_warn = (
                "\n- **[КРИТИЧНО]** `location_templates.json` недоступен — используется builtin fallback\n"
                '  Проверка: `python -c "from app.services.scene.scene_state_manager import *; '
                "print('ok')\"`"
            )

        node_warn = ""
        for npc_id, s in self._movement.npcs.items():
            if s.node_not_found:
                node_warn += (
                    f"\n- **[КРИТИЧНО]** NPC `{npc_id}`: узел `{s.missing_node}` не найден в графе\n"
                    f"  PowerShell: "
                    f'`Select-String -Path "backend/app/services/spatial/*.py" '
                    f'-Pattern "{s.missing_node}"`'
                )

        return f"""\
## #1 — АРХИТЕКТОР КОДА (патчи, файлы, архитектура)

### Сейчас делает:
{self._git.current_architect_action}

### Активные баги требующие патча:{spatial_warn}{node_warn}
{"_(баги не обнаружены в этой сессии)_" if not spatial_warn and not node_warn else ""}

### Последние изменения (git log -5):
{commits}

### Последние записи MUTATIONS.md:
{mutations}

### Файлы с активными TODO/FIXME:
{todos}

---"""

    def _section_architect2(self) -> str:
        # Данные рендеринга — координаты NPC из movement_report
        npc_with_coords = [
            (npc_id, s)
            for npc_id, s in self._movement.npcs.items()
            if s.coord_x is not None
        ]
        npc_no_coords = [
            (npc_id, s)
            for npc_id, s in self._movement.npcs.items()
            if s.coord_x is None
        ]

        coords_lines = (
            "\n".join(
                f"  - `{npc_id}`: x={s.coord_x:.1f} y={s.coord_y:.1f}"
                for npc_id, s in npc_with_coords
            )
            or "  - _(нет данных о координатах — SNAPSHOT-паттерн не сработал)_"
        )

        no_coords_lines = (
            "\n".join(
                f"  - `{npc_id}` (intent={s.last_intent})"
                for npc_id, s in npc_no_coords
            )
            or "  - _(нет)_"
        )

        graph_fallbacks = ", ".join(self._movement.graph_fallback_locations) or "нет"

        return f"""\
## #2 — АРХИТЕКТОР UI (pygame, рендеринг, визуал)

### Сейчас делает:
{self._git.current_architect_action}

### Состояние рендеринга (из последней сессии игры):
- NPC с известными координатами ({len(npc_with_coords)}):
{coords_lines}
- NPC без координат (lerp не работает, {len(npc_no_coords)}):
{no_coords_lines}
- Граф-fallback локаций: {graph_fallbacks}

### Визуальные аномалии:
- spatial_fallback triggered: {"⚠️ ДА" if self._movement.spatial_fallback_triggered else "✅ нет"}
- Узлы не найдены (NPC не могут добраться до цели): {self._movement.total_node_not_found}

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #3 — файлы backend/app/services/)_

---"""

    def _section_architect3(self) -> str:
        tick = self._tick

        # Таблица движения
        movement_table = self._movement.markdown_table()

        # Broken NPC (intent есть, traversal нет)
        broken = self._movement.get_broken_npcs()
        broken_lines = (
            "\n".join(
                f"  - `{npc_id}`: intent={self._movement.npcs[npc_id].last_intent}, "
                f"traversal=❌, coords=None"
                for npc_id in broken
            )
            or "  - _(нет разрывов в movement pipeline)_"
        )

        # Warnings из tick-чекера
        warnings = "\n".join(f"  - ⚠️ {w}" for w in tick.warnings) or "  - _(нет)_"

        # Каузальные разрывы — собираем из данных
        causal_breaks = []
        if tick.is_simulation_dead():
            causal_breaks.append(
                "#### [BREAK-1] Симуляция заморожена\n"
                "**Симптом:** все тики вернули 0 decisions\n"
                "**Файл для проверки:** `backend/app/services/npc/decision_hub.py`\n"
                '**PowerShell:** `Select-String -Path "backend/app/services/npc/decision_hub.py" '
                '-Pattern "def compute"`'
            )
        if self._movement.spatial_fallback_triggered:
            causal_breaks.append(
                "#### [BREAK-2] Spatial Fallback\n"
                "**Симптом:** `location_templates.json` недоступен → граф берётся из builtin\n"
                "**Цепь отказа:**\n"
                "  load_editor_json → fallback → builtin граф → узлы могут не совпадать с данными NPC\n"
                "**PowerShell:** "
                '`Select-String -Path "backend/app/services/spatial/*.py" -Pattern "fallback"`'
            )
        for npc_id, s in self._movement.npcs.items():
            if s.node_not_found:
                causal_breaks.append(
                    f"#### [BREAK-N] Узел `{s.missing_node}` не найден для `{npc_id}`\n"
                    f"**Симптом:** NPC получил intent={s.last_intent} но узел назначения отсутствует в графе\n"
                    f"**Цепь отказа:**\n"
                    f"  DECISION_HUB → SceneChange создан → MovementEngine.get_node('{s.missing_node}') → None\n"
                    f"  → traversal не создан → координаты None → lerp не работает\n"
                    f"**PowerShell:** "
                    f'`Select-String -Path "backend/app/services/spatial/graph_compiler.py" '
                    f'-Pattern "{s.missing_node}"`'
                )

        breaks_text = (
            "\n\n".join(causal_breaks)
            if causal_breaks
            else "_Каузальных разрывов не обнаружено_"
        )

        return f"""\
## #3 — АРХИТЕКТОР СИМУЛЯЦИИ (NPC, тики, давление, решения)

### Сейчас делает:
{self._git.current_architect_action}

### Состояние симуляции (последняя сессия игры):

**Tick Pipeline:**
{tick.summary_line()}
- LLM "Ничего не произошло": {tick.llm_nothing_count} раз
- LLM CJK-галлюцинации: {tick.llm_cjk_lines} строк
- Стартап backend: {"✅" if tick.startup_ok else "❌"}
- LLM сервер: {"✅" if tick.llm_server_ok else "❌ (не доступен при старте)"}

**Предупреждения:**
{warnings}

**Movement Pipeline (по NPC):**
{movement_table}

**NPC с разрывом в pipeline (intent есть, traversal нет):**
{broken_lines}

### Каузальные разрывы:

{breaks_text}

### Архитектурный долг (не трогать без обсуждения):
- Stale Cognition: DecisionHub работает на state T-1. Требует ADR-059.
- Cognitive Overlay Layer: отдельный спринт.

### Что НЕ трогать (сейчас меняет другой архитектор):
_(см. секции #1 и #2 — файлы frontend/)_"""
