import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { wsClient, WSEnvelope } from '../src/ws/client';
import { useSessionStore } from '../src/state/session-store';

/**
 * Main Talk screen — the primary interaction interface.
 *
 * Batch 1 scope:
 * - Connect to WS with auth
 * - Show connection + heartbeat status
 * - Execute button (gated by presence)
 * - Test execute blocking when heartbeat stale
 */
export default function TalkScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const {
    userId,
    connectionStatus,
    sessionId,
    lastHeartbeatSeq,
    presenceOk,
    lastExecuteBlockReason,
    setConnectionStatus,
    setSessionId,
    setHeartbeatSeq,
    setPresenceOk,
    setExecuteBlocked,
  } = useSessionStore();

  const [statusMessages, setStatusMessages] = useState<string[]>([]);
  const [isConnecting, setIsConnecting] = useState(false);
  const pulseAnim = useRef(new Animated.Value(1)).current;

  // Pulse animation for presence indicator
  useEffect(() => {
    if (connectionStatus === 'authenticated') {
      const pulse = Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 0.4,
            duration: 2500,
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 2500,
            useNativeDriver: true,
          }),
        ])
      );
      pulse.start();
      return () => pulse.stop();
    }
  }, [connectionStatus]);

  const addStatus = useCallback((msg: string) => {
    setStatusMessages((prev) => [...prev.slice(-9), `[${new Date().toLocaleTimeString()}] ${msg}`]);
  }, []);

  // Connect on mount
  useEffect(() => {
    connectWS();

    // Register handlers
    const unsubs = [
      wsClient.on('heartbeat_ack', (env: WSEnvelope) => {
        setHeartbeatSeq(env.payload.seq);
      }),
      wsClient.on('execute_blocked', (env: WSEnvelope) => {
        setExecuteBlocked(env.payload.reason);
        addStatus(`EXECUTE BLOCKED: ${env.payload.code} - ${env.payload.reason}`);
      }),
      wsClient.on('execute_ok', () => {
        setExecuteBlocked(null);
        addStatus('EXECUTE OK: Dispatch successful');
      }),
      wsClient.on('error', (env: WSEnvelope) => {
        addStatus(`ERROR: ${env.payload.code} - ${env.payload.message}`);
      }),
      wsClient.on('session_terminated', () => {
        setConnectionStatus('disconnected');
        setSessionId(null);
        setPresenceOk(false);
        addStatus('Session terminated');
      }),
    ];

    return () => {
      unsubs.forEach((u) => u());
      wsClient.disconnect();
    };
  }, []);

  async function connectWS() {
    setIsConnecting(true);
    setConnectionStatus('connecting');
    addStatus('Connecting to MyndLens BE...');

    try {
      await wsClient.connect();
      setConnectionStatus('authenticated');
      setSessionId(wsClient.currentSessionId);
      setPresenceOk(true);
      addStatus(`Connected! Session: ${wsClient.currentSessionId?.slice(0, 8)}...`);
    } catch (err: any) {
      setConnectionStatus('error');
      addStatus(`Connection failed: ${err.message}`);
    } finally {
      setIsConnecting(false);
    }
  }

  function handleExecute() {
    if (!wsClient.isAuthenticated) {
      addStatus('Cannot execute: not authenticated');
      return;
    }
    setExecuteBlocked(null);
    addStatus('Sending execute request...');
    wsClient.sendExecuteRequest('test-draft-' + Date.now());
  }

  function handleSettings() {
    router.push('/settings');
  }

  const statusColor =
    connectionStatus === 'authenticated'
      ? '#00D68F'
      : connectionStatus === 'connecting'
      ? '#FFAA00'
      : connectionStatus === 'error'
      ? '#E74C3C'
      : '#555568';

  return (
    <View style={[styles.container, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 16 }]}>
      {/* Top Bar */}
      <View style={styles.topBar}>
        <View style={styles.topBarLeft}>
          <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
          <Text style={styles.statusText}>
            {connectionStatus === 'authenticated'
              ? 'Connected'
              : connectionStatus === 'connecting'
              ? 'Connecting...'
              : connectionStatus === 'error'
              ? 'Error'
              : 'Disconnected'}
          </Text>
        </View>
        <TouchableOpacity onPress={handleSettings} style={styles.settingsBtn}>
          <Text style={styles.settingsIcon}>⚙</Text>
        </TouchableOpacity>
      </View>

      {/* Session Info */}
      <View style={styles.sessionInfo}>
        <Text style={styles.sessionLabel}>User</Text>
        <Text style={styles.sessionValue}>{userId || 'Not paired'}</Text>
        <Text style={styles.sessionLabel}>Session</Text>
        <Text style={styles.sessionValue}>{sessionId?.slice(0, 12) || '—'}...</Text>
      </View>

      {/* Presence Indicator */}
      <View style={styles.presenceSection}>
        <Animated.View
          style={[
            styles.presenceOrb,
            {
              backgroundColor: presenceOk ? '#6C5CE7' : '#333',
              opacity: pulseAnim,
              shadowColor: presenceOk ? '#6C5CE7' : 'transparent',
            },
          ]}
        />
        <View style={styles.presenceInfo}>
          <Text style={styles.presenceTitle}>
            {connectionStatus === 'authenticated' ? 'Presence Active' : 'Presence Inactive'}
          </Text>
          <Text style={styles.presenceDetail}>
            HB Seq: {lastHeartbeatSeq} | {presenceOk ? 'Fresh' : 'Stale'}
          </Text>
        </View>
      </View>

      {/* Execute Button */}
      <View style={styles.executeSection}>
        <TouchableOpacity
          style={[
            styles.executeButton,
            connectionStatus !== 'authenticated' && styles.executeButtonDisabled,
          ]}
          onPress={handleExecute}
          disabled={connectionStatus !== 'authenticated'}
          activeOpacity={0.7}
        >
          <Text style={styles.executeIcon}>▶</Text>
          <Text style={styles.executeText}>Execute</Text>
        </TouchableOpacity>

        {lastExecuteBlockReason && (
          <View style={styles.blockReasonBox}>
            <Text style={styles.blockReasonLabel}>BLOCKED</Text>
            <Text style={styles.blockReasonText}>{lastExecuteBlockReason}</Text>
          </View>
        )}
      </View>

      {/* Status Log */}
      <View style={styles.logSection}>
        <Text style={styles.logTitle}>Activity Log</Text>
        <View style={styles.logBox}>
          {statusMessages.length === 0 ? (
            <Text style={styles.logEmpty}>No activity yet</Text>
          ) : (
            statusMessages.map((msg, i) => (
              <Text key={i} style={styles.logEntry}>
                {msg}
              </Text>
            ))
          )}
        </View>
      </View>

      {/* Reconnect Button */}
      {connectionStatus !== 'authenticated' && !isConnecting && (
        <TouchableOpacity style={styles.reconnectBtn} onPress={connectWS}>
          <Text style={styles.reconnectText}>Reconnect</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A0A0F',
    paddingHorizontal: 20,
  },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  topBarLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  statusText: {
    fontSize: 14,
    color: '#A0A0B8',
    fontWeight: '600',
  },
  settingsBtn: {
    padding: 8,
  },
  settingsIcon: {
    fontSize: 24,
    color: '#8B8B9E',
  },
  sessionInfo: {
    backgroundColor: '#12121E',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#1A1A2E',
  },
  sessionLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: '#6C5CE7',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 2,
    marginTop: 8,
  },
  sessionValue: {
    fontSize: 14,
    color: '#FFFFFF',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  presenceSection: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#12121E',
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#1A1A2E',
    gap: 16,
  },
  presenceOrb: {
    width: 48,
    height: 48,
    borderRadius: 24,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 16,
    elevation: 8,
  },
  presenceInfo: {
    flex: 1,
  },
  presenceTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#FFFFFF',
    marginBottom: 4,
  },
  presenceDetail: {
    fontSize: 12,
    color: '#8B8B9E',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  executeSection: {
    marginBottom: 20,
  },
  executeButton: {
    backgroundColor: '#6C5CE7',
    borderRadius: 16,
    paddingVertical: 18,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    shadowColor: '#6C5CE7',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 6,
  },
  executeButtonDisabled: {
    backgroundColor: '#333340',
    shadowOpacity: 0,
    elevation: 0,
  },
  executeIcon: {
    fontSize: 18,
    color: '#FFFFFF',
  },
  executeText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  blockReasonBox: {
    backgroundColor: '#2D1B1B',
    borderRadius: 8,
    padding: 12,
    marginTop: 12,
    borderWidth: 1,
    borderColor: '#E74C3C44',
  },
  blockReasonLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: '#E74C3C',
    letterSpacing: 1,
    marginBottom: 4,
  },
  blockReasonText: {
    fontSize: 12,
    color: '#CC8888',
    lineHeight: 18,
  },
  logSection: {
    flex: 1,
    marginBottom: 12,
  },
  logTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#A0A0B8',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  logBox: {
    flex: 1,
    backgroundColor: '#0D0D18',
    borderRadius: 8,
    padding: 12,
    borderWidth: 1,
    borderColor: '#1A1A2E',
  },
  logEmpty: {
    color: '#555568',
    fontSize: 12,
    fontStyle: 'italic',
  },
  logEntry: {
    color: '#8B8B9E',
    fontSize: 11,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    lineHeight: 18,
  },
  reconnectBtn: {
    backgroundColor: '#1A1A2E',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#2A2A3E',
  },
  reconnectText: {
    color: '#6C5CE7',
    fontSize: 14,
    fontWeight: '600',
  },
});
