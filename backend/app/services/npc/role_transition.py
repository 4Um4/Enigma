from __future__ import annotations

# backend/app/services/npc/role_transition.py
"""
RoleTransition — валидация и выполнение смены профессии NPC.

ПРИНЦИП: Профессия NPC — не приговор. Обстоятельства меняют людей.
Но смена требует оснований и несёт издержки.

path: /project/backend/app/services/npc/role_transition.py
Назначение: Валидация и выполнение смены профессии NPC (ФАЗА 4-ROLE)
Зависимости: app.models.npc_state (NPCState, RoleChangeEntry), app.services.npc.npc_loader
Основные сущности: RoleTransition, TransitionResult

Назначение: Проверка возможности перехода + выполнение смены роли.
Зависимости: app.models.npc_state, app.services.npc.npc_loader
Основные сущности: RoleTransition, TransitionResult, TransitionDenied

КОНТРАКТ:
- can_transition() — ТОЛЬКО проверяет, НЕ меняет состояние
- execute_transition() — меняет NPCState, возвращает результат
- SocialGraph обновляется ВЫЗЫВАЮЩИМ кодом (game_loop), не здесь
"""


import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from app.models.npc_state import NPCState, RoleChangeEntry

logger = logging.getLogger(__name__)

# Корень конфигов NPC
_CONFIG_NPC_ROOT = Path("config/npc")


class TransitionDenied(Enum):
    """Причины отказа в смене роли."""

    ARCHETYPE_NOT_FOUND = "archetype_not_found"
    SAME_ROLE = "same_role"
    STRESS_TOO_HIGH = "stress_too_high"
    INTEGRITY_TOO_LOW = "integrity_too_low"
    NO_REASON = "no_reason"
    INSUFFICIENT_RESOURCES = "insufficient_resources"


@dataclass
class TransitionResult:
    """Результат попытки смены роли."""

    success: bool
    from_role: str
    to_role: str
    reason: str = ""
    denied: Optional[TransitionDenied] = None


class RoleTransition:
    """
    Валидация и выполнение смены профессии NPC.

    Правила (базовые, будут расширены):
    1. Целевой archetype должен существовать в config/npc/archetypes/
    2. Нельзя сменить на ту же роль
    3. Высокий стресс (>80) блокирует переход — NPC не в состоянии
    4. Низкая целостность (<0.3) блокирует — NPC не способен к осознанному выбору
    5. Нужна причина (reason) — пустая = отказ
    """

    # Пороги для блокировки
    STRESS_BLOCK_THRESHOLD: float = 80.0
    INTEGRITY_BLOCK_THRESHOLD: float = 0.3
    TRANSITION_COST: float = 20.0  # стоимость смены роли в золотых (Фаза 4-ROLE.3)

    def can_transition(
        self,
        state: NPCState,
        target_role: str,
        reason: str = "",
        economic_profile: Optional[Any] = None,
    ) -> TransitionResult:
        """
        Проверяет возможность смены роли. НЕ меняет состояние.

        Args:
            state: Текущее состояние NPC
            target_role: Имя целевого archetype (например "mercenary")
            reason: Причина смены (для CausalLedger)

        Returns:
            TransitionResult с success=True если переход возможен
        """
        # 1. Проверка причины
        if not reason or not reason.strip():
            return TransitionResult(
                success=False,
                from_role=state.current_role,
                to_role=target_role,
                denied=TransitionDenied.NO_REASON,
                reason="Смена роли без причины невозможна",
            )

        # 2. Проверка что не ту же роль
        if state.current_role == target_role:
            return TransitionResult(
                success=False,
                from_role=state.current_role,
                to_role=target_role,
                denied=TransitionDenied.SAME_ROLE,
                reason=f"NPC уже в роли {target_role}",
            )

        # 3. Проверка что archetype существует
        archetype_path = _CONFIG_NPC_ROOT / "archetypes" / f"{target_role}.json"
        if not archetype_path.exists():
            return TransitionResult(
                success=False,
                from_role=state.current_role,
                to_role=target_role,
                denied=TransitionDenied.ARCHETYPE_NOT_FOUND,
                reason=f"Archetype {target_role} не найден в config",
            )

        # 4. Проверка стресса
        if state.stress > self.STRESS_BLOCK_THRESHOLD:
            return TransitionResult(
                success=False,
                from_role=state.current_role,
                to_role=target_role,
                denied=TransitionDenied.STRESS_TOO_HIGH,
                reason=f"Стресс {state.stress:.0f} > {self.STRESS_BLOCK_THRESHOLD:.0f} — NPC не способен к переходу",
            )

        # 5. Проверка целостности
        if state.identity_integrity < self.INTEGRITY_BLOCK_THRESHOLD:
            return TransitionResult(
                success=False,
                from_role=state.current_role,
                to_role=target_role,
                denied=TransitionDenied.INTEGRITY_TOO_LOW,
                reason=f"Целостность {state.identity_integrity:.2f} < {self.INTEGRITY_BLOCK_THRESHOLD:.1f} — выбор не осознан",
            )

        # 6. Проверка ресурсов (Фаза 4-ROLE.3)
        if economic_profile is not None:
            _wealth = economic_profile.get_total_wealth()
            if _wealth < self.TRANSITION_COST:
                return TransitionResult(
                    success=False,
                    from_role=state.current_role,
                    to_role=target_role,
                    denied=TransitionDenied.INSUFFICIENT_RESOURCES,
                    reason=f"Недостаточно ресурсов: {_wealth:.1f}G < {self.TRANSITION_COST:.0f}G для смены роли",
                )

        return TransitionResult(
            success=True,
            from_role=state.current_role,
            to_role=target_role,
            reason=reason,
        )

    def execute_transition(
        self,
        state: NPCState,
        target_role: str,
        reason: str,
        tick: int = 0,
        economic_profile: Optional[Any] = None,
    ) -> TransitionResult:
        """
        Выполняет смену роли. Возвращает новый NPCState (иммутабельный контракт).

        Args:
            state: Текущее состояние NPC (не модифицируется)
            target_role: Имя целевого archetype
            reason: Причина для CausalLedger
            tick: Текущий тик мира
            economic_profile: Опционально — для проверки и списания стоимости

        Returns:
            TransitionResult — при успехе вызывающий код должен заменить state
        """
        # Валидация
        check = self.can_transition(state, target_role, reason, economic_profile)
        if not check.success:
            return check

        # Списание стоимости (Фаза 4-ROLE.3)
        if economic_profile is not None and economic_profile.can_afford(
            self.TRANSITION_COST
        ):
            economic_profile.spend(self.TRANSITION_COST)
            logger.info(
                f"[ROLE] {state.npc_id}: списано {self.TRANSITION_COST}G за смену роли"
            )

        # Запись в историю
        entry = RoleChangeEntry(
            from_role=state.current_role,
            to_role=target_role,
            tick=tick,
            reason=reason,
        )

        # Создаём обновлённый state (иммутабельный контракт)
        # role_history — новый список с добавленной записью
        new_history = list(state.role_history)
        new_history.append(entry)
        # Cap на историю (аналогично causal_ledger)
        if len(new_history) > 10:
            new_history = new_history[-10:]

        # Обновляем состояние через dataclass replace
        from dataclasses import replace

        new_state = replace(
            state,
            current_role=target_role,
            role_history=new_history,
        )

        logger.info(
            f"[ROLE] {state.npc_id}: {state.current_role} → {target_role} "
            f"(tick={tick}, reason={reason})"
        )

        # Возвращаем результат — вызывающий код (game_loop) должен:
        # 1. Загрузить activity_map из нового archetype
        # 2. Обновить SocialGraph если нужно
        # 3. Записать CausalEntry
        return TransitionResult(
            success=True,
            from_role=state.current_role,
            to_role=target_role,
            reason=reason,
        )
