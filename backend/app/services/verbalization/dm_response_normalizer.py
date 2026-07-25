"""
path: /backend/app/services/verbalization/dm_response_normalizer.py
Назначение: Изоляция логики восстановления текста из разных схем LLM (DMOutput Contract Layer).
Зависимости: None
Основные сущности: DMOutput, DMResponseNormalizer
"""

import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class DMOutput:
    """Структурированный результат нормализации ответа LLM."""

    dm_text: str
    schema_type: Literal["dm_response", "npc_schema", "unknown"]


class DMResponseNormalizer:
    """Нормализует сырой ответ LLM в DMOutput, пытаясь восстановить текст из неизвестных схем."""

    # ADR-O-MEMETIC-000: Кэш словаря мата для детерминированного пост-фильтра
    _PROFANITY_ROOTS: set[str] | None = None

    # Корень проекта (на 5 уровней выше: verbalization/ -> services/ -> app/ -> backend/ -> ROOT)
    _PROJECT_ROOT = Path(__file__).resolve().parents[4]

    @classmethod
    def _get_profanity_roots(cls) -> set[str]:
        if cls._PROFANITY_ROOTS is not None:
            return cls._PROFANITY_ROOTS

        try:
            insults_path = cls._PROJECT_ROOT / "backend" / "data" / "insults_ru.json"
            if insults_path.exists():
                data = json.loads(insults_path.read_text(encoding="utf-8"))
                cls._PROFANITY_ROOTS = set(data.get("roots", []))
            else:
                cls._PROFANITY_ROOTS = set()
        except Exception as e:
            logger.warning(f"[DM_NORMALIZER] Failed to load insults_ru.json: {e}")
            cls._PROFANITY_ROOTS = set()

        return cls._PROFANITY_ROOTS

    @classmethod
    def _apply_content_policy_filter(cls, text: str) -> str:
        """Детерминированный пост-фильтр мата, если ContentPolicy запрещает (OFF)."""
        from app.core.config import settings
        policy = settings.content_policy

        # Если мат разрешен, пропускаем
        if policy.profanity_level > 0:
            return text

        roots = cls._get_profanity_roots()
        if not roots:
            return text

        text_lower = text.lower()
        for root in roots:
            if root in text_lower:
                # Silent replacement (B-plan fallback для minor NPC / DM)
                logger.info(f"[CONTENT_POLICY] Profanity detected (root='{root}'). Replacing with fallback.")
                return random.choice([
                    "Происходит неловкое молчание.",
                    "Собеседник замолкает, подбирая слова.",
                    "В воздухе повисает напряжение."
                ])

        return text

    @staticmethod
    def normalize(raw: Any) -> DMOutput:
        if isinstance(raw, str):
            # ADR-O-322: Очистка от markdown-обёрток (```json ... ```)
            import re

            _cleaned_raw = raw.strip()
            # Надёжно снимаем открывающий тег (``` или ```json)
            _cleaned_raw = re.sub(
                r"^```(?:json)?\s*", "", _cleaned_raw, flags=re.IGNORECASE
            )
            # Надёжно снимаем закрывающий тег (```), даже если есть пробелы перед ним
            _cleaned_raw = re.sub(r"\s*```\s*$", "", _cleaned_raw).strip()

            try:
                result = json.loads(_cleaned_raw)
            except Exception:
                logger.info("plain text response (no JSON)")
                return DMOutput(dm_text=raw.strip(), schema_type="unknown")
        elif isinstance(raw, dict):
            result = raw
        else:
            return DMOutput(dm_text=str(raw).strip(), schema_type="unknown")

        if not isinstance(result, dict):
            return DMOutput(dm_text=str(result).strip(), schema_type="unknown")

        if "dm_response" in result:
            _text = result["dm_response"].strip()
            return DMOutput(
                dm_text=DMResponseNormalizer._apply_content_policy_filter(_text), schema_type="dm_response"
            )

        # ADR-O-322: Восстановление npc_schema (speech/text)
        if "speech" in result or "text" in result or "narrative" in result:
            _txt = result.get("speech") or result.get("text") or result.get("narrative")
            _txt = _txt.strip()
            return DMOutput(dm_text=DMResponseNormalizer._apply_content_policy_filter(_txt), schema_type="npc_schema")

        # ADR-O-313: DM-агент не генерирует реплики NPC.
        # Если LLM вернула неизвестную схему, просто берём самое длинное строковое значение.
        # Fallback: ищем любое длинное строковое значение
        for k, v in result.items():
            if isinstance(v, str) and len(v) > 20:
                logger.warning(f"[DM_NORMALIZER] unknown schema, using {k}.")
                _v = v.strip()
                return DMOutput(dm_text=DMResponseNormalizer._apply_content_policy_filter(_v), schema_type="unknown")

        return DMOutput(dm_text="", schema_type="unknown")
