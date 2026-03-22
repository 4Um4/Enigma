from pathlib import Path
from typing import Dict
from pydantic_settings import BaseSettings
ROOT_DIR = Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT_DIR / "Models LLM"

class NpcSettings(BaseSettings):
    npc_major_model_path: Path = MODEL_DIR / "gemma-3-12b-it-q4_k_m.gguf"
    llm_servers: Dict[str, Dict[str, str]] = {
        "npc": {
            "host": "127.0.0.1",
            "port": "8081",
            "description": "NPC dialogues"
        }
    }
    gpu_layers: int = 28  # 12B: 28/28 слоёв, все в VRAM
    threads: int = 12
    temperature: float = 0.85
    ctx_size: int = 4096  # 12B — ctx=4096 ок

    class Config:
        env_prefix = "NPC_"
        case_sensitive = False

npc_settings = NpcSettings()