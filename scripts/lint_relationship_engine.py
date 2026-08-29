"""
path: scripts/lint_relationship_engine.py
Назначение: Линтер онтологического контракта Relationship Engine (фаза A / M0, ADR-O-369).
    Гейт против тихого воскрешения уничтоженных сущностей и онтологических агрегатов:
    (1) валидация схемы architecture/relationship_engine.yaml — канонический набор узлов §5.0
        закрыт: новый узел = вердикт GPT + ADR («любое новое поле без класса — отказ линтера»);
    (2) scoped-греп запрещённых классов имён в МЕХАНИКЕ (backend/app/**/*.py);
        контент-канон config/ не сканируется — граница механика/контент по №35;
    (3) запретные рёбра (обратная причинность №26, матрица знаний 9.10.7) и write-политика.
    Ядро запрещённых имён захардкожено ЗДЕСЬ и сверяется с yaml — yaml может добавлять
    имена, но не удалять ядро (стена заморозки не разбирается изнутри).
Зависимости: PyYAML (стандарт проекта).
Основные сущности: RelationshipEngineLinter.

Запуск: python scripts/lint_relationship_engine.py
Подавление легального ПРОЗАИЧЕСКОГО упоминания (не для идентификаторов механики):
    # noqa: RE35 — в конце строки; каждое подавление видно в диффе и аудируемо.
"""

import os
import re
import sys
from typing import Any, Dict, List, Set

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_PATH = os.path.join(PROJECT_ROOT, "architecture", "relationship_engine.yaml")
SCAN_ROOT = os.path.join(PROJECT_ROOT, "backend", "app")
NOQA_MARKER = "# noqa: RE35"

# Канонический набор узлов §5.0 + §4.1 — закрыт до вердикта GPT (расширение только через ADR)
CANONICAL_ONTOLOGY_NODES: frozenset = frozenset({
    "NeedSystem", "PreferenceModel", "HardConstraint", "ExclusivityRequirement",
    "AttractionVector", "TrustFearScalars", "DebtRespectScalars", "TrustDeep",
    "Received", "Satiation", "CurrentArousal", "Frustration", "FrustrationByNeedProjection",
    "AdaptationCost", "ReciprocityBalance", "Infatuation", "Attachment", "Intimacy",
    "Bond", "SharedHistory", "NegotiatedAgreements", "Investment",
    "ObservedRelationshipState", "BeliefPredicates", "Satisfaction", "PartnerDesire",
    "ContextualFactors", "Compatibility", "Jealousy", "RelationshipUtility",
    "ExclusivityCompatibility", "LoveAggregates", "RelationshipValue",
    "ScenarioEvaluations", "AlternativeValue", "ScenarioLocalTerms", "IdealizationReadout",
})
CANONICAL_COMPONENT_NODES: frozenset = frozenset({
    "RelationshipEvents", "RelationshipStateStore", "RelationshipDynamics",
    "RelationshipEventSemantics", "RelationshipModifierResolver",
    "RelationshipBeliefs", "NeedProviderRelationship", "ExitStayIntents",
})

# Запретные рёбра (from, to): обратная причинность и границы слоёв (§6.16 п.9.10.7; №26; ПД5; №21)
FORBIDDEN_EDGES: frozenset = frozenset({
    ("DecisionHub", "RelationshipUtility"),
    ("ScenarioEvaluations", "RelationshipUtility"),
    ("DecisionHub", "AlternativeValue"),
    ("Frustration", "PartnerDesire"),
    ("Satiation", "NeedSystem"),
    ("AlternativeValue", "RelationshipUtility"),
    ("ObservedRelationshipState", "SharedHistory"),
    ("RelationshipDynamics", "Infatuation"),
    ("RelationshipDynamics", "Bond"),
})

# Ядро запрещённых имён: обязано присутствовать в yaml forbidden[].names (удаление = ошибка)
REQUIRED_FORBIDDEN_NAMES: frozenset = frozenset({
    "love_score", "is_in_love", "exit_intention", "stay_preference",
    "RomanticMarket", "PartnerPool", "infatuation", "Infatuation",
    "falling_in_love", "hope_bias", "romantic_attention", "RelationshipValue",
    "k_up", "k_down", "tau_n",
})

PROHIBITION_IDS = [f"N{i}" for i in range(1, 36)]  # §7 №1–№35 — реестр полный по построению

VALID_ONT_CLASSES = {"I", "II", "III", "IV", "TOMBSTONE", "FORBIDDEN"}
VALID_WRITABLE = {
    "state_applicator_only", "authoring", "ephemeral",
    "epistemic_revision_only", "read_only", "on_demand",
}

# Обязательные поля узла по онтологическому классу (§5.0)
REQUIRED_FIELDS: Dict[str, tuple] = {
    "I": ("owner", "writable", "update_phase", "invariant", "provenance", "ref"),
    "II": ("owner", "writable", "update_phase", "invariant", "provenance", "ref"),
    "III": ("owner", "writable", "ref"),
    "IV": ("writable", "ref"),
    "TOMBSTONE": ("reason", "replacement"),
    "FORBIDDEN": ("reason",),
}


class RelationshipEngineLinter:
    """Валидатор контракта RE: схема yaml + канон узлов + запретные рёбра + scoped-греп механики."""

    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.passed: List[str] = []

    def _load_yaml(self) -> Dict[str, Any]:
        if not os.path.exists(YAML_PATH):
            self.errors.append(f"MISSING FILE: {YAML_PATH}")
            return {}
        try:
            with open(YAML_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            self.errors.append(f"YAML PARSE ERROR in {YAML_PATH}: {e}")
            return {}

    # ── Проверки контракта ──────────────────────────────────────────────

    def _check_schema(self, data: Dict[str, Any]) -> None:
        if data.get("domain") != "RELATIONSHIP":
            self.errors.append("SCHEMA: отсутствует domain: RELATIONSHIP (требование build_graph)")
        spec = data.get("spec", {})
        for key in ("doc", "version", "phase", "adr"):
            if key not in spec:
                self.errors.append(f"SCHEMA: spec.{key} отсутствует")
        if not os.path.exists(os.path.join(PROJECT_ROOT, spec.get("doc", "___"))):
            self.errors.append(f"SCHEMA: spec.doc не найден на диске: {spec.get('doc')}")
        for key in ("scales", "moratorium", "forbidden", "prohibitions"):
            if key not in data:
                self.errors.append(f"SCHEMA: секция {key} отсутствует")
        self.passed.append("Schema: domain/spec/scales/moratorium/forbidden/prohibitions")

    def _check_canonical_nodes(self, nodes: Dict[str, Any]) -> None:
        expected: Set[str] = set(CANONICAL_ONTOLOGY_NODES) | set(CANONICAL_COMPONENT_NODES)
        actual = set(nodes.keys())
        for missing in sorted(expected - actual):
            self.errors.append(f"CANON: отсутствует канонический узел §5.0/§4.1: {missing}")
        for extra in sorted(actual - expected):
            self.errors.append(
                f"CANON: узел вне канона §5.0: {extra} — новый узел онтологии требует "
                f"вердикт GPT + ADR (запрет №13/№17; «любое новое поле без класса — отказ линтера»)"
            )
        self.passed.append(f"Canonical nodes: {len(expected)} узлов (§5.0 + §4.1)")

    def _check_node_contracts(self, nodes: Dict[str, Any]) -> None:
        for node_id, node in nodes.items():
            kind = node.get("kind", "ontology")
            if kind == "component":
                for field in ("role", "implementation_phase", "ref"):
                    if field not in node:
                        self.errors.append(f"NODE {node_id}: компонент без поля {field}")
                continue
            ont = node.get("ont_class")
            if ont not in VALID_ONT_CLASSES:
                self.errors.append(f"NODE {node_id}: ont_class отсутствует или неверен: {ont}")
                continue
            for field in REQUIRED_FIELDS[ont]:
                if field not in node:
                    self.errors.append(f"NODE {node_id} [{ont}]: отсутствует поле {field}")
            writable = node.get("writable")
            if ont in {"I", "II", "III", "IV"} and writable not in VALID_WRITABLE:
                self.errors.append(f"NODE {node_id} [{ont}]: writable вне допустимых: {writable}")
            if ont in {"TOMBSTONE", "FORBIDDEN"} and node.get("resurrection") != "forbidden":
                self.errors.append(f"NODE {node_id} [{ont}]: resurrection обязан быть forbidden")
        # COLLISION-заморозка: проекция фрустрации — только read-only от владельца
        proj = nodes.get("FrustrationByNeedProjection", {})
        if proj and (
            proj.get("writable") != "read_only"
            or proj.get("owner") != "Frustration"
            or proj.get("provenance") != "inherited_from_owner"
        ):
            self.errors.append(
                "COLLISION: FrustrationByNeedProjection обязан быть read_only проекцией "
                "владельца Frustration (вердикт Мастера, ADR-O-369)"
            )
        self.passed.append("Node contracts: поля по классам + collision-заморозка frustration")

    def _check_edges(self, edges: List[Dict[str, Any]]) -> None:
        known = set(CANONICAL_ONTOLOGY_NODES) | set(CANONICAL_COMPONENT_NODES) | {"DecisionHub"}
        for edge in edges:
            pair = (edge.get("from"), edge.get("to"))
            if pair in FORBIDDEN_EDGES:
                self.errors.append(f"EDGE FORBIDDEN: {pair[0]} -> {pair[1]} нарушает контракт")
            for side in ("from", "to"):
                if edge.get(side) not in known:
                    self.warnings.append(f"EDGE: {side}={edge.get(side)} вне известных узлов")
        self.passed.append(f"Edges: {len(edges)} каналов, запрещённые пары проверены")

    def _check_prohibition_registry(self, prohibitions: List[Dict[str, Any]]) -> None:
        ids = {p.get("id") for p in prohibitions}
        for pid in PROHIBITION_IDS:
            if pid not in ids:
                self.errors.append(f"PROHIBITIONS: отсутствует запрет {pid} (реестр §7 полон по построению)")
        for p in prohibitions:
            for field in ("rule", "enforcement", "ref"):
                if field not in p:
                    self.errors.append(f"PROHIBITIONS {p.get('id')}: нет поля {field}")
        moratorium = "N35.2"
        if moratorium not in ids and not any(
            str(p.get("id", "")).endswith("35.2") for p in prohibitions
        ):
            # мораторий живёт в отдельной секции — проверяется в _check_moratorium
            pass
        self.passed.append("Prohibitions: реестр №1-№35 с картой enforcement")

    def _check_moratorium(self, moratorium: Dict[str, Any]) -> None:
        if not moratorium or moratorium.get("id") != "N35.2":
            self.errors.append("MORATORIUM: секция №35.2 отсутствует (мораторий readout влюблённости до Р18)")
        elif "until" not in moratorium:
            self.errors.append("MORATORIUM: нет условия снятия (until)")
        self.passed.append("Moratorium №35.2 зарегистрирован")

    # ── Scoped-греп механики (№25/№27/№28/№34/№35) ─────────────────────

    def _iter_python_files(self):
        if not os.path.isdir(SCAN_ROOT):
            self.warnings.append(f"SCAN ROOT отсутствует: {SCAN_ROOT}")
            return
        for root, _dirs, files in os.walk(SCAN_ROOT):
            for name in files:
                if name.endswith(".py"):
                    yield os.path.join(root, name)

    def _check_name_classes(self, forbidden: Dict[str, Any]) -> None:
        declared: Set[str] = set()
        entries = []
        for key, entry in forbidden.items():
            if not isinstance(entry, dict) or not entry.get("grep"):
                continue
            names = [n for n in entry.get("names", []) if n]
            declared.update(names)
            entries.append((key, names, entry.get("verdict", "?")))
        # Стена заморозки: ядро нельзя удалить из yaml
        for core in sorted(REQUIRED_FORBIDDEN_NAMES - declared):
            self.errors.append(
                f"FREEZE WALL: имя {core} удалено из forbidden-секции yaml — "
                f"редактирование стены заморозки требует вердикта GPT + ADR"
            )
        if not entries:
            self.errors.append("FREEZE WALL: forbidden-секция пуста")
            return
        hits = 0
        for path in self._iter_python_files():
            rel = os.path.relpath(path, PROJECT_ROOT)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, start=1):
                        if NOQA_MARKER in line:
                            continue
                        for key, names, verdict in entries:
                            pattern = r"\b(?:%s)\b" % "|".join(
                                re.escape(n) for n in names
                            )
                            if re.search(pattern, line):
                                self.errors.append(
                                    f"NAME CLASS [{key}] {verdict}: {rel}:{lineno}: {line.strip()[:90]}"
                                )
                                hits += 1
            except OSError as e:
                self.warnings.append(f"READ FAIL: {rel}: {e}")
        self.passed.append(
            f"Name-class grep (backend/app, механика): {hits} нарушений; "
            f"контент-канон config/ вне зоны сканирования"
        )

    # ── Отчёт ───────────────────────────────────────────────────────────

    def _report(self) -> None:
        print("\n--- PASSED CHECKS ---")
        for p in self.passed:
            print(f"✅ {p}")
        if self.warnings:
            print("\n--- WARNINGS ---")
            for w in self.warnings:
                print(f"⚠️  {w}")
        if self.errors:
            print("\n--- ERRORS (ADR-O-369 VIOLATIONS) ---")
            for e in self.errors:
                print(f"❌ {e}")
            print("\n" + "=" * 60)
            print("🚨 LINTING FAILED: Relationship Engine contract violated.")
            print("=" * 60)
            sys.exit(1)
        print("\n" + "=" * 60)
        print("✅ LINTING PASSED: Relationship Engine онтологическая граница цела.")
        print("=" * 60)
        sys.exit(0)

    def lint(self) -> None:
        print("=" * 60)
        print("🛡️  LINTING RELATIONSHIP ENGINE CONTRACT (Phase A / ADR-O-369)")
        print("=" * 60)
        data = self._load_yaml()
        if data:
            self._check_schema(data)
            nodes = data.get("nodes", {})
            if nodes:
                self._check_canonical_nodes(nodes)
                self._check_node_contracts(nodes)
            self._check_edges(data.get("edges", []))
            self._check_prohibition_registry(data.get("prohibitions", []))
            self._check_moratorium(data.get("moratorium", {}))
            self._check_name_classes(data.get("forbidden", {}))
        self._report()


if __name__ == "__main__":
    RelationshipEngineLinter().lint()