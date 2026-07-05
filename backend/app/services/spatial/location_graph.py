"""backend/app/services/spatial/location_graph.py

Compatibility shim for older sandbox tests.

Some tests still import:
    from app.services.spatial.location_graph import LocationGraph, LocationNode

The runtime project model uses:
- app.models.spatial_contracts.NodeRef / NodeRole
- app.services.spatial.graph_compiler.compile_graph

This module re-exports minimal dataclasses used by tests, without affecting runtime logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class LocationNode:
    """Test-only node representation.

    Fields align with the sandbox tests expectations (x, y, connections).
    """

    node_id: str
    x: float
    y: float
    connections: Tuple[str, ...] = field(default_factory=tuple)


@dataclass
class LocationGraph:
    """Test-only graph representation.

    The sandbox tests expect:
    - .nodes (dict)
    - .all_nodes() and/or an attribute assigned from graph.all_nodes()
    """

    location_id: str
    nodes: Dict[str, LocationNode] = field(default_factory=dict)

    def all_nodes(self) -> Dict[str, LocationNode]:
        return self.nodes

    def __iter__(self) -> Iterable[LocationNode]:
        return iter(self.nodes.values())

