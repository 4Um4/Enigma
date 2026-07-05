"""
path: /backend/app/services/verbalization/dm_response_normalizer.py
Назначение: Изоляция логики восстановления текста из разных схем LLM (DMOutput Contract Layer).
Зависимости: None
Основные сущности: DMOutput, DMResponseNormalizer
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class DMOutput:
    """Структурированный результат нормализации ответа LLM."""
    dm_text: str
    schema_type: Literal["dm_response", "npc_schema", "unknown"]

class DMResponseNormalizer:
    """Нормализует сырой ответ LLM в DMOutput, пытаясь восстановить текст из неизвестных схем."""
    
    @staticmethod
    def normalize(raw: Any) -> DMOutput:
        if isinstance(raw, str):
            # ADR-O-322: Очистка от markdown-обёрток (```json ... ```)
            import re
            _cleaned_raw = raw.strip()
            # Надёжно снимаем открывающий тег (``` или ```json)
            _cleaned_raw = re.sub(r'^```(?:json)?\s*', '', _cleaned_raw, flags=re.IGNORECASE)
            # Надёжно снимаем закрывающий тег (```), даже если есть пробелы перед ним
            _cleaned_raw = re.sub(r'\s*```\s*$', '', _cleaned_raw).strip()
            
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
            return DMOutput(
                dm_text=result["dm_response"].strip(),
                schema_type="dm_response"
            )
        
        if "speech" in result or "action" in result:
            logger.warning(f"[DM_NORMALIZER] LLM returned NPC-schema, recovering.")
            return DMOutput(
                dm_text=(result.get("speech") or result.get("action") or "").strip(),
                schema_type="npc_schema"
            )
        
        # Fallback: ищем любое длинное строковое значение
        for k, v in result.items():
            if isinstance(v, str) and len(v) > 20:
                logger.warning(f"[DM_NORMALIZER] unknown schema, using {k}.")
                return DMOutput(
                    dm_text=v.strip(),
                    schema_type="unknown"
                )
                
        return DMOutput(dm_text="", schema_type="unknown")