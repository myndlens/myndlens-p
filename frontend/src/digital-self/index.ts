/**
 * Digital Self — public API surface.
 *
 * Import from here, not from individual files.
 */

import { loadPKG, savePKG, upsertNode, upsertEdge, storeFact, registerPerson } from './pkg';
import type { PKG } from './pkg';
export { resolve, getAttribute, buildContextCapsule, getStats } from './subject-graph';
export type { ResolvedEntity, ContextCapsule } from './subject-graph';
export { deleteDigitalSelf, getDigitalSelfSize } from './kill-switch';
export { runTier1Ingestion, ingestContacts, ingestCalendar } from './ingester';
export { generatePersonaSummary, getPKGStats, initONNX } from './onnx-ai';

/**
 * Merge a PKGDiff received from the server into the local on-device PKG.
 * Each node/edge in the diff is upserted (id-stable, no duplicates).
 * Vectors are stored in the node's data field for future on-device semantic search.
 */
export async function mergePKGDiff(
  userId: string,
  diff: { nodes: any[]; edges: any[] },
): Promise<{ nodesAdded: number; edgesAdded: number }> {
  const { loadPKG: load, savePKG: save } = await import('./pkg');
  const pkg = await load(userId);
  const now = new Date().toISOString();
  let nodesAdded = 0;
  let edgesAdded = 0;

  for (const n of diff.nodes) {
    if (!pkg.nodes[n.id]) nodesAdded++;
    pkg.nodes[n.id] = {
      ...n,
      // Store ONNX vector in data field for future on-device semantic search
      data: { ...n.data, _vector: n.vector },
      created_at: pkg.nodes[n.id]?.created_at ?? now,
      updated_at: now,
    };
  }

  for (const e of diff.edges) {
    if (!pkg.edges[e.id]) edgesAdded++;
    pkg.edges[e.id] = {
      ...e,
      created_at: pkg.edges[e.id]?.created_at ?? now,
      updated_at: now,
    };
  }

  await save(pkg);
  return { nodesAdded, edgesAdded };
}
