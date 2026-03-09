import os
from typing import Optional

from app.models.schemas import ModelSelection
from app.services.llama_cpp import LlamaCppAdapter
from app.services.model_router import ModelRouter
from app.core.config import settings


class LlmManager:
    """
    Facade для мультимодальной LLM системы.
    
    Поддерживает:
    - Выбор модели по агенту
    - Разные системные промпты для разных агентов
    - Router mode для подмены моделей
    """

    def __init__(self) -> None:
        self.router = ModelRouter()
        self.llama_cpp = LlamaCppAdapter()
        
        # Системные промпты для разных агентов
        self._system_prompts: dict[str, str] = {}
        self._load_system_prompts()

    def _load_system_prompts(self) -> None:
        """Загружает системные промпты для агентов."""
        # Загружаем базовый промпт DM
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            settings.system_prompt_file
        )
        
        try:
            import json
            with open(prompt_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # DM промпт - основной
                self._system_prompts["dm"] = data.get("SYSTEM PROMPT", "")
                # Для других агентов используем модифицированные версии
                self._system_prompts["npc"] = self._create_npc_prompt(data.get("SYSTEM PROMPT", ""))
                self._system_prompts["rules"] = self._create_rules_prompt()
                self._system_prompts["world"] = self._create_world_prompt()
                self._system_prompts["memory"] = self._create_memory_prompt()
        except Exception as e:
            print(f"Предупреждение: не удалось загрузить промпт: {e}")
            # Fallback промпты
            self._system_prompts["dm"] = "Ты - Dungeon Master для D&D 5e."
            self._system_prompts["npc"] = "Ты - NPC в D&D 5e кампании."
            self._system_prompts["rules"] = "Ты - эксперт по правилам D&D 5e."
            self._system_prompts["world"] = "Ты - симулятор мира D&D 5e."
            self._system_prompts["memory"] = "Ты - менеджер памяти кампании."

    def _create_npc_prompt(self, base_prompt: str) -> str:
        """Создает промпт для NPC агента."""
        return f"{base_prompt}\n\nТы играешь за персонажа. Отвечай от первого лица, как персонаж. Не описывай действия игрока."

    def _create_rules_prompt(self) -> str:
        """Создает промпт для Rules агента."""
        return """Ты - эксперт по правилам D&D 5e.
Отвечай кратко и точно.
Для действий игроков определяй:
- Нужен ли бросок d20
- Какая сложность (DC)
- Что происходит при успехе/провале

Используй правила из Player's Handbook."""

    def _create_world_prompt(self) -> str:
        """Создает промпт для World симуляции."""
        return """Ты - симулятор мира D&D 5e.
Отслеживай изменения в мире:
- НПС меняют локации
- События развиваются
- Квесты продвигаются или проваливаются
- Время течёт

Веди логику мира логично и последовательно."""

    def _create_memory_prompt(self) -> str:
        """Создает промпт для Memory агента."""
        return """Ты - менеджер памяти кампании.
Кратко суммируй важные события сессии.
Определяй:
- Ключевые решения игроков
- Изменения в мире
- Важные НПС и их состояние
- Прогресс квестов"""

    def switch_model(self, selection: ModelSelection) -> ModelSelection:
        """Ручное переключение модели."""
        return self.router.switch(selection)

    def switch_for_agent(self, agent_name: str) -> ModelSelection:
        """
        Переключить модель для указанного агента.
        
        Args:
            agent_name: dm, npc, rules, world, memory
            
        Returns:
            ModelSelection с выбранной моделью
        """
        return self.router.switch_to_agent(agent_name)

    def get_system_prompt(self, agent_name: str) -> str:
        """Получить системный промпт для агента."""
        return self._system_prompts.get(agent_name, self._system_prompts.get("dm", ""))

    def active_model(self) -> str:
        """Получить описание активной модели."""
        return self.router.describe()

    def run_for_agent(
        self,
        agent_name: str,
        user_prompt: str,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Запустить LLM для конкретного агента.
        
        Args:
            agent_name: dm, npc, rules, world, memory
            user_prompt: пользовательский промпт
            max_tokens: лимит токенов (опционально)
            
        Returns:
            Ответ от LLM
        """
        # Переключаем модель для агента
        model_selection = self.switch_for_agent(agent_name)
        
        # Получаем системный промпт
        system_prompt = self.get_system_prompt(agent_name)
        
        # Формируем полный промпт
        full_prompt = f"<system>\n{system_prompt}\n</system>\n\n<user>\n{user_prompt}\n</user>\n\n<assistant>\n"
        
        # Запускаем через llama.cpp с нужными параметрами
        model_info = self.router.get_current_model_info()
        
        if model_info:
            # Используем параметры из конфигурации модели
            return self.llama_cpp.run_prompt_with_params(
                prompt=full_prompt,
                max_tokens=max_tokens or settings.llama_cpp_max_tokens,
                temperature=model_info.temperature,
                top_p=model_info.top_p,
                repeat_penalty=model_info.repeat_penalty,
                n_keep=model_info.n_keep,
            )
        else:
            # Fallback
            return self.llama_cpp.run_prompt(full_prompt, max_tokens)

    def run(self, prompt: str, max_tokens: Optional[int] = None) -> str:
        """Запуск LLM с текущей моделью."""
        if self.router.current and self.router.current.provider.value == "llama_cpp":
            model_info = self.router.get_current_model_info()
            if model_info:
                return self.llama_cpp.run_prompt_with_params(
                    prompt=prompt,
                    max_tokens=max_tokens or settings.llama_cpp_max_tokens,
                    temperature=model_info.temperature,
                    top_p=model_info.top_p,
                    repeat_penalty=model_info.repeat_penalty,
                    n_keep=model_info.n_keep,
                )
            return self.llama_cpp.run_prompt(prompt, max_tokens)

        # Fallback для других провайдеров
        return f"[LLM:{self.active_model()}] {prompt}"

    def get_model_path(self, agent_name: str) -> Optional[str]:
        """Получить путь к модели для агента."""
        return self.router.get_agent_model_path(agent_name)

    def list_agents_and_models(self) -> dict:
        """Список агентов и их моделей."""
        return self.router.list_agents()

