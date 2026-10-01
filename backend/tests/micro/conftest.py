"""path: /project/backend/tests/micro/conftest.py

Назначение: env-иммунитет micro-канона (вердикт Мастера, D8P ambient-env
    leakage). Каноническая модель: pytest -> чистая известная конфигурация
    -> OFF-контракт тестов, а НЕ зависимость от ambient shell (production
    включает D8P_ENABLED через main.py setdefault -> любой дочерний процесс
    наследует ON). OFF-by-default для всего micro-suite; D8P-специфические
    тесты opt-in через собственный monkeypatch.setenv в теле теста
    (исполняется ПОСЛЕ autouse-fixture -> их env побеждает).
    STOP-граница: стабы (_SpyMemory, _StubSession) НЕ расширяются —
    лечение симптома запрещено вердиктом.

Зависимости: pytest.

Основные сущности: _d8p_off_by_default (autouse).
"""

import pytest


@pytest.fixture(autouse=True)
def _d8p_off_by_default(monkeypatch):
    """Убирает утечку D8P_ENABLED из ambient-окружения. Легально:
    d8p_enabled() читает os.environ на каждом вызове (не кэшируется
    на импорте — подтверждено чтением intelligence_queue.py:37-45)."""
    monkeypatch.delenv("D8P_ENABLED", raising=False)
    yield