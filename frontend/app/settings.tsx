import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Platform,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useSessionStore } from '../src/state/session-store';
import { clearAuth } from '../src/ws/auth';
import { wsClient } from '../src/ws/client';

/**
 * Settings — secondary screen.
 *
 * Sections:
 * 1. Account (read-only)
 * 2. Privacy & Control
 * 3. Diagnostics (collapsed, deemphasized)
 * 4. Sign Out
 *
 * Never shows: tokens, IDs, counters.
 */
export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { userId, connectionStatus, presenceOk, clearAuth: clearStoreAuth } = useSessionStore();
  const [diagOpen, setDiagOpen] = useState(false);

  async function handleSignOut() {
    wsClient.disconnect();
    await clearAuth();
    clearStoreAuth();
    router.replace('/login');
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 16 }]}>
      <View style={styles.header}>
        <Text style={styles.title}>Settings</Text>
        <TouchableOpacity onPress={() => router.back()} hitSlop={{ top: 16, bottom: 16, left: 16, right: 16 }}>
          <Text style={styles.close}>\u2715</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.scroll}>
        {/* Account */}
        <Text style={styles.section}>Account</Text>
        <View style={styles.card}>
          <Row label="Signed in as" value={userId || '\u2014'} />
          <Row label="Subscription" value="Active" />
        </View>

        {/* Privacy & Control */}
        <Text style={styles.section}>Privacy & Control</Text>
        <View style={styles.card}>
          <TouchableOpacity style={styles.actionRow}>
            <Text style={styles.actionText}>Clear conversation history</Text>
          </TouchableOpacity>
        </View>

        {/* Diagnostics (collapsed) */}
        <TouchableOpacity onPress={() => setDiagOpen(!diagOpen)} style={styles.diagHeader}>
          <Text style={styles.diagTitle}>Diagnostics</Text>
          <Text style={styles.diagChevron}>{diagOpen ? '\u25B2' : '\u25BC'}</Text>
        </TouchableOpacity>
        {diagOpen ? (
          <View style={styles.diagCard}>
            <Row label="Connection" value={connectionStatus === 'authenticated' ? 'Connected' : 'Disconnected'} />
            <Row label="Presence" value={presenceOk ? 'Active' : 'Inactive'} />
            <Row label="Version" value="0.2.0" />
            <Row label="Platform" value={Platform.OS} />
          </View>
        ) : null}

        {/* Sign Out */}
        <TouchableOpacity style={styles.signOut} onPress={handleSignOut}>
          <Text style={styles.signOutText}>Sign out</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0F', paddingHorizontal: 20 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 },
  title: { fontSize: 22, fontWeight: '700', color: '#FFFFFF' },
  close: { fontSize: 20, color: '#555568' },
  scroll: { flex: 1 },

  section: { fontSize: 12, fontWeight: '600', color: '#6C5CE7', textTransform: 'uppercase', letterSpacing: 1, marginTop: 20, marginBottom: 8 },
  card: { backgroundColor: '#12121E', borderRadius: 12, overflow: 'hidden' },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 14, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: '#1A1A2E' },
  rowLabel: { fontSize: 14, color: '#8B8B9E' },
  rowValue: { fontSize: 14, color: '#FFFFFF' },

  actionRow: { paddingVertical: 14, paddingHorizontal: 16 },
  actionText: { fontSize: 14, color: '#E74C3C' },

  diagHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 20, marginBottom: 8 },
  diagTitle: { fontSize: 12, fontWeight: '600', color: '#444455', textTransform: 'uppercase', letterSpacing: 1 },
  diagChevron: { fontSize: 10, color: '#444455' },
  diagCard: { backgroundColor: '#0D0D18', borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: '#1A1A2E' },

  signOut: { marginTop: 32, paddingVertical: 16, alignItems: 'center' },
  signOutText: { fontSize: 15, color: '#E74C3C', fontWeight: '600' },
});
