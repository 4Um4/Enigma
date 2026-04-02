# C:\DDD\Codex\VSC_Enigma\Enigma\backend\app\core\config.py
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
        BASE_DIR / "Models LLM" / "gemma-3-12b-it-q4_k_m.gguf"
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
    # GPU параметры для RTX 3070 Ti (8 GB VRAM) — Фаза M: Gemma-3-12B
    # ─────────────────────────────────────────────────────────────────
    # Gemma-3-12B Q4_K_M: ~7.0 GB в VRAM при ctx=4096
    # gpu_layers=38 — все слои в VRAM (Gemma-3 имеет 46 слоёв,
    # 38 в VRAM даёт ~6.8 GB; остаток на CPU но это embedding слои)
    # ctx=4096 — Gemma держит длинный контекст без деградации
    gpu_layers: int = 38                # Обновлено для Gemma-3-12B
    threads: int = 6
    ctx_size: int = 4096                # Увеличено: Gemma держит 4096 стабильно

    # Параметры генерации
    llama_cpp_temperature: float = 0.7
    llama_cpp_top_p: float = 0.9
    llama_cpp_repeat_penalty: float = 1.1
    llama_cpp_n_keep: int = 256         # ОПТИМИЗАЦИЯ: 512→256

    # Пути к моделям
    model_qwen_7b_path: str = str(
        BASE_DIR / "Models LLM" / "qwen2.5-7b-instruct-q4_k_m.gguf"  # отсутствует локально
    )
    model_qwen_9b_path: str = str(
        BASE_DIR / "Models LLM" / "Qwen3.5-9B.gguf"
    )
    model_saiga_path: str = str(
        BASE_DIR / "Models LLM" / "saiga_mistral_7b_model-q4_K.gguf"  # отсутствует локально
    )
    model_npc_major_path: str = str(BASE_DIR / "Models LLM" / "mistral-pygmalion-7b.Q5_K_M.gguf")
    model_npc_mass_path:  str = str(BASE_DIR / "Models LLM" / "mistral-pygmalion-7b.Q5_K_M.gguf")
    model_yandex_path:    str = str(BASE_DIR / "Models LLM" / "YandexGPT-5-Lite-8B-instruct-Q4_K_M.gguf")
    # Фаза M: Gemma-3-12B — основная модель для всех агентов
    model_gemma_12b_path: str = str(BASE_DIR / "Models LLM" / "gemma-3-12b-it-q4_k_m.gguf")

    # ─────────────────────────────────────────────────────────────────
    # Agent → Model mapping  (Фаза M: все агенты → Gemma-3-12B)
    # ─────────────────────────────────────────────────────────────────
    # Одна сильная 12B модель вместо пяти слабых 7B.
    # Преимущества: нет задержек переключения, стабильный instruction-following,
    # согласованное поведение DM и NPC, лучший русский язык.
    # Старые модели оставлены в available_models как _fallback.
    agent_model_map: Dict[str, str] = {
        "dm":       "gemma_12b",
        "npc":      "gemma_12b",
        "rules":    "gemma_12b",
        "memory":   "gemma_12b",
        "world":    "gemma_12b",
        # Fallback: если gemma недоступна — Qwen 7B
        "_fallback": "qwen_7b",
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
            # ── ФАЗА M: Основная модель ──────────────────────────────────────
            "gemma_12b": ModelConfig(
                name="gemma_12b",
                path=self.model_gemma_12b_path,
                display_name="Gemma-3-12B IT Q4_K_M (все агенты)",
                vram_mb=7000,
                context_size=4096,
                temperature=0.7,
                repeat_penalty=1.05,
            ),
            # ── Резервные модели (присутствуют локально) ─────────────────────
            "npc_major": ModelConfig(
                name="npc_major",
                path=self.model_npc_major_path,
                display_name="Mistral Pygmalion 7B Q5_K_M (Major NPCs)",
                vram_mb=4500,
                context_size=1024,
                temperature=0.8,
                repeat_penalty=1.15,
            ),
            "npc_mass": ModelConfig(
                name="npc_mass",
                path=self.model_npc_mass_path,   # тот же Q5 файл
                display_name="Mistral Pygmalion 7B Q5_K_M (Mass NPCs fallback)",
                vram_mb=4500,
                context_size=512,
                temperature=0.9,
            ),
            "qwen_9b": ModelConfig(
                name="qwen_9b",
                path=self.model_qwen_9b_path,
                display_name="Qwen3.5 9B (требует 12 GB VRAM)",
                vram_mb=5500,
                context_size=1024,
                temperature=0.8,
            ),
            "yandex_8b": ModelConfig(
                name="yandex_8b",
                path=self.model_yandex_path,
                display_name="YandexGPT-5 Lite 8B Q4_K_M (резерв)",
                vram_mb=5000,
                context_size=2048,
                temperature=0.7,
            ),
            # ── Отсутствуют локально (оставлены для будущего) ────────────────
            "qwen_7b": ModelConfig(
                name="qwen_7b",
                path=self.model_qwen_7b_path,    # файла нет — не использовать
                display_name="Qwen2.5 7B [ОТСУТСТВУЕТ]",
                vram_mb=4500,
                context_size=2048,
                temperature=0.75,
            ),
            "saiga": ModelConfig(
                name="saiga",
                path=self.model_saiga_path,      # файла нет — не использовать
                display_name="Saiga Mistral 7B [ОТСУТСТВУЕТ]",
                vram_mb=4000,
                context_size=1024,
                temperature=0.3,
            ),
        }

        # ── Валидация на старте: логируем отсутствующие файлы ────────────────
        import logging as _log
        _logger = _log.getLogger(__name__)
        for key, mcfg in self.available_models.items():
            from pathlib import Path as _Path
            if not _Path(mcfg.path).exists():
                _logger.warning(
                    f"[CONFIG] Модель '{key}' ({mcfg.display_name}) "
                    f"не найдена: {mcfg.path}"
                )

    # ─────────────────────────────────────────────────────────────────
    # Контекстно-зависимый ctx_size для агентов
    # (разные агенты нуждаются в разном количестве контекста)
    # ─────────────────────────────────────────────────────────────────
    def get_context_for_agent(self, agent_name: str) -> int:
        """Возвращает оптимальный ctx_size для агента.
        Gemma-3-12B держит 4096 стабильно — увеличены бюджеты."""
        ctx_map = {
            "dm":     2048,  # DM: SceneState + python_engines + история
            "npc":    1024,  # NPC: один персонаж, короткий диалог
            "rules":  1024,  # Rules: точность важнее длины
            "memory": 1024,  # Memory: суммаризация — короткий вывод
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

# Константы для обратной совместимости с тестами
DATA_DIR   = Path(settings.data_dir)
MODEL_PATH = Path(settings.model_gemma_12b_path)