import sys
from pathlib import Path
import pytest

# === 1. Добавляем backend в sys.path ===
ROOT_DIR = Path(__file__).resolve().parents[2]  # Enigma
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# === 2. Импортируем main корректно ===
from app.main import *

# === 3. Импортируем config для правильных путей данных ===
from app.core.config import DATA_DIR, MODEL_PATH
