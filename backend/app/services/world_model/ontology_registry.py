from __future__ import annotations

# backend/app/services/world_model/ontology_registry.py
"""
Назначение: Читатель открытой онтологии config/world/ontology/domains.yaml
            (ТЗ Отчёт №6 §5.1/§7, ADR-O-445). Каталог — документация, НЕ enum:
            реестр отвечает, что задокументировано, но НЕ запрещает Process'ам
            домены вне каталога (открытая онтология).
Зависимости: stdlib (dataclasses, pathlib, typing); yaml.
Основные сущности: DomainSpec, OntologyRegistry
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DOMAINS_PATH = _REPO_ROOT / "config" / "world" / "ontology" / "domains.yaml"


@dataclass(frozen=True)
class DomainSpec:
    """Задокументированный домен открытой онтологии."""

    name: str
    attributes: Tuple[str, ...]


class OntologyRegistry:
    """Read-only каталог доменов. Загрузка fail-fast по схеме."""

    def __init__(self, domains: Dict[str, DomainSpec]):
        self._domains: Dict[str, DomainSpec] = dict(domains)

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "OntologyRegistry":
        load_path = Path(path) if path is not None else DEFAULT_DOMAINS_PATH
        raw = yaml.safe_load(load_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("domains"), dict):
            raise ValueError(f"domains.yaml: ожидается корень 'domains: ...' ({load_path})")
        domains: Dict[str, DomainSpec] = {}
        for name, spec in raw["domains"].items():
            if not isinstance(name, str) or not name:
                raise ValueError("domains.yaml: пустое/нестроковое имя домена")
            attributes = tuple((spec or {}).get("attributes", ()))
            if not attributes or not all(isinstance(a, str) and a for a in attributes):
                raise ValueError(f"domains.yaml: домен '{name}' без непустых строковых attributes")
            domains[name] = DomainSpec(name=name, attributes=attributes)
        if not domains:
            raise ValueError("domains.yaml: каталог доменов пуст")
        return cls(domains)

    @property
    def domains(self) -> Tuple[DomainSpec, ...]:
        return tuple(self._domains.values())

    def is_documented(self, domain: str) -> bool:
        """Каталог — документация, не enum: False не запрещает использование домена."""
        return domain in self._domains

    def attributes_of(self, domain: str) -> Tuple[str, ...]:
        spec = self._domains.get(domain)
        return spec.attributes if spec else ()
