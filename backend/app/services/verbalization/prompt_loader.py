# backend\app\services\prompt_loader.py
"""
Prompt Loader - загрузчик системных промптов для LLM.

Позволяет:
- Загружать промпты из JSON файлов
- Поддерживать разные промпты для разных моделей (для будущей многомодельности)
- Кэшировать промпты в памяти
"""
import json
import os
from pathlib import Path
from typing import Optional, List

from jinja2 import Environment, FileSystemLoader, select_autoescape
try:
    from app.core.config import settings
except ImportError:
    # Fallback для запуска из корня проекта или тестов
    from backend.app.core.config import settings


class PromptLoader:
    """Загрузчик и рендерер системных промптов."""
    

    def __init__(self, prompts_dir: Optional[str] = None):
        """
        Инициализация загрузчика промптов и среды Jinja2.
        
        ЗАЧЕМ: Отделить доменную логику VerbalizationContext 
        от текстовой разметки промпта. Это позволяет гибко менять структуру 
        промпта без изменения кода DecisionHub / VerbalizationContext.
        """
        if prompts_dir:
            self.prompts_dir = Path(prompts_dir)
        else:
            # 4 уровня вверх: verbalization/ -> services/ -> app/ -> backend/
            self.prompts_dir = Path(__file__).resolve().parent.parent.parent.parent / "prompts"
            
        # Создаём папку prompts, если её нет
        self.prompts_dir.mkdir(parents=True, exist_ok=True)

        # Инициализация Jinja2
        self.env = Environment(
            loader=FileSystemLoader(str(self.prompts_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,      # Убирает лишние пустые строки от тегов {% %}
            lstrip_blocks=True,    # Убирает отступы слева внутри блоков
        )
        
        self._cache: dict[str, str] = {}


    def get_prompt_path(self, filename: str = "Promt_AI.json") -> Path:
        """
        Получить полный путь к файлу промпта.
        
        Args:
            filename: Имя файла промпта
            
        Returns:
            Полный путь к файлу
        """
        return self.prompts_dir / filename
    

    def load_prompt(self, filename: str = "Promt_AI.json", use_cache: bool = True) -> str:
        """
        Загрузить системный промпт из файла (JSON или текстовый).
        
        Args:
            filename: Имя файла промпта (по умолчанию Promt_AI.json)
            use_cache: Использовать кэширование (по умолчанию True)
            
        Returns:
            Системный промпт в виде строки
            
        Raises:
            FileNotFoundError: Если файл не найден
            ValueError: Если файл содержит невалидные данные
        """
        # Проверяем кэш
        if use_cache and filename in self._cache:
            return self._cache[filename]
        
        prompt_path = self.get_prompt_path(filename)
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Файл промпта не найден: {prompt_path}")
        
        # Пробуем сначала как JSON, потом как текст
        prompt_text = ""
        
        # Читаем файл целиком
        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        
        # Пробуем парсить как JSON
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                prompt_text = data.get("system_prompt") or data.get("system") or data.get("prompt", "")
            elif isinstance(data, str):
                prompt_text = data
        except json.JSONDecodeError:
            # Не JSON - значит это текстовый файл с промтом
            # Ищем начало и конец промта (если есть маркеры)
            prompt_text = content
            
            # Удаляем маркеры если есть
            for marker in ["SYSTEM PROMPT:", "END SYSTEM PROMPT", "SYSTEM_PROMPT:"]:
                if marker in prompt_text:
                    # Берём текст после маркера
                    parts = prompt_text.split(marker, 1)
                    if len(parts) > 1:
                        prompt_text = parts[1]
                    # Удаляем маркер завершения если есть
                    prompt_text = prompt_text.replace("END SYSTEM PROMPT", "").strip()
        
        if not prompt_text:
            raise ValueError(f"В файле промпта не найден текст промта")
        
        # Сохраняем в кэш
        if use_cache:
            self._cache[filename] = prompt_text
        
        return prompt_text
    

    def load_prompt_for_model(
        self, 
        model_name: str, 
        default_filename: str = "Promt_AI.json"
    ) -> str:
        """
        Загрузить промпт для конкретной модели (для будущей многомодельности).
        
        Args:
            model_name: Имя модели (например, "qwen2.5", "llama3.1", "saiga")
            default_filename: Имя файла промпта по умолчанию
            
        Returns:
            Системный промпт для модели
        """
        # Схема именования: Promt_AI_{model_name}.json
        model_specific_filename = f"Promt_AI_{model_name}.json"
        model_path = self.get_prompt_path(model_specific_filename)
        
        if model_path.exists():
            return self.load_prompt(model_specific_filename)
        
        # Fallback на общий промпт
        return self.load_prompt(default_filename)
    

    def clear_cache(self, filename: Optional[str] = None):
        """
        Очистить кэш промптов.
        
        Args:
            filename: Имя файла для очистки. Если None - очистить весь кэш
        """
        if filename is None:
            self._cache.clear()
        elif filename in self._cache:
            del self._cache[filename]
    

    def reload_prompt(self, filename: str = "Promt_AI.json") -> str:
        """
        Перезагрузить промпт из файла (игнорируя кэш).
        
        Args:
            filename: Имя файла промпта
            
        Returns:
            Системный промпт
        """
        self.clear_cache(filename)
        return self.load_prompt(filename, use_cache=False)


    def render_npc_prompt(
        self,
        verbalization_core: str,
        tier: str = "MINOR",
        npc_name: str = "",
        voice_profile: str = "",
        emotion: str = "нейтральное",
        narrative_hints: str = "",     # R3: Факты из памяти для EXPLAIN mode
        biography: str = "",
        max_tokens: int = 200,
        allow_profanity: bool = False, # R3: Флаг контент-политики
        template_name: str = "npc_speech.j2"
    ) -> str:
        """
        Рендерит полный промпт для вербализации NPC через Jinja2.
        
        ЗАЧЕМ:
        - VerbalizationContext передаёт только чистое ядро (intent + emotional_nuance + scene_hint).
        - PromptLoader отвечает за обёртку в tier-aware контекст, биографию, стиль речи и системный промпт.
        - Это сохраняет чистоту архитектуры: LLM получает только текст, без чисел и reasoning.
        """
        try:
            template = self.env.get_template(template_name)
        except Exception:  # TemplateNotFound или любая ошибка загрузки шаблона
            # Graceful fallback — система продолжает работать
            return f"{verbalization_core}\n\nГовори строго от первого лица. Одна короткая реплика."

        # Загружаем базовый системный промпт игры
        system_base = self.load_prompt("Promt_AI.json")

        return template.render(
            system_prompt=system_base,
            npc_name=npc_name or "Неизвестный NPC",
            tier=tier.upper(),
            voice_profile=voice_profile,
            emotion=emotion,
            verbalization_core=verbalization_core.strip(),
            narrative_hints=narrative_hints,      # R3: факты вместо сырой памяти
            allow_profanity=allow_profanity,      # R3: флаг контента
            biography=biography.strip()[:500],   # защита от слишком длинной биографии
            max_tokens=max_tokens
        )   


# Глобальный экземпляр загрузчика
_default_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """Получить глобальный экземпляр PromptLoader."""
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader


def load_system_prompt(filename: str = "Promt_AI.json") -> str:
    """
    Удобная функция для быстрой загрузки системного промпта.
    
    Args:
        filename: Имя файла промпта
        
    Returns:
        Системный промпт
    """
    loader = get_prompt_loader()
    return loader.load_prompt(filename)

