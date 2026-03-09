
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict


class ModelConfig(BaseSettings):
    """Конфигурация одной модели LLM."""
    name: str  # короткое имя для роутера (npc, dm, rules, memory)
    path: str  # полный путь к .gguf файлу
    display_name: str  # человеческое название
    vram_mb: int = 4000  # примерный VRAM в MB
    context_size: int = 4096
    temperature: float = 0.7
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    n_keep: int = 512


class Settings(BaseSettings):
    app_name: str = "Local AI Dungeon Master"
    default_model: str = "ollama:llama3.1"
    world_tick_minutes: int = 15
    data_dir: str = "data"
    min_cpu_physical_cores: int = 8
    min_ram_gb: int = 16
    enforce_system_requirements: bool = True
    orchestrator_workers: int = 4
    
    # === Llama.cpp пути ===
    llama_cpp_executable: str = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama.exe"
    llama_cpp_server_executable: str = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama-server.exe"
    llama_cpp_model_path: str = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\qwen2.5-7b-instruct-q4_k_m.gguf"
    llama_cpp_server_url: str = "http://127.0.0.1:8080"
    llama_cpp_max_tokens: int = 512
    llama_cpp_timeout_sec: int = 300
    
    # GPU параметры для RTX 3070 Ti (~8GB VRAM)
    gpu_layers: int = 33
    threads: int = 8
    ctx_size: int = 4096
    
    # Параметры генерации (для обратной совместимости)
    llama_cpp_temperature: float = 0.7
    llama_cpp_top_p: float = 0.9
    llama_cpp_repeat_penalty: float = 1.1
    llama_cpp_n_keep: int = 512
    
    # === Конфигурация моделей для мультимодальности ===
    # Уровень 1: Быстрые агенты (Rules, Memory)
    model_saiga_path: str = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\saiga_mistral_7b_model-q4_K.gguf"
    
    # Уровень 2: Диалоги (NPC)
    model_yandex_path: str = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf"
    
    # Уровень 3: Мозг (DM, World)
    model_qwen_7b_path: str = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\qwen2.5-7b-instruct-q4_k_m.gguf"
    model_qwen_9b_path: str = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\Qwen3.5-9B.gguf"
    
    # === Маппинг агент → модель ===
    # agent_name -> model_key для router
    agent_model_map: Dict[str, str] = {
        "dm": "qwen_7b",           # DM агент - основной
        "world": "qwen_9b",        # World симуляция - самая большая
        "npc": "yandex",           # NPC диалоги - специализированная
        "rules": "saiga",          # Rules агент - быстрая
        "memory": "saiga",         # Memory агент - быстрая
    }
    
    # === Доступные модели ===
    available_models: Dict[str, ModelConfig] = {
        "saiga": ModelConfig(
            name="saiga",
            path=model_saiga_path,
            display_name="Saiga Mistral 7B",
            vram_mb=4000,
        ),
        "yandex": ModelConfig(
            name="yandex", 
            path=model_yandex_path,
            display_name="YandexGPT 8B Lite",
            vram_mb=5000,
        ),
        "qwen_7b": ModelConfig(
            name="qwen_7b",
            path=model_qwen_7b_path,
            display_name="Qwen2.5 7B",
            vram_mb=4000,
        ),
        "qwen_9b": ModelConfig(
            name="qwen_9b",
            path=model_qwen_9b_path,
            display_name="Qwen3.5 9B",
            vram_mb=5500,
        ),
    }
    
    # Системный промпт DM
    system_prompt_file: str = "Promt_AI.json"

    model_config = SettingsConfigDict(env_prefix="AIDM_", env_file=".env", extra="ignore")


settings = Settings()
