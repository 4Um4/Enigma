# backend/app/services/perception/inference_engine.py
"""
Файл: backend/app/services/perception/inference_engine.py
Назначение: Строит гипотезы из атомарных фактов. Читает базу знаний.
Зависимости: backend.app.domain.inference, backend.app.domain.observed_fact, PyYAML
"""

import logging
import os
import uuid
from typing import Dict, List

import yaml
from app.domain.inference import Inference
from app.domain.observed_fact import ObservedFact

logger = logging.getLogger(__name__)


class InferenceEngine:
    """
    Строит гипотезы из атомарных фактов.
    ЗАПРЕТ: Не изменяет Reality (Инвариант 2).
    """

    def __init__(self) -> None:
        self._causes_map = self._load_causes_map()

    def _load_causes_map(self) -> Dict[str, List[str]]:
        """Загружает signal_causes.yaml из authoring/"""
        # Определяем путь к корню проекта (на 3 уровня вверх от этого файла)
        _root = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            )
        )
        _yaml_path = os.path.join(
            _root, "architecture", "authoring", "signal_causes.yaml"
        )

        if not os.path.exists(_yaml_path):
            logger.error(f"[INFER_ENGINE] signal_causes.yaml not found at {_yaml_path}")
            return {}

        with open(_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Разворачиваем плоский маппинг: "body_manifestation.tremor" -> ["fear", "cold", ...]
        flat_map = {}
        for signal_key, causes_data in data.get("signal_possible_causes", {}).items():
            causes = causes_data.get("possible_causes", [])
            flat_map[signal_key] = causes

        return flat_map

    def infer(self, facts: List[ObservedFact], current_tick: float) -> List[Inference]:
        inferences = []

        for fact in facts:
            # Пока строим простые 1-к-1 гипотезы.
            # В будущем здесь будет байесовский вывод.

            # Формируем ключ для поиска в signal_causes.yaml
            # fact.fact_type = "behavior", fact.fact_name = "tremor_amplitude" -> "body_manifestation.tremor"
            cause_key = self._map_fact_to_cause_key(fact)
            possible_causes = self._causes_map.get(cause_key, [])

            if possible_causes:
                inferences.append(
                    Inference(
                        inference_id=str(uuid.uuid4()),
                        target_id=fact.target_id,
                        source_fact_ids=(fact.fact_id,),
                        hypothesis=fact.fact_name,  # Пока гипотеза = имя факта
                        confidence=fact.confidence
                        * 0.9,  # Гипотеза всегда чуть слабее факта
                        possible_causes=tuple(possible_causes),
                        observed_at=fact.observed_at,
                    )
                )

        return inferences

    def _map_fact_to_cause_key(self, fact: ObservedFact) -> str:
        """Маппит имя факта на ключ в signal_causes.yaml"""
        if fact.fact_name == "tremor_amplitude":
            return "body_manifestation.tremor"
        if fact.fact_name == "muscle_tension_level":
            return "body_manifestation.muscle_tension"
        if fact.fact_name == "voice_tremor_amplitude":
            return "voice_manifestation.tremor"
        if fact.fact_name == "movement_speed":
            return "movement.coordination_impaired"  # Заглушка, потом уточним
        return ""
