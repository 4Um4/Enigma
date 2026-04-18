from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[3]  # Enigma/
BACKEND_DIR = ROOT_DIR / "backend"

# Добавляем backend в sys.path, чтобы импорт работал
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
    
from data.runtime_ports import get_runtime_ports

def get_llm_url() -> str:
    """Get current LLM server URL."""
    ports = get_runtime_ports()
    return f"http://127.0.0.1:{ports['llm_port']}"

def get_api_url() -> str:
    """Get current API server URL."""
    ports = get_runtime_ports()
    return f"http://127.0.0.1:{ports['api_port']}"

def get_llm_server_config(agent_name: str = "default") -> dict:
    """Get LLM server config for any agent (single port)."""
    ports = get_runtime_ports()
    return {
        "host": "127.0.0.1",
        "port": ports['llm_port'],
        "url": f"http://127.0.0.1:{ports['llm_port']}",
        "description": f"Shared LLM server on port {ports['llm_port']}"
    }

