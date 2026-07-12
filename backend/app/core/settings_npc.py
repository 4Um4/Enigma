from pathlib import Path
from typing import Dict

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT_DIR / "Models LLM"


class NpcSettings(BaseSettings):
    npc_model_path: Path = MODEL_DIR / "Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"
    llm_servers: Dict[str, Dict[str, str]] = {
        "npc": {
            "host": "127.0.0.1",
            "port": "8080",
            "description": "NPC dialogues",
        }
    }
    gpu_layers: int = 99
    threads: int = 8
    temperature: float = 0.9
    ctx_size: int = 8192

    model_config = SettingsConfigDict(env_prefix="NPC_", case_sensitive=False)


npc_settings = NpcSettings()
