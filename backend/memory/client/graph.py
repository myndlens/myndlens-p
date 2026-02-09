"""Graph Store — NetworkX canonical graph.

Deterministic layer: nodes with canonical UUIDs,
typed relationships (FACT, PREFERENCE, ENTITY, HISTORY, POLICY).
Persisted to MongoDB.
"""
import json
import logging
from typing import Any, Dict, List, Optional

import networkx as nx

from core.database import get_db

logger = logging.getLogger(__name__)

# Per-user graphs
_graphs: Dict[str, nx.DiGraph] = {}

EDGE_TYPES = {"FACT", "PREFERENCE", "ENTITY", "HISTORY", "POLICY"}


def get_graph(user_id: str) -> nx.DiGraph:
    if user_id not in _graphs:
        _graphs[user_id] = nx.DiGraph()
    return _graphs[user_id]


def add_node(
    user_id: str,
    node_id: str,
    node_type: str,
    data: Dict[str, Any],
    provenance: str = "EXPLICIT",
) -> None:
    """Add a node to the user's graph."""
    g = get_graph(user_id)
    g.add_node(node_id, type=node_type, provenance=provenance, **data)
    logger.debug("[Graph] Node added: user=%s node=%s type=%s", user_id, node_id, node_type)


def add_edge(
    user_id: str,
    source: str,
    target: str,
    edge_type: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """Add a typed edge."""
    if edge_type not in EDGE_TYPES:
        raise ValueError(f"Invalid edge type: {edge_type}. Must be one of {EDGE_TYPES}")
    g = get_graph(user_id)
    g.add_edge(source, target, type=edge_type, **(data or {}))


def get_node(user_id: str, node_id: str) -> Optional[Dict[str, Any]]:
    g = get_graph(user_id)
    if node_id in g.nodes:
        return dict(g.nodes[node_id])
    return None


def get_neighbors(
    user_id: str,
    node_id: str,
    edge_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get neighboring nodes, optionally filtered by edge type."""
    g = get_graph(user_id)
    if node_id not in g.nodes:
        return []

    results = []
    for neighbor in g.neighbors(node_id):
        edge_data = g.edges[node_id, neighbor]
        if edge_type and edge_data.get("type") != edge_type:
            continue
        results.append({
            "node_id": neighbor,
            "edge_type": edge_data.get("type"),
            **dict(g.nodes[neighbor]),
        })
    return results


def node_count(user_id: str) -> int:
    return get_graph(user_id).number_of_nodes()


async def persist_graph(user_id: str) -> None:
    """Save graph to MongoDB."""
    g = get_graph(user_id)
    data = nx.node_link_data(g)
    db = get_db()
    await db.graphs.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "graph_data": json.loads(json.dumps(data, default=str))}},
        upsert=True,
    )
    logger.info("[Graph] Persisted: user=%s nodes=%d edges=%d", user_id, g.number_of_nodes(), g.number_of_edges())


async def load_graph(user_id: str) -> nx.DiGraph:
    """Load graph from MongoDB."""
    db = get_db()
    doc = await db.graphs.find_one({"user_id": user_id})
    if doc and "graph_data" in doc:
        g = nx.node_link_graph(doc["graph_data"])
        _graphs[user_id] = g
        logger.info("[Graph] Loaded: user=%s nodes=%d", user_id, g.number_of_nodes())
        return g
    return get_graph(user_id)
