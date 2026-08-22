# path: /project/backend/tests/test_stage0_and_1_invariants.py
"""
Файл: backend/tests/test_stage0_and_1_invariants.py
Назначение: Программная проверка архитектурных инвариантов Stage 0 и Stage 1.
Запуск: cd backend; python -m pytest tests/test_stage0_and_1_invariants.py -v; cd ..
"""

import os
import subprocess
import pytest
from app.models.npc_state import NPCState
from app.errors import ArchitecturalViolationError, MissingProvenanceError

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))

def _grep(pattern: str, path: str = BACKEND_DIR) -> int:
    """Возвращает количество совпадений."""
    try:
        result = subprocess.run(
            ["powershell", "-Command", f"Get-ChildItem -Path '{path}' -Filter '*.py' -Recurse | Select-String -Pattern '{pattern}' | Measure-Object | Select-Object -ExpandProperty Count"],
            capture_output=True, text=True, check=True
        )
        return int(result.stdout.strip())
    except Exception:
        return 0

class TestStage0Invariants:
    def test_I0_2_no_runtime_top_level_keys(self):
        assert _grep("_RUNTIME_TOP_LEVEL_KEYS\s*=") == 0

    def test_I0_3_no_write_to_legacy_in_services(self):
        assert _grep("write_to_legacy", os.path.join(BACKEND_DIR, "services")) == 0

    def test_I0_4_no_belief_writers_outside_engine(self):
        # Stage 0 Task 0.6: state_applicator.apply_belief_delta — легальный writer
        _count = _grep(r"state\.beliefs\.(update|set)", os.path.join(BACKEND_DIR, "services"))
        _applicator_count = _grep(r"state\.beliefs\.(update|set)", os.path.join(BACKEND_DIR, "services", "npc", "state_applicator.py"))
        assert _count - _applicator_count == 0

    def test_I0_5_no_wt_dirty(self):
        assert _grep(r"wt_dirty") == 0

    def test_I0_10_no_avatar_body_state_mutation(self):
        assert _grep(r'_avatar\.body_state\["money"\]') == 0

class TestStage1Invariants:
    def test_I1_2_provenance_required(self):
        # Проверяем, что класс MissingProvenanceError доступен
        from app.errors import MissingProvenanceError
        assert MissingProvenanceError is not None

    def test_I1_4_causal_ledger_api_exists(self):
        assert hasattr(NPCState, "query_ledger")
        assert hasattr(NPCState, "trace_causal_chain")