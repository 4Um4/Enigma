from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Local AI Dungeon Master"
    default_model: str = "ollama:llama3.1"
    world_tick_minutes: int = 15
    data_dir: str = "data"
    min_cpu_physical_cores: int = 8
    min_ram_gb: int = 16
    enforce_system_requirements: bool = True
    orchestrator_workers: int = 4

    model_config = SettingsConfigDict(env_prefix="AIDM_", env_file=".env", extra="ignore")


settings = Settings()
