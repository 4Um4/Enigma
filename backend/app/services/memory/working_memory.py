from __future__ import annotations

# backend/app/services/memory/working_memory.py
"""
R1.2 / R5.1 — Working Memory: скользящее окно событий в RAM.
R5.1: поддержка EventMemory с decay lifecycle.
Не пишет на диск. Сбрасывается при перезапуске.
"""


from collections import deque
from typing import Any, Dict, List, Tuple, Union

from app.models.npc_state import EventMemory, MemoryStage

# Константа из Now.md — не магическое число
_DEFAULT_MAXLEN: int = 20


class WorkingMemory:
    """
    Скользящее окно последних событий сессии.
    Хранит EventMemory (R5.1) или legacy dict (обратная совместимость).
    """

    def __init__(self, maxlen: int = _DEFAULT_MAXLEN) -> None:
        self._buffers: Dict[str, deque] = {}
        self._maxlen = maxlen

    def push(
        self,
        campaign_id: str,
        event: Union[EventMemory, Dict[str, Any]],
    ) -> None:
        """Добавляет событие в буфер кампании."""
        if campaign_id not in self._buffers:
            self._buffers[campaign_id] = deque(maxlen=self._maxlen)
        self._buffers[campaign_id].append(event)

    def get(self, campaign_id: str) -> List[Union[EventMemory, Dict[str, Any]]]:
        """Возвращает все события буфера (от старых к новым)."""
        return list(self._buffers.get(campaign_id, []))

    def apply_decay(
        self,
        campaign_id: str,
        game_days: float = 1.0,
    ) -> List[Tuple[str, float]]:
        """
        R5.3 + Этап 8 — применяет decay по игровым дням, возвращает identity weights.
        Момент перехода в ABSTRACT — единственный триггер для L3 traits.
        Вызывается из MemoryManager.run_decay_if_needed() — не напрямую.
        """
        events = self.get(campaign_id)
        if not events:
            return []

        decayed: List = []
        identity_weights: List[Tuple[str, float]] = []

        for event in events:
            if isinstance(event, EventMemory):
                prev_stage = event.stage
                updated = event.decayed(game_days)

                # R5.3: переход в ABSTRACT → событие уходит в L3 Identity
                if (
                    prev_stage != MemoryStage.ABSTRACT
                    and updated.stage == MemoryStage.ABSTRACT
                ):
                    weight = updated.to_identity_weight()
                    if weight is not None:
                        identity_weights.append(weight)

                # EMRL E1.1 floor: событие, ставшее сутью ДО входа в цикл,
                # не выпускается в FORGOTTEN. Маркер сути — семантический,
                # не стадийный: stage ABSTRACT (зона <0.30 важности) ИЛИ
                # флаг is_compressed (реальная консолидация — «несколько
                # похожих сжаты в абстракцию»). Голая stage-зона COMPRESSED
                # без флага — просто стареющее событие, не суть (шум обязан
                # умирать — замок test_fresh_noise поймал захват зоны в
                # первое чтение контракта).
                # Проверка по входу (prev), не по updated.stage: ABSTRACT-окно
                # одного тика распада иначе проскакивается.
                # E1.1-финал: ЕДИНСТВЕННЫЙ маркер сути — is_compressed
                # (эпизод реально сжат консолидацией). Стадия ABSTRACT как
                # зона важности (<0.30) присваивается любому стареющему
                # событию — включая шум, который входил в цикл распада
                # с prev_stage=ABSTRACT и спасался floor'ом (замок
                # test_fresh_noise, третья итерация).
                _is_essence_on_entry = bool(event.is_compressed)
                if _is_essence_on_entry and updated.is_forgotten:
                    object.__setattr__(updated, "importance", 0.1)
                    object.__setattr__(updated, "accessibility", 0.2)
                    object.__setattr__(updated, "stage", MemoryStage.ABSTRACT)
                if not updated.is_forgotten:
                    decayed.append(updated)
                # Всё прочее ниже порога — молча умирает (как раньше):
                # событие не оставило следа смысла
            else:
                # Legacy dict — без decay
                decayed.append(event)

        self.replace_all(campaign_id, decayed)
        return identity_weights

    def get_keys_with_prefix(self, prefix: str) -> List[str]:
        """Возвращает ключи буферов начинающихся с prefix."""
        return [k for k in self._buffers if k.startswith(prefix)]

    def clear(self, campaign_id: str) -> None:
        """Очищает буфер кампании."""
        self._buffers.pop(campaign_id, None)

    def replace_all(
        self,
        campaign_id: str,
        events: List[Union[EventMemory, Dict[str, Any]]],
    ) -> None:
        """
        Атомарная замена буфера.
        Используется после decay — старые данные не трогаются до готовности нового списка.
        """
        new_buf: deque = deque(maxlen=self._maxlen)
        for event in events:
            new_buf.append(event)
        self._buffers[campaign_id] = new_buf
