"""
Движок социального распространения (Шаг D).

Распространяет события через граф NPC-NPC связей с искажением и затуханием.

path: /backend/app/services/social/social_engine.py
Назначение: Движок распространения слухов через граф связей с искажением и затуханием
Зависимости: app.models.social, logging
Основные сущности: SocialEngine

Контракт:
- SocialEngine НЕ пишет состояние. Возвращает List[PropagationResult].
- Вызывающий код (game_loop) решает, применять ли результаты.
- LLM НЕ получает числовые данные о слухах. Только continuity_note.
- Randomness НЕ используется — искажение детерминистично (trust-based).

Алгоритм (BFS от свидетелей):
1. Событие происходит → свидетели фиксируются (уже получили дельты от StateApplicator)
2. BFS от свидетелей по графу связей (max_hops=3)
3. На каждом хопе: intensity *= HOP_DECAY^hop, затем trust-based distortion
4. Если perceived_intensity > PROPAGATION_THRESHOLD → PropagationResult
5. Freq cap: одно событие не доходит до одного NPC чаще 1/FREQ_CAP_TICKS тиков

Искажение (только для негативных событий):
- Низкое доверие к источнику слуха → усиление (враги преувеличивают зло)
- Высокое доверие к источнику → смягчение (друзья защищают репутацию)
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.social import PropagationResult, Relationship, Rumor

logger = logging.getLogger(__name__)


class SocialEngine:
    """
    Фасад социального графа и распространения слухов.

    Хранит:
    - _graph: направленный граф {(source, target): Relationship}
    - _freq_tracker: throttle для предотвращения спама слухами (эфемерный, не сохраняется)
    """

    # === Константы искажения и затухания ===
    MAX_HOPS: int = 3
    HOP_DECAY: float = 0.8                # intensity *= 0.8 при каждом хопе
    PROPAGATION_THRESHOLD: float = 0.15    # ниже — слух не регистрируется
    FREQ_CAP_TICKS: int = 5               # мин. тиков между одинаковыми слухами

    # Искажение на основе доверия (только для негативных событий)
    LOW_TRUST_AMPLIFY: float = 1.3        # доверие < 0.2 → усиливает негатив
    HIGH_TRUST_DAMPEN: float = 0.7        # доверие > 0.6 → смягчает негатив
    TRUST_LOW_THRESHOLD: float = 0.2
    TRUST_HIGH_THRESHOLD: float = 0.6

    # Влияние на получателя (капы — один слух не может сломать отношения)
    TRUST_DELTA_SCALE: float = 0.05       # max |trust_delta| от одного слуха
    STRESS_DELTA_SCALE: float = 0.25      # max stress_delta от негативного слуха

    # Обратные связи по умолчанию (если reverse edge не в конфиге)
    DEFAULT_REVERSE_TRUST: float = 0.1
    DEFAULT_REVERSE_AFFECTION: float = 0.0
    DEFAULT_REVERSE_NATURE: str = "acquaintance"

    # Какие event_type считаются негативными
    NEGATIVE_EVENTS: Set[str] = frozenset({
        "player_attacks", "player_insults", "player_threatens",
        "player_steals", "npc_killed", "npc_breaks",
    })

    # Дополнительные propagatable события (не негативные, но достойные слухов)
    EXTRA_PROPAGATABLE: Set[str] = frozenset({
        "player_helpers", "npc_role_changed",
    })

    # Минимальная интенсивность исходного события для распространения
    MIN_ORIGIN_INTENSITY: float = 0.3

    def __init__(
        self,
        graph: Dict[Tuple[str, str], Relationship],
        name_map: Optional[Dict[str, str]] = None,
    ) -> None:
        self._graph = graph
        self._name_map = name_map or {}
        # Эфемерный throttle: {npc_id: {event_key: last_tick}}
        # Не сохраняется — при загрузке сессии сбрасывается (допустимо)
        self._freq_tracker: Dict[str, Dict[str, int]] = {}

    # ─── Графовые операции ───

    def get_relationship(self, source: str, target: str) -> Optional[Relationship]:
        """Направленная связь source → target."""
        return self._graph.get((source, target))

    def get_connections(self, npc_id: str) -> Dict[str, Relationship]:
        """Все исходящие связи NPC (кому он может рассказать слух)."""
        return {k[1]: v for k, v in self._graph.items() if k[0] == npc_id}

    def get_all_npc_ids(self) -> Set[str]:
        """Уникальные NPC, присутствующие в графе."""
        ids: Set[str] = set()
        for src, tgt in self._graph:
            ids.add(src)
            ids.add(tgt)
        return ids

    def are_connected(self, a: str, b: str) -> bool:
        """Хотя бы одна направленная связь между a и b."""
        return (a, b) in self._graph or (b, a) in self._graph

    # ─── Основное распространение ───

    def propagate(
        self,
        event_type: str,
        intensity: float,
        actor: str,
        target: str,
        witnesses: List[str],
        current_tick: int,
    ) -> List[PropagationResult]:
        """
        BFS-распространение события через социальный граф.

        Свидетели НЕ включаются в результаты — они уже получили дельты
        от StateApplicator напрямую. Слух начинается с хопа 1.

        Args:
            event_type: тип события ("player_attacks", ...)
            intensity: исходная интенсивность [0..1]
            actor: кто совершил (обычно "player")
            target: на кого направлено (npc_id)
            witnesses: npc_id, видевшие напрямую
            current_tick: для freq_cap

        Returns:
            PropagationResult для каждого NPC, узнавшего через слух.
        """
        if intensity < self.MIN_ORIGIN_INTENSITY:
            return []

        if not self._is_propagatable(event_type):
            return []

        is_negative = event_type in self.NEGATIVE_EVENTS
        results: List[PropagationResult] = []
        visited: Set[str] = set(witnesses)

        # Строим начальный фронт: связи свидетелей (hop=1)
        # Каждая запись: (neighbor_id, hop, carrier_id)
        frontier: List[Tuple[str, int, str]] = []
        for witness in witnesses:
            for neighbor_id in self.get_connections(witness):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    frontier.append((neighbor_id, 1, witness))

        while frontier:
            next_frontier: List[Tuple[str, int, str]] = []

            for neighbor_id, hop, carrier in frontier:
                if hop > self.MAX_HOPS:
                    continue

                # Частотный кап: не спамить одним слухом
                event_key = f"{event_type}:{target}"
                if not self._check_freq(neighbor_id, event_key, current_tick):
                    continue

                # Связь carrier → neighbor определяет искажение
                rel = self.get_relationship(carrier, neighbor_id)
                if rel is None:
                    continue

                # Затухание по хопам
                decayed = intensity * (self.HOP_DECAY ** hop)

                # Искажение на основе доверия к источнику (carrier)
                perceived = self._distort_intensity(
                    decayed, rel.effective_trust, is_negative
                )

                if perceived < self.PROPAGATION_THRESHOLD:
                    continue

                self._register_freq(neighbor_id, event_key, current_tick)

                rumor = Rumor(
                    origin_event_type=event_type,
                    origin_target=target,
                    origin_actor=actor,
                    base_intensity=intensity,
                    perceived_intensity=round(perceived, 4),
                    hop=hop,
                    carrier=carrier,
                    distortion_applied=round(perceived - decayed, 4),
                )

                trust_delta = self._compute_trust_delta(
                    perceived, is_negative, rel.effective_trust
                )
                stress_delta = (
                    round(perceived * self.STRESS_DELTA_SCALE, 4)
                    if is_negative
                    else 0.0
                )

                continuity_note = self._build_continuity_note(
                    neighbor_id, rumor, carrier
                )

                results.append(PropagationResult(
                    npc_id=neighbor_id,
                    trust_delta=round(trust_delta, 4),
                    stress_delta=stress_delta,
                    rumor=rumor,
                    continuity_note=continuity_note,
                ))

                # Продолжаем BFS: связи получателя → его соседи (hop+1)
                for next_neighbor in self.get_connections(neighbor_id):
                    if next_neighbor not in visited:
                        visited.add(next_neighbor)
                        next_frontier.append(
                            (next_neighbor, hop + 1, neighbor_id)
                        )

            frontier = next_frontier

        if results:
            logger.debug(
                "[SOCIAL] Propagated %s (int=%.2f) → %d recipients",
                event_type, intensity, len(results),
            )

        return results

    # ─── Persistence ───

    def get_runtime_state(self) -> Dict[str, Dict]:
        """
        Runtime-часть графа для сохранения в saves/.
        Сохраняет только mutated связи (где есть отличия от дефолтов).
        """
        runtime: Dict[str, Dict] = {}
        for (src, tgt), rel in self._graph.items():
            key = f"{src}\u2192{tgt}"  # стрелка → как разделитель
            rd = rel.to_runtime_dict()
            if any(v != 0 for v in rd.values()):
                runtime[key] = rd
        return runtime

    def apply_runtime_state(self, data: Dict[str, Dict]) -> None:
        """Восстановление runtime из saves/ (не трогает base_*)."""
        for key, rd in data.items():
            try:
                # Разделяем по стрелке →
                parts = key.split("\u2192")
                if len(parts) != 2:
                    continue
                src, tgt = parts[0], parts[1]
                rel = self._graph.get((src, tgt))
                if rel:
                    rel.apply_runtime_dict(rd)
            except (ValueError, KeyError):
                logger.warning("[SOCIAL] Invalid runtime key: %s", key)

    # ─── Приватные: искажение ───

    def _is_propagatable(self, event_type: str) -> bool:
        """Только значимые события становятся слухами."""
        return event_type in (self.NEGATIVE_EVENTS | self.EXTRA_PROPAGATABLE)

    def _distort_intensity(
        self,
        base_intensity: float,
        trust: float,
        is_negative: bool,
    ) -> float:
        """
        Искажение на основе доверия к источнику слуха.

        Негативные события:
        - Низкое доверие → линейная интерполяция к LOW_TRUST_AMPLIFY
        - Высокое доверие → линейная интерполяция к HIGH_TRUST_DAMPEN
        - Среднее доверие → factor = 1.0 (без искажения)

        Позитивные — без искажения (в будущем можно добавить обратную логику).
        """
        if not is_negative:
            return base_intensity

        if trust < self.TRUST_LOW_THRESHOLD:
            # trust=0 → amplify=1.3, trust=0.2 → amplify=1.0
            ratio = 1.0 - trust / self.TRUST_LOW_THRESHOLD
            factor = 1.0 + (self.LOW_TRUST_AMPLIFY - 1.0) * ratio
        elif trust > self.TRUST_HIGH_THRESHOLD:
            # trust=0.6 → dampen=1.0, trust=1.0 → dampen=0.7
            ratio = (trust - self.TRUST_HIGH_THRESHOLD) / (
                1.0 - self.TRUST_HIGH_THRESHOLD
            )
            factor = 1.0 - (1.0 - self.HIGH_TRUST_DAMPEN) * ratio
        else:
            factor = 1.0

        return max(0.0, min(1.0, base_intensity * factor))

    def _compute_trust_delta(
        self,
        perceived_intensity: float,
        is_negative: bool,
        relationship_trust: float,
    ) -> float:
        """
        Небольшое изменение доверия получателя к actor события.

        Негативный слух → trust к actor падает (масштаб ~0.05).
        Смягчается если получатель доверяет carrier (источнику слуха).
        """
        if not is_negative:
            return 0.0

        # Базовое изменение: пропорционально воспринятой интенсивности
        base_delta = -perceived_intensity * self.TRUST_DELTA_SCALE

        # Доверие к carrier модифицирует восприимчивость к слуху
        if relationship_trust > self.TRUST_HIGH_THRESHOLD:
            trust_discount = 0.5   # доверяет источнику → скидка 50%
        elif relationship_trust < self.TRUST_LOW_THRESHOLD:
            trust_discount = 1.2   # не доверяет → наоборот, больше верит
        else:
            trust_discount = 1.0

        # Жёсткий кап: один слух не может сдвинуть trust больше чем на 0.1
        return max(-0.1, base_delta * trust_discount)

    # ─── Приватные: freq cap ───

    def _check_freq(self, npc_id: str, event_key: str, current_tick: int) -> bool:
        npc_freq = self._freq_tracker.get(npc_id, {})
        last_tick = npc_freq.get(event_key, -999)
        return (current_tick - last_tick) >= self.FREQ_CAP_TICKS

    def _register_freq(
        self, npc_id: str, event_key: str, current_tick: int
    ) -> None:
        if npc_id not in self._freq_tracker:
            self._freq_tracker[npc_id] = {}
        self._freq_tracker[npc_id][event_key] = current_tick

    # ─── Приватные: нарратив ───

    def _build_continuity_note(
        self, npc_id: str, rumor: Rumor, carrier: str
    ) -> str:
        """
        Фактическая строка для SceneContinuity.
        Минимальна, без эмоций — DM решит как подать.
        """
        action_map = {
            "player_attacks": "атаковал",
            "player_insults": "оскорбил",
            "player_threatens": "угрожал",
            "player_steals": "украл у",
            "npc_killed": "убил",
            "npc_breaks": "сломал",
            "player_helpers": "помог",
            "npc_role_changed": "сменил роль",
        }

        action = action_map.get(rumor.origin_event_type, rumor.origin_event_type)
        target_name = self._name_map.get(rumor.origin_target, rumor.origin_target)
        carrier_name = self._name_map.get(carrier, carrier)

        hop_label = "" if rumor.hop == 1 else f" (через {rumor.hop} передач)"

        return (
            f"[слух] {npc_id} узнал от {carrier_name}{hop_label}: "
            f"{rumor.origin_actor} {action} {target_name}"
        )

    # ─── Социальные модификаторы для DecisionHub (Фаза 3.2) ───

    def compute_social_modifiers(
        self,
        npc_id: str,
        player_distances: Dict[str, float],
        event_type: str,
        event_target: Optional[str] = None,
        extra_event_types: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """
        Модификаторы score на основе социального графа + расстояний.

        Аналог EconomicModifier — добавляется к score в DecisionHub.compute().
        НЕ создаёт новые интенты — усиливает существующие по социальным триггерам.

        Триггеры:
        - Ревность: игрок близко к other + affection > 0.3 → INTIMIDATE
        - Защита союзника: игрок угрожает other + trust > 0.4 → THREATEN
        - Страх перед ассоциатом: игрок атакует other + fear > 0.3 → FLEE
        - Долговой рычаг: игрок рядом с должником → OBSERVE

        extra_event_types: дополнительные типы событий (например spatial_events)
        для расширения проверки без изменения основного event_type.
        """
        # Объединяем все типы событий для проверки
        _all_event_types = {event_type}
        if extra_event_types:
            _all_event_types.update(extra_event_types)
        modifiers: Dict[str, float] = {}

        connections = self.get_connections(npc_id)
        if not connections:
            return modifiers

        target_dist = player_distances.get(event_target, 999.0) if event_target else 999.0

        for other_id, rel in connections.items():
            other_dist = player_distances.get(other_id, 999.0)
            is_target = (other_id == event_target)

            # РЕВНОСТЬ: игрок рядом с significant other — по ВСЕМ связям, не только target
            # Фаза 3.4: исправление ПРОБЛЕМЫ 2 — NPC видит proximity к любому connected NPC
            _JEALOUSY_EVENTS = {"player_interacts", "player_threatens", "proximity_close"}
            if (rel.effective_affection > 0.3
                    and other_dist < 3.0
                    and bool(_all_event_types & _JEALOUSY_EVENTS)):
                bonus = round(0.4 * rel.effective_affection, 4)
                modifiers["INTIMIDATE"] = max(modifiers.get("INTIMIDATE", 0.0), bonus)

            # ЗАЩИТА СОЮЗНИКА: только если атакуют конкретного друга
            _PROTECT_EVENTS = {"player_attacks", "player_threatens", "player_insults"}
            if is_target and (rel.effective_trust > 0.4
                    and bool(_all_event_types & _PROTECT_EVENTS)):
                bonus = round(0.3 * rel.effective_trust, 4)
                modifiers["THREATEN"] = max(modifiers.get("THREATEN", 0.0), bonus)

            # СТРАХ ПЕРЕД АССОЦИАТОМ: только если атакуют того кого боимся
            if is_target and rel.fear > 0.3 and "player_attacks" in _all_event_types:
                bonus = round(0.3 * rel.fear, 4)
                modifiers["FLEE"] = max(modifiers.get("FLEE", 0.0), bonus)

            # ДОЛГОВОЙ РЫЧАГ: игрок рядом с любым должником — по ВСЕМ связям
            if rel.debt > 0 and other_dist < 4.0:
                bonus = round(0.2 * min(rel.debt / 50.0, 1.0), 4)
                modifiers["OBSERVE"] = max(modifiers.get("OBSERVE", 0.0), bonus)

        return modifiers

    # ─── Factory ───

    @classmethod
    def from_config(
        cls,
        config_data: Dict[str, Any],
        name_map: Optional[Dict[str, str]] = None,
    ) -> "SocialEngine":
        """
        Загружает социальный граф из village_relations.json.

        Автоматически создаёт обратные связи с дефолтными значениями,
        если прямая связь определена, а обратная — нет.
        Это позволяет слухам распространяться в обе стороны.
        """
        graph: Dict[Tuple[str, str], Relationship] = {}
        defined_pairs: Set[Tuple[str, str]] = set()

        relations = config_data.get("relations", {})
        for source_id, targets in relations.items():
            for target_id, rel_data in targets.items():
                rel = Relationship(
                    nature=rel_data.get("nature", "acquaintance"),
                    base_trust=float(rel_data.get("base_trust", 0.0)),
                    base_affection=float(rel_data.get("base_affection", 0.0)),
                )
                graph[(source_id, target_id)] = rel
                defined_pairs.add((source_id, target_id))

        # Обратные связи с дефолтами — для двустороннего распространения
        for src, tgt in list(defined_pairs):
            reverse = (tgt, src)
            if reverse not in graph:
                graph[reverse] = Relationship(
                    nature=cls.DEFAULT_REVERSE_NATURE,
                    base_trust=cls.DEFAULT_REVERSE_TRUST,
                    base_affection=cls.DEFAULT_REVERSE_AFFECTION,
                )

        logger.info(
            "[SOCIAL] Loaded %d edges (%d defined, %d reverse defaults)",
            len(graph), len(defined_pairs), len(graph) - len(defined_pairs),
        )

        return cls(graph=graph, name_map=name_map)