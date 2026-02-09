/**
 * WebSocket auth — handles pairing + token management.
 * Uses cross-platform storage wrapper.
 */
import { getItem, setItem, deleteItem } from '../utils/storage';
import { ENV } from '../config/env';

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

export interface PairResponse {
  token: string;
  user_id: string;
  device_id: string;
  env: string;
}

export async function pairDevice(userId: string): Promise<PairResponse> {
  const deviceId = await getOrCreateDeviceId();

  const response = await fetch(`${ENV.API_URL}/auth/pair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      device_id: deviceId,
      client_version: '1.0.0',
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Pairing failed: ${response.status} ${text}`);
  }

  const data: PairResponse = await response.json();

  // Store token and user ID
  await setItem(TOKEN_KEY, data.token);
  await setItem(USER_ID_KEY, data.user_id);

  return data;
}

export async function clearAuth(): Promise<void> {
  await deleteItem(TOKEN_KEY);
  await deleteItem(USER_ID_KEY);
}
