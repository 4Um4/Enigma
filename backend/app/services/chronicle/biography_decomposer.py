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
from typing import Any, Final, List, Optional

from app.domain.chronicle import (
    BiographyDecomposition,
    DecompositionItem,
)
from app.services.chronicle.decomposition_normalizer import (
    ChronicleDecompositionNormalizer,
    DecompositionError,
)

logger = logging.getLogger(__name__)

# Детерминированный препарсинг возрастных якорей (FR-1.2/FR-2.x, Fast Path)
_AGE_ANCHOR: Final[re.Pattern] = re.compile(
    r"\[\s*(\d{1,3})\s*лет\s*\]|в\s+(\d{1,3})\s*лет|с\s+(\d{1,3})\s*лет", re.IGNORECASE
)


@dataclass(frozen=True)
class DecomposeResult:
    """Результат разбора: items или честная ошибка (без молчаливых фолбэков)."""

    ok: bool
    items: List[DecompositionItem]
    error: Optional[str] = None
    age_anchors: Optional[List[int]] = None

    @staticmethod
    def failure(error: str) -> "DecomposeResult":
        return DecomposeResult(ok=False, items=[], error=error)

    @staticmethod
    def success(items: List[DecompositionItem], age_anchors: List[int]) -> "DecomposeResult":
        return DecomposeResult(ok=True, items=items, age_anchors=age_anchors)


class BiographyDecomposer:
    """LLM-декомпозитор фрагмента. Канон не пишет — только предлагает (П1)."""

    PROMPT_FILE = "backend/prompts/chronicle_decompose_system.txt"

    def __init__(self, router: Optional[Any] = None) -> None:
        # Router инъекцией (тестируемость); ленивая загрузка — как у DM.
        self._router = router
        self._system_prompt: Optional[str] = None

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

    def build_user_prompt(self, fragment: str, age_anchors: List[int]) -> str:
        """Детерминированный user-промпт (переиспользуется тестами)."""
        hints = f"Возрастные якоря фрагмента: {age_anchors}." if age_anchors else "Возрастных якорей не найдено."
        return f"{hints}\n\nФРАГМЕНТ:\n{fragment.strip()}"

    async def decompose(self, chronicle_id: str, fragment_ord: int, fragment: str) -> DecomposeResult:
        """
        Фрагмент → DecomposeResult. LLM через router.request(FACT_EXTRACTION);
        один retry; DecompositionError → failure() с текстом (не исключение).
        """
        if not fragment.strip():
            return DecomposeResult.failure("Пустой фрагмент")
        anchors = self.extract_age_anchors(fragment)
        user_prompt = self.build_user_prompt(fragment, anchors)
        from app.services.llm.router import ModelRouter  # ленивый (цикл-безопасно)

        router = self._router or ModelRouter()
        system_prompt = self._ensure_prompt()
        last_error = ""
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
                    raw, chronicle_id=chronicle_id, fragment_ord=fragment_ord
                )
                return DecomposeResult.success(items, anchors)
            except DecompositionError as e:
                last_error = str(e)
                continue  # ровно один retry (FR-2.2)
            except RuntimeError as e:
                # L4: отказ пула виден на error-уровне (тихий return = L4-нарушение)
                logger.error(f"[CHRONICLE_DECOMPOSER] LLM-пул недоступен: {e}")
                return DecomposeResult.failure(f"LLM-пул недоступен: {e}")
        return DecomposeResult.failure(f"Декомпозиция не удалась после retry: {last_error}")

    def to_transient(self, chronicle_id: str, fragment_ord: int, result: DecomposeResult) -> BiographyDecomposition:
        """Transient-объект для UI (не персистится; не канон)."""
        return BiographyDecomposition(chronicle_id=chronicle_id, fragment_ord=fragment_ord, items=tuple(result.items))
