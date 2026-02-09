/**
 * WebSocket auth — handles pairing + token management.
 */
import * as SecureStore from 'expo-secure-store';
import { ENV } from '../config/env';

const TOKEN_KEY = 'myndlens_auth_token';
const USER_ID_KEY = 'myndlens_user_id';
const DEVICE_ID_KEY = 'myndlens_device_id';

function generateDeviceId(): string {
  // Simple random ID for now; in production use expo-device or a crypto UUID
  return 'dev_' + Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
}

export async function getOrCreateDeviceId(): Promise<string> {
  let deviceId = await SecureStore.getItemAsync(DEVICE_ID_KEY);
  if (!deviceId) {
    deviceId = generateDeviceId();
    await SecureStore.setItemAsync(DEVICE_ID_KEY, deviceId);
  }
  return deviceId;
}

export async function getStoredToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function getStoredUserId(): Promise<string | null> {
  return SecureStore.getItemAsync(USER_ID_KEY);
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

  // Store token and user ID securely
  await SecureStore.setItemAsync(TOKEN_KEY, data.token);
  await SecureStore.setItemAsync(USER_ID_KEY, data.user_id);

  return data;
}

export async function clearAuth(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  await SecureStore.deleteItemAsync(USER_ID_KEY);
}
