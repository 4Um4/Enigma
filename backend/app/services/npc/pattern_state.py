"""
path: /project/backend/app/services/npc/pattern_state.py
Назначение: Инкрементальное состояние достаточной статистики PatternDetector
(ADR-O-400): заменяет полное сканирование query_raw(t_from=0) на
update(state(H1), H2) при математически доказанной эквивалентности.
Exactness contract: Σx/Σx² — Fraction (statistics.variance эталон);
cumulative — последовательный float в порядке потока (байт-идентичность
с оригиналом). Никакого I/O — чистая математика (Домен, §1).
Эквивалентность cumulative — против встроенного sum() ТЕКУЩЕГО интерпретатора:
CPython 3.12+ суммирует float'ы Ноймайером, CPython 3.11 (матрица CI) — обычным
последовательным сложением; жёсткая привязка к одному алгоритму даёт
ULP-расхождение с эталоном на другой версии (поймано oracle-кейсом 3.11).
Зависимости: app.domain.identity_events (TraitDriftEvent, EvidenceOfPersistence)
Основные сущности: SourceStats, WatermarkState
Запуск: тесты — backend/tests/test_pattern_watermark_oracle.py
"""

import math
import sys
from fractions import Fraction
from typing import Dict, Iterable, List

from app.domain.identity_events import EvidenceOfPersistence, TraitDriftEvent

# Гейт шума — тот же, что в pattern_detector (единый источник истины)
from app.services.npc.pattern_detector import MIN_EVENTS_FOR_PERSISTENCE

_INVALID_SOURCES = {"unknown", "", None}

# ADR-O-400 equivalence: встроенный sum() (эталон pattern_detector) с CPython 3.12
# использует компенсацию Ноймайера, до 3.12 — простое последовательное сложение.
# Кандидат обязан побитово повторять sum() версии, на которой он запущен, иначе
# oracle (только ==, approx запрещён) падает на ULP-расхождении в CI-матрице 3.11.
_SUM_USES_NEUMAIER = sys.version_info >= (3, 12)


class SourceStats:
    """Достаточная статистика одного (npc_id, source_id).
    Поля закрыты для мутирования вне update() (single-writer)."""

    __slots__ = ("n", "cumulative", "_comp", "_sum_x", "_sum_x2", "last_sign", "sign_flips", "first_seen")

    def __init__(self, first_seen: int) -> None:
        self.n: int = 0
        self.cumulative: float = 0.0
        self._comp: float = 0.0  # компенсация Ноймайера (sum() в CPython 3.12+)
        self._sum_x: Fraction = Fraction(0)
        self._sum_x2: Fraction = Fraction(0)
        # NOTE(mypy): знак из copysign — float; аннотация поля float.
        # Начальное значение 0 (int) сохраняет прежнюю сериализацию до первого update().
        self.last_sign: float = 0
        self.sign_flips: int = 0
        self.first_seen: int = first_seen

    def update(self, effect_value: float, observation_weight: float) -> None:
        # Эквивалентность с оригиналом: воспроизводим состояние встроенного sum()
        # (total + comp для Ноймайера 3.12+, чистый total для 3.11).
        weighted = effect_value * observation_weight
        if _SUM_USES_NEUMAIER:
            t = self.cumulative + weighted
            if abs(self.cumulative) >= abs(weighted):
                self._comp += (self.cumulative - t) + weighted
            else:
                self._comp += (weighted - t) + self.cumulative
            self.cumulative = t
        else:
            # CPython <= 3.11: sum() — последовательное сложение (0.0 + w0 = w0)
            self.cumulative = self.cumulative + weighted
        x = Fraction(effect_value)
        self._sum_x += x
        self._sum_x2 += x * x
        # Знак — из ИСХОДНОГО float (ADR-O-400 equivalence): math.copysign
        # различает -0.0/+0.0, Fraction(-0.0) — нет (поймано oracle-кейсом)
        sign = math.copysign(1, effect_value)
        if self.n > 0:
            if self.last_sign != sign:
                self.sign_flips += 1
        self.last_sign = sign
        self.n += 1

    def behavior_variance(self) -> float:
        if self.n < 2:
            return 0.0
        # Точная выборочная дисперсия (знаменатель n-1) = float(точного значения).
        exact_var = (self._sum_x2 - self._sum_x * self._sum_x / self.n) / (self.n - 1)
        return float(exact_var)

    def temporal_instability(self) -> float:
        return self.sign_flips / (self.n - 1) if self.n > 1 else 0.0

    def to_dict(self) -> dict:
        # §12.1: ключи — константы; Fraction → (num, den) для round-trip
        return {
            "n": self.n,
            "cumulative": self.cumulative,
            "comp": self._comp,
            "sum_x_num": self._sum_x.numerator,
            "sum_x_den": self._sum_x.denominator,
            "sum_x2_num": self._sum_x2.numerator,
            "sum_x2_den": self._sum_x2.denominator,
            "last_sign": self.last_sign,
            "sign_flips": self.sign_flips,
            "first_seen": self.first_seen,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SourceStats":
        obj = cls.__new__(cls)
        obj.n = d["n"]
        obj.cumulative = d["cumulative"]
        obj._comp = d["comp"]
        obj._sum_x = Fraction(d["sum_x_num"], d["sum_x_den"])
        obj._sum_x2 = Fraction(d["sum_x2_num"], d["sum_x2_den"])
        obj.last_sign = d["last_sign"]
        obj.sign_flips = d["sign_flips"]
        obj.first_seen = d["first_seen"]
        return obj


class WatermarkState:
    """Per-NPC агрегат по всем source_id + порядок первого появления.
    ADR-O-400 контракт 6: last_seen_tick — граница уже увиденной хроники
    (tail-read: query_raw(t_from=last_seen_tick + 1))."""

    def __init__(self) -> None:
        self._sources: Dict[str, SourceStats] = {}
        self.last_seen_tick: int = -1

    def ingest_tail(self, events: List[TraitDriftEvent]) -> None:
        """H2 = хвост хроники (tick > last_seen_tick). Нарушение
        tick-монотонности — RuntimeError (громко, не молчаливая потеря)."""
        for ev in events:
            if ev.tick_id <= self.last_seen_tick:
                raise RuntimeError(
                    f"[ADR-O-400] L1-монотонность нарушена: tick {ev.tick_id} <= "
                    f"watermark {self.last_seen_tick} (npc={ev.target_id})"
                )
        self.update(events)
        if events:
            self.last_seen_tick = events[-1].tick_id

    def update(self, events: Iterable[TraitDriftEvent]) -> None:
        for ev in events:
            if ev.source_id in _INVALID_SOURCES:
                raise ValueError(
                    f"Нарушение ADR-O-305: Событие с невалидным source_id='{ev.source_id}'"
                )
            st = self._sources.get(ev.source_id)
            if st is None:
                st = SourceStats(first_seen=len(self._sources))
                self._sources[ev.source_id] = st
            st.update(ev.effect_value, ev.observation_weight)

    def to_evidence(self) -> List[EvidenceOfPersistence]:
        out: List[EvidenceOfPersistence] = []
        for sid, st in sorted(self._sources.items(), key=lambda kv: kv[1].first_seen):
            if st.n < MIN_EVENTS_FOR_PERSISTENCE:
                continue
            out.append(EvidenceOfPersistence(
                source_id=sid,
                # финал Ноймайера — только когда он накапливался (3.12+);
                # на 3.11 comp всегда 0.0, а x + 0.0 изменил бы знак -0.0
                cumulative_effect=(
                    st.cumulative + st._comp if _SUM_USES_NEUMAIER else st.cumulative
                ),
                behavior_variance=st.behavior_variance() * st.temporal_instability(),
            ))
        return out

    def to_dict(self) -> dict:
        return {
            "last_seen_tick": self.last_seen_tick,
            "sources": {sid: st.to_dict() for sid, st in self._sources.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WatermarkState":
        obj = cls.__new__(cls)
        obj._sources = {}
        # Обратная совместимость: старая форма (без last_seen_tick) = чистый state
        obj.last_seen_tick = d.get("last_seen_tick", -1)
        for sid, sd in d.get("sources", {}).items():
            st = SourceStats.from_dict(sd)
            obj._sources[sid] = st
        return obj
