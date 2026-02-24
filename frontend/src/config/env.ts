/**
 * Environment config — single source for API URLs.
 * Reads from EXPO_PUBLIC_BACKEND_URL in .env.
 */

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || 'https://app.myndlens.com';

export const ENV = {
  BACKEND_URL,
  API_URL: `${BACKEND_URL}/api`,
  // WS URL: convert https:// to wss:// (or http to ws)
  WS_URL: `${BACKEND_URL.replace(/^http/, 'ws')}/api/ws`,
  HEARTBEAT_INTERVAL_MS: 5000,
} as const;
