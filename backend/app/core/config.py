# C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\config.py
# RTX 3070 Ti (8 GB VRAM) + Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M
#
# Единственная модель: Qwen2.5-7B Q5_K_M (~5.0 GB VRAM)
# Контекст: 8192 токенов (с flash-attn ~0.5-0.8 GB KV-cache)
# Параметры из Before.md: Temp 0.9 + Min-P 0.1 + Repeat-Penalty 1.12
# Запуск сервера: llama-server.exe -m ... --flash-attn -ngl 99 -c 8192

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from pathlib import Path
from typing import Dict, Optional, Literal

BASE_DIR = Path(__file__).resolve().parents[3]


class ModelConfig(BaseSettings):
    """Конфигурация модели LLM."""
    name: str
    path: str
    display_name: str
    vram_mb: int = 5000
    context_size: int = 8192
    temperature: float = 0.9
    top_p: float = 0.9
    repeat_penalty: float = 1.12
    n_keep: int = 800


class Settings(BaseSettings):
    app_name: str = "Enigma — Dark Fantasy RPG"
    default_model: str = "qwen_7b"
    world_tick_minutes: int = 15
    data_dir: str = str(BASE_DIR / "backend" / "data")
    min_cpu_physical_cores: int = 4
    min_ram_gb: int = 12
    enforce_system_requirements: bool = False
    orchestrator_workers: int = 2

    llama_cpp_server_executable: str = str(
        BASE_DIR / "Models LLM" / "llama" / "llama-server.exe"
    )
    llama_cpp_executable: str = str(
        BASE_DIR / "Models LLM" / "llama" / "llama-cli.exe"
    )
    llama_cpp_model_path: str = str(
        BASE_DIR / "Models LLM" / "Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"
    )

    llama_cpp_server_url: str = "http://127.0.0.1:8080"
    llama_cpp_max_tokens: int = 1024
    llama_cpp_timeout_sec: int = 180
    model_load_timeout_sec: int = 60

    llm_servers: Dict[str, Dict[str, str]] = {}

    llm_health_check_retries: int = 5
    llm_health_check_interval_sec: int = 2
    llm_fallback_enabled: bool = False  # нет fallback — одна модель

    # ─────────────────────────────────────────────────────────────────
    # Content policy
    # ─────────────────────────────────────────────────────────────────
    hardcore_mode: bool = True

    # ─────────────────────────────────────────────────────────────────
    # GPU: RTX 3070 Ti (8 GB VRAM) + Qwen2.5-7B Q5_K_M
    # ─────────────────────────────────────────────────────────────────
    # Модель:            ~5000 MB (28 слоёв, все в VRAM)
    # KV-cache ctx=8192: ~600 MB (с flash-attn)
    # ОС + CUDA:         ~500 MB
    # Буфер:             ~1092 MB
    # ИТОГО:             ~7192 MB (88% VRAM)
    gpu_layers: int = 99    # 99 > 28 → все слои на GPU
    threads: int = 8
    ctx_size: int = 8192

    # ─────────────────────────────────────────────────────────────────
    # Генерация (из Before.md — оптимально для Dark Fantasy)
    # ─────────────────────────────────────────────────────────────────
    # Temp 0.9 + Min-P 0.1 = креативный живой текст без бреда
    # Repeat-Penalty 1.12 = защита от зацикливания фраз
    llama_cpp_temperature: float = 0.9
    llama_cpp_top_p: float = 0.9
    llama_cpp_repeat_penalty: float = 1.12
    llama_cpp_min_p: float = 0.1
    llama_cpp_n_keep: int = 800

    # ─────────────────────────────────────────────────────────────────
    # Единственная модель проекта
    # ─────────────────────────────────────────────────────────────────
    model_qwen_7b_path: str = str(
        BASE_DIR / "Models LLM" / "Qwen2.5-7B-Instruct-abliterated-v2.Q5_K_M.gguf"
    )

    # Agent → Model mapping (все агенты → одна модель)
    agent_model_map: Dict[str, str] = {
        "dm":       "qwen_7b",
        "npc":      "qwen_7b",
        "rules":    "qwen_7b",
        "memory":   "qwen_7b",
        "world":    "qwen_7b",
    }

    available_models: Dict[str, ModelConfig] = {}

    log_dir: Path = Field(
        default_factory=lambda: BASE_DIR / "backend" / "data" / "logs"
    )

    system_prompt_file: str = str(BASE_DIR / "backend" / "Promt_AI.json")

    model_config = SettingsConfigDict(
        env_prefix="AIDM_",
        env_file=".env",
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    @model_validator(mode="after")
    def ensure_log_dir(self):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return self

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # VRAM бюджет для RTX 3070 Ti (8192 MB):
        #   Qwen2.5-7B Q5_K_M:    ~5000 MB
        #   KV-cache ctx=8192:      ~600 MB (с flash-attn)
        #   ОС + CUDA runtime:      ~500 MB
        #   Буфер:                 ~1092 MB
        #   ИТОГО:                 ~7192 MB (88% VRAM)
        self.available_models = {
            "qwen_7b": ModelConfig(
                name="qwen_7b",
                path=self.model_qwen_7b_path,
                display_name="Qwen2.5-7B-Instruct-abliterated Q5_K_M",
                vram_mb=5000,
                context_size=8192,
                temperature=0.9,
                top_p=0.9,
                repeat_penalty=1.12,
                n_keep=800,
            ),
        }

        # Валидация: логируем отсутствующий файл модели
        import logging as _log
        _logger = _log.getLogger(__name__)
        for key, mcfg in self.available_models.items():
            from pathlib import Path as _Path
            if not _Path(mcfg.path).exists():
                _logger.error(
                    f"[CONFIG] Модель '{key}' ({mcfg.display_name}) "
                    f"не найдена: {mcfg.path}"
                )

    def get_context_for_agent(self, agent_name: str) -> int:
        """Бюджет контекста для агента (не больше ctx_size модели)."""
        ctx_map = {
            "dm":     3072,  # DM: SceneState + python_engines + история
            "npc":    1536,  # NPC: один персонаж, диалог
            "rules":  1024,  # Rules: точность важнее длины
            "memory": 1024,  # Memory: суммаризация
            "world":  1024,  # World: краткие события
        }
        return ctx_map.get(agent_name.lower(), 1024)

    def get_llm_server_url(self, agent_name: Optional[str] = None) -> str:
        from .runtime_config import get_llm_url
        return get_llm_url()

    def get_llm_server_config(self, agent_name: str) -> Dict[str, str]:
        from .runtime_config import get_llm_server_config
        return get_llm_server_config(agent_name)

    def check_llm_servers_health(self) -> Dict[str, bool]:
        import urllib.request
        results = {}
        checked_ports = set()
        for agent_name, cfg in self.llm_servers.items():
            host = cfg.get("host", "127.0.0.1")
            port = cfg.get("port", "8080")
            key = f"{host}:{port}"
            if key in checked_ports:
                results[agent_name] = results.get(agent_name, False)
                continue
            checked_ports.add(key)
            url = f"http://{host}:{port}"
            try:
                with urllib.request.urlopen(url, timeout=2) as resp:
                    results[agent_name] = resp.status == 200
            except Exception:
                results[agent_name] = False
        return results


# ─────────────────────────────────────────────────────────────────────────────
# ErrorInterpreter (legacy)
# ─────────────────────────────────────────────────────────────────────────────
class ErrorInterpreter:
    def __init__(self):
        self.log_file = Path("logs/startup_errors.jsonl")
        self.log_file.parent.mkdir(exist_ok=True, parents=True)

    def log_exception(self, exc: Exception):
        human_msg = f"{type(exc).__name__}: {exc}"
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(human_msg + "\n")
        return human_msg

    def simulate_startup_error(self):
        exc = RuntimeError("Simulated startup error")
        self.log_exception(exc)
        raise exc


settings = Settings()

# Константы для обратной совместимости
DATA_DIR   = Path(settings.data_dir)
MODEL_PATH = Path(settings.model_qwen_7b_path)