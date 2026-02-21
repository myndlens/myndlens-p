/**
 * Digital Self Sync Manager
 *
 * Sends PKG node TEXT to the backend for ONNX embedding.
 * Backend generates the 384-dim vector and stores ONLY the vector — text is discarded.
 * On subsequent mandates, the backend resolves node_ids and the device provides
 * the readable text on-demand (ds_resolve / ds_context WS round-trip).
 *
 * What travels to the backend:
 *   SYNC:         { node_id, text }  — text used to generate vector, then discarded
 *   PER MANDATE:  { node_id, text }  — only for 2-3 matched nodes, ephemeral
 *   NEVER stored: raw contacts, calendar data, phone numbers
 */

import { Platform } from 'react-native';
import { loadPKG, savePKG, PKGNode } from './pkg';
import { getItem, setItem } from '../utils/storage';

const LAST_SYNC_KEY = 'myndlens_ds_last_sync';
const SYNC_INTERVAL_MS = 6 * 60 * 60 * 1000; // 6 hours

// ── Node text builder ──────────────────────────────────────────────────────

/**
 * Convert a PKG node to a meaningful text string for ONNX embedding.
 * The text encodes the node's identity and relationships so that
 * the backend can semantically match it against a user's spoken transcript.
 */
export function nodeToText(node: PKGNode): string {
  const parts: string[] = [node.label];

  switch (node.type) {
    case 'Person': {
      if (node.data.relationship) parts.push(node.data.relationship);
      if (node.data.organization) parts.push(node.data.organization);
      if (node.data.signal) parts.push(node.data.signal);
      break;
    }
    case 'Place': {
      if (node.data.category) parts.push(node.data.category);
      if (node.data.address) parts.push(node.data.address);
      break;
    }
    case 'Trait':
    case 'Interest': {
      if (node.data.context) parts.push(node.data.context);
      break;
    }
    case 'Event': {
      if (node.data.date) parts.push(node.data.date);
      if (node.data.location) parts.push(node.data.location);
      if (node.data.attendees) parts.push(`with ${node.data.attendees}`);
      break;
    }
    case 'Fact': {
      if (node.data.value) parts.push(String(node.data.value));
      if (node.data.label) parts.push(node.data.label);
      break;
    }
  }

  return parts.filter(Boolean).join(' — ');
}


// ── Delta detection ────────────────────────────────────────────────────────

/**
 * Returns nodes that need syncing: updated_at > synced_at (or never synced).
 */
function getDelta(nodes: PKGNode[]): PKGNode[] {
  return nodes.filter(n => {
    if (!n.synced_at) return true;
    return new Date(n.updated_at) > new Date(n.synced_at);
  });
}


// ── Sync to backend ────────────────────────────────────────────────────────

interface SyncResult {
  synced: number;
  deleted: number;
  skipped: number;
  error?: string;
}

/**
 * Sync delta PKG nodes to the backend.
 *
 * Sends { node_id, text } pairs over HTTPS (TLS encrypted).
 * Backend embeds the text using ONNX (bge-small-en-v1.5) and stores
 * ONLY the resulting vector — the text is never persisted on the backend.
 *
 * @param userId  - the authenticated user id
 * @param force   - if true, sync all nodes regardless of synced_at
 */
export async function syncPKGToBackend(
  userId: string,
  force = false,
): Promise<SyncResult> {
  const result: SyncResult = { synced: 0, deleted: 0, skipped: 0 };

  try {
    const pkg = await loadPKG(userId);
    const allNodes = Object.values(pkg.nodes);
    const delta = force ? allNodes : getDelta(allNodes);

    if (delta.length === 0) {
      result.skipped = allNodes.length;
      return result;
    }

    const apiUrl = process.env.EXPO_PUBLIC_BACKEND_URL ?? '';
    const token = await getItem('myndlens_auth_token') ?? '';

    // Build payload — { node_id, text } only. No raw personal data beyond the label.
    const payload = {
      user_id: userId,
      nodes: delta.map(n => ({ node_id: n.id, text: nodeToText(n) })),
    };

    const response = await fetch(`${apiUrl}/api/digital-self/sync`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const err = await response.text();
      result.error = `HTTP ${response.status}: ${err}`;
      return result;
    }

    // Mark synced nodes with current timestamp
    const now = new Date().toISOString();
    for (const node of delta) {
      if (pkg.nodes[node.id]) {
        pkg.nodes[node.id].synced_at = now;
      }
    }
    await savePKG(pkg);
    await setItem(LAST_SYNC_KEY, now);

    result.synced = delta.length;
    result.skipped = allNodes.length - delta.length;
    return result;
  } catch (err: any) {
    result.error = err?.message ?? 'Unknown sync error';
    return result;
  }
}


/**
 * Notify backend to remove vectors for deleted PKG nodes.
 */
export async function syncTombstones(
  userId: string,
  deletedNodeIds: string[],
): Promise<void> {
  if (deletedNodeIds.length === 0) return;
  try {
    const apiUrl = process.env.EXPO_PUBLIC_BACKEND_URL ?? '';
    const token = await getItem('myndlens_auth_token') ?? '';

    await fetch(`${apiUrl}/api/digital-self/sync`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ user_id: userId, deleted_node_ids: deletedNodeIds }),
    });
  } catch {
    // Tombstone sync failure is non-fatal — stale vectors cause no harm, just noise
  }
}


/**
 * Returns true if a foreground sync is due (last sync > SYNC_INTERVAL_MS ago).
 */
export async function isSyncDue(): Promise<boolean> {
  const last = await getItem(LAST_SYNC_KEY);
  if (!last) return true;
  return Date.now() - new Date(last).getTime() > SYNC_INTERVAL_MS;
}
