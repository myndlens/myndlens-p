/**
 * Digital Self — public API surface.
 *
 * Import from here, not from individual files.
 */

/**
 * Digital Self — public API surface.
 *
 * Import from here, not from individual files.
 */

export { loadPKG, savePKG, upsertNode, upsertEdge, storeFact, registerPerson } from './pkg';
export type { PKG, PKGNode, PKGEdge, NodeType, EdgeType } from './pkg';
export { resolve, getAttribute, buildContextCapsule, getStats } from './subject-graph';
export type { ResolvedEntity, ContextCapsule } from './subject-graph';
export { deleteDigitalSelf, getDigitalSelfSize } from './kill-switch';
export { runTier1Ingestion, ingestContacts, ingestCalendar } from './ingester';
export { generatePersonaSummary, getPKGStats, initONNX } from './onnx-ai';

/**
 * Merge a PKGDiff received from the server into the local on-device PKG.
 * Uses static imports — no dynamic require overhead.
 */
export async function mergePKGDiff(
  userId: string,
  diff: { nodes: any[]; edges: any[]; stats?: Record<string, number> },
): Promise<{ nodesAdded: number; edgesAdded: number; stats: Record<string, number> }> {
  const { loadPKG, savePKG } = await import('./pkg');
  const pkg = await loadPKG(userId);
  const now = new Date().toISOString();
  let nodesAdded = 0;
  let edgesAdded = 0;

  for (const n of diff.nodes ?? []) {
    if (!pkg.nodes[n.id]) nodesAdded++;
    pkg.nodes[n.id] = {
      ...n,
      data: { ...n.data, _vector: n.vector },   // store ONNX vector for on-device semantic search
      vector: undefined,                           // don't double-store at node root
      created_at: pkg.nodes[n.id]?.created_at ?? now,
      updated_at: now,
    };
  }

  for (const e of diff.edges ?? []) {
    if (!pkg.edges[e.id]) edgesAdded++;
    pkg.edges[e.id] = {
      ...e,
      created_at: pkg.edges[e.id]?.created_at ?? now,
      updated_at: now,
    };
  }

  await savePKG(pkg);
  return { nodesAdded, edgesAdded, stats: diff.stats ?? {} };
}
