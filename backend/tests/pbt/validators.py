# backend/tests/pbt/validators.py
"""
Валидаторы инвариантов для Property-Based Testing (Подсистема 1, Этап 1.2).

Запуск: 
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class CausalDriftReport:
    """Отчёт о дрейфе каузальной согласованности."""
    unexplained_changes: List[str] = field(default_factory=list)
    
    def has_causal_chain(self) -> bool:
        """Возвращает True, если все изменения объяснимы."""
        return len(self.unexplained_changes) == 0

class CausalProvenanceValidator:
    """
    Инвариант I: Causal Provenance.
    Любое изменение наблюдаемого состояния должно быть объяснимо конечной причинной цепью.
    В базовой реализации: если NPC не был целью InterventionEvent и изменил стейт — это дрейф.
    """
    @staticmethod
    def validate(snapshot_before: Dict[str, Any], snapshot_after: Dict[str, Any], intervention: Dict[str, Any]) -> CausalDriftReport:
        report = CausalDriftReport()
        target_id = intervention.get("target_id")
        
        npcs_before = {n["id"]: n for n in snapshot_before.get("npcs", [])}
        npcs_after = {n["id"]: n for n in snapshot_after.get("npcs", [])}
        
        for npc_id, npc_after in npcs_after.items():
            npc_before = npcs_before.get(npc_id)
            if npc_before is None:
                # Появление нового NPC без причины
                report.unexplained_changes.append(f"NPC {npc_id} appeared without cause")
                continue
                
            # Простая проверка: если стейт изменился, но NPC не был целью — это нарушение
            if npc_before != npc_after and npc_id != target_id:
                report.unexplained_changes.append(f"NPC {npc_id} changed state without being intervention target")
                
        return report