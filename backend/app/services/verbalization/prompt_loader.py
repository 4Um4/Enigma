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
import re
from pathlib import Path
from typing import Optional, List

from jinja2 import Environment, FileSystemLoader, select_autoescape
try:
    from app.core.config import settings
except ImportError:
    # Fallback для запуска из корня проекта или тестов
    from backend.app.core.config import settings

from dataclasses import dataclass
from enum import Enum


# ═══════════════════════════════════════════════════════════════════════════════
# BEHAVIOR MODE — структурный контроль, не текстовая рекомендация
# ═══════════════════════════════════════════════════════════════════════════════

class BehaviorMode(Enum):
    """Режим генерации — определяет ДОПУСТИМЫЕ действия LLM.
    
    НЕ строка в промпте — структурный сигнал, который LLM не может "проигнорировать".
    Передаётся как отдельный блок в system_prompt.
    """
    FLEXIBLE = "FLEXIBLE"      # Можно уточнять, торговаться, задавать вопросы
    STRICT = "STRICT"          # Никаких отклонений от намерения
    REACTIVE = "REACTIVE"      # Только реакция, не инициирует диалог
    SILENT = "SILENT"          # Только наблюдение, не вмешивается


# Маппинг: intent → mode (НЕ строка ограничения)
# Ключевой принцип: разные intent'ы требуют разных режимов генерации
INTENT_TO_MODE: dict[str, BehaviorMode] = {
    # Гибкие — можно уточнять и диалогировать
    "TALK": BehaviorMode.FLEXIBLE,
    "NEGOTIATE": BehaviorMode.FLEXIBLE,
    "PERSUADE": BehaviorMode.FLEXIBLE,
    "REQUEST": BehaviorMode.FLEXIBLE,
    
    # Жёсткие — никакого дрейфа от намерения
    "THREAT": BehaviorMode.STRICT,
    "ATTACK": BehaviorMode.STRICT,
    "INTIMIDATE": BehaviorMode.STRICT,
    "COMMAND": BehaviorMode.STRICT,
    
    # Реактивные — только ответ, не инициатива
    "FLEE": BehaviorMode.REACTIVE,
    "DEFEND": BehaviorMode.REACTIVE,
    "DODGE": BehaviorMode.REACTIVE,
    
    # Пассивные
    "IDLE": BehaviorMode.SILENT,
    "OBSERVE": BehaviorMode.SILENT,
    "EXPLAIN": BehaviorMode.SILENT,
}

# Default если intent не найден
_DEFAULT_MODE = BehaviorMode.STRICT


def _get_behavior_mode(intent: str) -> BehaviorMode:
    """Получить режим поведения из intent.
    
    ЗАЧЕМ: Режим генерации — структурный сигнал, не текстовая рекомендация.
    LLM не может "проигнорировать" mode блок в промпте так же легко как текст.
    """
    if not intent:
        return _DEFAULT_MODE
    
    # Нормализация: берём базовый intent без подтипов
    clean_intent = intent.strip().split("_")[0].upper()
    
    return INTENT_TO_MODE.get(clean_intent, _DEFAULT_MODE)


# Форматирование mode для промпта — структурный блок, не рекомендация
_MODE_FORMAT = """
=== РЕЖИМ ПОВЕДЕНИЯ: {mode} ===
Это не рекомендация. Это ограничение возможностей генерации.
"""
from typing import Union, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# VERBALIZATION CORE — Whitelist-контракт (источник смысла)
# ═══════════════════════════════════════════════════════════════════════════════
# Запрет: verbalization_core = str → НЕДОПУСТИМО
# Только структурированные данные. Смысл формируется ДО текста.

@dataclass(frozen=True, slots=True)
class VerbalizationCore:
    """Whitelist-контракт для ядра вербализации.
    
    Только три поля. Нельзя протащить числа, теги, internals.
    Смысл детерминирован: intent + target + scene → текст.
    
    ЗАЧЕМ: Устраняет класс багов "утечка смысла" (-60%).
    sanitize становится запасным фильтром, не основным.
    """
    intent: str   # "ATTACK", "TALK", "FLEE" — что хочет NPC
    target: str   # "игрок", "Торнин" — к кому направлено
    scene: str    # "Игрок спрашивает про эль" — что происходит
    
    def __post_init__(self):
        # Защита от пустых обязательных полей
        if not self.intent or not self.intent.strip():
            raise ValueError("VerbalizationCore.intent не может быть пустым")
    
    def to_prompt_text(self) -> str:
        """Формирует текст для промпта из структурированных данных.
        
        Единственная точка превращения смысл → текст.
        sanitize больше не главный фильтр — это просто подстраховка.
        """
        parts = [f"Намерение: {self.intent.strip().upper()}"]
        
        if self.target and self.target.strip():
            parts.append(f", цель: {self.target.strip()}")
        parts.append(".")
        
        if self.scene and self.scene.strip():
            # Sanitize на входе — защитный слой от грязных данных
            clean_scene = _sanitize_verbalization_core(self.scene.strip())
            if clean_scene:
                parts.append(f"\nСитуация: {clean_scene}")
        
        return "".join(parts)


# ═════════════════════════════════════════════════════════════════════════════════
# INTENT-DRIVEN ОГРАНИЧЕНИЯ — поведение зависит от намерения
# ═══════════════════════════════════════════════════════════════════════════════

# Маппинг: intent → дополнительные ограничения на поведение
# Ключевой принцип: ограничения не глобальны — они зависят от контекста
INTENT_CONSTRAINTS: dict[str, str] = {
    "TALK": "Можешь задавать уточняющие вопросы, если это естественно.",
    "NEGOTIATE": "Можешь торговаться и предлагать варианты.",
    "PERSUADE": "Можешь уговаривать и приводить аргументы.",
    "THREAT": "НЕ задавай вопросов. Только угроза или требование.",
    "ATTACK": "НЕ задавай вопросов. Действуй, не спрашивай разрешения.",
    "FLEE": "НЕ задавай вопросов. Только реакция бегства.",
    "INTIMIDATE": "НЕ задавай вопросы. Дави, не спрашивай.",
    "IDLE": "Короткая фраза или молчание. Не инициируй диалог.",
    "OBSERVE": "Только наблюдение. Не вмешивайся, не обращайся.",
    "EXPLAIN": "Краткое объяснение факта. Без вопросов к игроку.",
}

# Default если intent не найден в маппинге
_DEFAULT_CONSTRAINT = "Не задавай вопросы. Одна короткая фраза."


def _get_intent_constraint(intent: str) -> str:
    """Получить ограничение поведения на основе intent.
    
    ЗАЧЕМ: Разные намерения требуют разного поведения.
    TALK можно уточнять, THREAT нельзя.
    
    ПРИОРИТЕТЫ:
    1. Точное совпадение (ATTACK_BRUTAL → свой constraint)
    2. Базовый intent (ATTACK_BRUTAL → ATTACK)
    3. Semantic fallback (хук для будущей классификации)
    """
    if not intent:
        return _semantic_fallback(intent)
    
    clean_intent = intent.strip().upper()
    
    # Уровень 1: точное совпадение
    if clean_intent in INTENT_CONSTRAINTS:
        return INTENT_CONSTRAINTS[clean_intent]
    
    # Уровень 2: базовый intent (до "_")
    base_intent = clean_intent.split("_")[0]
    if base_intent in INTENT_CONSTRAINTS:
        return INTENT_CONSTRAINTS[base_intent]
    
    # Уровень 3: semantic fallback (точка расширения)
    return _semantic_fallback(clean_intent)


def _semantic_fallback(intent: str) -> str:
    """Fallback для неизвестных intent'ов.
    
    ЗАЧЕМ: Точка расширения — когда появятся подтипы (GOAP),
    здесь включится классификация без переписывания _get_intent_constraint.
    
    ТЕКУЩЕЕ: простой дефолт.
    БУДУЩЕЕ: semantic class mapping.
    """
    return _DEFAULT_CONSTRAINT


# ═══════════════════════════════════════════════════════════════════════════════
# СЛОЙ РАЗРЕШЕНИЯ КОНФЛИКТОВ: State (Emotion/Scene) > Intent > Constraint
# ═══════════════════════════════════════════════════════════════════════════════

# Эмоции, которые создают конфликт с "мягкими" intent'ами
_DANGER_EMOTIONS: set[str] = {
    "ярость", "в ярости", "бешенство", "в бешенстве",
    "паника", "в панике", "страх парализует",
}

# Слова в scene, которые создают конфликт
_DANGER_SCENE_WORDS: set[str] = {
    "готов убить", "достаёт оружие", "хватается за нож", "нападает",
    "бросается на", "замахивается",
}

# Intent'ы, уязвимые к конфликту (допускают вопросы/диалог)
_SOFT_INTENTS: set[str] = {"TALK", "NEGOTIATE", "PERSUADE", "EXPLAIN"}

# Ужесточённый constraint для конфликтных ситуаций
_STRICT_OVERRIDE_CONSTRAINT: str = "НЕ задавай вопросов. Только реакция на угрозу или действие."


def detect_semantic_conflict(intent: str, emotion: str, scene: str) -> bool:
    """Детектирует конфликт между intent и эмоциональным/сценовым контекстом.
    
    ЗАЧЕМ: TALK intent + "в ярости" = поведенческий гибрид.
    Лучше ужесточить constraint, чем позволить LLM решить сама.
    """
    if intent not in _SOFT_INTENTS:
        return False
    
    emotion_lower = emotion.lower()
    scene_lower = scene.lower()
    
    if any(danger in emotion_lower for danger in _DANGER_EMOTIONS):
        return True
    
    if any(danger in scene_lower for danger in _DANGER_SCENE_WORDS):
        return True
    
    return False


def resolve_effective_constraint(intent: str, emotion: str, scene: str) -> str:
    """Разрешает конфликт слоёв и возвращает финальный constraint.
    
    ЗАЧЕМ: Intent не абсолютен — emotion/scene могут его ужесточить.
    Но мы НЕ меняем intent (Core свят), мы ужесточаем constraint.
    
    ПРИНЦИП: State (Emotion/Scene) > Intent > Constraint.
    """
    if detect_semantic_conflict(intent, emotion, scene):
        return _STRICT_OVERRIDE_CONSTRAINT
    
    return _get_intent_constraint(intent)


# Константы лимитов для NPC промпта (защита от деградации токенного бюджета)
VERBALIZATION_CORE_MAX_LEN = 300    # ~75 токенов — текущая ситуация
VOICE_PROFILE_MAX_LEN = 150         # ~40 токенов — стиль речи
EMOTION_MAX_LEN = 100               # ~25 токенов — эмоциональный фон


def _sanitize_verbalization_core(core: str) -> str:
    """Удаляет технические данные и ограничивает длину verbalization_core.
    
    NPC должен видеть описания, а не машинные параметры.
    Это граница системы — последняя точка контроля.
    
    Приоритет секций (при нехватке контекста):
    1. core — что происходит (обязательно)
    2. emotion — эмоциональный фон
    3. voice — стиль речи
    4. biography — опционально (может быть отброшена)
    """
    if not core:
        return core
    
    # Паттерны технических данных (case-insensitive)
    patterns = [
        r'\b\w+:\s*-?\d+\.?\d*\b',        # stress: 85, trust: -25
        r'\bscore\s*=\s*[\d.]+\b',          # score=0.73
        r'\bcommitment\s*=\s*[\d.]+\b',     # commitment=0.9
        r'\bintent\s*=\s*\w+\b',            # intent=ATTACK
        r'\bdelta_\w+\s*=\s*[+-]?\d+\b',    # delta_stress=+10
        r'\[\w+\]',                          # [SYSTEM], [DEBUG], [INTERNAL]
        r'\bwill\s*=\s*[\d.]+\b',           # will=0.5
    ]
    
    result = core
    for pattern in patterns:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    # Убираем артефакты очистки
    result = re.sub(r',\s*,', ',', result)
    result = re.sub(r'^\s*,\s*', '', result)
    result = re.sub(r',\s*$', '', result)
    result = re.sub(r'\s{2,}', ' ', result).strip()
    
    # Ограничение длины — обрезка на границе предложения/слова
    if len(result) > VERBALIZATION_CORE_MAX_LEN:
        result = result[:VERBALIZATION_CORE_MAX_LEN]
        # Приоритет: точка > запятая > пробел (чтобы не разрывать слово)
        last_dot = result.rfind('.')
        last_comma = result.rfind(',')
        last_space = result.rfind(' ')
        
        # Берём лучший вариант, но не раньше половины лимита
        candidates = [
            (last_dot, '.'), 
            (last_comma, ','), 
            (last_space, '')
        ]
        for pos, suffix in candidates:
            if pos > VERBALIZATION_CORE_MAX_LEN // 2:
                result = result[:pos].rstrip() + suffix
                break
    
    return result if result else "Ситуация в сцене"


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
        verbalization_core: VerbalizationCore,
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
        - VerbalizationCore (whitelist) — единственный источник смысла.
        - str НЕ допускается — миграция завершена.
        - to_prompt_text() — единственная точка смысл → текст.
        """
        # Типовая проверка — early fail если кто-то передал строку
        if not isinstance(verbalization_core, VerbalizationCore):
            raise TypeError(
                f"verbalization_core должен быть VerbalizationCore, "
                f"получен {type(verbalization_core).__name__}"
            )
        
        # Единственная точка смысл → текст
        core_text = verbalization_core.to_prompt_text()
        try:
            template = self.env.get_template(template_name)
        except Exception:  # TemplateNotFound или любая ошибка загрузки шаблона
            # Graceful fallback — система продолжает работать
            return f"{core_text}\n\nГовори строго от первого лица. Одна короткая реплика."

        # Загружаем NPC системный промпт (НЕ DM промпт!)
        # Чистый текстовый файл — без комментариев и кода
        npc_sys_path = self.get_prompt_path("npc_system.txt")
        if npc_sys_path.exists():
            with open(npc_sys_path, "r", encoding="utf-8") as f:
                system_base = f.read().strip()
        else:
            # Fallback если файл отсутствует
            system_base = (
                "Ты — персонаж игрового мира. Говори от первого лица.\n"
                "Одна короткая реплика. Не придумывай действия за других.\n"
                "Не возвращай JSON. Не задавай вопросы."
            )
        
        # Добавляем режим поведения — структурный сигнал, не текстовая рекомендация
        mode = _get_behavior_mode(verbalization_core.intent)
        system_base += _MODE_FORMAT.format(mode=mode.value)
        
        # Разрешение конфликта: emotion/scene могут ужесточить constraint
        constraint = resolve_effective_constraint(
            intent=verbalization_core.intent,
            emotion=emotion,
            scene=verbalization_core.scene,
        )
        system_base += f"\nОГРАНИЧЕНИЕ: {constraint}"

        return template.render(
            system_prompt=system_base,
            npc_name=npc_name or "Неизвестный NPC",
            tier=tier.upper(),
            voice_profile=voice_profile.strip()[:VOICE_PROFILE_MAX_LEN],
            emotion=emotion.strip()[:EMOTION_MAX_LEN],
            verbalization_core=core_text,
            narrative_hints=narrative_hints.strip()[:200] if narrative_hints else "",
            allow_profanity=allow_profanity,
            biography=biography.strip()[:500],
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

