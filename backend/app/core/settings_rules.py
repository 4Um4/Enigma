from pydantic_settings import BaseSettings
from .config import Settings
from pathlib import Path

# ------------------------
# Paths
# ------------------------
ROOT_DIR = Path(__file__).resolve().parents[3]   # Enigma root
BACKEND_DIR = ROOT_DIR / "backend"
DATA_DIR = BACKEND_DIR / "data"
MODELS_DIR = ROOT_DIR / "Models LLM"

# Полный путь к модели Saiga
GEMMA_12B_PATH = MODELS_DIR / "gemma-3-12b-it-q4_k_m.gguf"

# =========================
# Settings
# =========================
class RulesSettings(Settings):
    """Rules Agent - fast & accurate model for rules checking."""
    
    # Rules server (port 8083)
    llm_servers: dict = {
        "rules": {"host": "127.0.0.1", "port": "8083", "description": "Rules checking"},
    }
    
    # Precision over speed/creativity
    gpu_layers: int = 28
    temperature: float = 0.3  # Low temp for rules accuracy
    top_p: float = 0.8
    ctx_size: int = 4096
    repeat_penalty: float = 1.15

    # Model path
    rules_model_path: Path = GEMMA_12B_PATH

# ------------------------
# URL for llama_cpp server
# ------------------------
llama_cpp_server_url: str = "http://127.0.0.1:8083"

rules_settings = RulesSettings()
