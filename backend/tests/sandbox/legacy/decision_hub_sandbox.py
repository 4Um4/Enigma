# -*- coding: utf-8 -*-
"""
decision_hub_sandbox.py — калибровка DecisionHub без LLM/pygame.

Запуск: cd backend ; python decision_hub_sandbox.py

Генерирует N случайных NPCState + EventContext, прогоняет через
DecisionHub.compute() и строит распределение score/intent.

Выявляет:
- Взрывы score (> 3.0)
- Коллапсы score (< -1.0)
- Доминирование одного intent (100% IDLE/OBSERVE = сломанная формула)

path: /backend/decision_hub_sandbox.py
Назначение: Песочница для калибровки DecisionHub (1000+ рандомных NPC)
Зависимости: app.models.npc_state, app.models.npc_profile, app.models.behavior_mask, app.services.npc.decision_hub, app.services.events.event_types, matplotlib (опционально)
Основные сущности: SandboxConfig, HubSnapshot, DecisionHubSandbox, HubReporter
"""

import csv
import os
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.domain.identity_events import EffectiveDrives

_MOCK_DRIVES = EffectiveDrives.from_dict({"control": 0.5, "significance": 0.5, "fear": 0.5, "desire": 0.5})

from app.models.behavior_mask import BehaviorMask, BehaviorMaskState
from app.models.npc_profile import NPCProfileL0, PsycheBase
from app.models.npc_state import NPCState, WillState
from app.services.events.event_types import EventType
from app.services.npc.decision_hub import DecisionHub, EventContext


@dataclass
class SandboxConfig:
    """Настройки симуляции."""

    iterations: int = 2000
    seed: int = 42
    score_anomaly_low: float = -1.0
    score_anomaly_high: float = 3.0
    # Спринт 30: Артефакты песочницы должны лежать в песочнице, а не в корне проекта
    output_csv: str = str(Path(__file__).resolve().parent / "hub_balance_results.csv")


@dataclass
class HubSnapshot:
    """Результат одного прогона."""

    iteration: int
    npc_id: str
    event_type: str
    intent: str
    score: float
    winning_margin: float  # отрыв победителя от второго места
    stress: float
    integrity: float
    will_state: str
    mask_active: bool
    scores_trace: Dict[str, float] = field(default_factory=dict)


class DecisionHubSandbox:
    """Ядро симуляции DecisionHub."""

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config
        self.snapshots: List[HubSnapshot] = []
        self.errors: List[Dict[str, Any]] = []

    @staticmethod
    def _rand_float(low: float = 0.0, high: float = 1.0) -> float:
        return random.uniform(low, high)

    def _generate_state(self, npc_id: str) -> NPCState:
        """Генерирует валидный NPCState со случайными экстремальными значениями."""
        return NPCState(
            npc_id=npc_id,
            stress=self._rand_float(0.0, 100.0),  # реальный диапазон стресса
            resentment=self._rand_float(0.0, 1.0),
            dependency=self._rand_float(0.0, 1.0),
            identity_integrity=self._rand_float(0.0, 1.0),
            pressure_resistance=self._rand_float(0.0, 1.0),
            will_state=random.choice(list(WillState)),
            behavior_mask=BehaviorMaskState(
                mask=random.choice(list(BehaviorMask)),
                intensity=self._rand_float(0.0, 1.0),
            ),
        )

    def _generate_profile(self, npc_id: str) -> NPCProfileL0:
        """Генерирует валидный NPCProfileL0."""
        return NPCProfileL0(
            id=npc_id,
            name=f"NPC_{npc_id}",
            tier=random.choice(["mass", "minor", "major"]),
            drives_base={
                "control": self._rand_float(0.0, 1.0),
                "significance": self._rand_float(0.0, 1.0),
                "fear": self._rand_float(0.0, 1.0),
                "desire": self._rand_float(0.0, 1.0),
            },
            psyche_base=PsycheBase(
                willpower=random.randint(10, 100),
                breakpoint=random.randint(10, 100),
                loyalty_base=random.randint(0, 100),
            ),
            voice_profile="neutral",
        )

    def _generate_event(self) -> EventContext:
        """Генерирует случайный EventContext."""
        return EventContext(
            event_type=random.choice(list(EventType)),
            actor_id="player",
            success=random.choice([True, False]),
            intensity=self._rand_float(0.0, 1.5),
            distance=self._rand_float(0.0, 20.0),
            witness_count=random.randint(0, 10),
            location="sandbox_tavern",
            scene_flags=set(),
            scene_facts=[],
        )

    def run(self) -> List[HubSnapshot]:
        """Запускает симуляцию."""
        random.seed(self.config.seed)
        hub = DecisionHub(seed=self.config.seed)

        print(f"[SANDBOX] Запуск: {self.config.iterations} итераций (seed={self.config.seed})")
        print()

        for i in range(1, self.config.iterations + 1):
            npc_id = f"npc_{i}"
            state = self._generate_state(npc_id)
            profile = self._generate_profile(npc_id)
            event = self._generate_event()

            try:
                result = hub.compute(
                    state=state,
                    personality=profile,
                    event=event,
                )

                # Считаем отрыв победителя
                sorted_scores = sorted(result.scores_trace.values(), reverse=True)
                margin = (sorted_scores[0] - sorted_scores[1]) if len(sorted_scores) > 1 else sorted_scores[0]

                snap = HubSnapshot(
                    iteration=i,
                    npc_id=npc_id,
                    event_type=event.event_type.value,
                    intent=result.intent.value,
                    score=result.score,
                    winning_margin=margin,
                    stress=state.stress,
                    integrity=state.identity_integrity,
                    will_state=state.will_state.value,
                    mask_active=state.behavior_mask.is_active(),
                    scores_trace=result.scores_trace,
                )
                self.snapshots.append(snap)

            except Exception as e:
                self.errors.append(
                    {
                        "iteration": i,
                        "npc_id": npc_id,
                        "error": str(e),
                    }
                )

        print(f"[SANDBOX] Успешно: {len(self.snapshots)}, Ошибок: {len(self.errors)}")
        if self.errors:
            print(f"[SANDBOX] Пример ошибки: {self.errors[0]['error']}")
        print()
        return self.snapshots


class HubReporter:
    """Анализ и вывод результатов."""

    INTENT_LABELS: Dict[str, str] = {
        "idle": "бездействие",
        "talk": "разговор",
        "warn": "предупреждение",
        "intimidate": "запугивание",
        "flee": "бегство",
        "attack": "атака",
        "help": "помощь",
        "report": "донос",
        "trade": "торговля",
        "observe": "наблюдение",
        "explain": "объяснение",
        "block_path": "преградить путь",
        "ambush": "засада",
        "seek_ally": "поиск союзника",
        "offer_job": "предложить работу",
        "request_service": "просьба об услуге",
        "spread_rumor": "распространить слух",
        "call_for_help": "зов помощи",
        "change_role": "сменить роль",
    }

    def __init__(self, snapshots: List[HubSnapshot], config: SandboxConfig) -> None:
        self.snaps = snapshots
        self.config = config

    def _fmt_intent(self, intent: str) -> str:
        return self.INTENT_LABELS.get(intent, intent)

    def print_distribution(self) -> None:
        """Консольная гистограмма распределения intents."""
        if not self.snaps:
            print("[REPORTER] Нет данных")
            return

        from collections import Counter

        intent_counts = Counter(s.intent for s in self.snaps)
        total = len(self.snaps)

        print("── РАСПРЕДЕЛЕНИЕ INTENT ──")
        for intent, count in intent_counts.most_common():
            pct = count / total * 100
            bar = "#" * int(pct / 2)
            print(f"{self._fmt_intent(intent):<25}: {count:>5} ({pct:>5.1f}%) {bar}")
        print()

    def print_score_stats(self) -> None:
        """Статистика score + аномалии."""
        if not self.snaps:
            return

        scores = [s.score for s in self.snaps]
        margins = [s.winning_margin for s in self.snaps]

        print("── СТАТИСТИКА SCORE ──")
        print(f"MIN:  {min(scores):.3f}")
        print(f"MAX:  {max(scores):.3f}")
        print(f"AVG:  {sum(scores) / len(scores):.3f}")
        print(f" MED: {sorted(scores)[len(scores) // 2]:.3f}")
        print()

        print("── ОТРЫВ ПОБЕДИТЕЛЯ (margin) ──")
        print(f"MIN:  {min(margins):.3f}")
        print(f"MAX:  {max(margins):.3f}")
        print(f"AVG:  {sum(margins) / len(margins):.3f}")
        print()

        # Аномалии
        anomalies_low = [s for s in self.snaps if s.score < self.config.score_anomaly_low]
        anomalies_high = [s for s in self.snaps if s.score > self.config.score_anomaly_high]

        if anomalies_low:
            print(f"── АНОМАЛИИ (score < {self.config.score_anomaly_low}): {len(anomalies_low)} ──")
            for a in anomalies_low[:10]:
                print(
                    f"  {a.npc_id}: score={a.score:.2f}, intent={a.intent}, stress={a.stress:.1f}, integrity={a.integrity:.2f}, mask={a.mask_active}"
                )
            print()

        if anomalies_high:
            print(f"── АНОМАЛИИ (score > {self.config.score_anomaly_high}): {len(anomalies_high)} ──")
            for a in anomalies_high[:10]:
                print(
                    f"  {a.npc_id}: score={a.score:.2f}, intent={a.intent}, stress={a.stress:.1f}, integrity={a.integrity:.2f}, mask={a.mask_active}"
                )
            print()

        if not anomalies_low and not anomalies_high:
            print("✅ Взрывов и коллапсов не обнаружено.")
            print()

    def print_top_scores(self) -> None:
        """Топ-5 максимальных и минимальных score с детализацией trace."""
        if not self.snaps:
            return

        sorted_snaps = sorted(self.snaps, key=lambda s: s.score)

        print("── ТОП-5 МИНИМАЛЬНЫХ SCORE ──")
        for s in sorted_snaps[:5]:
            trace_str = ", ".join(f"{k}:{v:.2f}" for k, v in sorted(s.scores_trace.items(), key=lambda x: x[1])[:5])
            print(f"{s.npc_id}: {s.score:.2f} | {trace_str}")
        print()

        print("── ТОП-5 МАКСИМАЛЬНЫХ SCORE ──")
        for s in sorted_snaps[-5:]:
            trace_str = ", ".join(
                f"{k}:{v:.2f}" for k, v in sorted(s.scores_trace.items(), key=lambda x: x[1], reverse=True)[:5]
            )
            print(f"{s.npc_id}: {s.score:.2f} | {trace_str}")
        print()

    def save_csv(self) -> None:
        """Сохраняет результаты в CSV для анализа в Excel."""
        if not self.snaps:
            return

        fieldnames = [
            "iteration",
            "npc_id",
            "event_type",
            "intent",
            "score",
            "winning_margin",
            "stress",
            "integrity",
            "will_state",
            "mask_active",
            "scores_trace",
        ]
        with open(self.config.output_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for snap in self.snaps:
                row = {k: getattr(snap, k) for k in fieldnames}
                row["scores_trace"] = str(snap.scores_trace)
                writer.writerow(row)

        print(f"[REPORTER] CSV сохранён: {self.config.output_csv}")

    def plot_charts(self) -> None:
        """Рисует графики через matplotlib."""
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("[REPORTER] matplotlib не установлен — графики пропущены")
            return

        if not self.snaps:
            return

        # 1. Гистограмма score
        fig, ax = plt.subplots(figsize=(10, 5))
        scores = [s.score for s in self.snaps]
        ax.hist(scores, bins=50, color="skyblue", edgecolor="black")
        ax.axvline(
            self.config.score_anomaly_low,
            color="red",
            linestyle="--",
            label=f"Аномалия ({self.config.score_anomaly_low})",
        )
        ax.axvline(
            self.config.score_anomaly_high,
            color="red",
            linestyle="--",
            label=f"Аномалия ({self.config.score_anomaly_high})",
        )
        ax.set_xlabel("Score")
        ax.set_ylabel("Количество")
        ax.set_title("Распределение Score в DecisionHub")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(str(Path(__file__).resolve().parent / "hub_balance_score.png"), dpi=300)
        plt.close(fig)

        # 2. Круговая диаграмма intents
        from collections import Counter

        intent_counts = Counter(s.intent for s in self.snaps)
        labels = [self._fmt_intent(k) for k in intent_counts.keys()]
        sizes = list(intent_counts.values())

        fig, ax = plt.subplots(figsize=(8, 8))
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=140)
        ax.set_title("Распределение Intent")
        fig.tight_layout()
        fig.savefig(str(Path(__file__).resolve().parent / "hub_balance_intents.png"), dpi=300)
        plt.close(fig)

        print("[REPORTER] Графики сохранены: hub_balance_*.png")


def main() -> None:
    config = SandboxConfig(
        iterations=2000,
        seed=42,
    )

    sandbox = DecisionHubSandbox(config)
    snapshots = sandbox.run()

    if snapshots:
        reporter = HubReporter(snapshots, config)
        reporter.print_distribution()
        reporter.print_score_stats()
        reporter.print_top_scores()
        reporter.save_csv()
        reporter.plot_charts()


if __name__ == "__main__":
    main()
