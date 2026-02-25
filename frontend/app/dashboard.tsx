/**
 * Dashboard Screen — Hamburger Menu → Dashboard
 *
 * Calls ObeGee backend directly (not the MyndLens backend mock).
 * Uses the stored ObeGee JWT token from SecureStore.
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { getStoredToken } from '../src/ws/auth';

const OBEGEE = process.env.EXPO_PUBLIC_OBEGEE_URL || 'https://obegee.co.uk';

async function obegee(path: string, token: string) {
  const r = await fetch(`${OBEGEE}/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return r.ok ? r.json() : null;
}

export default function DashboardScreen() {
  const insets = useSafeAreaInsets();
  const router  = useRouter();
  const [tab, setTab] = useState<'overview' | 'connections' | 'usage'>('overview');

  const [tenant, setTenant]           = useState<any>(null);
  const [subscription, setSubscription] = useState<any>(null);
  const [runtime, setRuntime]         = useState<any>(null);
  const [usage, setUsage]             = useState<any>(null);
  const [approvalPolicy, setPolicy]   = useState<any>(null);
  const [waStatus, setWaStatus]       = useState<any>(null);
  const [mlStatus, setMlStatus]       = useState<any>(null);
  const [loading, setLoading]         = useState(true);
  const [refreshing, setRefreshing]   = useState(false);

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true); else setLoading(true);
    try {
      const token = await getStoredToken();
      if (!token) { setLoading(false); setRefreshing(false); return; }

      const [t, sub, u, pol, ml] = await Promise.all([
        obegee('/tenants/my-tenant', token),
        obegee('/billing/subscription', token),
        obegee('/usage/today', token),
        obegee('/approvals/policy', token),
        obegee('/myndlens/status', token),
      ]);

      setTenant(t);
      setSubscription(sub);
      setUsage(u);
      setPolicy(pol);
      setMlStatus(ml);

      // Tenant-specific calls need tenant_id
      if (t?.tenant_id) {
        const [rt, wa] = await Promise.all([
          obegee(`/runtime/health/${t.tenant_id}`, token),
          obegee(`/whatsapp/status/${t.tenant_id}`, token),
        ]);
        setRuntime(rt);
        setWaStatus(wa);
      }
    } catch {}
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const TABS = [
    { key: 'overview',     label: 'Overview'     },
    { key: 'connections',  label: 'Connections'  },
    { key: 'usage',        label: 'Usage'        },
  ] as const;

  const isRunning    = runtime?.status === 'running';
  const waConnected  = waStatus?.status === 'connected';
  const mlConnected  = mlStatus?.connected;

  if (loading) {
    return (
      <View style={[s.container, { paddingTop: insets.top + 20, alignItems: 'center', justifyContent: 'center' }]}>
        <ActivityIndicator size="large" color="#6C5CE7" />
        <Text style={{ color: '#888', marginTop: 12, fontSize: 13 }}>Loading workspace…</Text>
      </View>
    );
  }

  return (
    <View style={[s.container, { paddingTop: insets.top + 12 }]} data-testid="dashboard-screen">
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} data-testid="dashboard-back-btn">
          <Text style={s.backArrow}>←</Text>
        </TouchableOpacity>
        <Text style={s.title}>Workspace</Text>
        <View style={{ width: 32 }} />
      </View>

      {/* Agent status pill */}
      <View style={[s.pill, { backgroundColor: isRunning ? '#00D68F18' : '#FF444418', borderColor: isRunning ? '#00D68F' : '#FF4444' }]}>
        <View style={[s.pillDot, { backgroundColor: isRunning ? '#00D68F' : '#FF4444' }]} />
        <Text style={[s.pillText, { color: isRunning ? '#00D68F' : '#FF4444' }]}>
          OpenClaw Tenant {isRunning ? 'Running' : (runtime?.status || 'Offline')}
          {runtime?.node_version ? `  ·  Node ${runtime.node_version}` : ''}
        </Text>
      </View>

      {/* Tabs */}
      <View style={s.tabRow}>
        {TABS.map(t => (
          <TouchableOpacity key={t.key}
            style={[s.tab, tab === t.key && s.tabActive]}
            onPress={() => setTab(t.key)}
            data-testid={`tab-${t.key}`}>
            <Text style={[s.tabText, tab === t.key && s.tabTextActive]}>{t.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView
        style={s.content}
        contentContainerStyle={{ paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor="#6C5CE7" />}
      >
        {/* ── OVERVIEW ── */}
        {tab === 'overview' && (
          <View data-testid="overview-tab">
            <Row label="Workspace" value={tenant?.workspace_slug || '—'} badge={tenant?.status} badgeOk={tenant?.status === 'READY'} />
            <Row label="Model" value={tenant?.model_provider || 'Moonshot (Kimi K2.5)'} />
            <Row label="Subscription"
              value={(subscription?.plan_id || 'No plan').replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}
              badge={subscription?.status}
              badgeOk={subscription?.status === 'active'}
            />
            {subscription?.current_period_end && (
              <Row label="Renews" value={new Date(subscription.current_period_end).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })} />
            )}

            <Text style={s.sectionTitle}>Approval Policy</Text>
            <PolicyRow label="Auto-approve low risk"    on={approvalPolicy?.auto_approve_low} />
            <PolicyRow label="Auto-approve medium risk" on={approvalPolicy?.auto_approve_medium} />
          </View>
        )}

        {/* ── CONNECTIONS ── */}
        {tab === 'connections' && (
          <View data-testid="connections-tab">
            <ConnRow label="WhatsApp"    connected={waConnected}   note={waConnected ? 'Connected' : 'Not connected — pair at obegee.co.uk'} />
            <ConnRow label="MyndLens"    connected={mlConnected}   note={mlConnected ? (mlStatus?.device_name || 'Paired') : 'App not paired to workspace'} />
          </View>
        )}

        {/* ── USAGE ── */}
        {tab === 'usage' && (
          <View data-testid="usage-tab">
            <View style={s.card}>
              <Text style={s.cardTitle}>Today</Text>
              <UsageBar label="Messages"   used={usage?.messages_used ?? 0}  cap={usage?.messages_cap ?? 500} />
              <UsageBar label="Tokens"     used={usage?.tokens_used ?? 0}    cap={usage?.tokens_cap ?? 100000} unit="k" />
              <UsageBar label="Tool calls" used={usage?.tool_calls_used ?? 0} cap={usage?.tool_calls_cap ?? 100} />
            </View>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

const Row = ({ label, value, badge, badgeOk }: any) => (
  <View style={s.card}>
    <Text style={s.cardSub}>{label}</Text>
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 2 }}>
      <Text style={s.cardValue}>{value}</Text>
      {badge && (
        <View style={[s.badge, { backgroundColor: badgeOk ? '#00D68F18' : '#88888818' }]}>
          <Text style={[s.badgeText, { color: badgeOk ? '#00D68F' : '#888' }]}>{badge}</Text>
        </View>
      )}
    </View>
  </View>
);

const PolicyRow = ({ label, on }: any) => (
  <View style={s.policyRow}>
    <View style={[s.dot, { backgroundColor: on ? '#00D68F' : '#444' }]} />
    <Text style={s.policyText}>{label}</Text>
    <Text style={[s.policyVal, { color: on ? '#00D68F' : '#666' }]}>{on ? 'On' : 'Off'}</Text>
  </View>
);

const ConnRow = ({ label, connected, note }: any) => (
  <View style={s.card}>
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
      <Text style={s.cardValue}>{label}</Text>
      <View style={[s.badge, { backgroundColor: connected ? '#00D68F18' : '#FF444418', borderColor: connected ? '#00D68F30' : '#FF444430' }]}>
        <Text style={[s.badgeText, { color: connected ? '#00D68F' : '#FF6666' }]}>{connected ? 'Connected' : 'Not connected'}</Text>
      </View>
    </View>
    <Text style={[s.cardSub, { marginTop: 4 }]}>{note}</Text>
  </View>
);

const UsageBar = ({ label, used, cap, unit }: any) => {
  const pct = cap > 0 ? Math.min((used / cap) * 100, 100) : 0;
  const fmt = (n: number) => unit === 'k' ? `${(n / 1000).toFixed(1)}k` : String(n);
  return (
    <View style={s.usageRow}>
      <Text style={s.usageLabel}>{label}</Text>
      <View style={s.progressBg}>
        <View style={[s.progressFill, { width: `${pct}%` as any }]} />
      </View>
      <Text style={s.usageValue}>{fmt(used)}/{fmt(cap)}</Text>
    </View>
  );
};

// ── Styles ────────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  container:    { flex: 1, backgroundColor: '#0A0A14' },
  header:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, marginBottom: 12 },
  backArrow:    { fontSize: 24, color: '#AAAAB8' },
  title:        { fontSize: 20, fontWeight: '700', color: '#F0F0F5' },
  pill:         { flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 20, marginBottom: 14, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, borderWidth: 1 },
  pillDot:      { width: 8, height: 8, borderRadius: 4 },
  pillText:     { fontSize: 13, fontWeight: '600' },
  tabRow:       { flexDirection: 'row', paddingHorizontal: 16, marginBottom: 12, gap: 6 },
  tab:          { flex: 1, paddingVertical: 10, borderRadius: 10, backgroundColor: '#111', alignItems: 'center' },
  tabActive:    { backgroundColor: '#6C5CE722', borderWidth: 1, borderColor: '#6C5CE7' },
  tabText:      { color: '#777', fontSize: 13, fontWeight: '600' },
  tabTextActive:{ color: '#6C5CE7' },
  content:      { flex: 1, paddingHorizontal: 20 },
  sectionTitle: { color: '#AAAAB8', fontSize: 12, fontWeight: '700', marginTop: 16, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 },
  card:         { backgroundColor: '#111', borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1, borderColor: '#1E1E2E' },
  cardTitle:    { color: '#E0E0E8', fontSize: 15, fontWeight: '600', marginBottom: 4 },
  cardValue:    { color: '#D0D0E0', fontSize: 15, fontWeight: '600' },
  cardSub:      { color: '#888', fontSize: 12 },
  badge:        { paddingHorizontal: 10, paddingVertical: 3, borderRadius: 8, borderWidth: 1 },
  badgeText:    { fontSize: 12, fontWeight: '600' },
  dot:          { width: 8, height: 8, borderRadius: 4 },
  policyRow:    { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: '#1E1E2E' },
  policyText:   { flex: 1, color: '#C0C0D0', fontSize: 14 },
  policyVal:    { fontSize: 13, fontWeight: '600' },
  usageRow:     { flexDirection: 'row', alignItems: 'center', marginTop: 10, gap: 8 },
  usageLabel:   { color: '#888', fontSize: 12, width: 70 },
  usageValue:   { color: '#D0D0E0', fontSize: 12, width: 70, textAlign: 'right' },
  progressBg:   { flex: 1, height: 6, backgroundColor: '#1E1E2E', borderRadius: 3, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: '#6C5CE7', borderRadius: 3 },
});
