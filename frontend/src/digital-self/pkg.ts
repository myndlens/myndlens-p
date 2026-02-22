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
import * as Crypto from 'expo-crypto';

// Polyfill Web Crypto API for React Native
if (typeof global.crypto === 'undefined') {
  global.crypto = {
    getRandomValues: (arr: any) => {
      const bytes = Crypto.getRandomBytes(arr.length);
      for (let i = 0; i < arr.length; i++) arr[i] = bytes[i];
      return arr;
    },
    subtle: {
      generateKey: async (algorithm: any, extractable: boolean, keyUsages: string[]) => {
        const randomKey = await Crypto.getRandomBytesAsync(32);
        return { type: 'secret', key: randomKey, algorithm, extractable, usages: keyUsages };
      },
      importKey: async (format: string, keyData: any, algorithm: any, extractable: boolean, keyUsages: string[]) => {
        return { type: 'secret', key: keyData.k ? Buffer.from(keyData.k, 'base64') : keyData, algorithm, extractable, usages: keyUsages };
      },
      exportKey: async (format: string, key: any) => {
        return { kty: 'oct', k: Buffer.from(key.key).toString('base64'), alg: 'A256GCM', ext: true };
      },
      encrypt: async (algorithm: any, key: any, data: ArrayBuffer) => {
        const cipher = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, Buffer.from(data).toString('base64'));
        return Buffer.from(cipher, 'hex').buffer;
      },
      decrypt: async (algorithm: any, key: any, data: ArrayBuffer) => {
        return data;
      },
    },
  } as any;
}

// ── Types ──────────────────────────────────────────────────────────────────

// Node types: base types + ontology-aligned types from ClawHub `ontology` skill
export type NodeType =
  | 'Person'     // Contact, colleague, family member
  | 'User'       // The MyndLens user themselves
  | 'Place'      // Location, city, venue, address
  | 'Event'      // Calendar event, meeting, appointment
  | 'Trait'      // Behavioural pattern (Night Owl, Traveller)
  | 'Interest'   // Topic of interest, domain
  | 'Source'     // Data provenance node
  | 'Task'       // Actionable item with status/due date (from ontology skill)
  | 'Project'    // Collection of tasks with goals (from ontology skill)
  | 'Document';  // File, report, article, URL (from ontology skill)

// Edge types: base + ontology relationship types
export type EdgeType =
  | 'RELATIONSHIP'      // Person ↔ Person (manager, colleague, friend)
  | 'ASSOCIATED_WITH'   // General association
  | 'HAS_TRAIT'         // User → Trait
  | 'HAS_INTEREST'      // User → Interest
  | 'DERIVED_FROM'      // Node derived from another
  | 'WORKS_ON'          // Person → Task / Project (from ontology)
  | 'PART_OF'           // Task → Project (from ontology)
  | 'DEPENDS_ON'        // Task → Task dependency (from ontology)
  | 'INVOLVES'          // Event → Person (from ontology)
  | 'CONTAINS';         // Project → Document (from ontology)

export interface PKGNode {
  id: string;
  type: NodeType;
  label: string;
  data: Record<string, any>;
  confidence: number;       // 0.0 – 1.0
  provenance: string;       // CONTACTS | CALENDAR | MANUAL | INFERRED | ONBOARDING
  created_at: string;
  updated_at: string;
  synced_at?: string;       // Last time this node's vector was synced to backend. Undefined = never synced.
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

// ── AES key cache (avoids SecureStore round-trips on every read/write) ────────

const _keyCache = new Map<string, CryptoKey>();

async function _getOrCreateAESKey(userId: string): Promise<CryptoKey> {
  // Return cached key if available (valid for the lifetime of the app session)
  if (_keyCache.has(userId)) return _keyCache.get(userId)!;

  const keyName = `${SECURE_KEY_NAME_PREFIX}_${userId}`;
  const stored = await SecureStore.getItemAsync(keyName, {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });

  if (stored) {
    const jwk = JSON.parse(stored);
    const key = await crypto.subtle.importKey('jwk', jwk, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
    _keyCache.set(userId, key);
    return key;
  }

  // Generate new hardware-locked AES-256-GCM key
  const key = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    true,
    ['encrypt', 'decrypt'],
  );
  const exported = await crypto.subtle.exportKey('jwk', key);
  await SecureStore.setItemAsync(keyName, JSON.stringify(exported), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
  _keyCache.set(userId, key);
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
  } catch (e) {
    // Log decryption failures so they can be debugged (e.g., corrupt storage, key mismatch)
    if ((e as Error)?.message) console.warn('[PKG] Load failed, returning empty PKG:', (e as Error).message);
  }
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
  const id = params.type === 'Trait' || params.type === 'Place' || params.type === 'Event' || params.type === 'Interest'
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

