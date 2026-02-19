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
