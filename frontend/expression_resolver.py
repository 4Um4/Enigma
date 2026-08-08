"""
path: /frontend/expression_resolver.py
Назначение: Data-driven движок разрешения визуальных состояний (S174).
Оценивает кандидатов (ExpressionCandidate) на основе наблюдаемых данных (PerceivedEntity)
и правил из visual_casting конфига NPC.
Зависимости: dataclasses, typing
Основные сущности: ExpressionResolver, ExpressionResult
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class ExpressionResult:
    """Результат разрешения визуального состояния."""
    expression_id: str
    asset: Optional[List]
    rule_id: Optional[str] = None
    priority: int = 0

class ExpressionResolver:
    """Разрешает визуальное состояние NPC на основе data-driven правил."""

    def resolve(self, entity: Any, casting_config: Optional[Dict]) -> ExpressionResult:
        """
        Возвращает ExpressionResult для наиболее подходящего выражения.
        Если ничего не подошло — возвращает fallback.
        """
        if not casting_config:
            return ExpressionResult(expression_id="neutral", asset=None)

        rules = casting_config.get("rules", [])
        best_candidate: Optional[ExpressionResult] = None

        for rule in rules:
            if self._check_evidence(entity, rule.get("evidence", [])):
                priority = rule.get("priority", 0)
                if not best_candidate or priority > best_candidate.priority:
                    best_candidate = ExpressionResult(
                        expression_id=rule.get("expression_id", "unknown"),
                        asset=rule.get("asset"),
                        rule_id=rule.get("rule_id"),
                        priority=priority
                    )

        if best_candidate:
            return best_candidate

        # Фоллбэк на нейтральное состояние
        fallback = casting_config.get("fallback", {})
        return ExpressionResult(
            expression_id=fallback.get("expression_id", "neutral"),
            asset=fallback.get("asset"),
            priority=-1
        )

    def _check_evidence(self, entity: Any, evidence: List[Dict]) -> bool:
        """Проверяет, выполняются ли все условия из массива evidence."""
        if not evidence:
            return False
            
        for condition in evidence:
            field = condition.get("field")
            op = condition.get("op")
            val = condition.get("value")
            
            entity_val = getattr(entity, field, None)
            if entity_val is None:
                return False
                
            try:
                if op == "==" and not (entity_val == val): return False
                elif op == "!=" and not (entity_val != val): return False
                elif op == ">" and not (float(entity_val) > float(val)): return False
                elif op == "<" and not (float(entity_val) < float(val)): return False
                elif op == ">=" and not (float(entity_val) >= float(val)): return False
                elif op == "<=" and not (float(entity_val) <= float(val)): return False
            except (ValueError, TypeError):
                return False
                
        return True