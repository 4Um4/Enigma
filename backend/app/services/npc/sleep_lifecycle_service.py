"""
path: /project/backend/app/services/npc/sleep_lifecycle_service.py
Назначение: Управление жизненным циклом сна NPC (Phase 0.6).
Вынесено из LifeEngine для соблюдения Separation of Concerns и подготовки к Phase E (DreamSignal).
Зависимости: app.domain.events, app.services.npc.sleep_states, app.models.scene
Основные сущности: SleepLifecycleService
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, TYPE_CHECKING

from app.domain.body import DreamSignal
from app.domain.events import EventDTO
from app.services.scene_change import ChangeType, SceneChange
from app.services.npc.sleep_states import is_sleeping
from app.services.npc.coupling_resolver import CouplingResolver
from app.services.npc.dream_generation_service import DreamGenerationService

if TYPE_CHECKING:
    from app.services.events.event_bus import EventBus

logger = logging.getLogger(__name__)


class SleepLifecycleService:
    """Управляет переходами сна, восстановлением и генерацией событий (DreamSignal)."""

    def __init__(self, event_bus: "EventBus") -> None:
        self._event_bus = event_bus
        self._coupling_resolver = CouplingResolver()

    def process_sleep_lifecycle(
        self, npc: Dict[str, Any], tick: int
    ) -> List[SceneChange]:
        """Основная точка входа Фазы 0.6. Обрабатывает состояние сна для одного NPC.

        Args:
            npc: Словарь состояния NPC (мутабельный).
            tick: Номер текущего тика.

        Returns:
            Список SceneChange, если произошёл переход (пробуждение). Пустой список, если изменений нет.
        """
        _routine = npc.get("routine", {})
        _current = _routine.get("current", "")

        if not is_sleeping(_current):
            # S188 ARCH-SLEEP Phase A/D: Накопление sleep_pressure и затухание arousal во время бодрствования.
            self._process_wake_lifecycle(npc)
            self._update_coupling_profile(npc)
            return []

        # S189 ARCH-SLEEP Phase D: Динамическая аккумуляция arousal от стимулов (даже во сне).
        self._accumulate_arousal_from_stimuli(npc)

        # 1. Проверка пробуждения (ранее LifeEngine._arousal_gate)
        wake_changes = self._check_wake_up(npc, tick)
        if wake_changes:
            # NPC проснулся — публикуем событие для TimeSkipExecutor и Memory
            self._publish_sleep_event("sleep_end", npc, tick)
            self._update_coupling_profile(npc)
            return wake_changes

        # 2. Восстановление во сне (ранее LifeEngine.recover_stress_tick)
        self._apply_sleep_recovery(npc)
        self._update_coupling_profile(npc)

        # S189 ARCH-SLEEP Phase E: Sensory Incorporation & DreamSignal.
        _dream_signal = DreamGenerationService.generate(npc, tick)
        if _dream_signal:
            self._publish_dream_event(_dream_signal)
            # S189 ARCH-SLEEP Phase F: Сохраняем остаток сна для применения при пробуждении.
            npc["dream_residue"] = {
                "salience": _dream_signal.salience,
                "perception": _dream_signal.distorted_perception,
            }

        return []

    def _update_coupling_profile(self, npc: Dict[str, Any]) -> None:
        """Вычисляет и сохраняет CouplingProfile в body_state как dict (Phase B)."""
        _body = npc.get("body_state")
        if _body:
            _profile = self._coupling_resolver.resolve(_body)
            _body["coupling_profile"] = {
                "external_vision_mult": _profile.external_vision_mult,
                "external_hearing_mult": _profile.external_hearing_mult,
                "motor_output_mult": _profile.motor_output_mult,
                "memory_activation_mult": _profile.memory_activation_mult,
                "imagination_mult": _profile.imagination_mult,
                "coupling_mode": _profile.coupling_mode.value,
            }

    def _check_wake_up(
        self, npc: Dict[str, Any], tick: int
    ) -> List[SceneChange]:
        """Проверяет, должен ли спящий NPC пробудиться (Arousal Gate)."""
        _routine = npc.get("routine", {})
        _current = _routine.get("current", "")

        # Когнитивный паралич замораживает пробуждение
        _kernel = npc.get("perceptual_kernel")
        _init_sup = (
            _kernel.get("initiative_suppression", 0.0)
            if isinstance(_kernel, dict)
            else getattr(_kernel, "initiative_suppression", 0.0)
            if _kernel
            else 0.0
        )
        if _init_sup > 0.7:
            return []

        # Attention Capture замораживает поведенческие переходы
        _rd = (
            _kernel.get("recent_directive")
            if isinstance(_kernel, dict)
            else getattr(_kernel, "recent_directive", None)  # noqa: ENIGMA001, ENIGMA002
            if _kernel
            else None
        )
        if _rd and isinstance(_rd, dict) and _rd.get("interrupts_routine"):
            return []

        # Расчёт wake_pressure
        _threat = 0.0
        _directive_salience = 0.0
        if isinstance(_kernel, dict):
            _threat = _kernel.get("threat_gradient", 0.0)
            _directive_salience = 0.8 if _rd else 0.0
        elif _kernel:
            _threat = getattr(_kernel, "threat_gradient", 0.0)
            _directive_salience = 0.8 if _rd else 0.0

        _body = npc.get("body_state", {})
        if isinstance(_body, dict):
            _fatigue = float(_body.get("fatigue", 0.0)) / 100.0
            # S189 ARCH-SLEEP Phase D: Чистое чтение динамически накопленного arousal.
            _arousal = float(_body.get("arousal", 0.0))
        else:
            _fatigue = 0.0
            _arousal = 0.0

        # S189 ARCH-SLEEP Phase D: wake_pressure теперь полностью опирается на arousal.
        wake_pressure = _arousal

        # Расчёт sleep_resistance
        _sleep_start = _routine.get("_sleep_start_tick", tick)
        _depth = min(1.0, max(0.0, (tick - _sleep_start) / 20.0))
        sleep_resistance = _fatigue * 0.4 + 0.05 + _depth * 0.1

        if wake_pressure > sleep_resistance:
            npc_id = npc.get("id", "unknown")
            logger.info(
                f"[SLEEP_LIFECYCLE] {npc_id}: WAKE — "
                f"pressure={wake_pressure:.3f} > resistance={sleep_resistance:.3f} "
                f"(threat={_threat:.2f}, directive={_directive_salience:.2f})"
            )

            # Transition: sleeping -> нет активности
            _routine["current"] = ""
            # BUG-SLEEP-004 FIX: Сброс _sleep_start_tick
            _routine.pop("_sleep_start_tick", None)

            # S189 ARCH-SLEEP Phase F: Конвертация DreamResidue в фоновое аффективное давление.
            _residue = npc.pop("dream_residue", None)
            if _residue and _residue.get("salience", 0.0) > 0.3:
                _salience = float(_residue["salience"])
                # Повышаем affective_load (он будет естественно затухать в последующие тики).
                _curr_load = float(npc.get("affective_load", 0.0))
                npc["affective_load"] = min(1.0, _curr_load + _salience * 0.5)
                # Если это был кошмар (salience > 0.7), оставляем лёгкий осадок паранойи (threat_gradient).
                if _salience > 0.7:
                    _kernel = npc.get("perceptual_kernel")
                    if isinstance(_kernel, dict):
                        _curr_threat = float(_kernel.get("threat_gradient", 0.0))
                        _kernel["threat_gradient"] = min(1.0, _curr_threat + _salience * 0.3)
                logger.info(
                    f"[DREAM_RESIDUE] {npc_id}: Woke up with residue "
                    f"(salience={_salience:.2f}, perception={_residue.get('perception')})"
                )

            return [
                SceneChange(
                    type=ChangeType.NPC_POSITION,
                    target=npc_id,
                    field="activity",
                    value="",
                    cause="sleep_lifecycle",
                )
            ]

        return []

    def _apply_sleep_recovery(self, npc: Dict[str, Any]) -> None:
        """Восстановление стресса, усталости и сброс sleep_pressure/arousal во сне."""
        from app.core.constants import STRESS_RECOVERY_SLEEPING

        psyche = npc.setdefault("psyche", {})
        current_stress = psyche.get("stress", 0)
        if current_stress > 0:
            psyche["stress"] = max(0, current_stress - STRESS_RECOVERY_SLEEPING)

        _body = npc.setdefault("body_state", {})
        # BUG-SLEEP-002 FIX: Sleep restores fatigue 7x faster
        _fatigue_rate = 0.20
        _body["fatigue"] = max(0.0, float(_body.get("fatigue", 0.0)) - _fatigue_rate)
        
        # S188 ARCH-SLEEP Phase A: Сброс телесных осей во сне.
        # sleep_pressure убывает (50 тиков до полного восстановления), arousal = 0 (глубокий сон).
        _curr_pressure = float(_body.get("sleep_pressure", 0.0))
        _body["sleep_pressure"] = max(0.0, _curr_pressure - 0.02)
        _body["arousal"] = 0.0

    def _process_wake_lifecycle(self, npc: Dict[str, Any]) -> None:
        """S188 ARCH-SLEEP Phase A/D: Физиология бодрствования.
        
        Накапливает sleep_pressure (потребность во сне) и модулирует arousal (возбуждение).
        arousal затухает в покое, но взлетает при наличии стимулов.
        """
        _body = npc.setdefault("body_state", {})
        
        # 1. Накопление sleep_pressure (0.005 за тик -> 200 тиков до полного истощения)
        _curr_pressure = float(_body.get("sleep_pressure", 0.0))
        _body["sleep_pressure"] = min(1.0, _curr_pressure + 0.005)
        
        # 2. Модуляция arousal
        _curr_arousal = float(_body.get("arousal", 0.0))
        
        # S189 ARCH-SLEEP Phase D: Аккумуляция от стимулов
        self._accumulate_arousal_from_stimuli(npc)
        _new_arousal = float(_body.get("arousal", 0.0))
        
        # Если стимулы не вызвали роста, применяем базовое затухание
        if _new_arousal <= _curr_arousal:
            _body["arousal"] = max(0.0, _curr_arousal - 0.05)

    def _accumulate_arousal_from_stimuli(self, npc: Dict[str, Any]) -> None:
        """S189 ARCH-SLEEP Phase D: Динамическая аккумуляция arousal от стимулов CFRM.
        
        Читает PerceptualKernel (threat, uncertainty, anomaly, directive) и накапливает arousal в body_state.
        Вызывается как во сне, так и при бодрствовании, чтобы тело могло естественно реагировать на стимулы.
        """
        _body = npc.get("body_state")
        if not _body:
            return
            
        _curr_arousal = float(_body.get("arousal", 0.0))
        _kernel = npc.get("perceptual_kernel")
        _threat = 0.0
        _uncertainty = 0.0
        _anomaly = 0.0
        _directive_salience = 0.0
        
        if isinstance(_kernel, dict):
            _threat = float(_kernel.get("threat_gradient", 0.0))
            _uncertainty = float(_kernel.get("uncertainty", 0.0))
            _anomaly = float(_kernel.get("anomaly_score", 0.0))
            _rd = _kernel.get("recent_directive")
            if _rd and isinstance(_rd, dict) and _rd.get("interrupts_routine"):
                _directive_salience = 0.8
        elif _kernel:
            _threat = float(getattr(_kernel, "threat_gradient", 0.0))
            _uncertainty = float(getattr(_kernel, "uncertainty", 0.0))
            _anomaly = float(getattr(_kernel, "anomaly_score", 0.0))
            _rd = getattr(_kernel, "recent_directive", None)  # noqa: ENIGMA002
            if _rd and _rd.get("interrupts_routine"):
                _directive_salience = 0.8

        # Внешние стимулы накапливают возбуждение.
        _stimuli_pressure = max(_threat, _uncertainty * 0.5, _anomaly * 0.5, _directive_salience)
        
        if _stimuli_pressure > 0.1:
            _body["arousal"] = min(1.0, _curr_arousal + _stimuli_pressure * 0.15)

    def _publish_sleep_event(
        self, event_type: str, npc: Dict[str, Any], tick: int
    ) -> None:
        """Публикует событие сна в EventBus (для TimeSkipExecutor и памяти)."""
        npc_id = npc.get("id", "unknown")
        event = EventDTO.create(
            event_type=event_type,
            source=npc_id,
            payload={"tick": tick},
            timestamp=float(tick),
        )
        self._event_bus.publish(event)

    def _publish_dream_event(self, dream_signal: "DreamSignal") -> None:
        """Публикует событие сна (DREAM/NIGHTMARE) в EventBus (Phase E)."""
        _event_type = "nightmare" if dream_signal.salience > 0.7 else "dream"
        event = EventDTO.create(
            event_type=_event_type,
            source=dream_signal.target_id,
            payload={
                "tick": dream_signal.tick,
                "raw_stimulus": dream_signal.raw_stimulus,
                "distorted_perception": dream_signal.distorted_perception,
                "salience": dream_signal.salience,
            },
            timestamp=float(dream_signal.tick),
        )
        self._event_bus.publish(event)
