# backend/app/services/memory/promotion_engine.py
"""
Этап 9 — MemoryPromotionEngine: сжатие памяти.
Отдельный класс (Закон 4.1.3) — не метод LayeredMemory.

Правило: 3+ событий с одинаковыми тегами + importance < 0.5 → compress.
Шаблоны сжатия: набор тегов → текст абстракции.

path: backend/app/services/memory/promotion_engine.py
Назначение: Сжатие старых событий в абстракции (Этап 9). Отдельный класс — Закон 4.1.3.
Зависимости: EventMemory, MemoryStage
Основные сущности: MemoryPromotionEngine, CompressionResult
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

# Выше объявление _IDENTITY_RULES использует List и Tuple — они уже импортированы

from app.models.npc_state import EventMemory, MemoryStage


# Минимальное количество событий для сжатия
_COMPRESS_MIN_EVENTS: int = 3

# Порог importance — события выше порога сжимаются через ResonanceEngine (Этап 10)
_COMPRESS_MAX_IMPORTANCE: float = 0.6


# ── Шаблоны сжатия: набор тегов → текст абстракции ──

_COMPRESSION_TEMPLATES: Dict[frozenset, str] = {
    frozenset({"positive", "dialogue"}): "Игрок был дружелюбен в разговорах (несколько раз)",
    frozenset({"positive"}): "Игрок вёл себя хорошо (несколько раз)",
    frozenset({"negative", "dialogue"}): "Игрок был груб в разговорах (несколько раз)",
    frozenset({"negative"}): "Игрок вёл себя плохо (несколько раз)",
    frozenset({"combat"}): "Были стычки (несколько раз)",
    frozenset({"trade"}): "Игрок торговал (несколько раз)",
}


def _resolve_template(tags: Tuple[str, ...]) -> str:
    """Подбирает шаблон по тегам. Fallback — общий текст."""
    tag_set = frozenset(tags)
    for pattern, text in _COMPRESSION_TEMPLATES.items():
        if pattern.issubset(tag_set):
            return text
    return "Ряд событий схожего типа (сжато)"


@dataclass(frozen=True)
class CompressionResult:
    """Результат одной операции сжатия."""
    compressed: EventMemory          # новая абстракция
    removed_ids: Tuple[str, ...]     # ID исходных событий


# ── Мета-паттерны: комбинация черт → новая черта (Этап 10) ──

# Формат: (условие: Dict[trait, min_weight], результат: (trait_name, delta))
_IDENTITY_RULES: List[Tuple[Dict[str, float], Tuple[str, float]]] = [
    # Обида + страх → недоверие к незнакомцам
    ({"resentment": 0.3, "fear": 0.2}, ("distrusts_strangers", 0.2)),
    # Зависимость → угодливость
    ({"dependency": 0.4}, ("eager_to_please", 0.15)),
    # Подозрительность + обида → враждебность
    ({"suspicious": 0.3, "resentment": 0.3}, ("hostile_disposition", 0.2)),
    # Доверие → лояльность
    ({"trust_bias": 0.5}, ("loyal_to_player", 0.2)),
]


class MemoryPromotionEngine:
    """Сжатие памяти + генерация мета-черт (Этапы 9-10).

    READ-ONLY относительно входных данных — возвращает результат,
    вызывающий код применяет к narrative_cache / identity_cache.
    """

    def compress(
        self,
        events: Sequence[EventMemory],
    ) -> List[CompressionResult]:
        """Ищет группы для сжатия и возвращает результаты.

        Условия сжатия:
        - 3+ событий с одинаковыми тегами
        - importance < 0.5 (рядовые, не критические)
        - не секреты
        - не сжатые (is_compressed=False)
        """
        # Фильтруем кандидатов
        candidates = [
            e for e in events
            if not e.is_compressed
            and not e.is_secret
            and not e.is_forgotten
            and e.importance < _COMPRESS_MAX_IMPORTANCE
        ]

        if len(candidates) < _COMPRESS_MIN_EVENTS:
            return []

        # Группируем по набору тегов
        groups: Dict[frozenset, List[EventMemory]] = {}
        for e in candidates:
            key = frozenset(e.tags)
            groups.setdefault(key, []).append(e)

        results: List[CompressionResult] = []

        for _tags, group in groups.items():
            if len(group) < _COMPRESS_MIN_EVENTS:
                continue

            # Все события группы — без лимита, меньше фрагментации
            batch = group

            # Средние значения для абстракции
            avg_importance = round(
                sum(e.importance for e in batch) / len(batch), 4
            )
            avg_decay = round(
                sum(e.decay_rate for e in batch) / len(batch), 4
            )
            # Самый поздний день из группы
            max_day = max(e.day for e in batch)
            # Самый частый target_id
            target_counts: Dict[str, int] = {}
            for e in batch:
                target_counts[e.target_id] = target_counts.get(e.target_id, 0) + 1
            most_common_target = max(target_counts, key=target_counts.get)

            template = _resolve_template(batch[0].tags)

            compressed = EventMemory(
                event_type="compressed",
                target_id=most_common_target,
                emotion_tag="neutral",
                day=max_day,
                importance=min(avg_importance * 1.1, _COMPRESS_MAX_IMPORTANCE),
                clarity=0.5,
                confidence=0.6,
                decay_rate=avg_decay,
                stage=MemoryStage.ABSTRACT,
                summary=f"{template} ({len(batch)} раз)",
                npc_id=batch[0].npc_id,
                tags=batch[0].tags,
                is_compressed=True,
                compressed_from=tuple(
                    getattr(e, "id", f"seq_{e.sequence_id}") for e in batch
                ),
            )

            results.append(CompressionResult(
                compressed=compressed,
                removed_ids=tuple(
                    getattr(e, "id", f"seq_{e.sequence_id}") for e in batch
                ),
            ))

        return results

    # ──────────────────────────────────────────────────────────────────────
    # Этап 10: мета-паттерны — комбинация черт → новая черта
    # ──────────────────────────────────────────────────────────────────────
    def check_identity(
        self,
        identity_traits: Dict[str, float],
    ) -> List[Tuple[str, float]]:
        """Проверяет комбинации накопленных черт, возвращает новые.

        Вызывается после apply_identity_weights() — когда кэш обновлён.
        Не мутирует identity_traits — возвращает список (trait_name, delta)
        для применения через apply_identity_weights().
        """
        new_traits: List[Tuple[str, float]] = []

        for conditions, (trait_name, delta) in _IDENTITY_RULES:
            # Проверяем что все условия выполнены
            if all(
                identity_traits.get(t, 0.0) >= min_w
                for t, min_w in conditions.items()
            ):
                # Не создаём дубликат — только если черты ещё нет
                if trait_name not in identity_traits:
                    new_traits.append((trait_name, delta))

        return new_traits