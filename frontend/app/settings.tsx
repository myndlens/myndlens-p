import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
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
import { ENV } from '../src/config/env';

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { userId, connectionStatus, presenceOk, clearAuth: clearStoreAuth } = useSessionStore();
  const [diagOpen, setDiagOpen] = useState(false);
  const [nickname, setNickname] = useState('MyndLens');
  const [nickSaved, setNickSaved] = useState(false);

  useEffect(() => {
    if (userId) {
      fetch(`${ENV.API_URL}/nickname/${userId}`)
        .then(r => r.json())
        .then(d => setNickname(d.nickname || 'MyndLens'))
        .catch(() => {});
    }
  }, [userId]);

  async function saveNickname() {
    const nick = nickname.trim() || 'MyndLens';
    await fetch(`${ENV.API_URL}/nickname`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId || 'anon', nickname: nick }),
    }).catch(() => {});
    setNickSaved(true);
    setTimeout(() => setNickSaved(false), 2000);
  }

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
          <Text style={styles.close}>{'\u2715'}</Text>
        </TouchableOpacity>
      </View>

      <ScrollView style={styles.scroll}>
        {/* Proxy Nickname */}
        <Text style={styles.section}>Assistant Name</Text>
        <View style={styles.card}>
          <Text style={styles.nickHint}>Give your assistant a name</Text>
          <View style={styles.nickRow}>
            <TextInput
              style={styles.nickInput}
              value={nickname}
              onChangeText={setNickname}
              placeholder="MyndLens"
              placeholderTextColor="#444"
              maxLength={30}
              data-testid="nickname-input"
            />
            <TouchableOpacity style={styles.nickSaveBtn} onPress={saveNickname} data-testid="nickname-save-btn">
              <Text style={styles.nickSaveText}>{nickSaved ? 'Saved' : 'Save'}</Text>
            </TouchableOpacity>
          </View>
          {nickSaved && <Text style={styles.nickConfirm}>Your assistant will now respond as "{nickname.trim() || 'MyndLens'}"</Text>}
        </View>

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
  card: { backgroundColor: '#12121E', borderRadius: 12, overflow: 'hidden', padding: 0 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 14, paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: '#1A1A2E' },
  rowLabel: { fontSize: 14, color: '#8B8B9E' },
  rowValue: { fontSize: 14, color: '#FFFFFF' },

  nickHint: { fontSize: 13, color: '#777', paddingHorizontal: 16, paddingTop: 14, paddingBottom: 8 },
  nickRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingBottom: 12, gap: 8 },
  nickInput: { flex: 1, backgroundColor: '#0A0A14', borderWidth: 1, borderColor: '#2A2A3A', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12, fontSize: 16, color: '#F0F0F5' },
  nickSaveBtn: { backgroundColor: '#6C63FF', borderRadius: 10, paddingHorizontal: 20, paddingVertical: 12 },
  nickSaveText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  nickConfirm: { color: '#00D68F', fontSize: 13, paddingHorizontal: 16, paddingBottom: 12 },

  actionRow: { paddingVertical: 14, paddingHorizontal: 16 },
  actionText: { fontSize: 14, color: '#E74C3C' },

  diagHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 20, marginBottom: 8 },
  diagTitle: { fontSize: 12, fontWeight: '600', color: '#444455', textTransform: 'uppercase', letterSpacing: 1 },
  diagChevron: { fontSize: 10, color: '#444455' },
  diagCard: { backgroundColor: '#0D0D18', borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: '#1A1A2E' },

  signOut: { marginTop: 32, paddingVertical: 16, alignItems: 'center' },
  signOutText: { fontSize: 15, color: '#E74C3C', fontWeight: '600' },
});
