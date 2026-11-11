"""
path: /project/backend/app/domain/npc_intent_enum.py
Назначение: Перечисление намерений агентов (NPC и Аватар).
    Доменная сущность: определяет ЧТО агент может намереваться сделать.
    Исторически определён в models/npc_state.py; перенесён в домен для
    закрытия INV-DOMAIN-PURITY (домен не импортирует из models).
    models/npc_state.py реэкспортирует для обратной совместимости.
Зависимости: enum (stdlib)
Основные сущности: Intent
"""

from enum import Enum


class Intent(str, Enum):
    """Возможные намерения NPC. DecisionHub выбирает одно из них."""

    IDLE = "idle"  # нет активного намерения
    TALK = "talk"  # вступить в диалог
    WARN = "warn"  # предупредить
    INTIMIDATE = "intimidate"  # запугать
    FLEE = "flee"  # уйти / сбежать
    ATTACK = "attack"  # атаковать
    HELP = "help"  # помочь
    REPORT = "report"  # донести властям
    TRADE = "trade"  # предложить сделку
    OBSERVE = "observe"  # наблюдать, не действовать
    EXPLAIN = "explain"  # ответить "почему" — для диалога
    APPROACH = "approach"  # подойти к целевой сущности (игрок/NPC/объект)

    # ── Проактивные интенты (Фаза 3.4: Agenda Loop) ─────────────────────
    BLOCK_PATH = "block_path"  # преградить дорогу (шаг 9 из Мечты)
    AMBUSH = "ambush"  # устроить засаду
    SEEK_ALLY = "seek_ally"  # пойти за союзником
    OFFER_JOB = "offer_job"  # предложить работу (Economic Engine)
    REQUEST_SERVICE = "request_service"  # попросить об услуге
    SPREAD_RUMOR = "spread_rumor"  # распространить слух (Social Graph)
    CALL_FOR_HELP = "call_for_help"  # позвать на помощь
    CHANGE_ROLE = "change_role"  # сменить роль (Role Transition)
    STEAL = "steal"  # скрытое действие: кража (unlockable, OpportunityEngine, S209)
