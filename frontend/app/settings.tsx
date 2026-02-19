import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  Switch, TextInput, Alert,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useSessionStore } from '../src/state/session-store';
import { clearAuth } from '../src/ws/auth';
import { wsClient } from '../src/ws/client';
import { ENV } from '../src/config/env';
import {
  loadSettings, saveSettings,
  UserSettings, DEFAULT_SETTINGS,
} from '../src/state/settings-prefs';
import { deleteDigitalSelf } from '../src/digital-self/kill-switch';
import { runTier1Ingestion } from '../src/digital-self/ingester';
import { getStoredUserId, getStoredToken } from '../src/ws/auth';
import {
  saveIMAPCredentials, loadIMAPCredentials, deleteIMAPCredentials,
  saveGmailToken, loadGmailToken,
  saveLinkedInCredentials, loadLinkedInCredentials,
  revokeAllCredentials,
  IMAPCredentials,
} from '../src/digital-self/credentials';

// ── Reusable sub-components ────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={s.section}>
      <Text style={s.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

function Row({
  label, sub, right,
}: { label: string; sub?: string; right: React.ReactNode }) {
  return (
    <View style={s.row}>
      <View style={s.rowText}>
        <Text style={s.rowLabel}>{label}</Text>
        {sub ? <Text style={s.rowSub}>{sub}</Text> : null}
      </View>
      {right}
    </View>
  );
}

function CheckRow({
  label, sub, value, onChange,
}: { label: string; sub?: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <Row
      label={label}
      sub={sub}
      right={
        <Switch
          value={value}
          onValueChange={onChange}
          trackColor={{ false: '#2A2A3E', true: '#6C5CE7' }}
          thumbColor={value ? '#fff' : '#888'}
        />
      }
    />
  );
}

function SegmentRow({
  label, sub, options, value, onChange,
}: {
  label: string;
  sub?: string;
  options: { key: string; label: string }[];
  value: string;
  onChange: (k: string) => void;
}) {
  return (
    <View style={s.segmentBlock}>
      <Text style={s.rowLabel}>{label}</Text>
      {sub ? <Text style={s.rowSub}>{sub}</Text> : null}
      <View style={s.segmentRow}>
        {options.map(o => (
          <TouchableOpacity
            key={o.key}
            style={[s.segBtn, value === o.key && s.segBtnActive]}
            onPress={() => onChange(o.key)}
          >
            <Text style={[s.segBtnText, value === o.key && s.segBtnTextActive]}>
              {o.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

function ActionBtn({
  label, onPress, destructive = false,
}: { label: string; onPress: () => void; destructive?: boolean }) {
  return (
    <TouchableOpacity
      style={[s.actionBtn, destructive && s.actionBtnDestructive]}
      onPress={onPress}
    >
      <Text style={[s.actionBtnText, destructive && s.actionBtnTextDestructive]}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

// ── Main Screen ────────────────────────────────────────────────────────────

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { userId, clearAuth: clearStoreAuth } = useSessionStore();
  const [prefs, setPrefs] = useState<UserSettings>(DEFAULT_SETTINGS);
  const [nickname, setNickname] = useState('MyndLens');
  const [nickSaved, setNickSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  // Category B credential state
  const [imapCreds, setImapCreds] = useState<IMAPCredentials>({ host: '', port: 993, email: '', password: '' });
  const [imapSaved, setImapSaved] = useState(false);
  const [gmailToken, setGmailToken] = useState('');
  const [linkedinToken, setLinkedinToken] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<string | null>(null);

  useEffect(() => {
    loadSettings().then(setPrefs);
    loadIMAPCredentials().then(c => c && setImapCreds(c));
    loadGmailToken().then(t => t && setGmailToken(t));
    loadLinkedInCredentials().then(c => c && setLinkedinToken(c?.access_token ?? ''));
    if (userId) {
      fetch(`${ENV.API_URL}/nickname/${userId}`)
        .then(r => r.json())
        .then(d => setNickname(d.nickname || 'MyndLens'))
        .catch(() => {});
    }
  }, [userId]);

  const update = useCallback(async (patch: Partial<UserSettings>) => {
    const next = { ...prefs, ...patch };
    setPrefs(next);
    await saveSettings(next);
  }, [prefs]);

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

  async function handleImportDataSources() {
    setSaving(true);
    try {
      const uid = await getStoredUserId() ?? 'local';
      const result = await runTier1Ingestion(uid);
      Alert.alert('Imported', `${result.contacts} contacts · ${result.calendar} calendar items`);
    } catch (e: any) {
      Alert.alert('Import Error', e.message);
    }
    setSaving(false);
  }

  async function handleSaveIMAP() {
    await saveIMAPCredentials(imapCreds);
    setImapSaved(true);
    setTimeout(() => setImapSaved(false), 2000);
  }

  async function handleSyncEmail() {
    if (!imapCreds.host || !imapCreds.email || !imapCreds.password) {
      Alert.alert('Missing credentials', 'Please enter your IMAP details first.');
      return;
    }
    setSyncing(true);
    setSyncResult(null);
    try {
      const token = await getStoredToken();
      const res = await fetch(`${ENV.API_URL}/digital-self/email/sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(imapCreds),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setSyncResult(
        `✅ Found ${data.contacts_found} contacts · ${data.travel_signals} travel signals`,
      );
    } catch (e: any) {
      setSyncResult(`❌ ${e.message}`);
    }
    setSyncing(false);
  }

  async function handleSaveGmail() {
    if (!gmailToken.trim()) return;
    await saveGmailToken(gmailToken.trim());
    Alert.alert('Saved', 'Gmail token saved securely.');
  }

  async function handleSaveLinkedIn() {
    if (!linkedinToken.trim()) return;
    await saveLinkedInCredentials({ access_token: linkedinToken.trim() });
    Alert.alert('Saved', 'LinkedIn token saved securely.');
  }

  async function handleRevokeAll() {
    Alert.alert(
      'Revoke All Credentials',
      'This removes all stored email, messaging, and social credentials. Data already imported is kept.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Revoke All', style: 'destructive', onPress: async () => {
          await revokeAllCredentials();
          setImapCreds({ host: '', port: 993, email: '', password: '' });
          setGmailToken('');
          setLinkedinToken('');
          Alert.alert('Done', 'All credentials revoked.');
        }},
      ],
    );
  }

  async function handlePauseDS() {
    await update({ ds_paused: !prefs.ds_paused });
  }

  async function handleResetPrefs() {
    Alert.alert(
      'Reset Preferences',
      'All settings will return to defaults. Your Digital Self data is not affected.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Reset',
          style: 'destructive',
          onPress: async () => {
            setPrefs({ ...DEFAULT_SETTINGS });
            await saveSettings({ ...DEFAULT_SETTINGS });
          },
        },
      ],
    );
  }

  async function handleDeleteDS() {
    Alert.alert(
      'Delete Digital Self',
      'This permanently deletes your entire Digital Self — all contacts, calendar patterns, traits, and preferences. This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete Everything',
          style: 'destructive',
          onPress: async () => {
            const uid = await getStoredUserId() ?? 'local';
            await deleteDigitalSelf(uid);
            Alert.alert('Done', 'Your Digital Self has been deleted.');
          },
        },
      ],
    );
  }

  return (
    <View style={[s.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={{ top: 16, bottom: 16, left: 16, right: 16 }}>
          <Text style={s.back}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={s.title}>Settings</Text>
        <View style={{ width: 44 }} />
      </View>

      <ScrollView
        contentContainerStyle={[s.scroll, { paddingBottom: insets.bottom + 32 }]}
        showsVerticalScrollIndicator={false}
      >

        {/* ─── 1. TRAVEL MONITORING ───────────────────────────────────────── */}
        <Section title="✈️  Travel Monitoring & Concierge">
          <CheckRow
            label="Enable proactive travel monitoring"
            sub="Monitor flights, hotels, and ground travel for disruptions and automatically reduce friction."
            value={prefs.travel_monitoring_enabled}
            onChange={v => update({ travel_monitoring_enabled: v })}
          />

          {prefs.travel_monitoring_enabled && (
            <>
              <Text style={s.subHeading}>Monitoring Scope</Text>
              <CheckRow label="Flights" value={prefs.travel_scope.flights} onChange={v => update({ travel_scope: { ...prefs.travel_scope, flights: v } })} />
              <CheckRow label="Hotels" value={prefs.travel_scope.hotels} onChange={v => update({ travel_scope: { ...prefs.travel_scope, hotels: v } })} />
              <CheckRow label="Ground transport" value={prefs.travel_scope.ground} onChange={v => update({ travel_scope: { ...prefs.travel_scope, ground: v } })} />

              <Text style={s.subHeading}>Auto-Action Policy</Text>
              <CheckRow
                label="Low-risk actions (default ON)"
                sub="Notify hotel of late arrival · Adjust pickup timing"
                value={prefs.auto_action.low_risk}
                onChange={v => update({ auto_action: { ...prefs.auto_action, low_risk: v } })}
              />
              <CheckRow
                label="Medium-risk actions"
                sub="Change seat · Request bed type · Meal requests — confirm once per trip"
                value={prefs.auto_action.medium_risk}
                onChange={v => update({ auto_action: { ...prefs.auto_action, medium_risk: v } })}
              />
              <CheckRow
                label="High-risk actions"
                sub="Rebook flights · Change fare class · Alternate hotel — always ask"
                value={prefs.auto_action.high_risk}
                onChange={v => update({ auto_action: { ...prefs.auto_action, high_risk: v } })}
              />
            </>
          )}
        </Section>

        {/* ─── 2. DIGITAL SELF DATA SOURCES ──────────────────────────────── */}
        <Section title="🧠  Digital Self — Data Sources">
          <Text style={s.principle}>Explicit opt-in. Explain value before asking. Reversible at any time.</Text>

          <Text style={s.subHeading}>Device Signals (Tier 1)</Text>
          <CheckRow
            label="Contacts & Call Logs"
            sub="Map your inner circle · People nodes · Relationship inference"
            value={prefs.data_sources.contacts}
            onChange={v => update({ data_sources: { ...prefs.data_sources, contacts: v } })}
          />
          <CheckRow
            label="Calendar"
            sub="Learn work hours, habitual locations, upcoming travel intents"
            value={prefs.data_sources.calendar}
            onChange={v => update({ data_sources: { ...prefs.data_sources, calendar: v } })}
          />

          {(prefs.data_sources.contacts || prefs.data_sources.calendar) && (
            <ActionBtn
              label={saving ? 'Importing…' : 'Import from device now'}
              onPress={handleImportDataSources}
            />
          )}

          <Text style={s.subHeading}>Email Access (Optional · Coming Soon)</Text>
          <CheckRow label="Gmail" value={prefs.data_sources.email_gmail} onChange={v => update({ data_sources: { ...prefs.data_sources, email_gmail: v } })} />
          <CheckRow label="Outlook" value={prefs.data_sources.email_outlook} onChange={v => update({ data_sources: { ...prefs.data_sources, email_outlook: v } })} />
          <CheckRow label="Other (IMAP)" value={prefs.data_sources.email_imap} onChange={v => update({ data_sources: { ...prefs.data_sources, email_imap: v } })} />

          <Text style={s.subHeading}>Messaging (Optional · Coming Soon)</Text>
          <CheckRow label="WhatsApp" value={prefs.data_sources.messaging_whatsapp} onChange={v => update({ data_sources: { ...prefs.data_sources, messaging_whatsapp: v } })} />
          <CheckRow label="iMessage" value={prefs.data_sources.messaging_imessage} onChange={v => update({ data_sources: { ...prefs.data_sources, messaging_imessage: v } })} />
          <CheckRow label="Telegram" value={prefs.data_sources.messaging_telegram} onChange={v => update({ data_sources: { ...prefs.data_sources, messaging_telegram: v } })} />
          <Text style={s.disclosure}>Messages are scanned locally for travel artifacts only.</Text>

          <Text style={s.subHeading}>Social & Professional (Optional · Coming Soon)</Text>
          <CheckRow label="LinkedIn" sub="Company affiliation · Role seniority · Business vs personal" value={prefs.data_sources.social_linkedin} onChange={v => update({ data_sources: { ...prefs.data_sources, social_linkedin: v } })} />
          <CheckRow label="Instagram / X (interest signals only)" value={prefs.data_sources.social_other} onChange={v => update({ data_sources: { ...prefs.data_sources, social_other: v } })} />

          <Text style={s.subHeading}>Financial Signals (Optional · Sensitive · Coming Soon)</Text>
          <CheckRow label="Payment methods (tokenized)" value={prefs.data_sources.financial_payment} onChange={v => update({ data_sources: { ...prefs.data_sources, financial_payment: v } })} />
          <CheckRow label="Corporate card flag" value={prefs.data_sources.financial_corporate} onChange={v => update({ data_sources: { ...prefs.data_sources, financial_corporate: v } })} />
        </Section>

        {/* ─── 3. AUTOMATION & CONSENT ────────────────────────────────────── */}
        <Section title="⚙️  Automation & Consent">
          <SegmentRow
            label="Delegation Mode"
            sub="How much MyndLens can do on your behalf without asking"
            options={[
              { key: 'advisory', label: 'Advisory' },
              { key: 'assisted', label: 'Assisted' },
              { key: 'delegated', label: 'Delegated' },
            ]}
            value={prefs.delegation_mode}
            onChange={v => update({ delegation_mode: v as UserSettings['delegation_mode'] })}
          />
          <Text style={s.delegationHint}>
            {prefs.delegation_mode === 'advisory' && 'Advisory: MyndLens suggests. You decide every action.'}
            {prefs.delegation_mode === 'assisted' && 'Assisted (default): Low-risk actions run automatically. Medium+ require confirmation.'}
            {prefs.delegation_mode === 'delegated' && 'Delegated: MyndLens acts on your behalf. High-risk actions still require your approval.'}
          </Text>
        </Section>

        {/* ─── 4. PRIVACY, SECURITY & STORAGE ─────────────────────────────── */}
        <Section title="🔒  Privacy, Security & Storage">
          <SegmentRow
            label="Data Residency"
            options={[
              { key: 'on_device', label: 'On-Device Only' },
              { key: 'cloud_backup', label: 'Cloud Backup' },
            ]}
            value={prefs.data_residency}
            onChange={v => update({ data_residency: v as UserSettings['data_residency'] })}
          />

          <CheckRow
            label="Pause Digital Self learning"
            sub="Stop ingesting new signals. Existing data is preserved."
            value={prefs.ds_paused}
            onChange={() => handlePauseDS()}
          />

          <View style={s.divider} />
          <ActionBtn label="Reset preferences to defaults" onPress={handleResetPrefs} />
          <ActionBtn label="View Digital Self" onPress={() => router.push('/persona' as any)} />
          <ActionBtn label="Delete Digital Self" onPress={handleDeleteDS} destructive />
        </Section>

        {/* ─── 5. NOTIFICATIONS & VOICE ───────────────────────────────────── */}
        <Section title="🔔  Notifications & Voice">
          <SegmentRow
            label="Notification Mode"
            options={[
              { key: 'proactive', label: 'Proactive' },
              { key: 'silent', label: 'Silent' },
              { key: 'escalation', label: 'Escalation Only' },
            ]}
            value={prefs.notification_mode}
            onChange={v => update({ notification_mode: v as UserSettings['notification_mode'] })}
          />
          <SegmentRow
            label="Voice Verbosity"
            options={[
              { key: 'low', label: 'Concise' },
              { key: 'medium', label: 'Normal' },
              { key: 'high', label: 'Detailed' },
            ]}
            value={prefs.voice_verbosity}
            onChange={v => update({ voice_verbosity: v as UserSettings['voice_verbosity'] })}
          />
        </Section>

        {/* ─── ASSISTANT NICKNAME ─────────────────────────────────────────── */}
        <Section title="🤖  Assistant">
          <Text style={s.rowLabel}>Nickname</Text>
          <View style={s.nickRow}>
            <TextInput
              style={s.nickInput}
              value={nickname}
              onChangeText={setNickname}
              placeholder="MyndLens"
              placeholderTextColor="#555"
              returnKeyType="done"
              onSubmitEditing={saveNickname}
            />
            <TouchableOpacity style={s.nickSave} onPress={saveNickname}>
              <Text style={s.nickSaveText}>{nickSaved ? '✓ Saved' : 'Save'}</Text>
            </TouchableOpacity>
          </View>
        </Section>

        {/* ─── ACCOUNT ────────────────────────────────────────────────────── */}
        <Section title="👤  Account">
          <ActionBtn label="Sign Out" onPress={handleSignOut} destructive />
        </Section>

      </ScrollView>
    </View>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0A0A14' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingBottom: 12,
    borderBottomWidth: 1, borderBottomColor: '#1A1A2E',
  },
  back: { color: '#6C5CE7', fontSize: 17, width: 44 },
  title: { color: '#fff', fontSize: 18, fontWeight: '600' },
  scroll: { paddingHorizontal: 16, paddingTop: 16 },

  section: {
    backgroundColor: '#111122', borderRadius: 14, padding: 16,
    marginBottom: 16,
  },
  sectionTitle: {
    color: '#fff', fontSize: 15, fontWeight: '700', marginBottom: 14,
  },
  subHeading: {
    color: '#6C5CE7', fontSize: 11, fontWeight: '700', letterSpacing: 0.8,
    textTransform: 'uppercase', marginTop: 14, marginBottom: 6,
  },
  principle: {
    color: '#555568', fontSize: 12, fontStyle: 'italic', marginBottom: 8, lineHeight: 18,
  },
  disclosure: {
    color: '#444', fontSize: 11, marginTop: 4, marginBottom: 4,
  },

  row: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingVertical: 8, gap: 12,
  },
  rowText: { flex: 1 },
  rowLabel: { color: '#E0E0E0', fontSize: 14 },
  rowSub: { color: '#666', fontSize: 12, marginTop: 2, lineHeight: 16 },

  segmentBlock: { marginTop: 4, marginBottom: 8 },
  segmentRow: { flexDirection: 'row', gap: 6, marginTop: 8 },
  segBtn: {
    flex: 1, paddingVertical: 7, borderRadius: 8,
    backgroundColor: '#1A1A2E', alignItems: 'center',
  },
  segBtnActive: { backgroundColor: '#6C5CE7' },
  segBtnText: { color: '#888', fontSize: 12, fontWeight: '500' },
  segBtnTextActive: { color: '#fff' },

  delegationHint: {
    color: '#555568', fontSize: 12, fontStyle: 'italic',
    marginTop: 6, lineHeight: 18,
  },

  divider: { height: 1, backgroundColor: '#1A1A2E', marginVertical: 10 },

  actionBtn: {
    backgroundColor: '#1A1A2E', borderRadius: 10, padding: 12,
    alignItems: 'center', marginTop: 8,
  },
  actionBtnDestructive: { borderWidth: 1, borderColor: '#E74C3C', backgroundColor: 'transparent' },
  actionBtnText: { color: '#6C5CE7', fontSize: 14, fontWeight: '600' },
  actionBtnTextDestructive: { color: '#E74C3C' },

  nickRow: { flexDirection: 'row', gap: 8, marginTop: 8 },
  nickInput: {
    flex: 1, backgroundColor: '#1A1A2E', borderRadius: 10, padding: 10,
    color: '#fff', fontSize: 15,
  },
  nickSave: {
    backgroundColor: '#6C5CE7', borderRadius: 10, paddingHorizontal: 14,
    justifyContent: 'center',
  },
  nickSaveText: { color: '#fff', fontSize: 13, fontWeight: '600' },
});
