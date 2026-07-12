"""
path: scripts/lint_perception_architecture.py
Назначение: Линтер для проверки YAML-контрактов на соответствие 5 инвариантам Эпистемологической Ортогональности (§17).
Зависимости: PyYAML
Основные сущности: PerceptionArchitectureLinter

Запуск: python scripts/lint_perception_architecture.py
"""

import yaml
import os
import sys
import re
from typing import List, Dict, Any


class PerceptionArchitectureLinter:
    def __init__(self, arch_dir: str = "architecture"):
        self.arch_dir = arch_dir
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.passed: List[str] = []

    def _load_yaml(self, filepath: str) -> Dict[str, Any]:
        if not os.path.exists(filepath):
            self.errors.append(f"MISSING FILE: {filepath}")
            return {}
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                self.errors.append(f"YAML PARSE ERROR in {filepath}: {e}")
                return {}

    def lint(self):
        print("=" * 60)
        print("🛡️  LINTING PERCEPTION ARCHITECTURE (§17)")
        print("=" * 60)

        # 1. Проверка perception_architecture.yaml
        arch_data = self._load_yaml(
            os.path.join(self.arch_dir, "perception_architecture.yaml")
        )
        if arch_data:
            self._check_causal_loop(arch_data)
            self._check_consumer_isolation(arch_data)
            self._check_observation_relation_purity(arch_data)

        # 2. Проверка manifestation_signals.yaml
        man_data = self._load_yaml(
            os.path.join(self.arch_dir, "manifestation_signals.yaml")
        )
        if man_data:
            self._check_manifestation_immutability(man_data)
            self._check_no_resolution_in_manifestation(man_data)

        # 3. Проверка observed_fact_types.yaml
        fact_data = self._load_yaml(
            os.path.join(self.arch_dir, "observed_fact_types.yaml")
        )
        if fact_data:
            self._check_atomic_facts(fact_data)

        # 4. Проверка авторинга (signal_causes.yaml)
        authoring_path = os.path.join(self.arch_dir, "authoring", "signal_causes.yaml")
        auth_data = self._load_yaml(authoring_path)
        if auth_data:
            self._check_no_priors_in_authoring(auth_data)

        self._report()

    def _check_causal_loop(self, data: Dict):
        """Инвариант 2: Запрет каузального возврата. Inference не должен писать в Reality/Manifestation."""
        edges = data.get("edges", [])
        forbidden_targets = {"Reality", "ManifestationState"}
        forbidden_sources = {"Inference", "Memory"}

        for edge in edges:
            src = edge.get("from", "")
            dst = edge.get("to", "")
            if src in forbidden_sources and dst in forbidden_targets:
                self.errors.append(
                    f"CAUSAL LOOP VIOLATION: Edge from {src} to {dst} is forbidden (Invariant 2)."
                )
        self.passed.append("Invariant 2 (No Causal Loop): Checked")

    def _check_consumer_isolation(self, data: Dict):
        """Инвариант 3: Изоляция потребителей. Consumers не могут читать Reality напрямую."""
        edges = data.get("edges", [])
        consumers = data.get("consumers", [])
        # Очищаем имена потребителей от пояснений в скобках
        consumer_names = {c.split(" ")[0] for c in consumers}
        forbidden_sources = {"Reality", "ManifestationState"}

        for edge in edges:
            src = edge.get("from", "")
            dst = edge.get("to", "")
            if src in forbidden_sources and dst in consumer_names:
                self.errors.append(
                    f"CONSUMER ISOLATION VIOLATION: Consumer '{dst}' reads directly from '{src}' (Invariant 3)."
                )
        self.passed.append("Invariant 3 (Consumer Isolation): Checked")

    def _check_observation_relation_purity(self, data: Dict):
        """Инвариант 4: Реляционная сущность. ObservationRelation не должен содержать метаданных сущности."""
        nodes = data.get("nodes", {})
        obs_node = nodes.get("ObservationRelation", {})
        desc = obs_node.get("description", "").lower()

        forbidden_keywords = ["npc id", "faction", "mood", "emotion", "memory"]
        found_forbidden = [
            kw
            for kw in forbidden_keywords
            if kw in desc and "запрещено" not in desc.split(kw)[0][-20:]
        ]

        # Дополнительная проверка: наличие слова "запрещено" рядом с этими терминами в desc
        # (так как мы описываем запрет в самом описании)
        if not all(kw in desc and "запрещено" in desc for kw in forbidden_keywords):
            self.warnings.append(
                "Invariant 4 (Observation Purity): Ensure description explicitly forbids NPC id, Faction, Mood, Memory."
            )
        self.passed.append("Invariant 4 (Observation Purity): Checked")

    def _check_manifestation_immutability(self, data: Dict):
        """Инвариант 5: Единственный мост. Manifestation должен ссылаться на Reality и быть immutable."""
        channels = data.get("channels", {})
        for ch_name, ch_data in channels.items():
            upstream = ch_data.get("upstream", "")
            if upstream != "Reality":
                self.errors.append(
                    f"MANIFESTATION BRIDGE VIOLATION: Channel '{ch_name}' has upstream '{upstream}', must be 'Reality' (Invariant 5)."
                )
        self.passed.append("Invariant 5 (Manifestation Immutability): Checked")

    def _check_no_resolution_in_manifestation(self, data: Dict):
        """Запрет: В manifestation_signals.yaml не должно быть requires_resolution."""
        channels = data.get("channels", {})
        for ch_name, ch_data in channels.items():
            if "requires_resolution" in ch_data:
                self.errors.append(
                    f"RESOLUTION LEAK: Channel '{ch_name}' has 'requires_resolution'. This belongs to PerceptionPhysics, not Manifestation."
                )
        self.passed.append("No Resolution in Manifestation: Checked")

    def _check_atomic_facts(self, data: Dict):
        """Инвариант 6 (§17.2): Атомарность фактов. Запрет составных выводов."""
        fact_types = data.get("fact_types", {})
        # Список запрещенных (составных) названий фактов
        composite_patterns = [
            r"hand_on_weapon",
            r"avoiding_eye_contact",
            r"staring_at_player",
            r"trembling",
            r"posture_tense",
            r"fleeing",
            r"speaking_fast",
        ]

        for category, facts in fact_types.items():
            if not isinstance(facts, dict):
                continue
            for fact_name in facts.keys():
                for pattern in composite_patterns:
                    if re.match(pattern, fact_name, re.IGNORECASE):
                        self.errors.append(
                            f"ATOMIC FACT VIOLATION: Fact '{fact_name}' in '{category}' is composite, not atomic (§17.2)."
                        )
        self.passed.append("Atomic Facts (§17.2): Checked")

    def _check_no_priors_in_authoring(self, data: Dict):
        """Инвариант: Авторинг не должен содержать статических priors."""
        causes = data.get("signal_possible_causes", {})
        for signal, data_dict in causes.items():
            possible_causes = data_dict.get("possible_causes", {})
            if isinstance(possible_causes, dict):  # Если это словарь с priors
                for cause, priors in possible_causes.items():
                    if isinstance(priors, dict) and "prior" in priors:
                        self.errors.append(
                            f"AUTHORING PRIOR VIOLATION: Signal '{signal}' cause '{cause}' contains static 'prior'. Priors must be dynamic."
                        )
            elif isinstance(possible_causes, list):  # Если это список (как мы сделали)
                pass  # Всё ок
        self.passed.append("No Static Priors in Authoring: Checked")

    def _report(self):
        print("\n--- PASSED CHECKS ---")
        for p in self.passed:
            print(f"✅ {p}")

        if self.warnings:
            print("\n--- WARNINGS ---")
            for w in self.warnings:
                print(f"⚠️ {w}")

        if self.errors:
            print("\n--- ERRORS (§17 VIOLATIONS) ---")
            for e in self.errors:
                print(f"❌ {e}")
            print("\n" + "=" * 60)
            print(
                "🚨 LINTING FAILED: Architecture contracts violate Epistemology Invariants."
            )
            print("=" * 60)
            sys.exit(1)
        else:
            print("\n" + "=" * 60)
            print(
                "✅ LINTING PASSED: All perception architecture invariants are intact."
            )
            print("=" * 60)
            sys.exit(0)


if __name__ == "__main__":
    # Определяем корень проекта (предполагаем, что скрипт лежит в /scripts)
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    arch_path = os.path.join(root_dir, "architecture")

    linter = PerceptionArchitectureLinter(arch_dir=arch_path)
    linter.lint()
