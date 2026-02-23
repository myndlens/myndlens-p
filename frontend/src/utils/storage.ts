/**
 * Secure storage wrapper — native only (expo-secure-store).
 * Mobile-first, voice-first. No localStorage.
 */
let SecureStore: any = null;

try {
  SecureStore = require('expo-secure-store');
} catch {
  console.warn('[Storage] expo-secure-store not available, using in-memory fallback');
}

// In-memory fallback for test environments where SecureStore unavailable
const _mem: Record<string, string> = {};

export async function getItem(key: string): Promise<string | null> {
  try {
    if (SecureStore) return await SecureStore.getItemAsync(key);
  } catch { /* fall through */ }
  return _mem[key] ?? null;
}

export async function setItem(key: string, value: string): Promise<void> {
  try {
    if (SecureStore) { await SecureStore.setItemAsync(key, value); return; }
  } catch { /* fall through */ }
  _mem[key] = value;
}

export async function removeItem(key: string): Promise<void> {
  try {
    if (SecureStore) { await SecureStore.deleteItemAsync(key); return; }
  } catch { /* fall through */ }
  delete _mem[key];
}

// Alias for callers that use deleteItem
export const deleteItem = removeItem;
