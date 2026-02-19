"""Digital Self Retriever — sole memory authority.

ONLY this module may query vector DB, traverse graph, write memory.
Other services NEVER access memory storage directly.

Read: allowed for L1 (suggestive), authoritative for L2 (verification)
Write: only post-execution OR via explicit user confirmation
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from memory.client import vector, graph, kv

logger = logging.getLogger(__name__)


async def recall(
    user_id: str,
    query_text: str,
    n_results: int = 3,
) -> List[Dict[str, Any]]:
    """Retrieve relevant memory for a query. Read-only, side-effect free."""
    # 1. Semantic search in vector store — scoped to this user only
    vector_results = vector.query(query_text, n_results=n_results, where={"user_id": user_id})

    # 2. Enrich with graph context — load from DB if not in memory
    enriched = []
    for vr in vector_results:
        node_id = vr.get("metadata", {}).get("node_id", vr["id"])
        if user_id not in graph._graphs:
            await graph.load_graph(user_id)
        graph_node = graph.get_node(user_id, node_id)
        neighbors = graph.get_neighbors(user_id, node_id)

        enriched.append({
            "node_id": node_id,
            "text": vr["text"],
            "distance": vr.get("distance"),
            "provenance": (graph_node or {}).get("provenance", "OBSERVED"),
            "graph_type": (graph_node or {}).get("type"),
            "neighbors": len(neighbors),
            "metadata": vr.get("metadata", {}),
        })

    logger.info(
        "[DigitalSelf] Recall: user=%s query='%s' results=%d",
        user_id, query_text[:40], len(enriched),
    )
    return enriched


async def resolve_entity(
    user_id: str,
    human_ref: str,
) -> Optional[Dict[str, Any]]:
    """Resolve a human reference to canonical entity."""
    return await kv.resolve_entity(user_id, human_ref)


async def store_fact(
    user_id: str,
    text: str,
    fact_type: str = "FACT",
    provenance: str = "EXPLICIT",
    related_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Store a new fact in the Digital Self. Returns node_id.

    Write rules: only post-execution OR via explicit user confirmation.
    """
    node_id = str(uuid.uuid4())

    # Add to vector store
    vector.add_document(
        doc_id=node_id,
        text=text,
        metadata={
            "node_id": node_id,
            "user_id": user_id,
            "type": fact_type,
            "provenance": provenance,
            **(metadata or {}),
        },
    )

    # Add to graph
    graph.add_node(
        user_id=user_id,
        node_id=node_id,
        node_type=fact_type,
        data={"text": text, **(metadata or {})},
        provenance=provenance,
    )

    # Link to related node if provided
    if related_to:
        graph.add_edge(user_id, related_to, node_id, edge_type=fact_type)

    # Persist graph
    await graph.persist_graph(user_id)

    logger.info(
        "[DigitalSelf] Fact stored: user=%s node=%s type=%s prov=%s",
        user_id, node_id, fact_type, provenance,
    )
    return node_id


async def register_entity(
    user_id: str,
    entity_type: str,
    name: str,
    aliases: Optional[List[str]] = None,
    data: Optional[Dict[str, Any]] = None,
    provenance: str = "EXPLICIT",
) -> str:
    """Register a named entity (person, place, etc.)."""
    canonical_id = str(uuid.uuid4())
    human_refs = [name] + (aliases or [])

    # KV registry
    await kv.register_entity(
        user_id=user_id,
        canonical_id=canonical_id,
        entity_type=entity_type,
        human_refs=human_refs,
        data=data,
        provenance=provenance,
    )

    # Graph node
    graph.add_node(
        user_id=user_id,
        node_id=canonical_id,
        node_type="ENTITY",
        data={"name": name, "entity_type": entity_type, **(data or {})},
        provenance=provenance,
    )

    # Vector store
    vector.add_document(
        doc_id=canonical_id,
        text=f"{entity_type}: {name}",
        metadata={"node_id": canonical_id, "user_id": user_id, "type": "ENTITY", "provenance": provenance},
    )

    await graph.persist_graph(user_id)

    logger.info(
        "[DigitalSelf] Entity registered: user=%s id=%s name=%s type=%s",
        user_id, canonical_id, name, entity_type,
    )
    return canonical_id


def get_memory_stats(user_id: str) -> Dict[str, Any]:
    """Get memory statistics for a user."""
    return {
        "vector_count": vector.count(),
        "graph_nodes": graph.node_count(user_id),
    }
