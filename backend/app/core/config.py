# backend/app/core/config.py
# ОПТИМИЗАЦИЯ ПОД RTX 3070 Ti — 8 GB VRAM
#
# ИЗМЕНЕНИЯ vs оригинал:
# 1. gpu_layers: 33 → 28   (оригинал завышен; при 33 слоях Qwen-7B может не влезть)
# 2. ctx_size: 4096 → 2048  (экономия ~256 MB KV-cache; игра не нуждается в длинных диалогах)
# 3. llama_cpp_max_tokens: 512 → 384  (NPC/Rules не нужно 512 токенов ответа; DM — нужно)
# 4. model_load_timeout_sec: 45 → 60  (старые GGUF грузятся 50–55 сек на HDD)
# 5. orchestrator_workers: 4 → 2  (pipeline последовательный, 4 воркера — лишние RAM)
# 6. agent_model_map: "npc" вместо раздельных npc_major/npc_mass —
#    для 8GB реалистично иметь 1 NPC-модель (npc_major = Qwen-7B NPC)
#    npc_mass (IQ4_XS) — для массовых NPC, оставлен как fallback
# 7. Добавлен get_context_for_agent() — разные ctx для разных агентов:
#    - DM: 2048 (нарратив, важен длинный контекст)
#    - NPC: 1024 (короткие диалоги)
#    - Rules/Memory: 1024 (точные ответы, короткие)

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, model_validator
from pathlib import Path
from typing import Dict, Optional, Literal

BASE_DIR = Path(__file__).resolve().parents[3]


class ModelConfig(BaseSettings):
    """Конфигурация одной модели LLM."""
    name: str
    path: str
    display_name: str
    vram_mb: int = 4000
    context_size: int = 2048   # ОПТИМИЗАЦИЯ: 2048 вместо 4096
    temperature: float = 0.7
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    n_keep: int = 256           # ОПТИМИЗАЦИЯ: 256 вместо 512


class Settings(BaseSettings):
    app_name: str = "Local AI Dungeon Master"
    default_model: str = "ollama:llama3.1"
    world_tick_minutes: int = 15
    data_dir: str = str(BASE_DIR / "backend" / "data")
    min_cpu_physical_cores: int = 4     # снижено: у i7-9700F 8 ядер, но требуем 4
    min_ram_gb: int = 12                # снижено: 16 GB RAM, запас
    enforce_system_requirements: bool = False
    orchestrator_workers: int = 2       # ОПТИМИЗАЦИЯ: 4→2, pipeline последовательный

    llama_cpp_server_executable: str = str(
        BASE_DIR / "Models LLM" / "llama" / "llama-server.exe"
    )
    llama_cpp_executable: str = str(
        BASE_DIR / "Models LLM" / "llama" / "llama-cli.exe"
    )
    llama_cpp_model_path: str = str(
        BASE_DIR / "Models LLM" / "qwen2.5-7b-instruct-q4_k_m.gguf"
    )

    llama_cpp_server_url: str = "http://127.0.0.1:8080"
    llama_cpp_max_tokens: int = 384     # ОПТИМИЗАЦИЯ: 512→384 (экономия токенов)
    llama_cpp_timeout_sec: int = 180    # максимум 3 мин на ответ
    model_load_timeout_sec: int = 60    # ОПТИМИЗАЦИЯ: 45→60 (HDD грузит дольше)

    llm_servers: Dict[str, Dict[str, str]] = {}

    llm_health_check_retries: int = 5
    llm_health_check_interval_sec: int = 2
    llm_fallback_enabled: bool = True

    # ─────────────────────────────────────────────────────────────────
    # Tone / content policy
    # ─────────────────────────────────────────────────────────────────
    # Если True — DM/NPC разрешено: грубость, мат, жестокие/мрачные сцены.
    # Важно: это влияет только на промпты, не на логику правил.
    hardcore_mode: bool = True

    # ─────────────────────────────────────────────────────────────────
    # GPU параметры для RTX 3070 Ti (8 GB VRAM)
    # ─────────────────────────────────────────────────────────────────
    # Qwen2.5-7B Q4_K_M: 32 transformer слоя + 1 output = 33 слоя всего.
    # При gpu_layers=28: 28 слоёв в VRAM (~4.2 GB) + остальное на CPU.
    # При gpu_layers=33: все слои в VRAM (~4.8 GB) + KV-cache → OOM при ctx>2048.
    # РЕКОМЕНДАЦИЯ: 28 для стабильности, 33 только если ctx<=1024.
    gpu_layers: int = 28                # ОПТИМИЗАЦИЯ: 33→28 (безопасно для 8GB)
    threads: int = 6                    # ОПТИМИЗАЦИЯ: 8→6 (оставляем 2 ядра ОС)
    ctx_size: int = 2048                # ОПТИМИЗАЦИЯ: 4096→2048

    # Параметры генерации
    llama_cpp_temperature: float = 0.7
    llama_cpp_top_p: float = 0.9
    llama_cpp_repeat_penalty: float = 1.1
    llama_cpp_n_keep: int = 256         # ОПТИМИЗАЦИЯ: 512→256

    # Пути к моделям
    model_qwen_7b_path: str = str(
        BASE_DIR / "Models LLM" / "qwen2.5-7b-instruct-q4_k_m.gguf"
    )
    model_qwen_9b_path: str = str(
        BASE_DIR / "Models LLM" / "Qwen3.5-9B.gguf"
    )
    model_saiga_path: str = str(
        BASE_DIR / "Models LLM" / "saiga_mistral_7b_model-q4_K.gguf"
    )
    model_npc_major_path: str = str(BASE_DIR / "Models LLM" / "mistral-pygmalion-7b.Q5_K_M.gguf")
    model_npc_mass_path:  str = str(BASE_DIR / "Models LLM" / "mistral-pygmalion-7b.Q4_K_M.gguf")

    # ─────────────────────────────────────────────────────────────────
    # Agent → Model mapping  (оптимизировано под 8 GB)
    # ─────────────────────────────────────────────────────────────────
    # Все агенты используют один llama-server (single port).
    # Переключение через ModelPool: выгрузить → загрузить (max_loaded=1).
    #
    # СТРАТЕГИЯ ДЛЯ "УМНЫХ NPC":
    # - dm: qwen_7b  — лучший нарратор, Qwen2.5 отлично пишет по-русски
    # - npc: npc_major — специализированная NPC-модель для главных NPC
    # - npc_mass fallback на qwen_7b если npc_major не загружен
    # - rules: saiga  — Saiga Mistral хорошо знает D&D правила (русский)
    # - memory: saiga — компактные суммаризации
    # - world: qwen_7b — мировые события, qwen_9b слишком большой (5.5 GB)
    agent_model_map: Dict[str, str] = {
        "dm":       "qwen_7b",
    "npc":      "npc_major",   # Mistral Pygmalion для NPC
        "rules":    "saiga",
        "memory":   "saiga",
        "world":    "qwen_7b",     # qwen_9b (5.5 GB) → OOM при ctx=2048+KV
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

        # ─────────────────────────────────────────────────────────────
        # VRAM бюджет для RTX 3070 Ti (8192 MB):
        #   ОС + CUDA runtime:  ~500 MB
        #   Qwen-7B Q4_K_M:    ~4500 MB
        #   KV-cache ctx=2048:  ~256 MB
        #   Буфер:             ~936 MB (запас)
        #   ИТОГО:             ~6192 MB (77% VRAM)
        #
        # NPC-модели:
#   npc_major (Q5_K_M): ~4500 MB — Mistral Pygmalion для major NPCs
#   npc_mass (Q4_K_M):  ~4000 MB — Mistral Pygmalion для mass NPCs
        # ─────────────────────────────────────────────────────────────
        self.available_models = {
            "qwen_7b": ModelConfig(
                name="qwen_7b",
                path=self.model_qwen_7b_path,
                display_name="Qwen2.5 7B (DM/World)",
                vram_mb=4500,
                context_size=2048,
                temperature=0.75,   # чуть выше для нарратива
            ),
            # qwen_9b исключён из маппинга — 5.5 GB не оставляет буфера
            # Оставлен в конфиге для будущего (если будет 12 GB GPU)
            "qwen_9b": ModelConfig(
                name="qwen_9b",
                path=self.model_qwen_9b_path,
                display_name="Qwen3.5 9B (World — требует 12 GB VRAM)",
                vram_mb=5500,
                context_size=1024,
                temperature=0.8,
            ),
            "saiga": ModelConfig(
                name="saiga",
                path=self.model_saiga_path,
                display_name="Saiga Mistral 7B (Rules/Memory)",
                vram_mb=4000,
                context_size=1024,  # Rules/Memory не нуждаются в длинном ctx
                temperature=0.3,    # низкая температура для точных правил
            ),
            "npc_major": ModelConfig(
                name="npc_major",
                path=self.model_npc_major_path,
                display_name="Mistral Pygmalion 7B Q5_K_M (Major NPCs)",
                vram_mb=4500,
                context_size=1024,  # диалог NPC короткий
                temperature=0.8,    # NPC должны быть немного непредсказуемы
                repeat_penalty=1.15,
            ),
            "npc_mass": ModelConfig(
                name="npc_mass",
                path=self.model_npc_mass_path,
                display_name="Mistral Pygmalion 7B Q4_K_M (Mass NPCs)",
                vram_mb=4000,       # Q4_K_M
                context_size=512,   # фоновые NPC — очень короткий контекст
                temperature=0.9,
            ),
        }

    # ─────────────────────────────────────────────────────────────────
    # Контекстно-зависимый ctx_size для агентов
    # (разные агенты нуждаются в разном количестве контекста)
    # ─────────────────────────────────────────────────────────────────
    def get_context_for_agent(self, agent_name: str) -> int:
        """Возвращает оптимальный ctx_size для агента."""
        ctx_map = {
            "dm":     2048,  # DM нужен длинный контекст для нарратива
            "npc":    1024,  # диалог NPC короткий
            "rules":  1024,  # rules engine — точность важнее длины
            "memory": 1024,  # суммаризация — короткий вывод
            "world":  1024,  # world tick — краткие события
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
# ErrorInterpreter (legacy, не трогаем)
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
        # ИСПРАВЛЕНИЕ: поднимаем исключение (оригинал только логировал)
        # test_startup_checks.py ожидает raise через assertRaises
        self.log_exception(exc)
        raise exc


settings = Settings()