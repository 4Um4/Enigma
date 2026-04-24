from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    """Базовый класс настроек проекта Enigma."""
    project_root: Path = Path(__file__).resolve().parents[3]
    data_path: Path = project_root / "backend" / "data"
    models_path: Path = project_root / "Models LLM"


class DmSettings(Settings):
    """DM Agent — нарративная генерация (Qwen2.5-7B)."""

    llama_cpp_model_path: Path = Settings().models_path / "Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"

    llm_servers: dict = {
        "dm": {
            "host": "127.0.0.1",
            "port": 8080,
            "description": "DM narrative server",
        },
    }

    gpu_layers: int = 99
    temperature: float = 0.6
    repeat_penalty: float = 1.15
    ctx_size: int = 8192


dm_settings = DmSettings()

llama_cpp_server_url: str = f"http://{dm_settings.llm_servers['dm']['host']}:{dm_settings.llm_servers['dm']['port']}"