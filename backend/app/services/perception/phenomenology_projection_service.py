# path: backend/app/services/perception/phenomenology_projection_service.py
# Назначение: Перевод Simulation Truth (NPC states) в PerceptionEvent.
# ЗАПРЕТ: Телепатия. Сервис не имеет права читать fear/trust напрямую для текстов.
# Зависимости: app.domain.perception

from __future__ import annotations

from typing import Dict, List

from app.domain.perception import PerceptionEvent


class PhenomenologyProjectionService:
    """Переводит сырые стейты NPC в смыслы (PerceptionEvent).
    
    Если NPC имеет высокий initiative_suppression, он "замер".
    Если NPC имеет высокий fear, он "отворачивается" (избегание взгляда).
    """

    def project(
        self, 
        all_npcs_raw: List[Dict], 
        current_tick: int,
        current_location_id: str = ""
    ) -> List[PerceptionEvent]:
        """Сканирует NPC и генерирует события восприятия."""
        events: List[PerceptionEvent] = []

        for npc_dict in all_npcs_raw:
            # Фильтруем NPC не в нашей локации (если передан ID)
            npc_loc = npc_dict.get("location_id") or npc_dict.get("location", "")
            if current_location_id and npc_loc and npc_loc != current_location_id:
                continue

            npc_id = npc_dict.get("npc_id") or npc_dict.get("id", "unknown") # Починка слепоты (id vs npc_id)
            psyche = npc_dict.get("psyche", {})
            body = npc_dict.get("body_state", {})

            # --- Слой 1: Периферия (Наблюдение за поведением) ---
            # 1. Когнитивный ступор (Cognitive Freeze)
            initiative_sup = float(psyche.get("initiative_suppression", 0.0))
            if initiative_sup > 0.7:
                events.append(PerceptionEvent(
                    salience=0.6 + (initiative_sup - 0.7) * 1.0, # 0.6 - 0.9
                    category="PERIPHERAL",
                    semantic_seed="замер",
                    source_cluster=npc_id,
                    expiration_tick=current_tick + 3 # Наблюдение живет 3 тика
                ))

            # 2. Избегание контакта (Fear -> Avoid Gaze)
            fear = float(psyche.get("fear", 0.0))
            # Fallback: Если NPC формирует интент бегства, он визуально отводит взгляд/дергается,
            # даже если скаляр fear в словаре еще не обновился 
            active_intent = npc_dict.get("active_intent", "")
            is_fleeing = "flee" in str(active_intent).lower()
            
            if fear > 0.6 or is_fleeing:
                events.append(PerceptionEvent(
                    salience=0.4 + (max(fear - 0.6, 0.0)) * 0.5,
                    category="PERIPHERAL",
                    semantic_seed="отворачивается" if not is_fleeing else "отворачивается",
                    source_cluster=npc_id,
                    expiration_tick=current_tick + 2
                ))

            # --- Слой 2: Атмосфера (Средовое давление) ---
            # Если в локации много стресса, это фон
            stress = float(psyche.get("stress", 0.0))
            if stress > 50.0:
                events.append(PerceptionEvent(
                    salience=0.3,
                    category="ATMOSPHERE",
                    semantic_seed="напряжение",
                    source_cluster=npc_id,
                    expiration_tick=current_tick + 5
                ))

        return events