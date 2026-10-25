"""
Декомпозитор биографии (ADR-O-420, CCH-2).

Файл: backend/app/services/chronicle/biography_decomposer.py
Назначение: фрагмент автора → BiographyDecomposition (transient, не канон).
Зависимости: app.domain.chronicle; LLM — через ModelRouter (VRAM-семафор).
Основные сущности: BiographyDecomposer

ДЕТЕРМИНИЗМ (прецеденты, второй механизм запрещён):
- temperature=0.0; seed НЕ дублируется здесь — за ним llama_cpp_provider
  (_complete_via_server, KernelRNG salt=prompt) — тот же путь, что compressor;
- retry ×1 при DecompositionError (FR-2.2: retry → «не разобрано»);
- DEBT-CHRONICLE-REPLAY: replay-кэш промптов (llm_cache.LLMCache.record)
  не подключён — рекордер привязан к тик-сессии, редактор вне тика.
  Подключение — отдельная задача контура replay (маркер для владельца).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Final, List, Optional

from app.domain.chronicle import (
    BiographyDecomposition,
    DecompositionItem,
)
from app.services.chronicle.decomposition_normalizer import (
    ChronicleDecompositionNormalizer,
    DecompositionError,
)

logger = logging.getLogger(__name__)


def _default_roster_provider() -> Dict[str, str]:
    """S367: lazy default roster source — npc_loader.get_display_names.
    Единственный источник истины; per-call fetch (config правится вне тик-сессии).
    Ленивый импорт (цикл-безопасно)."""
    from app.services.npc.npc_loader import get_display_names
    return get_display_names()


# Детерминированный препарсинг возрастных якорей (FR-1.2/FR-2.x, Fast Path)
_AGE_ANCHOR: Final[re.Pattern] = re.compile(
    r"\[\s*(\d{1,3})\s*лет\s*\]|"            # [8 лет]
    r"в\s+(\d{1,3})\s*лет|"                  # в 14 лет
    r"с\s+(\d{1,3})\s*лет|"                  # с 12 лет
    r"к\s+(\d{1,3})\s*годам|"                # к 23 годам (S365)
    r"в\s+(\d{1,3})\s*год(а|у)?\b|"          # в 24 года / в 24 год / в 24 (S365)
    r"\bв\s+(\d{1,3})\b(?=\s+(?:он|она|они|застал|пошёл|пошла|начал|начала))",  # «В 24 застал» (S365)
    re.IGNORECASE
)


@dataclass(frozen=True)
class DecomposeResult:
    """Результат разбора: items или честная ошибка (без молчаливых фолбэков).

    S371.0: raw_response сохраняется при failure для диагностики JSON-ошибок
    (классификация truncation/unicode/quote/escape/unknown)."""

    ok: bool
    items: List[DecompositionItem]
    error: Optional[str] = None
    age_anchors: Optional[List[int]] = None
    raw_response: Optional[str] = None  # S371.0: сырой ответ LLM при failure (диагностика)

    @staticmethod
    def failure(error: str, raw_response: Optional[str] = None) -> "DecomposeResult":
        return DecomposeResult(ok=False, items=[], error=error, raw_response=raw_response)

    @staticmethod
    def success(items: List[DecompositionItem], age_anchors: List[int]) -> "DecomposeResult":
        return DecomposeResult(ok=True, items=items, age_anchors=age_anchors)


class BiographyDecomposer:
    """LLM-декомпозитор фрагмента. Канон не пишет — только предлагает (П1)."""

    PROMPT_FILE = "backend/prompts/chronicle_decompose_system.txt"

    def __init__(
        self,
        router: Optional[Any] = None,
        roster_provider: Optional[Any] = None,
    ) -> None:
        # Router инъекцией (тестируемость); ленивая загрузка — как у DM.
        # S367: roster_provider — callable () -> Dict[str, str]; None -> lazy
        # get_display_names (единственный источник истины, npc_loader).
        self._router = router
        self._system_prompt: Optional[str] = None
        self._roster_provider = roster_provider

    def _ensure_prompt(self) -> str:
        if self._system_prompt is None:
            from app.services.verbalization.prompt_loader import load_system_prompt
            self._system_prompt = load_system_prompt(self.PROMPT_FILE)
        return self._system_prompt

    @staticmethod
    def extract_age_anchors(text: str) -> List[int]:
        """Fast Path: [8 лет] / «в 14 лет» / «с 12 лет» — детерминированно, без LLM."""
        anchors: List[int] = []
        for m in _AGE_ANCHOR.finditer(text):
            raw = next(g for g in m.groups() if g is not None)
            n = int(raw)
            if 0 <= n <= 120:
                anchors.append(n)
        return anchors

    def build_user_prompt(
        self,
        fragment: str,
        age_anchors: List[int],
        roster: Optional[Dict[str, str]] = None,
    ) -> str:
        """Детерминированный user-промпт (переиспользуется тестами).
        S365: hint «не найдено» не протекает в prompt — иначе LLM повторяет
        его в summary (урок guard_borko: «Возрастных якорей не найдено. В 24
        застал…» попало в summary как CoT-утечка).
        S367: roster (опц.) — снимок известных NPC (id->display_name) из
        npc_loader.get_display_names. roster=None -> блок отсутствует
        (backward-compat: s365 test_cot_leak_blocked вызывает с 2 аргументами)."""
        if age_anchors:
            hints = f"Возрастные якоря фрагмента: {age_anchors}.\n\n"
        else:
            hints = ""
        if roster:
            names = ", ".join(sorted(str(v) for v in roster.values() if isinstance(v, str)))
            roster_block = (
                "ИЗВЕСТНЫЕ NPC (roster): " + names + ".\n"
                "Если target_hint не сопоставляется ОДНОЗНАЧНО ни с одним именем выше — "
                "задай ClarificationQuestion (SELECT_EXISTING_NPC/CREATE_NEW_NPC/"
                "UNKNOWN_PERSON/LEAVE_WHITE_SPOT).\n\n"
            )
        else:
            roster_block = ""
        return f"{hints}{roster_block}ФРАГМЕНТ:\n{fragment.strip()}"

    async def decompose(self, chronicle_id: str, fragment_ord: int, fragment: str) -> DecomposeResult:
        """
        Фрагмент → DecomposeResult. LLM через router.request(FACT_EXTRACTION);
        один retry; DecompositionError → failure() с текстом (не исключение).
        """
        if not fragment.strip():
            return DecomposeResult.failure("Пустой фрагмент")
        anchors = self.extract_age_anchors(fragment)
        roster = (self._roster_provider or _default_roster_provider)()
        user_prompt = self.build_user_prompt(fragment, anchors, roster)
        from app.services.llm.router import ModelRouter  # ленивый (цикл-безопасно)

        router = self._router or ModelRouter()
        system_prompt = self._ensure_prompt()
        last_error = ""
        import asyncio as _aio

        _POOL_WAITS = (1.0, 3.0, 5.0)  # сек пауз при «пул занят» (Q4_K_M выдыхает на серии)
        _pool_retry = 0
        for attempt in (1, 2):
            try:
                from app.services.llm.provider import GenerationParams

                params = GenerationParams(
                    temperature=0.0,
                    max_tokens=2048,
                    response_format={"type": "json_object"},  # доезжает, когда провайдер включит; нормализатор деградирует сам
                )
                raw = await router.request(
                    capability="fact_extraction",
                    prompt=user_prompt,
                    params=params,
                    system_prompt=system_prompt,
                )
                items = ChronicleDecompositionNormalizer.normalize(
                    raw, chronicle_id=chronicle_id, fragment_ord=fragment_ord, roster=roster
                )
                return DecomposeResult.success(items, anchors)
            except DecompositionError as e:
                last_error = str(e)
                last_raw = raw if 'raw' in locals() else None  # S371.0: сохранить сырой ответ для диагностики
                continue  # ровно один retry (FR-2.2)
            except RuntimeError as e:
                # L4: отказ пула виден на warn-уровне. «Пул занят» — возмущение
                # среды (LLM обрабатывает предыдущий запрос), НЕ приговор:
                # ждём и пробуем снова (вердикт Мастера «готов ждать»);
                # сдаёмся только после исчерпания пауз.
                if _pool_retry < len(_POOL_WAITS):
                    _w = _POOL_WAITS[_pool_retry]
                    _pool_retry += 1
                    logger.warning(
                        f"[CHRONICLE_DECOMPOSER] пул занят ({str(e)[:60]}) — пауза {_w}с, попытка {_pool_retry + 1}/4"
                    )
                    await _aio.sleep(_w)
                    continue  # тот же attempt, счётчик пул-ретраев отдельный
                logger.error(f"[CHRONICLE_DECOMPOSER] LLM-пул недоступен после ожидания: {e}")
                return DecomposeResult.failure(f"LLM-пул недоступен: {e}")
        return DecomposeResult.failure(
            f"Декомпозиция не удалась после retry: {last_error}",
            raw_response=last_raw if 'last_raw' in locals() else None,
        )

    def to_transient(self, chronicle_id: str, fragment_ord: int, result: DecomposeResult) -> BiographyDecomposition:
        """Transient-объект для UI (не персистится; не канон)."""
        return BiographyDecomposition(chronicle_id=chronicle_id, fragment_ord=fragment_ord, items=tuple(result.items))
