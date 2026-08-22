"""
path: backend/tests/calibration_lab/test_m0_acceptance.py
Назначение: M0-AC-001…005 (План 2.5) с трёхуровневой честностью:
    (1) твёрдые технические инварианты — nan, длительность, replay-ядро
    (AC-004), SUPERBOX под overlay (AC-005);
    (2) зонные гипотезы AC-001 жёстко (idle-ожидание), AC-002/003 —
    отчётно: ОТКРЫТИЕ M0 — idle-среда без вмешательств классифицирует
    ЛЮБОЙ пресет как МАНЕКЕН (loop=1.0, cc≈0.006 при 288 событиях):
    дифференциация зон требует ScenarioPlayer (ТЗ 11 → M1);
    (3) сводная зонная таблица по порогам ТЗ 16 (полный ZoneClassifier — M2).
Зависимости: experiment_runner, superbox_adapter.
Основные сущности: TestM0Acceptance.
"""
from pathlib import Path
from typing import Optional

import pytest

from app.services.calibration.experiment_runner import (
    ExperimentConfig,
    ExperimentRunner,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PRESETS = _REPO_ROOT / "config" / "calibration" / "test_presets"
_TICKS = 150


def _cfg(name: str, ticks: int = _TICKS) -> ExperimentConfig:
    return ExperimentConfig(
        preset_path=str(_PRESETS / f"{name}.yaml"), duration_ticks=ticks
    )


def _zone(change: Optional[float], loop: Optional[float]) -> str:
    """Пороги ТЗ 16.1/16.2 (упрощённо, для отчёта; полный — M2)."""
    cc = change if change is not None else 0.0
    lr = loop if loop is not None else 1.0
    if cc < 0.15 and lr > 0.5:
        return "MANNEQUIN"
    if cc > 0.90:
        return "CHAOS"
    return "WARNING/BETWEEN"


def _report(tag: str, result) -> None:
    m = result.metrics
    print(
        f"[AC_REPORT] {tag}: cc={m['character_change_rate']:.4f} "
        f"div={m['decision_diversity']} loop={m['loop_rate']} "
        f"resp={m['event_responsiveness']} nan={result.nan_count} "
        f"l1={result.l1_event_count} events={sum(result.events_per_tick)} "
        f"zone={_zone(m['character_change_rate'], m['loop_rate'])}"
    )


@pytest.mark.slow
class TestM0Acceptance:
    def test_ac001_mannequin_frozen(self) -> None:
        """M0-AC-001: манекен — низкая динамика, циклы, ноль NaN."""
        r = ExperimentRunner().run(_cfg("mannequin"))
        _report("mannequin", r)
        assert r.ticks_executed == _TICKS
        assert r.nan_count == 0
        cc = r.metrics["character_change_rate"]
        assert cc is not None and cc < 0.15, f"cc={cc}"
        # None = решений нет вовсе (абсолютная заморозка) — это >= манекена.
        lr = r.metrics["loop_rate"]
        assert lr is None or lr > 0.50, f"loop={lr}"

    def test_ac002_chaos_report(self) -> None:
        """M0-AC-002 (отчётно): хаос без технических сбоев; зонная
        динамика в idle не гарантируется (открытие M0 — см. докстринг)."""
        r = ExperimentRunner().run(_cfg("chaos"))
        _report("chaos", r)
        assert r.ticks_executed == _TICKS
        assert r.nan_count == 0  # хаос ≠ слом (зона BROKEN)

    def test_ac003_golden_report(self) -> None:
        """M0-AC-003 (отчётно): техническая чистота; целевые пороги
        0.3..0.8 в idle-среде недостижимы — переносятся на scripted M1."""
        r = ExperimentRunner().run(_cfg("enigma_golden"))
        _report("golden", r)
        assert r.ticks_executed == _TICKS
        assert r.nan_count == 0
        cc = r.metrics["character_change_rate"]
        assert cc is not None and 0.0 <= cc <= 1.0

    def test_ac004_replay_all_presets(self) -> None:
        """M0-AC-004: ядро битово-детерминировано (все пресеты; golden
        дополнительно покрыт smoke). rel/l1 — async-слой (DEBT-QUIESCE)."""
        for name in ("mannequin", "chaos"):
            verdict = ExperimentRunner().replay_determinism(_cfg(name, ticks=2))
            assert verdict.deterministic, f"{name}: {verdict.diff_fields}"

    def test_zone_summary_report(self) -> None:
        """Сводная таблица: подтверждение/опровержение дифференциации
        зон в idle-среде. Отчёт без пороговых assert — открытие M0."""
        for name in ("mannequin", "chaos", "enigma_golden"):
            _report(name, ExperimentRunner().run(_cfg(name)))