from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    """
    Базовый класс настроек проекта Enigma.
    Используется для наследования другими агентами.
    """
    project_root: Path = Path(__file__).resolve().parents[3]  # Enigma root
    data_path: Path = project_root / "backend" / "data"
    models_path: Path = project_root / "Models LLM"


class DmSettings(Settings):
    """
    DM Agent specific settings - primary narrative model.

    Настройки для агента DM:
    - модель для нарративной генерации
    - сервер llama.cpp
    - параметры GPU и контекста
    """

    # Пути к моделям: используем относительные пути
    llama_cpp_model_path: Path = Settings().models_path / "gemma-3-12b-it-q4_k_m.gguf"

    # Настройки LLM сервера
    llm_servers: dict = {
        "dm": {
            "host": "127.0.0.1",
            "port": 8080,
            "description": "DM narrative server",
        },
    }

    # Параметры генерации текста
    gpu_layers: int = 28
    temperature: float = 0.75
    ctx_size: int = 4096  # 12B — KV-cache мал, ctx=4096 ок


# Создаём объект настроек DM
dm_settings = DmSettings()

# URL сервера LLM для DM (только после создания объекта)
llama_cpp_server_url: str = f"http://{dm_settings.llm_servers['dm']['host']}:{dm_settings.llm_servers['dm']['port']}"
