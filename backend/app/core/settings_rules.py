from pathlib import Path

from .config import Settings

ROOT_DIR = Path(__file__).resolve().parents[3]
BACKEND_DIR = ROOT_DIR / "backend"
DATA_DIR = BACKEND_DIR / "data"
MODELS_DIR = ROOT_DIR / "Models LLM"


class RulesSettings(Settings):
    """Rules Agent — проверка правил (Qwen2.5-7B)."""

    llm_servers: dict = {
        "rules": {"host": "127.0.0.1", "port": "8080", "description": "Rules checking"},
    }

    gpu_layers: int = 99
    temperature: float = 0.9
    ctx_size: int = 8192
    repeat_penalty: float = 1.12

    rules_model_path: Path = (
        MODELS_DIR / "Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"
    )


llama_cpp_server_url: str = "http://127.0.0.1:8181"

rules_settings = RulesSettings()
