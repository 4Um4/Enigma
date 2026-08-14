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

    def resolve(self, agent_id: str) -> EpistemicContext:
        records = self._store.get_all_for_agent(agent_id)
        
        threats = []
        allies = []
        violations = 0
        max_conf = 0.0

        for record in records:
            if record.confidence < CONFIDENCE_THRESHOLD:
                continue
                
            pred = record.proposition.predicate
            subj = record.proposition.subject_id
            max_conf = max(max_conf, record.confidence)

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
            max_confidence=max_conf
        )

    @staticmethod
    def to_modifiers(context: EpistemicContext) -> dict[str, float]:
        """
        S188: Преобразует EpistemicContext в нейтральные decision modifiers.
        DecisionHub получает только числа, не зная об эпистемической семантике.
        """
        modifiers = {}
        if context.perceived_threats:
            # S189: Модификатор пропорционален max_confidence.
            # При confidence=0.5 даёт 0.496 (0.5 * 0.992), что меняет score с 0.221 на 0.717.
            _epistemic_boost = round(context.max_confidence * 0.992, 4)
            modifiers["warn"] = _epistemic_boost
            modifiers["attack"] = _epistemic_boost
            modifiers["block_path"] = round(_epistemic_boost * 0.5, 4)
            
        # Союзники могут слегка повышать trade/help/approach
        if context.perceived_allies:
            _ally_boost = round(context.max_confidence * 0.2, 4)
            modifiers["trade"] = _ally_boost
            modifiers["help"] = _ally_boost
            
        return modifiers