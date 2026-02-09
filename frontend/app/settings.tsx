import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Platform,
  Alert,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useSessionStore } from '../src/state/session-store';
import { clearAuth } from '../src/ws/auth';
import { wsClient } from '../src/ws/client';
import { ENV } from '../src/config/env';

/**
 * Settings screen — session info, debug, disconnect.
 */
export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const {
    userId,
    connectionStatus,
    sessionId,
    lastHeartbeatSeq,
    presenceOk,
    clearAuth: clearStoreAuth,
  } = useSessionStore();

  async function handleDisconnect() {
    wsClient.disconnect();
    await clearAuth();
    clearStoreAuth();
    router.replace('/pairing');
  }

  function handleClose() {
    router.back();
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 16 }]}>
      <View style={styles.header}>
        <Text style={styles.title}>Settings</Text>
        <TouchableOpacity onPress={handleClose} style={styles.closeBtn}>
          <Text style={styles.closeBtnText}>✕</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.content}>
        {/* Session Info */}
        <Text style={styles.sectionTitle}>Session</Text>
        <View style={styles.card}>
          <InfoRow label="User ID" value={userId || '—'} />
          <InfoRow label="Session ID" value={sessionId || '—'} />
          <InfoRow label="Status" value={connectionStatus} />
          <InfoRow label="Heartbeat Seq" value={String(lastHeartbeatSeq)} />
          <InfoRow label="Presence" value={presenceOk ? 'Fresh' : 'Stale'} />
        </View>

        {/* Connection Info */}
        <Text style={styles.sectionTitle}>Connection</Text>
        <View style={styles.card}>
          <InfoRow label="API URL" value={ENV.API_URL} />
          <InfoRow label="WS URL" value={ENV.WS_URL} />
          <InfoRow label="HB Interval" value={`${ENV.HEARTBEAT_INTERVAL_MS}ms`} />
        </View>

        {/* System */}
        <Text style={styles.sectionTitle}>System</Text>
        <View style={styles.card}>
          <InfoRow label="Version" value="0.1.0 (Batch 1)" />
          <InfoRow label="Platform" value={Platform.OS} />
          <InfoRow label="Batches" value="B0 + B1" />
        </View>

        {/* Disconnect */}
        <TouchableOpacity style={styles.disconnectBtn} onPress={handleDisconnect}>
          <Text style={styles.disconnectText}>Disconnect & Unpair</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0A0A0F',
    paddingHorizontal: 20,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 24,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  closeBtn: {
    padding: 8,
  },
  closeBtnText: {
    fontSize: 20,
    color: '#8B8B9E',
  },
  content: {
    flex: 1,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#6C5CE7',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 8,
    marginTop: 16,
  },
  card: {
    backgroundColor: '#12121E',
    borderRadius: 12,
    padding: 4,
    borderWidth: 1,
    borderColor: '#1A1A2E',
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1A1A2E',
  },
  infoLabel: {
    fontSize: 13,
    color: '#8B8B9E',
  },
  infoValue: {
    fontSize: 13,
    color: '#FFFFFF',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    maxWidth: '60%',
    textAlign: 'right',
  },
  disconnectBtn: {
    backgroundColor: '#2D1B1B',
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 32,
    borderWidth: 1,
    borderColor: '#E74C3C44',
  },
  disconnectText: {
    color: '#E74C3C',
    fontSize: 15,
    fontWeight: '600',
  },
});
