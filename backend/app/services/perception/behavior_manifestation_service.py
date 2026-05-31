"""
Назначение: Сервис для трансформации латентных ограничений NPC в наблюдаемые моторные паттерны, которые могут быть восприняты Игроком. (Переводит казуальные ограничения в физические следы. Не читает эмоции. Только тело.)
Зависимости: logging, backend.app.domain.embodied_trace

TODO:
- В будущем можно добавить более сложные паттерны, такие как дыхание, пульс, или даже микровыражения лица, если это будет разрешено в рамках запретов.
- Возможно введение разных "стилей" проявления для разных типов NPC (например, животные могут проявлять боль через рычание и скуление, а люди — через замер и дрожь).
"""

import logging
from app.domain.embodied_trace import EmbodiedTraceDTO

logger = logging.getLogger(__name__)

def _safe_get(d, *keys, default=0.0):
    current = d
    for key in keys:
        if current is None: return default
        if isinstance(current, dict): current = current.get(key, default)
        else: current = getattr(current, key, default)
        if current is None: return default
    try: return float(current)
    except (TypeError, ValueError): return default

class BehaviorManifestationService:
    """
    ФАЗА 8.5: Перевод латентных ограничений в наблюдаемые моторные паттерны.
    
    ЗАПРЕТ: Не читает psyche (fear, anger). Только моторные замки и физиологию.
    """
    
    def produce_traces(self, scene_state, all_npcs_raw=None) -> list[EmbodiedTraceDTO]:
        traces = []
        print(f"[MANIFEST_ENTRY] scene_state type={type(scene_state).__name__}, all_npcs_raw={'YES' if all_npcs_raw else 'NO'}")
        if not scene_state or not isinstance(scene_state, dict):
            print(f"[MANIFEST_ENTRY] EARLY RETURN: scene_state invalid")
            return traces
            
        # Читаем из npc_positions (там лежат дельты и наблюдаемые состояния)
        npc_positions = scene_state.get("npc_positions", {})
        print(f"[MANIFEST_ENTRY] npc_positions count={len(npc_positions)} keys={list(npc_positions.keys())[:5]}")
        
        # Правило X: строим маппинг npc_id → body_state из all_npcs_raw
        # StateApplicator пишет body_state в all_npcs_raw, НЕ в npc_positions
        body_state_map: dict[str, dict] = {}
        if all_npcs_raw:
            for npc in all_npcs_raw:
                nid = npc.get("id") or npc.get("npc_id")
                if nid and npc.get("body_state"):
                    body_state_map[nid] = npc["body_state"]
            logger.debug(f"[MANIFEST] all_npcs_raw count={len(all_npcs_raw)} body_state_ids={list(body_state_map.keys())}")
        
        for npc_id, npc_data in npc_positions.items():
            if npc_id == "player": continue
            body_state = body_state_map.get(npc_id)
            trace = self._manifest_npc(npc_id, npc_data, body_state)
            if trace.locomotion_instability > 0.05 or trace.posture_rigidity > 0.05 or trace.micro_pause_density > 0.05:
                traces.append(trace)
        return traces

    def _manifest_npc(self, npc_id: str, data: dict, body_state: dict = None) -> EmbodiedTraceDTO:
        # Читаем наблюдаемые моторные паттерны из npc_positions
        stress_delta = float(data.get("stress_delta", 0))
        psyche_state = str(data.get("psyche_state", "calm"))
        in_transit = bool(data.get("in_transit", False))
        
        # Правило X: Читаем физиологию из body_state (НЕ эмоции!)
        # StateApplicator пишет pain/blood_loss/shock_impulse сюда
        pain = 0.0
        blood_loss = 0.0
        fatigue = 0.0
        shock_impulse = 0.0
        if body_state:
            pain = float(body_state.get("pain", 0.0))
            blood_loss = float(body_state.get("blood_loss", 0.0))
            fatigue = float(body_state.get("fatigue", 0.0))
            shock_impulse = float(body_state.get("shock_impulse", 0.0))
        
        # Вычисляем моторные искажения
        # 1. Замер/Напряжение: настороженность ИЛИ защитный рефлекс от боли
        is_alert = psyche_state in ("alert", "fleeing", "shock")
        posture_rigidity = 0.8 if is_alert else 0.0
        if pain > 20.0:
            # Боль вызывает окаменелость — защитный рефлекс тела
            posture_rigidity = max(posture_rigidity, min(1.0, pain / 80.0))
        
        # 2. Дрожь/Пошатывание: от боли и шока (Правило X — не только стресс)
        instability = min(1.0, stress_delta / 15.0)
        if pain > 10.0:
            instability = max(instability, min(1.0, pain / 50.0))
        if shock_impulse > 0.3:
            instability = max(instability, min(1.0, shock_impulse))
        
        # 3. Микро-остановки: кровопотеря и усталость (Правило X)
        micro_pause = 0.0
        if blood_loss > 0.05:
            micro_pause = min(1.0, blood_loss * 5.0)
        if fatigue > 30.0:
            micro_pause = max(micro_pause, min(1.0, fatigue / 80.0))
        
        # 4. Прерывание действия: шок прерывает текущую активность
        action_interrupt = min(1.0, shock_impulse) if shock_impulse > 0.5 else 0.0
        
        # [DIAG S61] Снятие слепка причинных факторов (Правило X vs Semantic Inflation)
        print(f"[MANIFEST_DIAG] npc={npc_id} psyche={psyche_state} stress_d={stress_delta:.2f} pain={pain:.2f} shock_imp={shock_impulse:.2f} → instab={instability:.2f} rigid={posture_rigidity:.2f}")
        is_frozen = posture_rigidity > 0.7 and not in_transit
        is_shaking = instability > 0.3
        
        return EmbodiedTraceDTO(
            npc_id=npc_id,
            locomotion_instability=instability,
            posture_rigidity=posture_rigidity,
            action_interruption=action_interrupt,
            micro_pause_density=micro_pause,
            is_frozen=is_frozen,
            is_shaking=is_shaking
        )
