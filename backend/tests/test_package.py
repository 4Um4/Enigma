#!/usr/bin/env python3
"""
Package Import Smoke Test - verifies app.services imports work.
"""

import sys
from pathlib import Path

# Match test_startup_checks.py sys.path setup
ROOT_DIR = Path(__file__).resolve().parents[2]  # Enigma/
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def test_app_imports():
    """Test core app.services imports succeed."""
    try:
        from app.services.error_interpreter import get_error_interpreter
        from app.services.llm.provider_manager import get_model_pool
        from app.services.readiness import ReadinessService
        from app.services.system_requirements import SystemRequirements

        print("✅ All app.services imports OK")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        raise


def test_main_imports():
    """Test app.main imports for FastAPI startup."""
    try:
        from app.core.config import settings
        from app.main import app

        print("✅ app.main and config OK")
    except ImportError as e:
        print(f"❌ app.main import failed: {e}")
        raise


if __name__ == "__main__":
    test_app_imports()
    test_main_imports()
    print("\n🎉 Package imports fully operational!")
