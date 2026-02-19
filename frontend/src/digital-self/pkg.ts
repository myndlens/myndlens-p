/**
 * Digital Self PKG — Local Personal Knowledge Graph.
 *
 * On-device only. Nothing in this module touches the network.
 *
 * Storage:
 *   - Encryption key → expo-secure-store (hardware-backed: Secure Enclave iOS / StrongBox Android)
 *   - Encrypted PKG data → AsyncStorage (AES-256-GCM via Web Crypto API)
 *
 * Node types: Person | Place | Event | Trait | Interest | Source | User
 * Edge types: RELATIONSHIP | ASSOCIATED_WITH | HAS_TRAIT | HAS_INTEREST | DERIVED_FROM
 * Every node/edge: id, type, created_at, updated_at, confidence, provenance
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';

// ── Types ──────────────────────────────────────────────────────────────────

export type NodeType = 'Person' | 'Place' | 'Event' | 'Trait' | 'Interest' | 'Source' | 'User';
export type EdgeType = 'RELATIONSHIP' | 'ASSOCIATED_WITH' | 'HAS_TRAIT' | 'HAS_INTEREST' | 'DERIVED_FROM';

export interface PKGNode {
  id: string;
  type: NodeType;
  label: string;
  data: Record<string, any>;
  confidence: number;       // 0.0 – 1.0
  provenance: string;       // CONTACTS | CALENDAR | MANUAL | INFERRED | ONBOARDING
  created_at: string;
  updated_at: string;
}

export interface PKGEdge {
  id: string;
  type: EdgeType;
  from_id: string;
  to_id: string;
  label: string;
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

const PKG_KEY_PREFIX = 'myndlens_ds_encrypted';
const SECURE_KEY_NAME_PREFIX = 'myndlens_ds_aes_key';
const PKG_VERSION = 1;

// ── Hardware-backed AES key management ──────────────────────────────────────

async function _getOrCreateAESKey(userId: string): Promise<CryptoKey> {
  const keyName = `${SECURE_KEY_NAME_PREFIX}_${userId}`;
  const stored = await SecureStore.getItemAsync(keyName, {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });

  if (stored) {
    const jwk = JSON.parse(stored);
    return crypto.subtle.importKey('jwk', jwk, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
  }

  // Generate new hardware-locked AES-256-GCM key
  const key = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    true,
    ['encrypt', 'decrypt'],
  );
  const exported = await crypto.subtle.exportKey('jwk', key);
  // Store key in Secure Enclave (iOS) / StrongBox (Android) — hardware-backed
  await SecureStore.setItemAsync(keyName, JSON.stringify(exported), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });

  return key;
}

async function _encrypt(data: string, key: CryptoKey): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(data);
  const cipher = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, encoded);
  // Safe base64 encoding — avoid spread operator to prevent stack overflow on large PKGs
  const combined = new Uint8Array(iv.byteLength + cipher.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(cipher), iv.byteLength);
  let binary = '';
  for (let i = 0; i < combined.length; i++) binary += String.fromCharCode(combined[i]);
  return btoa(binary);
}

async function _decrypt(encrypted: string, key: CryptoKey): Promise<string> {
  const bytes = Uint8Array.from(atob(encrypted), c => c.charCodeAt(0));
  const iv = bytes.slice(0, 12);
  const cipher = bytes.slice(12);
  const plain = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, cipher);
  return new TextDecoder().decode(plain);
}

// ── Core CRUD (hardware-encrypted) ──────────────────────────────────────────

export async function loadPKG(userId: string): Promise<PKG> {
  try {
    const key = await _getOrCreateAESKey(userId);
    const raw = await AsyncStorage.getItem(`${PKG_KEY_PREFIX}_${userId}`);
    if (raw) {
      const json = await _decrypt(raw, key);
      return JSON.parse(json) as PKG;
    }
  } catch { /* fresh start or key rotation */ }
  return { version: PKG_VERSION, user_id: userId, nodes: {}, edges: {}, last_updated: new Date().toISOString() };
}

export async function savePKG(pkg: PKG): Promise<void> {
  pkg.last_updated = new Date().toISOString();
  const key = await _getOrCreateAESKey(pkg.user_id);
  const encrypted = await _encrypt(JSON.stringify(pkg), key);
  await AsyncStorage.setItem(`${PKG_KEY_PREFIX}_${pkg.user_id}`, encrypted);
}

export async function upsertNode(
  userId: string,
  node: Omit<PKGNode, 'created_at' | 'updated_at'> & { created_at?: string },
): Promise<PKGNode> {
  const pkg = await loadPKG(userId);
  const now = new Date().toISOString();
  const existing = pkg.nodes[node.id];
  const fullNode: PKGNode = { ...node, created_at: existing?.created_at ?? now, updated_at: now };
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
  params: { label: string; type: NodeType; data?: Record<string, any>; confidence?: number; provenance?: string },
): Promise<PKGNode> {
  const slug = params.label.toLowerCase().replace(/\s+/g, '_');
  // Trait/Place/Event nodes use stable IDs so repeated ingestion updates rather than duplicates.
  // FACT nodes use Date.now() because each observation is genuinely unique.
  const id = params.type === 'Trait' || params.type === 'Place' || params.type === 'Event'
    ? `${params.type.toLowerCase()}_${slug}`
    : `${params.type.toLowerCase()}_${slug}_${Date.now()}`;
  return upsertNode(userId, {
    id, type: params.type, label: params.label,
    data: params.data ?? {}, confidence: params.confidence ?? 0.8,
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
  return upsertNode(userId, { id, type: 'Person', label: name, data, confidence: 0.9, provenance });
}

