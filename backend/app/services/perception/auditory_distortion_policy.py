"""
path: /project/backend/app/services/perception/auditory_distortion_policy.py
Назначение: Стратегия искажения текста при плохом восприятии.
Зависимости: typing
Основные сущности: AuditoryDistortionPolicy
"""
import random

class AuditoryDistortionPolicy:
    """
    Решает, как именно исказить текст, если auditory_clarity < 1.0.
    Не режет тупо пополам, а эмулирует обрывки слуха.
    """
    @staticmethod
    def distort(text: str, clarity: float) -> str:
        if clarity >= 0.9 or not text:
            return text
        if clarity < 0.2:
            return "*невнятно*"
        
        words = text.split()
        if not words:
            return "*невнятно*"
            
        # Чем ниже clarity, тем меньше слов слышно
        keep_ratio = max(0.1, clarity)
        num_to_keep = max(1, int(len(words) * keep_ratio))
        
        # Выбираем случайные слова (эмулируя обрывки)
        kept_words = random.sample(words, num_to_keep)
        return " ".join(kept_words) + "..."