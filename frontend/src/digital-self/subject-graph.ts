/**
 * Subject Graph — on-device query interface for the Digital Self PKG.
 *
 * Primary interface for resolving entities and retrieving context.
 * Used to build the context capsule sent with each mandate.
 *
 * No network calls. Everything is local.
 */

import { loadPKG, PKGNode, PKG } from './pkg';

export interface ResolvedEntity {
  node: PKGNode;
  confidence: number;
  evidence: string;
}

export interface ContextCapsule {
  entities: ResolvedEntity[];
  traits: string[];
  places: string[];
  summary: string;   // Plain-English context summary for the LLM prompt
}

// ── Resolve a human reference to a PKG node ──────────────────────────────

export async function resolve(
  userId: string,
  query: string,
): Promise<ResolvedEntity | null> {
  const pkg = await loadPKG(userId);
  const q = query.toLowerCase().trim();

  // Exact label match first
  for (const node of Object.values(pkg.nodes)) {
    if (node.label.toLowerCase() === q) {
      return { node, confidence: node.confidence, evidence: `Exact match: ${node.label}` };
    }
  }

  // Alias / data field match
  for (const node of Object.values(pkg.nodes)) {
    const aliases = (node.data.aliases as string[] | undefined) ?? [];
    if (aliases.some(a => a.toLowerCase() === q)) {
      return { node, confidence: node.confidence * 0.9, evidence: `Alias match: ${node.label}` };
    }
  }

  // Partial label match
  for (const node of Object.values(pkg.nodes)) {
    if (node.label.toLowerCase().includes(q) || q.includes(node.label.toLowerCase())) {
      return { node, confidence: node.confidence * 0.7, evidence: `Partial match: ${node.label}` };
    }
  }

  return null;
}

// ── Get a specific attribute (e.g., "home_airport", "home_city") ──────────

export async function getAttribute(
  userId: string,
  attribute: string,
): Promise<string | null> {
  const pkg = await loadPKG(userId);
  for (const node of Object.values(pkg.nodes)) {
    const val = node.data[attribute];
    if (val) return String(val);
  }
  // Check Place nodes for location attributes
  if (attribute === 'home_city' || attribute === 'home_airport') {
    const places = Object.values(pkg.nodes).filter(n => n.type === 'Place');
    if (places.length > 0) return places[0].label;
  }
  return null;
}

// ── Build context capsule for a given mandate query ───────────────────────

export async function buildContextCapsule(
  userId: string,
  mandateQuery: string,
): Promise<ContextCapsule> {
  const pkg = await loadPKG(userId);
  const nodes = Object.values(pkg.nodes);

  if (nodes.length === 0) {
    return { entities: [], traits: [], places: [], summary: '' };
  }

  const q = mandateQuery.toLowerCase();

  // Find relevant entities mentioned in the mandate
  const entities: ResolvedEntity[] = [];
  for (const node of nodes) {
    if (node.type === 'Person' && q.includes(node.label.toLowerCase())) {
      entities.push({ node, confidence: node.confidence, evidence: `Mentioned in query` });
    }
  }

  // Include all traits
  const traits = nodes
    .filter(n => n.type === 'Trait')
    .map(n => n.label);

  // Include all places
  const places = nodes
    .filter(n => n.type === 'Place')
    .map(n => n.label);

  // Build natural-language summary for the LLM
  const parts: string[] = [];

  const userNode = nodes.find(n => n.type === 'User');
  if (userNode) parts.push(`User: ${userNode.label}`);

  const people = nodes.filter(n => n.type === 'Person').slice(0, 10);
  if (people.length > 0) {
    const personSummaries = people.map(p => {
      const rel = p.data.relationship ? ` (${p.data.relationship})` : '';
      const email = p.data.email ? `, email: ${p.data.email}` : '';
      const phone = p.data.phone ? `, phone: ${p.data.phone}` : '';
      return `${p.label}${rel}${email}${phone}`;
    });
    parts.push(`Contacts: ${personSummaries.join('; ')}`);
  }

  if (traits.length > 0) parts.push(`User traits: ${traits.join(', ')}`);
  if (places.length > 0) parts.push(`Known places: ${places.join(', ')}`);

  const summary = parts.join(' | ');

  return { entities, traits, places, summary };
}

// ── Node count (for status display) ──────────────────────────────────────

export async function getStats(userId: string): Promise<{ nodes: number; edges: number }> {
  const pkg = await loadPKG(userId);
  return {
    nodes: Object.keys(pkg.nodes).length,
    edges: Object.keys(pkg.edges).length,
  };
}
