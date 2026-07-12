"""
contract_base.py — абстракция для叙事 контрактов.

Принцип: любой потребитель контракта (LLM caller, validator, logger)
работает с Protocol, а не с конкретным классом.

ЗАЧЕМ:
- Позволяет создать DMContract, NPCContract, SystemContract
- Consumer код не меняется при смене типа контракта
- Легко мокать в тестах

Путь: backend/app/services/verbalization/contract_base.py
Назначение: Абстракция (Protocol) для нарративных контрактов — позволяет создавать различные типы контрактов (DM, NPC, System) без изменения потребителей.
Зависимости: typing (Protocol, runtime_checkable)
Основные сущности: NarrativeContractProtocol
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class NarrativeContractProtocol(Protocol):
    """
    Протокол叙事 контракта.

    Любой контракт должен предоставлять:
    - system_prompt: инструкции для LLM
    - user_prompt: данные для генерации
    - max_sentences: лимит для валидатора
    - contract_id: для логирования/дебага
    """

    @property
    def system_prompt(self) -> str: ...

    @property
    def user_prompt(self) -> str: ...

    @property
    def max_sentences(self) -> int: ...

    @property
    def contract_id(self) -> str: ...

    @property
    def forbidden_actions(self) -> list[str]: ...
