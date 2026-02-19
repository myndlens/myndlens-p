/**
 * WebSocket auth — handles token management.
 * Uses cross-platform storage wrapper.
 * Pairing is handled via ObeGee directly in login.tsx.
 */
import { getItem, setItem, deleteItem } from '../utils/storage';

const TOKEN_KEY = 'myndlens_auth_token';
const USER_ID_KEY = 'myndlens_user_id';
const DEVICE_ID_KEY = 'myndlens_device_id';

function generateDeviceId(): string {
  return 'dev_' + Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
}

export async function getOrCreateDeviceId(): Promise<string> {
  let deviceId = await getItem(DEVICE_ID_KEY);
  if (!deviceId) {
    deviceId = generateDeviceId();
    await setItem(DEVICE_ID_KEY, deviceId);
  }
  return deviceId;
}

export async function getStoredToken(): Promise<string | null> {
  return getItem(TOKEN_KEY);
}

export async function getStoredUserId(): Promise<string | null> {
  return getItem(USER_ID_KEY);
}

export async function clearAuth(): Promise<void> {
  await deleteItem(TOKEN_KEY);
  await deleteItem(USER_ID_KEY);
}
