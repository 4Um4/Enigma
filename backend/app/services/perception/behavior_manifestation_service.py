from typing import Any, Dict

"""
Назначение: Сервис для трансформации латентных ограничений NPC в наблюдаемые моторные паттерны, которые могут быть восприняты Игроком. (Переводит казуальные ограничения в физические следы. Не читает эмоции. Только тело.)
Зависимости: logging, backend.app.domain.embodied_trace

- В будущем можно добавить более сложные паттерны, такие как дыхание, пульс, или даже микровыражения лица, если это будет разрешено в рамках запретов.
- Возможно введение разных "стилей" проявления для разных типов NPC (например, животные могут проявлять боль через рычание и скуление, а люди — через замер и дрожь).
"""

import logging

from app.domain.embodied_trace import EmbodiedTraceDTO

logger = logging.getLogger(__name__)


def _safe_get(d, *keys, default=0.0):
    current = d
    for key in keys:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            current = getattr(current, key, default)
        if current is None:
            return default
    try:
        return float(current)
    except (TypeError, ValueError) as e:
        logger.debug(f"[MANIFEST] Не удалось конвертировать значение '{current}' в float: {e}")
        return default


from dataclasses import dataclass


@dataclass(frozen=True)
class BodyConstraint:
    """P5.3: Универсальное функциональное ограничение тела."""
    region: str          # "LEG", "ARM", "TORSO", etc.
    function: str        # "LOCOMOTION", "MANIPULATION", etc.
    severity: float      # 0.0 - 1.0

class BehaviorManifestationService:
    """
    ФАЗА 8.5: Перевод латентных ограничений в наблюдаемые моторные паттерны.

    ЗАПРЕТ: Не читает psyche (fear, anger). Только моторные замки и физиологию.
    """

    # P5.3: Маппинг регионов и функций
    _REGION_MAP = {
        "leg": "LEG", "limb": "LEG", "foot": "LEG",
        "arm": "ARM", "hand": "ARM", "shoulder": "ARM"
    }
    _FUNCTION_MAP = {
        "LEG": "LOCOMOTION",
        "ARM": "MANIPULATION"
    }
    _SEVERITY_MAP = {
        "crippling": 0.8,
        "severe": 0.5,
        "moderate": 0.2
    }

    def _derive_constraints(self, wounds: list) -> list[BodyConstraint]:
        """P5.3: Вывод функциональных ограничений из ран."""
        constraints = []
        for w in wounds:
            if not isinstance(w, dict):
                continue
            part = str(w.get("body_part", "")).lower()
            sev = str(w.get("severity", "")).lower()

            region = self._REGION_MAP.get(part)
            if not region:
                continue

            severity = self._SEVERITY_MAP.get(sev, 0.0)
            if severity == 0.0:
                continue

            function = self._FUNCTION_MAP.get(region, "UNKNOWN")
            constraints.append(BodyConstraint(region=region, function=function, severity=severity))
        return constraints

    def _apply_constraints_to_motor(
        self, constraints: list[BodyConstraint], instability: float, posture_rigidity: float, micro_pause: float, action_interrupt: float
    ) -> tuple:
        """P5.3: Применение ограничений к моторным проекциям."""
        gait_asymmetry = 0.0
        arm_restriction = 0.0

        for c in constraints:
            if c.function == "LOCOMOTION":
                gait_asymmetry = max(gait_asymmetry, c.severity)
                instability = max(instability, c.severity * 0.6)
                micro_pause = max(micro_pause, c.severity * 0.4)
            elif c.function == "MANIPULATION":
                arm_restriction = max(arm_restriction, c.severity)
                posture_rigidity = max(posture_rigidity, c.severity * 0.5)
                action_interrupt = max(action_interrupt, c.severity * 0.7)

        return gait_asymmetry, arm_restriction, instability, posture_rigidity, micro_pause, action_interrupt

    def produce_traces(self, scene_state, all_npcs_raw=None) -> list[EmbodiedTraceDTO]:
        traces = []
        if not scene_state or not isinstance(scene_state, dict):
            return traces

        # Читаем из npc_positions (там лежат дельты и наблюдаемые состояния)
        npc_positions = scene_state.get("npc_positions", {})
        logger.info(f"[ARCHAE_PRODUCE] npc_pos_count={len(npc_positions)} all_npcs_raw_count={len(all_npcs_raw) if all_npcs_raw else 0}")

        # Правило X: строим маппинг npc_id → body_state из all_npcs_raw
        # StateApplicator пишет body_state в all_npcs_raw, НЕ в npc_positions
        body_state_map: dict[str, dict] = {}
        # S122: Также собираем psyche для чтения стресса и аффекта (§ENIGMA-S72)
        psyche_map: dict[str, dict] = {}
        if all_npcs_raw:
            for npc in all_npcs_raw:
                nid = npc.get("id") or npc.get("npc_id")
                if nid:
                    if npc.get("body_state"):
                        body_state_map[nid] = npc["body_state"]
                    if npc.get("psyche"):
                        psyche_map[nid] = npc["psyche"]
            logger.debug(
                f"[MANIFEST] all_npcs_raw count={len(all_npcs_raw)} body_state_ids={list(body_state_map.keys())}"
            )

        for npc_id, npc_data in npc_positions.items():
            if npc_id == "player":
                continue
            body_state = body_state_map.get(npc_id)
            psyche = psyche_map.get(npc_id, {})
            trace = self._manifest_npc(npc_id, npc_data, body_state, psyche)
            logger.info(f"[ARCHAE_TRACE_GEN] npc={npc_id} rigid={trace.posture_rigidity:.2f} instab={trace.locomotion_instability:.2f} mpd={trace.micro_pause_density:.2f}")
            if (
                trace.locomotion_instability > 0.05
                or trace.posture_rigidity > 0.05
                or trace.micro_pause_density > 0.05
            ):
                traces.append(trace)
        return traces

    def _manifest_npc(
        self, npc_id: str, data: Dict[str, Any], body_state: Dict[str, Any] = None, psyche: Dict[str, Any] = None
    ) -> EmbodiedTraceDTO:
        # Rule X (ADR-101/112): Моторика определяется строго физиологией и PerceptualKernel
        # НЕ телепатия: мы не читаем "NPC боится", мы наблюдаем дрожь рук и напряжённую позу
        in_transit = bool(data.get("in_transit", False))

        # Читаем физиологию из body_state
        pain = 0.0
        blood_loss = 0.0
        fatigue = 0.0
        shock_impulse = 0.0
        if body_state:
            pain = float(body_state.get("pain", 0.0))
            blood_loss = float(body_state.get("blood_loss", 0.0))
            fatigue = float(body_state.get("fatigue", 0.0))
            shock_impulse = float(body_state.get("shock_impulse", 0.0))

        # S122: Читаем стресс и аффективную нагрузку (§ENIGMA-S72: Эмоция = энергия разрядки)
        stress = float(psyche.get("stress", 0.0)) if psyche else 0.0
        affective_load = float(psyche.get("affective_load", 0.0)) if psyche else 0.0
        logger.info(f"[ARCHAE_BM] npc={npc_id} has_bs={bool(body_state)} fatigue={fatigue} stress={stress} affect={affective_load} pain={pain} shock={shock_impulse}")

        # Эмоциональные моторные проявления (наблюдаемые, не телепатия)
        # Страх → дрожь, напряжённая поза, застывание
        # Тревога → суетливость, частые паузы
        # Гнев → ригидность, резкие движения
        _emo_rigidity = 0.0
        _emo_instability = 0.0
        _emo_micro_pause = 0.0
        _emo_action_interrupt = 0.0

        # ADR-O-205: Motor Projection (Rule X Enforcement).
        # Тело не знает о эмоциях (интерпретациях). Оно реагирует на сырую физику стимула.
        # threat_gradient -> ригидность (замер)
        # pain/shock_impulse -> тремор и прерывание (ниже)
        _kernel = data.get("perceptual_kernel")
        if _kernel:
            _threat = getattr(_kernel, "threat_gradient", 0.0)

            # ADR-O-205: Когнитивно-моторные рефлексы (только восприятие, не физиология)
            _emo_rigidity = min(0.8, _threat * 0.9)  # Замер от осознанной угрозы
            # Тремор (instability) формируется строго от боли и шока ниже (Rule X)

        # S122: Эмоциональная энергия (stress, affective_load) переходит в моторику
        # Стресс вызывает мышечное напряжение (ригидность)
        if stress > 20.0:
            _emo_rigidity = max(_emo_rigidity, min(0.6, stress / 100.0))
        # Аффективная нагрузка вызывает дрожь и суету
        if affective_load > 0.3:
            _emo_instability = min(0.5, (affective_load - 0.3) * 0.7)
            _emo_micro_pause = min(0.5, (affective_load - 0.3) * 0.5)

        # Вычисляем моторные искажения (строго физиология + PerceptualKernel + Аффект, Rule X)
        # 1. Замер/Напряжение: защитный рефлекс от боли + мышечный замок от шока + угроза + стресс
        posture_rigidity = _emo_rigidity
        if pain > 20.0:
            posture_rigidity = min(1.0, pain / 80.0)
        if shock_impulse > 0.5:
            posture_rigidity = max(posture_rigidity, min(1.0, shock_impulse * 0.8))

        # 2. Дрожь/Пошатывание: от боли, шока и аффективной перегрузки
        instability = _emo_instability
        if pain > 10.0:
            instability = max(instability, min(1.0, pain / 50.0))
        if shock_impulse > 0.3:
            instability = max(instability, min(1.0, shock_impulse))

        # 3. Микро-остановки: кровопотеря, усталость и когнитивная перегрузка (аффект)
        micro_pause = _emo_micro_pause
        if blood_loss > 0.05:
            micro_pause = max(micro_pause, min(1.0, blood_loss * 5.0))
        if fatigue > 30.0:
            micro_pause = max(micro_pause, min(1.0, fatigue / 80.0))

        # 4. Прерывание действия: шок прерывает текущую активность
        action_interrupt = max(
            _emo_action_interrupt,
            min(1.0, shock_impulse) if shock_impulse > 0.5 else 0.0,
        )

        # P5.3: Generalize BodyConstraint primitive
        _wounds = []
        if body_state and isinstance(body_state.get("injuries"), list):
            _wounds = body_state.get("injuries", [])
        elif isinstance(data.get("wounds"), list):
            _wounds = data.get("wounds", [])

        _constraints = self._derive_constraints(_wounds)
        gait_asymmetry, arm_restriction, instability, posture_rigidity, micro_pause, action_interrupt = \
            self._apply_constraints_to_motor(_constraints, instability, posture_rigidity, micro_pause, action_interrupt)

        is_frozen = posture_rigidity > 0.7
        is_shaking = instability > 0.3

        # ADR-O-318: Rule X Causal Candidate Projection.
        # Причины выводятся только из реально активированных причинных ветвей.
        # Это не телепатия: мы не отдаем affective_load, мы отдаем "emotional_overload".
        _possible_causes: set[str] = set()

        if instability > 0.3:
            if pain > 10.0:
                _possible_causes.add("pain")
            if shock_impulse > 0.3:
                _possible_causes.add("shock")
            if affective_load > 0.3:
                _possible_causes.add("emotional_overload")
        if gait_asymmetry > 0.2:
            _possible_causes.add("leg_injury")
        if arm_restriction > 0.2:
            _possible_causes.add("arm_injury")

        if posture_rigidity > 0.3:
            if pain > 20.0:
                _possible_causes.add("pain")
            if shock_impulse > 0.5:
                _possible_causes.add("shock")
            if stress > 20.0:
                _possible_causes.add("stress")
            if _kernel and _threat > 0.0:
                _possible_causes.add("threat")

        if micro_pause > 0.0:
            if blood_loss > 0.05:
                _possible_causes.add("blood_loss")
            if fatigue > 30.0:
                _possible_causes.add("fatigue")
            if affective_load > 0.3:
                _possible_causes.add("cognitive_overload")

        # manifestation_confidence: насколько сильно выражено проявление
        _confidence = min(
            1.0,
            max(
                pain / 50.0,
                shock_impulse,
                blood_loss * 5.0,
                fatigue / 80.0,
                stress / 100.0,
                affective_load,
                _threat if _kernel else 0.0,
            ),
        )

        return EmbodiedTraceDTO(
            npc_id=npc_id,
            locomotion_instability=instability,
            posture_rigidity=posture_rigidity,
            action_interruption=action_interrupt,
            micro_pause_density=micro_pause,
            is_frozen=is_frozen,
            is_shaking=is_shaking,
            gait_asymmetry=gait_asymmetry,
            arm_restriction=arm_restriction,
            confidence=_confidence,
            possible_causes=tuple(sorted(_possible_causes)),
        )
