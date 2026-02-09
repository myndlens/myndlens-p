/**
 * Session store — Zustand store for app-wide session state.
 */
import { create } from 'zustand';

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'authenticated' | 'error';

interface SessionState {
  // Auth
  userId: string | null;
  deviceId: string | null;
  isPaired: boolean;

  // Connection
  connectionStatus: ConnectionStatus;
  sessionId: string | null;

  // Presence
  lastHeartbeatSeq: number;
  presenceOk: boolean;

  // Execute gate
  lastExecuteBlockReason: string | null;

  // Actions
  setAuth: (userId: string, deviceId: string) => void;
  clearAuth: () => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setSessionId: (id: string | null) => void;
  setHeartbeatSeq: (seq: number) => void;
  setPresenceOk: (ok: boolean) => void;
  setExecuteBlocked: (reason: string | null) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  userId: null,
  deviceId: null,
  isPaired: false,

  connectionStatus: 'disconnected',
  sessionId: null,

  lastHeartbeatSeq: 0,
  presenceOk: false,

  lastExecuteBlockReason: null,

  setAuth: (userId, deviceId) => set({ userId, deviceId, isPaired: true }),
  clearAuth: () => set({ userId: null, deviceId: null, isPaired: false, sessionId: null, connectionStatus: 'disconnected' }),
  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setSessionId: (id) => set({ sessionId: id }),
  setHeartbeatSeq: (seq) => set({ lastHeartbeatSeq: seq, presenceOk: true }),
  setPresenceOk: (ok) => set({ presenceOk: ok }),
  setExecuteBlocked: (reason) => set({ lastExecuteBlockReason: reason }),
}));
