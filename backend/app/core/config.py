
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
    enforce_system_requirements: bool = False
    orchestrator_workers: int = 4
    
    # === Llama.cpp пути ===
    llama_cpp_executable: str = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama.exe"
    llama_cpp_server_executable: str = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\llama\llama-server.exe"
    llama_cpp_model_path: str = r"C:\DDD\Codex\VSC_Enigma\Enigma\Models LLM\qwen2.5-7b-instruct-q4_k_m.gguf"
    
    # === LLM Server URL (основной порт для DM агента) ===
    # ВНИМАНИЕ: Запуск llama-server на порту 8080 (see start_enigma.bat)
    llama_cpp_server_url: str = "http://127.0.0.1:8080"
    llama_cpp_max_tokens: int = 512
    llama_cpp_timeout_sec: int = 300
    
    # === Мультиагентная конфигурация LLM серверов ===
    # Каждый агент может использовать свой порт для параллельной работы
    # Если все агенты на одной машине - используется один сервер с ротацией моделей
    llm_servers: Dict[str, Dict[str, str]] = {
        "dm": {"host": "127.0.0.1", "port": "8080", "description": "DM агент - основной нарратив"},
        "npc": {"host": "127.0.0.1", "port": "8080", "description": "NPC агент - диалоги"},
        "world": {"host": "127.0.0.1", "port": "8080", "description": "World симуляция"},
        "rules": {"host": "127.0.0.1", "port": "8080", "description": "Rules агент - проверка правил"},
        "memory": {"host": "127.0.0.1", "port": "8080", "description": "Memory агент - память"},
    }
    
    # === Настройки проверки здоровья LLM сервера ===
    llm_health_check_retries: int = 5
    llm_health_check_interval_sec: int = 2
    llm_fallback_enabled: bool = True
    
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

    model_config = SettingsConfigDict(
        env_prefix="AIDM_", 
        env_file=".env", 
        extra="ignore",
        protected_namespaces=("settings_",)
    )

    def get_llm_server_url(self, agent_name: str | None = None) -> str:
        """
        Получить URL LLM сервера для указанного агента.
        
        Args:
            agent_name: Имя агента (dm, npc, world, rules, memory) или None для основного URL
            
        Returns:
            Полный URL сервера (например, http://127.0.0.1:8080)
        """
        if agent_name and agent_name in self.llm_servers:
            server_config = self.llm_servers[agent_name]
            host = server_config.get("host", "127.0.0.1")
            port = server_config.get("port", "8080")
            return f"http://{host}:{port}"
        return self.llama_cpp_server_url
    
    def get_llm_server_config(self, agent_name: str) -> Dict[str, str]:
        """
        Получить конфигурацию LLM сервера для указанного агента.
        
        Args:
            agent_name: Имя агента (dm, npc, world, rules, memory)
            
        Returns:
            Словарь с конфигурацией сервера (host, port, description)
        """
        if agent_name in self.llm_servers:
            return self.llm_servers[agent_name]
        return {"host": "127.0.0.1", "port": "8080", "description": "Default server"}
    
    def check_llm_servers_health(self) -> Dict[str, bool]:
        """
        Проверить доступность всех LLM серверов.
        
        Returns:
            Словарь {agent_name: is_available}
        """
        import urllib.request
        import urllib.error
        
        results = {}
        checked_ports = set()
        
        for agent_name, config in self.llm_servers.items():
            host = config.get("host", "127.0.0.1")
            port = config.get("port", "8080")
            key = f"{host}:{port}"
            
            # Skip already checked ports
            if key in checked_ports:
                results[agent_name] = results.get(agent_name, False)
                continue
            
            checked_ports.add(key)
            url = f"http://{host}:{port}"
            
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    results[agent_name] = resp.status == 200
            except Exception:
                results[agent_name] = False
        
        return results


settings = Settings()
