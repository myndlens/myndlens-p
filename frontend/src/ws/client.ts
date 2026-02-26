/**
 * WebSocket client — connects to MyndLens BE with auth.
 *
 * Protocol:
 * 1. Connect to WS endpoint
 * 2. Send AUTH message with token + device_id
 * 3. Receive AUTH_OK with session_id
 * 4. Start heartbeat loop
 * 5. Route incoming messages to handlers
 */
import { ENV } from '../config/env';
import { getStoredToken, getOrCreateDeviceId } from './auth';

export type WSMessageType =
  | 'auth' | 'heartbeat' | 'audio_chunk' | 'execute_request' | 'cancel' | 'text_input'
  | 'auth_ok' | 'auth_fail' | 'heartbeat_ack'
  | 'transcript_partial' | 'transcript_final'
  | 'draft_update' | 'tts_audio'
  | 'execute_blocked' | 'execute_ok'
  | 'error' | 'session_terminated'
  | 'ds_resolve'    // Backend → Device: resolve these node IDs
  | 'ds_context';   // Device → Backend: here is the readable text for those nodes

export interface WSEnvelope {
  type: WSMessageType;
  id: string;
  timestamp: string;
  payload: Record<string, any>;
}

export type WSMessageHandler = (envelope: WSEnvelope) => void;

export class MyndLensWSClient {
  private ws: WebSocket | null = null;
  private sessionId: string | null = null;
  private handlers: Map<WSMessageType, WSMessageHandler[]> = new Map();
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private heartbeatSeq: number = 0;
  private _isConnected: boolean = false;
  private _isAuthenticated: boolean = false;
  private _userId: string | null = null;
  // Prevents session_terminated from firing when disconnect() is called
  // intentionally as part of a connect() → reconnect flow.
  private _suppressNextClose: boolean = false;

  get isConnected(): boolean { return this._isConnected; }
  get isAuthenticated(): boolean { return this._isAuthenticated; }
  get currentSessionId(): string | null { return this.sessionId; }
  get userId(): string | null { return this._userId; }

  /**
   * Register a handler for a specific message type.
   */
  on(type: WSMessageType, handler: WSMessageHandler): () => void {
    const existing = this.handlers.get(type) || [];
    existing.push(handler);
    this.handlers.set(type, existing);
    // Return unsubscribe function
    return () => {
      const handlers = this.handlers.get(type) || [];
      const idx = handlers.indexOf(handler);
      if (idx >= 0) handlers.splice(idx, 1);
    };
  }

  /**
   * Connect to the WebSocket server.
   */
  async connect(): Promise<void> {
    if (this.ws) {
      // Closing the old socket intentionally — suppress the session_terminated
      // event that onclose would normally dispatch. This close is part of a
      // controlled reconnect, not an unexpected session loss.
      this._suppressNextClose = true;
      this.disconnect();
    }

    return new Promise(async (resolve, reject) => {
      try {
        const token = await getStoredToken();
        if (!token) {
          reject(new Error('No auth token available. Pair device first.'));
          return;
        }

        const deviceId = await getOrCreateDeviceId();
        const wsUrl = ENV.WS_URL;

        console.log('[WS] Connecting to', wsUrl);
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
          console.log('[WS] Connected, sending AUTH');
          this._isConnected = true;

          // Send AUTH message with user prefs so backend can enforce them server-side
          const prefs = await import('../state/settings-prefs').then(m => m.loadSettings()).catch(() => ({})) as any;
          this.send('auth', {
            token,
            device_id: deviceId,
            client_version: '1.0.0',
            delegation_mode: prefs?.delegation_mode || 'assisted',
            ds_paused:       prefs?.ds_paused ?? false,
            data_residency:  prefs?.data_residency || 'on_device',
          });
        };

        this.ws.onmessage = (event) => {
          try {
            const envelope: WSEnvelope = JSON.parse(event.data);
            this._routeMessage(envelope, resolve, reject);
          } catch (err) {
            console.error('[WS] Failed to parse message:', err);
          }
        };

        this.ws.onclose = (event) => {
          console.log('[WS] Closed:', event.code, event.reason);
          const suppressed = this._suppressNextClose;
          this._suppressNextClose = false;
          this._cleanup();
          // Only notify listeners of an unexpected session loss.
          // Suppressed = this close was triggered by connect() to clear a stale socket.
          if (!suppressed) {
            this._dispatch('session_terminated', {
              type: 'session_terminated',
              id: '',
              timestamp: new Date().toISOString(),
              payload: { code: event.code, reason: event.reason },
            });
          }
        };

        this.ws.onerror = (error) => {
          console.warn('[WS] Connection error (non-fatal):', error?.type || 'unknown');
          // Don't reject - let onclose handle reconnection
        };

      } catch (err) {
        reject(err);
      }
    });
  }

  /**
   * Send a typed message to the server.
   */
  send(type: WSMessageType, payload: Record<string, any> = {}): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('[WS] Cannot send, not connected');
      return;
    }

    const envelope: WSEnvelope = {
      type,
      id: Math.random().toString(36).substring(2),
      timestamp: new Date().toISOString(),
      payload,
    };

    this.ws.send(JSON.stringify(envelope));
  }

  /**
   * Send an execute request (with presence gate on server).
   */
  sendExecuteRequest(draftId: string, touchToken?: string): void {
    this.send('execute_request', {
      session_id: this.sessionId,
      draft_id: draftId,
      touch_token: touchToken || null,
    });
  }

  /**
   * Disconnect and cleanup.
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
    }
    this._cleanup();
  }

  // ---- Private ----

  private _routeMessage(envelope: WSEnvelope, resolve?: Function, reject?: Function): void {
    const { type } = envelope;

    switch (type) {
      case 'auth_ok':
        this.sessionId = envelope.payload.session_id;
        this._userId = envelope.payload.user_id;
        this._isAuthenticated = true;
        this._startHeartbeat(envelope.payload.heartbeat_interval_ms || ENV.HEARTBEAT_INTERVAL_MS);
        console.log('[WS] Authenticated, session:', this.sessionId);
        resolve?.();
        break;

      case 'auth_fail':
        console.error('[WS] Auth failed:', envelope.payload.reason);
        this._isAuthenticated = false;
        reject?.(new Error(envelope.payload.reason));
        break;

      case 'heartbeat_ack':
        // Heartbeat acknowledged — no action needed
        break;

      case 'ds_resolve': {
        // Backend matched vector nodes and needs us to provide the readable text.
        // Look up node IDs in local PKG, send back { nodes: [{id, text}] }.
        const nodeIds: string[] = envelope.payload.node_ids ?? [];
        const sessionId: string = envelope.payload.session_id ?? this.sessionId ?? '';
        if (nodeIds.length > 0 && sessionId) {
          this._handleDsResolve(nodeIds, sessionId).catch(err => {
            console.log('[WS] ds_resolve handler error:', err);
          });
        }
        break;
      }

      default:
        break;
    }

    // Dispatch to registered handlers
    this._dispatch(type, envelope);
  }

  private _dispatch(type: WSMessageType, envelope: WSEnvelope): void {
    const handlers = this.handlers.get(type) || [];
    for (const handler of handlers) {
      try {
        handler(envelope);
      } catch (err) {
        console.error(`[WS] Handler error for ${type}:`, err);
      }
    }
  }

  /**
   * Handle ds_resolve: backend matched vector node IDs and needs readable text.
   * Look up each node_id in the local PKG, return the text-only representation.
   * Responds immediately with ds_context — keeps pipeline latency minimal.
   */
  private async _handleDsResolve(nodeIds: string[], sessionId: string): Promise<void> {
    try {
      const userId = this._userId ?? '';
      if (!userId) return;

      const { loadPKG } = require('../digital-self/pkg');
      const { nodeToText } = require('../digital-self/sync');
      const pkg = await loadPKG(userId);

      const nodes = nodeIds
        .filter(id => pkg.nodes[id])
        .map((id: string) => ({
          id,
          text: nodeToText(pkg.nodes[id]),
        }));

      this.send('ds_context', {
        session_id: sessionId,
        nodes,
      });

      console.log(`[WS] ds_context sent: ${nodes.length} nodes resolved`);
    } catch (err) {
      console.log('[WS] ds_resolve lookup failed:', err);
      // Send empty ds_context so backend doesn't time out waiting
      this.send('ds_context', { session_id: sessionId, nodes: [] });
    }
  }

  private _startHeartbeat(intervalMs: number): void {
    this._stopHeartbeat();
    this.heartbeatSeq = 0;

    this.heartbeatTimer = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN && this.sessionId) {
        this.heartbeatSeq++;
        this.send('heartbeat', {
          session_id: this.sessionId,
          seq: this.heartbeatSeq,
          client_ts: new Date().toISOString(),
        });
      }
    }, intervalMs);

    console.log(`[WS] Heartbeat started: ${intervalMs}ms interval`);
  }

  private _stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private _cleanup(): void {
    this._stopHeartbeat();
    this._isConnected = false;
    this._isAuthenticated = false;
    this.sessionId = null;
    this.ws = null;
  }
}

// Singleton instance
export const wsClient = new MyndLensWSClient();
