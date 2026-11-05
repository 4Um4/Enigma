"""
path: /backend/app/services/cognition/proposition_verifier.py
Назначение: P5-B — семантическая верификация того, что LLM-реплика NPC
действительно выражает candidate Proposition, извлечённый из intent'а
ДО генерации текста.

Верификатор НЕ использует ключевые слова. LLM получает candidate
Proposition и финальный текст реплики, отвечает YES/NO по критериям:
  - Прямое высказывание или парафраза → YES
  - Молчание (текст пустой или тема не затронута) → NO
  - Отрицание («X не говорил этого») → NO
  - Искажение (NPC сказал про другой объект/предикат) → NO

P5-B Master directive:
  Production без доступного verifier'а → fail-closed: claim НЕ публикуется.
  PassthroughVerifier — только для ЯВНОГО внедрения в unit-тестах
  старых структурных контрактов P1-P4. Не является default.

Зависимости: app.infrastructure.llm (LLMClient)
Основные сущности: PropositionVerifier, PassthroughVerifier (test-only)
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class LLMClientProtocol(Protocol):
    """Минимальный контракт LLM-клиента — достаточно для верификации."""

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int = 16,
        timeout: float | None = None,
    ) -> str: ...


class _VerifierProtocol(Protocol):
    """Внутренний контракт любого верификатора (real или test-passthrough)."""

    def verify(self, proposition: dict[str, Any], text: str) -> bool: ...


class PassthroughVerifier:
    """
    TEST-ONLY. Не используется как production default.

    Явно внедряется в unit-тестах P1-P4 структурных контрактов, где
    требуется проверить механику propagation без реальной семантической
    проверки. В production wiring'е НЕ участвует — заменяется на
    PropositionVerifier с реальным LLM-клиентом.

    Любая production-инсталляция с этим классом — misconfiguration.
    """

    def verify(self, proposition: dict[str, Any], text: str) -> bool:  # noqa: ARG002
        return True


class PropositionVerifier:
    """
    P5-B production-верификатор. LLM-based семантическая проверка.

    Fail-closed по умолчанию:
      - LLM-вызов упал → False (claim suppress'ится)
      - LLM вернул пусто/мусор/«MAYBE» → False
      - timeout → False
      - Пустой текст реплики → False (барьер, без LLM-вызова)
    """

    YES_TOKENS = ("YES", "ДА", "TRUE", "1", "ПОДТВЕРЖДАЮ", "ПОДТВ")
    NO_TOKENS = ("NO", "НЕТ", "FALSE", "0", "ОТВЕРГАЮ", "НЕ")

    def __init__(
        self,
        llm: LLMClientProtocol,
        *,
        timeout: float = 5.0,
        max_tokens: int = 3,
    ):
        self._llm = llm
        self._timeout = timeout
        self._max_tokens = max_tokens

    def verify(self, proposition: dict[str, Any], text: str) -> bool:
        if not text or not text.strip():
            logger.debug(
                "verify: empty text → False (silence case). prop=%s",
                proposition,
            )
            return False
        if not proposition:
            return False

        prompt = self._build_prompt(proposition, text)
        try:
            raw = self._llm.complete(
                prompt,
                max_tokens=self._max_tokens,
                timeout=self._timeout,
            )
        except TimeoutError as exc:
            logger.warning(
                "verify: LLM timeout (%.1fs) — fail-closed=False. prop=%s err=%s",
                self._timeout, proposition, exc,
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "verify: LLM call failed — fail-closed=False. prop=%s err=%s",
                proposition, exc,
            )
            return False

        verdict = (raw or "").strip().upper()
        if any(verdict.startswith(tok) for tok in self.NO_TOKENS):
            logger.info(
                "verify → NO (rejected). prop=%s text_head=%r raw=%r",
                proposition, text[:160], raw,
            )
            return False
        confirmed = any(verdict.startswith(tok) for tok in self.YES_TOKENS)
        if confirmed:
            logger.info(
                "verify → YES (confirmed). prop=%s text_head=%r",
                proposition, text[:160],
            )
        else:
            logger.warning(
                "verify → AMBIGUOUS verdict (fail-closed=False). "
                "prop=%s raw=%r text_head=%r",
                proposition, raw, text[:160],
            )
        return confirmed

    @staticmethod
    def _build_prompt(proposition: dict[str, Any], text: str) -> str:
        subject = proposition.get("subject", "?")
        predicate = proposition.get("predicate", "?")
        obj = proposition.get("object", "?")
        polarity = proposition.get("polarity", True)
        polarity_hint = "положительное" if polarity else "отрицательное (утверждение-отрицание)"
        return (
            "Ты — семантический верификатор реплик NPC в ролевой симуляции.\n"
            "Проверь, выражает ли данная реплика NPC следующее утверждение.\n\n"
            f"Утверждение (candidate proposition, {polarity_hint}):\n"
            f"  субъект:  {subject}\n"
            f"  предикат: {predicate}\n"
            f"  объект:   {obj}\n\n"
            f"Реплика NPC (финальный сгенерированный текст):\n"
            f'"""\n{text}\n"""\n\n'
            "Критерии вердикта:\n"
            "  - Прямое высказывание или осмысленный парафраз → YES\n"
            "  - Молчание: тема не затронута, NPC говорит о другом → NO\n"
            "  - Отрицание: «X не говорил этого», «ничего подобного не было» → NO\n"
            "  - Искажение: NPC сказал про ДРУГОЙ субъект/объект/предикат → NO\n"
            "  - polarity=False (отрицательное утверждение): реплика должна "
            "выражать ОТРИЦАНИЕ отношения (что событие НЕ произошло), "
            "а не подтверждать его → иначе NO\n\n"
            "ВАЖНО: проверяй ТОЧНО объект и предикат. Если реплика говорит "
            "про другого персонажа (не указанный объект) — это искажение → NO. "
            "Если реплика содержит отрицание («не», «ничего подобного») — это "
            "отрицание, не подтверждение → NO.\n\n"
            "Примеры:\n"
            "  Утверждение: (Open_road, INSULTED, tornin)\n"
            "  Реплика «Open_road оскорбил вас, Торнин» → YES\n"
            "  Реплика «Сегодня славная погода» → NO (off-topic)\n"
            "  Реплика «Open_road вас не оскорблял» → NO (отрицание)\n"
            "  Реплика «Open_road оскорбил горана» → NO (другой объект)\n\n"
            "Ответ — ровно одно слово: YES или NO."
        )
