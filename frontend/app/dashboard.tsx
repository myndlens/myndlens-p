import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator, Switch,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { ENV } from '../src/config/env';

export default function DashboardScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [tab, setTab] = useState<'overview' | 'tools' | 'agents' | 'usage'>('overview');
  const [config, setConfig] = useState<any>(null);
  const [agents, setAgents] = useState<any[]>([]);
  const [usage, setUsage] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const api = (path: string) => fetch(`${ENV.API_URL}/dashboard${path}`).then(r => r.json());

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [c, a, u] = await Promise.all([api('/workspace/config'), api('/workspace/agents'), api('/workspace/usage')]);
      setConfig(c);
      setAgents(a.agents || []);
      setUsage(u);
    } catch {}
    setLoading(false);
  }

  if (loading) {
    return (
      <View style={[styles.container, { paddingTop: insets.top + 20 }]}>
        <ActivityIndicator size="large" color="#6C63FF" />
      </View>
    );
  }

  const TABS = [
    { key: 'overview', label: 'Overview' },
    { key: 'tools', label: 'Tools' },
    { key: 'agents', label: 'Agents' },
    { key: 'usage', label: 'Usage' },
  ] as const;

  return (
    <View style={[styles.container, { paddingTop: insets.top + 12 }]} data-testid="dashboard-screen">
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} data-testid="dashboard-back-btn">
          <Text style={styles.backArrow}>{'\u2190'}</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Dashboard</Text>
        <View style={{ width: 32 }} />
      </View>

      <View style={styles.tabRow}>
        {TABS.map(t => (
          <TouchableOpacity key={t.key} style={[styles.tab, tab === t.key && styles.tabActive]} onPress={() => setTab(t.key)} data-testid={`tab-${t.key}`}>
            <Text style={[styles.tabText, tab === t.key && styles.tabTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView style={styles.content} contentContainerStyle={{ paddingBottom: 40 }}>
        {tab === 'overview' && config && (
          <View data-testid="overview-tab">
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Workspace</Text>
              <Text style={styles.cardValue}>{config.workspace?.name || config.workspace?.slug}</Text>
              <View style={[styles.badge, { backgroundColor: config.workspace?.status === 'READY' ? '#00D68F22' : '#FF444422' }]}>
                <Text style={[styles.badgeText, { color: config.workspace?.status === 'READY' ? '#00D68F' : '#FF4444' }]}>{config.workspace?.status}</Text>
              </View>
            </View>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Model</Text>
              <Text style={styles.cardValue}>{config.workspace?.model}</Text>
            </View>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Subscription</Text>
              <Text style={styles.cardValue}>{config.subscription?.plan_id} - {config.subscription?.status}</Text>
            </View>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Runtime</Text>
              <Text style={styles.cardValue}>Status: {config.runtime?.status}</Text>
            </View>
          </View>
        )}

        {tab === 'tools' && config && (
          <View data-testid="tools-tab">
            <Text style={styles.sectionTitle}>Enabled Tools</Text>
            {(config.tools?.enabled || []).map((t: string) => (
              <View key={t} style={styles.toolRow}>
                <View style={styles.toolDot} />
                <Text style={styles.toolName}>{t}</Text>
                <Switch value={true} trackColor={{ true: '#6C63FF' }} thumbColor="#fff" disabled />
              </View>
            ))}
            <Text style={[styles.sectionTitle, { marginTop: 20 }]}>Approval Policy</Text>
            <View style={styles.toolRow}>
              <Text style={styles.toolName}>Auto-approve low risk</Text>
              <Switch value={config.approval_policy?.auto_approve_low} trackColor={{ true: '#6C63FF' }} thumbColor="#fff" disabled />
            </View>
            <View style={styles.toolRow}>
              <Text style={styles.toolName}>Auto-approve medium risk</Text>
              <Switch value={config.approval_policy?.auto_approve_medium} trackColor={{ true: '#6C63FF' }} thumbColor="#fff" disabled />
            </View>
          </View>
        )}

        {tab === 'agents' && (
          <View data-testid="agents-tab">
            <Text style={styles.sectionTitle}>Agents ({agents.length})</Text>
            {agents.map((a: any) => (
              <View key={a.id} style={styles.card}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={styles.cardTitle}>{a.name}</Text>
                  <View style={[styles.badge, { backgroundColor: a.status === 'active' ? '#00D68F22' : '#88888822' }]}>
                    <Text style={[styles.badgeText, { color: a.status === 'active' ? '#00D68F' : '#888' }]}>{a.status}</Text>
                  </View>
                </View>
                <Text style={styles.cardSub}>Model: {a.model}</Text>
                <Text style={styles.cardSub}>Skills: {a.skills?.join(', ') || 'None'}</Text>
                <Text style={styles.cardSub}>Tools: {a.tools?.join(', ') || 'Default'}</Text>
              </View>
            ))}
          </View>
        )}

        {tab === 'usage' && usage && (
          <View data-testid="usage-tab">
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Today's Usage</Text>
              <View style={styles.usageRow}>
                <Text style={styles.usageLabel}>Messages</Text>
                <View style={styles.progressBg}>
                  <View style={[styles.progressFill, { width: `${Math.min((usage.today?.messages / usage.limits?.messages) * 100, 100)}%` }]} />
                </View>
                <Text style={styles.usageValue}>{usage.today?.messages}/{usage.limits?.messages}</Text>
              </View>
              <View style={styles.usageRow}>
                <Text style={styles.usageLabel}>Tokens</Text>
                <View style={styles.progressBg}>
                  <View style={[styles.progressFill, { width: `${Math.min((usage.today?.tokens / usage.limits?.tokens) * 100, 100)}%` }]} />
                </View>
                <Text style={styles.usageValue}>{(usage.today?.tokens / 1000).toFixed(1)}k/{(usage.limits?.tokens / 1000).toFixed(0)}k</Text>
              </View>
              <View style={styles.usageRow}>
                <Text style={styles.usageLabel}>Tool Calls</Text>
                <Text style={styles.usageValue}>{usage.today?.tool_calls}</Text>
              </View>
            </View>
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Subscription</Text>
              <Text style={styles.cardValue}>{usage.subscription?.plan_name} - {usage.subscription?.status}</Text>
            </View>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A0F' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, marginBottom: 12 },
  backArrow: { fontSize: 24, color: '#AAAAB8' },
  title: { fontSize: 20, fontWeight: '700', color: '#F0F0F5' },
  tabRow: { flexDirection: 'row', paddingHorizontal: 16, marginBottom: 12, gap: 6 },
  tab: { flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: '#14141E', alignItems: 'center' },
  tabActive: { backgroundColor: '#6C63FF22', borderWidth: 1, borderColor: '#6C63FF' },
  tabText: { color: '#777', fontSize: 13, fontWeight: '600' },
  tabTextActive: { color: '#6C63FF' },
  content: { flex: 1, paddingHorizontal: 20 },
  sectionTitle: { color: '#AAAAB8', fontSize: 14, fontWeight: '600', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 },
  card: { backgroundColor: '#14141E', borderRadius: 14, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: '#1E1E2E' },
  cardTitle: { color: '#E0E0E8', fontSize: 16, fontWeight: '600', marginBottom: 4 },
  cardValue: { color: '#AAAAB8', fontSize: 14 },
  cardSub: { color: '#777', fontSize: 13, marginTop: 4 },
  badge: { alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 3, borderRadius: 8, marginTop: 6 },
  badgeText: { fontSize: 12, fontWeight: '600' },
  toolRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#1E1E2E' },
  toolDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#00D68F', marginRight: 12 },
  toolName: { flex: 1, color: '#D0D0E0', fontSize: 15 },
  usageRow: { flexDirection: 'row', alignItems: 'center', marginTop: 12, gap: 8 },
  usageLabel: { color: '#AAAAB8', fontSize: 13, width: 70 },
  usageValue: { color: '#D0D0E0', fontSize: 13, width: 70, textAlign: 'right' },
  progressBg: { flex: 1, height: 8, backgroundColor: '#1E1E2E', borderRadius: 4, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: '#6C63FF', borderRadius: 4 },
});
