/**
 * Digital Self PKG — Local Personal Knowledge Graph.
 *
 * On-device only. Nothing in this module touches the network.
 * Storage: AsyncStorage (JSON). Encrypted keys: expo-secure-store.
 *
 * Node types: Person | Place | Event | Trait | Interest | Source
 * Edge types: RELATIONSHIP | ASSOCIATED_WITH | HAS_TRAIT | HAS_INTEREST | DERIVED_FROM
 *
 * Every node/edge has: id, type, created_at, updated_at, confidence, provenance
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

// ── Types ──────────────────────────────────────────────────────────────────

export type NodeType = 'Person' | 'Place' | 'Event' | 'Trait' | 'Interest' | 'Source' | 'User';
export type EdgeType = 'RELATIONSHIP' | 'ASSOCIATED_WITH' | 'HAS_TRAIT' | 'HAS_INTEREST' | 'DERIVED_FROM';

export interface PKGNode {
  id: string;
  type: NodeType;
  label: string;               // Human-readable name (e.g., "Bob", "London", "Night Owl")
  data: Record<string, any>;   // Type-specific fields (email, phone, role, etc.)
  confidence: number;          // 0.0 – 1.0
  provenance: string;          // Source: "CONTACTS" | "CALENDAR" | "MANUAL" | "INFERRED"
  created_at: string;          // ISO timestamp
  updated_at: string;
}

export interface PKGEdge {
  id: string;
  type: EdgeType;
  from_id: string;
  to_id: string;
  label: string;               // e.g., "is manager of", "lives in"
  confidence: number;
  provenance: string;
  created_at: string;
  updated_at: string;
}

export interface PKG {
  version: number;
  user_id: string;
  nodes: Record<string, PKGNode>;
  edges: Record<string, PKGEdge>;
  last_updated: string;
}

// ── Storage keys ────────────────────────────────────────────────────────────

const PKG_KEY = 'myndlens_digital_self_pkg';
const PKG_VERSION = 1;

// ── Core CRUD ───────────────────────────────────────────────────────────────

export async function loadPKG(userId: string): Promise<PKG> {
  try {
    const raw = await AsyncStorage.getItem(`${PKG_KEY}_${userId}`);
    if (raw) return JSON.parse(raw) as PKG;
  } catch { /* fresh start */ }
  return { version: PKG_VERSION, user_id: userId, nodes: {}, edges: {}, last_updated: new Date().toISOString() };
}

export async function savePKG(pkg: PKG): Promise<void> {
  pkg.last_updated = new Date().toISOString();
  await AsyncStorage.setItem(`${PKG_KEY}_${pkg.user_id}`, JSON.stringify(pkg));
}

export async function upsertNode(
  userId: string,
  node: Omit<PKGNode, 'created_at' | 'updated_at'> & { created_at?: string },
): Promise<PKGNode> {
  const pkg = await loadPKG(userId);
  const now = new Date().toISOString();
  const existing = pkg.nodes[node.id];
  const fullNode: PKGNode = {
    ...node,
    created_at: existing?.created_at ?? now,
    updated_at: now,
  };
  pkg.nodes[node.id] = fullNode;
  await savePKG(pkg);
  return fullNode;
}

export async function upsertEdge(userId: string, edge: Omit<PKGEdge, 'created_at' | 'updated_at'>): Promise<PKGEdge> {
  const pkg = await loadPKG(userId);
  const now = new Date().toISOString();
  const existing = pkg.edges[edge.id];
  const fullEdge: PKGEdge = { ...edge, created_at: existing?.created_at ?? now, updated_at: now };
  pkg.edges[edge.id] = fullEdge;
  await savePKG(pkg);
  return fullEdge;
}

export async function storeFact(
  userId: string,
  params: {
    label: string;
    type: NodeType;
    data?: Record<string, any>;
    confidence?: number;
    provenance?: string;
  },
): Promise<PKGNode> {
  const id = `${params.type.toLowerCase()}_${params.label.toLowerCase().replace(/\s+/g, '_')}_${Date.now()}`;
  return upsertNode(userId, {
    id,
    type: params.type,
    label: params.label,
    data: params.data ?? {},
    confidence: params.confidence ?? 0.8,
    provenance: params.provenance ?? 'MANUAL',
  });
}

export async function registerPerson(
  userId: string,
  name: string,
  data: { email?: string; phone?: string; role?: string; relationship?: string; company?: string },
  provenance = 'MANUAL',
): Promise<PKGNode> {
  const id = `person_${name.toLowerCase().replace(/\s+/g, '_')}`;
  return upsertNode(userId, {
    id,
    type: 'Person',
    label: name,
    data,
    confidence: 0.9,
    provenance,
  });
}
