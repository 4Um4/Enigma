"""
path: /project/backend/app/services/body/body_engine.py
Назначение: S2B.1 (контракт) + S2B.2 (energy dynamics).
    Pure calculator: body_state + activity + Δt → PhysiologyPayload(energy_delta).
    НИКОГДА не пишет в body_state (Mutation Contract #3).
    Body → pressure/restriction, NOT decision (#7).
Зависимости: app.models, app.core.constants (Δt)
Основные сущности: BodyEngine
"""
from __future__ import annotations

import logging
from typing import Any, List

from app.domain.body import is_sleep_coupling

logger = logging.getLogger(__name__)


class BodyEngine:
    """S2B.1–S2B.5: PhysiologicalTransition (energy/hydration/nutrition/fatigue).

    ADR-O-373: вход — ПЛОСКИЙ NPCStateSnapshot (idle-проекция Phase 0.5), не
    сырой npc-дикт: raw-форма в рантайме не существует (S2B.1–2B.4 были
    production-мёртвыми — тихий no-op на body_state-чтении).
    fatigue — two-way износ (0=свеж, 100=истощён, инверсия energy); единственная
    per-tick fatigue-проекция (combat — event-продюсер; PHYSICS_COMPOSITE =
    pass-through на агрегации, аддитивность возникает в StateApplicator).
    One World Tick → one physiology projection. Pure function, no state.
    """

    name: str = "body_engine"

    # ── Calibration (S2B.2; move to config later) ──────────────────
    BASE_EXPENDITURE_RATE: float = 0.5    # per tick at load=1.0
    BASE_RECOVERY_RATE: float = 0.3       # per tick at load=0.0
    SLEEP_RECOVERY_MULTIPLIER: float = 3.0
    # S2B.3: hydration — one-way loss (no passive recovery; drinking = action)
    BASE_HYDRATION_LOSS: float = 0.2  # per tick at rest (respiration, basal)
    # S2B.4: nutrition — one-way loss (eating = action, future). Запас калорий
    # эффективнее воды → трата МЕДЛЕННЕЕ hydration (инвариант иерархии кризисов:
    # hydration → быстрый, nutrition → медленный; тест test_slower_than_hydration).
    # v1 calibration constant (S2B.4, вердикт Мастера), не физиологический закон.
    BASE_NUTRITION_LOSS: float = 0.05  # per tick at rest
    NUTRITION_LOAD_COEFF: float = 0.5  # < hydration-коэф. (1.0): слабее реагирует на load
    # S2B.5 (ADR-O-373): fatigue — two-way износ. Иерархия масштабов (закон №11-
    # аналог): износ медленнее топлива — 0.25 < 0.5 (BASE_EXPENDITURE_RATE);
    # инвариант кодируется ОТДЕЛЬНЫМ тестом. v1 calibration constants
    # (вердикт Мастера), не физиологический закон.
    BASE_FATIGUE_RATE: float = 0.25  # износ per tick at load=1.0
    BASE_FATIGUE_RECOVERY: float = 0.1  # пассивный отдых per tick at load=0.0

    # Physiological load map (NOT occupational — body cost, not job title)
    _ACTIVITY_LOADS = {
        "": 0.0,           # IDLE
        "idle": 0.0,
        "sleeping": 0.1,   # REST (low baseline, but high recovery via coupling)
        "resting": 0.1,
        "eating": 0.2,
        "Обедает за столом": 0.2,
        "Обедает в общем зале": 0.2,
        "guarding_gate": 0.5,   # WORK (standing watch)
        "working": 0.5,
    }

    def _get_activity_load(self, npc: dict) -> float:
        """Determine physiological load from activity + velocity + coupling.

        Priority: coupling (sleep overrides) > velocity (movement) > activity string.
        """
        _coupling = str(npc.get("coupling_mode", "") or "")

        # Sleep overrides — very low load (body at rest)
        if is_sleep_coupling(_coupling):
            return 0.1

        # Velocity → WALK/RUN (movement is expensive)
        _vel = npc.get("velocity", (0.0, 0.0))
        if isinstance(_vel, (tuple, list)) and len(_vel) >= 2:
            _speed = abs(_vel[0]) + abs(_vel[1])
            if _speed > 0.5:
                return 0.9  # RUN
            if _speed > 0.1:
                return 0.7  # WALK

        # Activity string → load (ADR-O-373: плоское поле; routine-резолв — в билдере)
        _activity = str(npc.get("activity", "") or "")
        return self._ACTIVITY_LOADS.get(_activity, 0.3)  # default: light activity

    def _get_body_modifier(self, npc: dict) -> float:
        """Body characteristics → expenditure modifier.

        body_mass: heavier body spends proportionally more.
        Default 1.0 (no modifier). S2B.2: proof that body affects cost.
        ADR-O-373: плоское поле снапшота (placeholder до S2B.7).
        """
        return max(0.5, float(npc.get("body_mass", 1.0)))

    def handle(
        self,
        npcs: List[Any],
        campaign_id: str,
        current_tick: int,
    ) -> List[Any]:
        """Pure function: energy transition per tick.

        Returns List[StateDeltas] — applied by StateApplicator (single writer).
        Δt = GAME_TICK_INTERVAL_SECONDS (sole temporal input; no wall-clock).
        """
        from app.core.constants import GAME_TICK_INTERVAL_SECONDS
        from app.models.delta_payloads import PhysiologyPayload
        from app.models.state_delta import DeltaDomain, StateDeltas

        _dt = float(GAME_TICK_INTERVAL_SECONDS)
        results: List[Any] = []

        for npc in npcs:
            npc_id = npc.get("npc_id") or npc.get("id") or ""
            if not npc_id:
                continue

            # ADR-127: DEAD does NOT affect physics layer
            if npc.get("life_status", "ALIVE") == "DEAD":
                continue

            # ADR-O-373: вход — плоский снапшот; вложенного body_state ЗДЕСЬ НЕТ
            # (поля спроецированы билдером). Гейт живости — life_status (DEAD-skip).
            _load = self._get_activity_load(npc)
            _modifier = self._get_body_modifier(npc)
            _coupling = str(npc.get("coupling_mode", "") or "")

            # Expenditure: load-dependent, body-mass-scaled
            _expenditure = self.BASE_EXPENDITURE_RATE * _load * _modifier

            # Recovery: inverse to load; sleep bonus via coupling (NOT via activity string)
            _recovery = self.BASE_RECOVERY_RATE * (1.0 - _load)
            if is_sleep_coupling(_coupling):
                _recovery *= self.SLEEP_RECOVERY_MULTIPLIER

            # Net: energy_delta = recovery - expenditure
            energy_delta = round(_recovery - _expenditure, 4)

            # S2B.3: hydration — one-way loss (activity accelerates; body_mass scales)
            _hydration_loss = self.BASE_HYDRATION_LOSS * (1.0 + _load) * _modifier
            hydration_delta = round(-_hydration_loss, 4)

            # S2B.4: nutrition — one-way loss; load-коэф. 0.5 (медленнее воды);
            # body_mass масштабирует. nutrition = STOCK (запас), НЕ hunger (S2B.10).
            _nutrition_loss = (
                self.BASE_NUTRITION_LOSS
                * (1.0 + _load * self.NUTRITION_LOAD_COEFF)
                * _modifier
            )
            nutrition_delta = round(-_nutrition_loss, 4)

            # S2B.5 (ADR-O-373): fatigue — two-way износ, «плохо вверх»
            # (0=свеж, 100=истощён; инверсия energy). Единственная per-tick
            # fatigue-проекция: combat (ImpactEngine) — event-продюсер;
            # PHYSICS_COMPOSITE = pass-through на агрегации, вклады
            # применяются последовательно единым StateApplicator (clamp).
            _fatigue_wear = self.BASE_FATIGUE_RATE * _load * _modifier
            _fatigue_recovery = self.BASE_FATIGUE_RECOVERY * (1.0 - _load)
            if is_sleep_coupling(_coupling):
                _fatigue_recovery *= self.SLEEP_RECOVERY_MULTIPLIER
            fatigue_delta = round(_fatigue_wear - _fatigue_recovery, 4)

            if (
                abs(energy_delta) > 0.001
                or abs(hydration_delta) > 0.001
                or abs(nutrition_delta) > 0.001
                or abs(fatigue_delta) > 0.001
            ):
                results.append(
                    StateDeltas(
                        npc_id=npc_id,
                        domain=DeltaDomain.PHYSIOLOGY,
                        payload=PhysiologyPayload(
                            energy_delta=energy_delta,
                            hydration_delta=hydration_delta,
                            nutrition_delta=nutrition_delta,
                            fatigue_delta=fatigue_delta,
                        ),
                        source=f"body_engine:load={_load:.1f}:mod={_modifier:.1f}",
                    )
                )

        return results
