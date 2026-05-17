from pathlib import Path
from .config import Settings

ROOT_DIR = Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT_DIR / "Models LLM"

from typing import ClassVar


class WorldSettings(Settings):
    """World Simulation (Qwen2.5-7B)."""

    model_qwen_7b_path: str = str(MODEL_DIR / "Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf")

    WORLD_PORT: ClassVar[int] = 8080
    llm_servers: dict = {
        "world": {"host": "127.0.0.1", "port": str(WORLD_PORT), "description": "World simulation"},
    }

    llama_cpp_server_url: str = f"http://127.0.0.1:{WORLD_PORT}"

    gpu_layers: int = 99
    temperature: float = 0.9
    ctx_size: int = 8192
    threads: int = 8


world_settings = WorldSettings()