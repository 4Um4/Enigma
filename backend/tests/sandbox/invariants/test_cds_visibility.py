"""Invariant: CDS Visibility (SHI > 0).
Защищает систему от регрессии, когда CausalObserver перестаёт видеть решения NPC (SHI=0%).

Запуск: cd backend; python -m pytest tests/sandbox/invariants/test_cds_visibility.py -v --tb=short; cd ..
"""
import sys
import tempfile
import os
from pathlib import Path

# Добавляем корень проекта в path для импорта diagnostics
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from diagnostics.causal_observer import CausalObserver


def test_cds_shi_not_zero_when_decisions_exist():
    """Если в логе есть [DECISION_HUB], SHI должен быть > 0."""
    log_content = (
        "[TICK_DECISIONS] start\n"
        "[DECISION_HUB] thief_shadow: intent=Intent.IDLE score=0.000 event=player_interacts\n"
        "[TICK_DECISIONS] end\n"
    )
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False, encoding='utf-8') as f:
        f.write(log_content)
        log_path = f.name
        
    try:
        obs = CausalObserver(log_path=log_path)
        obs._parse_log_file()
        
        tick_report = obs._tick_checker.build()
        assert tick_report.total_decisions > 0, "CDS не засчитал решение (total_decisions=0)"
        assert not tick_report.is_simulation_dead(), "CDS считает симуляцию мёртвой"
    finally:
        os.unlink(log_path)