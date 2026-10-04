# path: backend/tests/test_re_gh_contracts.py
# Назначение: контрактные тесты G/H-фазы RE (ADR-O-419) — NeedSlot.gen_rate + динамика.
# Зависимости: app.domain.relationship_contracts
# Основные сущности: TestGenRateContract

import pytest

from app.domain.relationship_contracts import (
    NEED_ID_INTIMACY,
    NEED_ID_SEXUAL,
    RE_NEED_SLOTS,
    ContractValidationError,
    NeedSlot,
)

# ВАЖНО (§12.3): здесь конструктор легален — это юнит-случаи ВАЛИДАЦИИ контракта.
# Состояния сцены в тестах G/H создаются только через сторовые/фабричные пути.


class TestGenRateContract:
    """gen_rate — ставка пассивного накопления давления (§6.1 п.4, ADR-O-419)."""

    def test_default_slots_have_gen_rate_placeholder(self) -> None:
        # PLACEHOLDER/CALIBRATION_CANDIDATE (вердикт GPT №2): значение не утверждено.
        assert RE_NEED_SLOTS[NEED_ID_SEXUAL].gen_rate == 0.1
        assert RE_NEED_SLOTS[NEED_ID_INTIMACY].gen_rate == 0.1

    def test_gen_rate_zero_is_legal(self) -> None:
        # Нулевая кинетика легальна: будущие слоты могут не накапливать давление.
        slot = NeedSlot(need_id=NEED_ID_SEXUAL, gen_rate=0.0)
        assert slot.gen_rate == 0.0

    def test_gen_rate_negative_rejected(self) -> None:
        with pytest.raises(ContractValidationError, match="gen_rate"):
            NeedSlot(need_id=NEED_ID_SEXUAL, gen_rate=-0.01)

    def test_gen_rate_nan_rejected(self) -> None:
        with pytest.raises(ContractValidationError, match="gen_rate"):
            NeedSlot(need_id=NEED_ID_SEXUAL, gen_rate=float("nan"))

    def test_gen_rate_non_number_rejected(self) -> None:
        with pytest.raises(ContractValidationError, match="gen_rate"):
            NeedSlot(need_id=NEED_ID_SEXUAL, gen_rate="fast")  # type: ignore[arg-type]