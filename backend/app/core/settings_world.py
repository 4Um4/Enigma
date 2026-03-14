from pathlib import Path
from pydantic_settings import BaseSettings
from .config import Settings

# ROOT_DIR → корень проекта Enigma
ROOT_DIR = Path(__file__).resolve().parents[3]  # app/core/settings_world.py → Enigma
MODEL_DIR = ROOT_DIR / "Models LLM"

from typing import ClassVar

class WorldSettings(Settings):
    """World Simulation settings - large model for complex simulation."""

    # World model (larger)
    model_qwen_9b_path: str = str(MODEL_DIR / "Qwen3.5-9B.gguf")

    # World server (порт для сырого старта)
    WORLD_PORT: ClassVar[int] = 8082  # теперь Pydantic не считает это полем
    llm_servers: dict = {
        "world": {"host": "127.0.0.1", "port": str(WORLD_PORT), "description": "World simulation"},
    }

    llama_cpp_server_url: str = f"http://127.0.0.1:{WORLD_PORT}"

    gpu_layers: int = 40
    temperature: float = 0.8
    ctx_size: int = 8192
    threads: int = 6

# Создаём экземпляр настроек
world_settings = WorldSettings()