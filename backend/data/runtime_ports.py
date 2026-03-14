# backend/data/runtime_ports.py
# -*- coding: utf-8 -*-
"""
Runtime port management for Enigma.
Handles dynamic assignment, saving, and loading of LLM/API/frontend ports.
"""

from pathlib import Path
import json
from typing import Dict

# ========================================
# Константы
# ========================================
BASE_DIR = Path(__file__).parent
RUNTIME_PORTS_FILE = BASE_DIR / "runtime_ports.json"

DEFAULT_PORTS: Dict[str, int] = {
    "llm_port": 8080,
    "api_port": 8000,
    "frontend_port": 3001
}

# ========================================
# Основные функции
# ========================================

def save_ports(ports: Dict[str, int]) -> None:
    """
    Save assigned runtime ports to JSON.
    Creates folder if missing.
    """
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNTIME_PORTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(ports, f, indent=2)
    # Для диагностики можно вернуть путь
    # print(f"[INFO] Runtime ports saved: {RUNTIME_PORTS_FILE}")

def load_ports() -> Dict[str, int]:
    """
    Load ports from JSON or return defaults.
    Validates keys and fills missing ones.
    """
    if RUNTIME_PORTS_FILE.exists():
        try:
            with open(RUNTIME_PORTS_FILE, 'r', encoding='utf-8') as f:
                ports = json.load(f)
            # Валидация: убедиться, что все ключи присутствуют
            for key, default_value in DEFAULT_PORTS.items():
                if key not in ports or not isinstance(ports[key], int):
                    ports[key] = default_value
            return ports
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    # fallback на дефолтные
    return DEFAULT_PORTS.copy()

def get_runtime_ports() -> Dict[str, int]:
    """
    Get current runtime ports.
    Returns loaded ports or defaults.
    """
    return load_ports()