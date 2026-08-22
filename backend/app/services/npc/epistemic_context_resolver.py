# backend/app/services/npc/epistemic_context_resolver.py
"""
path: /project/backend/app/services/npc/epistemic_context_resolver.py
Назначение: Проецирует сырые EpistemicRecord в EpistemicContext для DecisionHub.
Зависимости: app.domain.epistemology, app.services.npc.epistemic_store
"""

import logging
from app.domain.epistemology import EpistemicContext, EpistemicRecord, Predicate
from app.services.npc.epistemic_store import EpistemicStore

logger = logging.getLogger(__name__)

# S188: Архитектурный порог уверенности. 
# Убеждения ниже этого порога не формируют perceived threats/allies.
CONFIDENCE_THRESHOLD = 0.5

class EpistemicContextResolver:
    """
    Преобразует EpistemicStore -> EpistemicContext.
    Чистая функция (Read-Only). Не мутирует Store.
    """
    def __init__(self, store: EpistemicStore):
        self._store = store

    def get_confidence_for_subject(self, agent_id: str, subject_id: str) -> float:
        """S211 (§18): проекция убеждения агента о КОНКРЕТНОМ субъекте.

        Возвращает максимальную confidence по пропозициям с данным subject_id
        (polarity=True; опровержения считаются отдельными записями и в
        максимум не смешиваются). 0.0 = агент ничего не считает о субъекте.
        Гейт игровых возможностей (ACCUSE/BLACKMAIL-future) читает ТОЛЬКО
        этот API — никакой прямой доступ к Store вне резолвера (S208).
        """
        best = 0.0
        for r in self._store.get_all_for_agent(agent_id):
            if (r.proposition.subject_id == subject_id
                    and r.proposition.polarity
                    and r.confidence > best):
                best = r.confidence
        return best

    def resolve(self, agent_id: str) -> EpistemicContext:
        records = self._store.get_all_for_agent(agent_id)
        
        threats = []
        allies = []
        violations = 0
        max_conf = 0.0
        # S197: Сохраняем утверждение с максимальной уверенностью для Causal Provenance.
        _trigger_prop = None

        for record in records:
            if record.confidence < CONFIDENCE_THRESHOLD:
                continue
                
            pred = record.proposition.predicate
            subj = record.proposition.subject_id
            
            if record.confidence > max_conf:
                max_conf = record.confidence
                _trigger_prop = record.proposition

            if pred in [Predicate.STOLE, Predicate.ATTACKED]:
                if subj not in threats:
                    threats.append(subj)
                violations += 1
            elif pred == Predicate.HELPED:
                if subj not in allies:
                    allies.append(subj)

        return EpistemicContext(
            agent_id=agent_id,
            perceived_threats=tuple(threats),
            perceived_allies=tuple(allies),
            perceived_violations=violations,
            max_confidence=max_conf,
            trigger_proposition=_trigger_prop
        )

    @staticmethod
    def to_modifiers(
        context: EpistemicContext, archetype: str = ""
    ) -> dict[str, float]:
        """
        S188: Преобразует EpistemicContext в нейтральные decision modifiers.
        DecisionHub получает только числа, не зная об эпистемической семантике.

        S211 (слой 3, R7): архетип-дифференциация. Один и тот же belief
        ведёт к разным действиям по натуре агента (disposition-веса поверх
        epistemic_boost). archetype="" → прежнее поведение (обратная
        совместимость: все существующие вызовы не тронуты).
        """
        modifiers = {}
        if context.perceived_threats:
            # S189/S198: базовый буст = confidence × 1.5.
            _epistemic_boost = round(context.max_confidence * 1.5, 4)
            if archetype:
                from app.domain.epistemic_dispositions import (
                    get_epistemic_disposition,
                )
                _disp = get_epistemic_disposition(archetype)
                for _intent, _weight in _disp.items():
                    if _weight > 0.0:
                        modifiers[_intent] = round(_epistemic_boost * _weight, 4)
                # block_path — не диспозиция, а общий прессинг (все архетипы)
                modifiers["block_path"] = round(_epistemic_boost * 0.5, 4)
            else:
                # Легаси-ветка (S198): плоский warn=attack=boost — точка
                # R7-монокультуры, сохранена для вызовов без архетипа.
                modifiers["warn"] = _epistemic_boost
                modifiers["attack"] = _epistemic_boost
                modifiers["block_path"] = round(_epistemic_boost * 0.5, 4)
            
        # Союзники могут слегка повышать trade/help/approach
        if context.perceived_allies:
            _ally_boost = round(context.max_confidence * 0.2, 4)
            modifiers["trade"] = _ally_boost
            modifiers["help"] = _ally_boost
            
        return modifiers