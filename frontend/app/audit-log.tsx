/**
 * Audit Log Screen — shows the user's server-side audit trail.
 */
import React, { useEffect, useState } from 'react';
import { View, Text, FlatList, StyleSheet, ActivityIndicator, TouchableOpacity } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { ENV } from '../src/config/env';
import { getStoredToken } from '../src/ws/auth';

interface AuditEvent {
  event_id: string;
  event_type: string;
  session_id?: string;
  user_id?: string;
  details: Record<string, any>;
  timestamp: string;
  env: string;
}

export default function AuditLogScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const token = await getStoredToken();
      const res = await fetch(`${ENV.API_URL}/digital-self/audit-log?limit=50`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setEvents(data.events ?? []);
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  }

  function formatTime(iso: string): string {
    try {
      return new Date(iso).toLocaleString();
    } catch { return iso; }
  }

  function formatType(type: string): string {
    return type.replace(/_/g, ' ').toLowerCase()
      .replace(/^\w/, c => c.toUpperCase());
  }

  return (
    <View style={[s.container, { paddingTop: insets.top }]}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={s.back}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={s.title}>Audit Log</Text>
        <TouchableOpacity onPress={load}>
          <Text style={s.refresh}>↻</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <ActivityIndicator color="#6C5CE7" style={{ marginTop: 40 }} />
      ) : error ? (
        <Text style={s.error}>{error}</Text>
      ) : events.length === 0 ? (
        <Text style={s.empty}>No audit events found.</Text>
      ) : (
        <FlatList
          data={events}
          keyExtractor={item => item.event_id}
          contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: insets.bottom + 16 }}
          renderItem={({ item }) => (
            <View style={s.card}>
              <View style={s.cardHeader}>
                <Text style={s.cardType}>{formatType(item.event_type)}</Text>
                <Text style={s.cardEnv}>{item.env}</Text>
              </View>
              <Text style={s.cardTime}>{formatTime(item.timestamp)}</Text>
              {item.session_id && (
                <Text style={s.cardDetail}>Session: {item.session_id.slice(0, 12)}…</Text>
              )}
              {Object.keys(item.details).length > 0 && (
                <Text style={s.cardDetail}>
                  {Object.entries(item.details)
                    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
                    .join(' · ')}
                </Text>
              )}
            </View>
          )}
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A14' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingBottom: 12,
    borderBottomWidth: 1, borderBottomColor: '#1A1A2E',
  },
  back: { color: '#6C5CE7', fontSize: 17, width: 44 },
  title: { color: '#fff', fontSize: 18, fontWeight: '600' },
  refresh: { color: '#6C5CE7', fontSize: 20, width: 44, textAlign: 'right' },
  error: { color: '#E74C3C', margin: 16 },
  empty: { color: '#555', margin: 16, textAlign: 'center', marginTop: 40 },
  card: {
    backgroundColor: '#111122', borderRadius: 10, padding: 12, marginBottom: 8,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  cardType: { color: '#fff', fontSize: 13, fontWeight: '600' },
  cardEnv: { color: '#6C5CE7', fontSize: 11 },
  cardTime: { color: '#666', fontSize: 11, marginBottom: 4 },
  cardDetail: { color: '#555', fontSize: 11, lineHeight: 16 },
});
