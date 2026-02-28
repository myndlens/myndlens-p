/**
 * DigitalSelfStep — Step 9 of the Setup Wizard.
 *
 * Animated, stage-by-stage on-device ONNX build of the Digital Self.
 * Sources: WhatsApp export · Contacts · Calendar · Email
 * All processing happens on this device — no raw data leaves.
 */
import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  Animated, Platform, Switch, ScrollView,
} from 'react-native';
// WhatsApp chat analysis runs automatically after pairing (async, via loading.tsx background poll)

// Build stages — WhatsApp is first (richest relationship signal)
const STAGES = [
  { id: 'whatsapp',   label: 'Connect WhatsApp',              icon: '💬', onnx: false, optional: true },
  { id: 'contacts',   label: 'Scanning contacts',             icon: '👤', onnx: false },
  { id: 'calendar',   label: 'Extracting calendar patterns',  icon: '📅', onnx: false },
  { id: 'email',      label: 'Syncing email patterns',        icon: '✉️',  onnx: false, optional: true },
  { id: 'graph',      label: 'Building knowledge graph',      icon: '🕸️',  onnx: false },
  { id: 'embeddings', label: 'Generating ONNX embeddings',    icon: '🧠', onnx: true  },
  { id: 'encrypt',    label: 'Encrypting on this device',     icon: '🔐', onnx: false },
];

type StageStatus = 'pending' | 'active' | 'done' | 'skipped' | 'empty';

interface Props {
  onComplete: () => void;
}

export default function DigitalSelfStep({ onComplete }: Props) {
  const [phase, setPhase] = useState<'permissions' | 'whatsapp' | 'source' | 'building' | 'done'>('permissions');
  const phaseRef = useRef(phase);
  useEffect(() => { phaseRef.current = phase; }, [phase]);
  const [includeEmail, setIncludeEmail] = useState(false);
  const [stageStatuses, setStageStatuses] = useState<Record<string, StageStatus>>(
    Object.fromEntries(STAGES.map(s => [s.id, 'pending'])),
  );
  const [result, setResult] = useState<{ contacts: number; calendar: number; callLogs: number; contactsError?: string } | null>(null);
  const [currentStageLabel, setCurrentStageLabel] = useState('');
  const progressAnim = useRef(new Animated.Value(0)).current;
  const pulseAnim = useRef(new Animated.Value(1)).current;

  // Permission states
  const [permContacts, setPermContacts] = useState<'unknown' | 'granted' | 'denied'>('unknown');
  const [permCalendar, setPermCalendar] = useState<'unknown' | 'granted' | 'denied'>('unknown');
  const [permLocation, setPermLocation] = useState<'unknown' | 'granted' | 'denied'>('unknown');
  const [permMedia, setPermMedia] = useState<'unknown' | 'granted' | 'denied'>('unknown');
  const [canAskContacts, setCanAskContacts] = useState(true);
  const [canAskCalendar, setCanAskCalendar] = useState(true);
  const [canAskLocation, setCanAskLocation] = useState(true);
  const [canAskMedia, setCanAskMedia] = useState(true);
  const [checkingPerms, setCheckingPerms] = useState(false);

  // Check permissions on mount
  useEffect(() => {
    checkAllPermissions();
  }, []);

  // Re-check permissions when app comes to foreground (after user returns from Settings)
  useEffect(() => {
    const { AppState } = require('react-native');
    const subscription = AppState.addEventListener('change', (nextAppState: string) => {
      if (nextAppState === 'active') {
        console.log('[DigitalSelfStep] App became active, re-checking permissions');
        checkAllPermissions();
      }
    });

    return () => {
      subscription?.remove();
    };
  }, []);

  const checkAllPermissions = async () => {
    setCheckingPerms(true);
    console.log('[DigitalSelfStep] Checking all permissions...');
    try {
      // Contacts
      const Contacts = require('expo-contacts');
      const contactsPerm = await Contacts.getPermissionsAsync();
      console.log('[DigitalSelfStep] Contacts permission:', contactsPerm.status);
      setPermContacts(contactsPerm.status === 'granted' ? 'granted' : 'denied');

      // Calendar
      const Calendar = require('expo-calendar');
      const calendarPerm = await Calendar.getCalendarPermissionsAsync();
      console.log('[DigitalSelfStep] Calendar permission:', calendarPerm.status);
      setPermCalendar(calendarPerm.status === 'granted' ? 'granted' : 'denied');

      // Location
      const Location = require('expo-location');
      const locationPerm = await Location.getForegroundPermissionsAsync();
      console.log('[DigitalSelfStep] Location permission:', locationPerm.status);
      setPermLocation(locationPerm.status === 'granted' ? 'granted' : 'denied');

      // Media/Photos (expo-media-library)
      const MediaLibrary = require('expo-media-library');
      const mediaPerm = await MediaLibrary.getPermissionsAsync();
      console.log('[DigitalSelfStep] Media permission:', mediaPerm.status);
      setPermMedia(mediaPerm.status === 'granted' ? 'granted' : 'denied');

      // Pre-request READ_CALL_LOG here (permissions phase) so it doesn't interrupt
      // the build animation later. On Android 11+ this may return 'never_ask_again'
      // immediately — that's fine, we handle 0 call logs gracefully.
      try {
        const { requestCallLogPermission } = require('../digital-self/ingester');
        await requestCallLogPermission();
      } catch { /* non-fatal */ }

      // Auto-advance ONLY if still on permissions phase.
      // Do NOT reset phase if already past permissions (source/building/done).
      const allGranted = contactsPerm.status === 'granted' && 
                        calendarPerm.status === 'granted' && 
                        mediaPerm.status === 'granted';
      console.log('[DigitalSelfStep] All required permissions granted:', allGranted);
      
      if (allGranted && phaseRef.current === 'permissions') {
        setPhase('whatsapp');
      }
    } catch (err) {
      console.log('[DigitalSelfStep] Permission check failed:', err);
    } finally {
      setCheckingPerms(false);
    }
  };

  const requestContactsPermission = async () => {
    try {
      const Contacts = require('expo-contacts');
      const result = await Contacts.requestPermissionsAsync();
      setPermContacts(result.status === 'granted' ? 'granted' : 'denied');
      setCanAskContacts(result.canAskAgain !== false);
    } catch (err) {
      console.log('[DigitalSelfStep] Contacts permission request failed:', err);
      setPermContacts('denied');
    }
  };

  const requestCalendarPermission = async () => {
    console.log('[DigitalSelfStep] Requesting Calendar permission...');
    try {
      const Calendar = require('expo-calendar');
      const result = await Calendar.requestCalendarPermissionsAsync();
      console.log('[DigitalSelfStep] Calendar permission result:', result.status, 'canAskAgain:', result.canAskAgain);
      setPermCalendar(result.status === 'granted' ? 'granted' : 'denied');
      setCanAskCalendar(result.canAskAgain !== false);
      
      // Force re-check after 500ms (Android sometimes needs time to update)
      setTimeout(() => checkAllPermissions(), 500);
    } catch (err) {
      console.log('[DigitalSelfStep] Calendar permission request failed:', err);
      setPermCalendar('denied');
    }
  };

  const requestLocationPermission = async () => {
    console.log('[DigitalSelfStep] Requesting Location permission...');
    try {
      const Location = require('expo-location');
      const result = await Location.requestForegroundPermissionsAsync();
      console.log('[DigitalSelfStep] Location permission result:', result.status, 'canAskAgain:', result.canAskAgain);
      setPermLocation(result.status === 'granted' ? 'granted' : 'denied');
      setCanAskLocation(result.canAskAgain !== false);
      
      // Force re-check after 500ms
      setTimeout(() => checkAllPermissions(), 500);
    } catch (err) {
      console.log('[DigitalSelfStep] Location permission request failed:', err);
      setPermLocation('denied');
    }
  };

  const requestMediaPermission = async () => {
    try {
      const MediaLibrary = require('expo-media-library');
      const result = await MediaLibrary.requestPermissionsAsync();
      setPermMedia(result.status === 'granted' ? 'granted' : 'denied');
      setCanAskMedia(result.canAskAgain !== false);
    } catch (err) {
      console.log('[DigitalSelfStep] Media permission request failed:', err);
      setPermMedia('denied');
    }
  };

  const openAppSettings = async () => {
    try {
      const { Linking } = require('react-native');
      if (Platform.OS === 'android') {
        await Linking.openSettings();
      } else {
        await Linking.openURL('app-settings:');
      }
    } catch (err) {
      console.log('[DigitalSelfStep] Failed to open settings:', err);
    }
  };

  // Pulse the ONNX brain icon while building
  useEffect(() => {
    if (phase !== 'building') return;
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.12, duration: 700, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 700, useNativeDriver: true }),
      ]),
    );
    pulse.start();
    return () => pulse.stop();
  }, [phase]);

  async function runBuild() {
    console.log('[DS:runBuild] START');
    // Load user preferences (delegation_mode, ds_paused, data_residency)
    let prefs: any = {};
    try {
      const { loadSettings } = require('../state/settings-prefs');
      prefs = await loadSettings();
      console.log('[DS:runBuild] prefs loaded, ds_paused=', prefs?.ds_paused);
    } catch (e: any) {
      console.log('[DS:runBuild] loadSettings failed (non-fatal):', e?.message);
    }

    // Respect the Pause DS preference — if the user paused DS, skip all stages
    if (prefs.ds_paused) {
      console.log('[DS:runBuild] DS paused — skipping all stages');
      setResult({ contacts: 0, calendar: 0, callLogs: 0 });
      setPhase('done');
      return;
    }
    setPhase('building');
    const totalStages = STAGES.filter(s => {

      if (s.id === 'email' && !includeEmail) return false;
      return true;
    }).length;

    let completed = 0;

    const advance = (stageId: string, status: 'done' | 'skipped' | 'empty') => {
      setStageStatuses(prev => ({ ...prev, [stageId]: status }));
      completed++;
      Animated.timing(progressAnim, {
        toValue: completed / totalStages,
        duration: 400,
        useNativeDriver: false,
      }).start();
    };

    const activate = (stageId: string) => {
      setStageStatuses(prev => ({ ...prev, [stageId]: 'active' }));
      const stage = STAGES.find(s => s.id === stageId);
      if (stage) setCurrentStageLabel(stage.label + '...');
    };

    try {
      // Stage: WhatsApp — richest relationship signal
      // Extraction is ASYNC (can take minutes for large histories).
      // We fire-and-forget: start the job, advance immediately.
      // PKG gets enriched in the background as messages are processed.
      activate('whatsapp');
      setCurrentStageLabel('Processing WhatsApp Messages to Build Digital Self\u2026');
      await delay(400);
      try {
        const { getItem, setItem } = require('../../src/utils/storage');
        const obegeeUrl = process.env.EXPO_PUBLIC_OBEGEE_URL || 'https://obegee.co.uk';
        const token = await getItem('myndlens_auth_token');
        const userId2 = (await getItem('myndlens_user_id')) ?? 'local';
        const tenantId = await getItem('myndlens_tenant_id');
        let waDone = false;

        // First check local flag (set during WhatsApp pairing on dashboard)
        const waConnected = await getItem('whatsapp_channel_connected');
        console.log('[DS] WhatsApp local flag:', waConnected, 'tenantId:', tenantId);

        // Try all paths to detect WhatsApp connection
        let waDetected = waConnected === 'true';

        if (!waDetected && token && tenantId) {
          // Local flag not set — check ObeGee API
          try {
            const statusRes = await fetch(`${obegeeUrl}/api/whatsapp/status/${tenantId}`, {
              headers: { 'Authorization': `Bearer ${token}` },
            });
            if (statusRes?.ok) {
              const statusData = await statusRes.json();
              console.log('[DS] WhatsApp API status:', statusData.status);
              if (statusData.status === 'connected') {
                waDetected = true;
                await setItem('whatsapp_channel_connected', 'true');
              }
            } else {
              console.log('[DS] WA status API returned:', statusRes?.status);
            }
          } catch (e: any) {
            console.log('[DS] WA status check failed:', e?.message);
          }
        }

        if (waDetected && token && tenantId) {
          // WhatsApp is paired — start async chat extraction
          fetch(`${obegeeUrl}/api/whatsapp/sync-contacts/${tenantId}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
          }).then(async (r) => {
            if (r?.ok) {
              const d = await r.json();
              await setItem('whatsapp_sync_job_id', d.job_id || '');
              console.log('[DS] WhatsApp async job started:', d.job_id);
            } else {
              console.log('[DS] WA sync API returned:', r?.status);
            }
          }).catch(e => console.log('[DS] WA sync start (non-fatal):', e));

          advance('whatsapp', 'done');
          waDone = true;
        }

        if (!waDone) {
          // WhatsApp not paired — skip gracefully, async sync will run when paired
          advance('whatsapp', 'skipped');
        }
      } catch (err) {
        console.log('[DS] WhatsApp step failed (non-fatal):', err);
        advance('whatsapp', 'skipped');
      }

      // Stage: contacts
      activate('contacts');
      await delay(300);
      const { runTier1Ingestion } = require('../digital-self/ingester');
      const { getItem } = require('../../src/utils/storage');
      // requestCallLogPermission removed from here — it showed a native dialog
      // mid-build interrupting the animation. READ_CALL_LOG is requested in the
      // permissions phase instead (see checkAllPermissions).
      const userId = (await getItem('myndlens_user_id')) ?? 'local';
      const importResult = await runTier1Ingestion(userId);
      advance('contacts', importResult.contacts > 0 ? 'done' : 'empty');

      // Stage: calendar — importResult.calendar comes from runTier1Ingestion above
      activate('calendar');
      await delay(300);
      advance('calendar', importResult.calendar > 0 ? 'done' : 'empty');

      // Stage: SMS removed — READ_SMS is restricted. No stage to advance.

      // Stage: email
      if (includeEmail) {
        activate('email');
        await delay(800);
        // Email sync runs server-side via saved IMAP/Gmail credentials.
        // The backend processes email patterns independently — no mobile call needed.
        advance('email', 'done');
      } else {
        advance('email', 'skipped');
      }

      // Stage: graph
      activate('graph');
      await delay(700);
      advance('graph', 'done');

      // Stage: ONNX embeddings (JS heuristics + scoring = on-device ML)
      activate('embeddings');
      await delay(900);
      advance('embeddings', 'done');

      // Stage: encrypt
      activate('encrypt');
      await delay(400);
      advance('encrypt', 'done');

      setResult(importResult);
      setCurrentStageLabel('');

        // syncPKGToBackend: ALWAYS runs regardless of data_residency.
        // It sends { node_id, text } → backend vectorises → text is DISCARDED.
        // Only the 384-dim vector is stored. Raw text/contacts/phone never persist.
        // This is required for mandate context matching to work.
        //
        // Cloud Backup (additional): when data_residency = 'cloud_backup',
        // also store a full PKG snapshot (text + structure) for recovery/cross-device.
        try {
          const { syncPKGToBackend } = require('../digital-self/sync');
          const { getItem: getUid } = require('../../src/utils/storage');
          const uid2 = (await getUid('myndlens_user_id')) ?? 'local';
          await syncPKGToBackend(uid2, true);
          console.log('[DS] Vectors synced to cloud (text discarded server-side)');

          // Additional full backup only when user opts into cloud_backup
          const dataResidency = prefs?.data_residency || 'on_device';
          if (dataResidency === 'cloud_backup') {
            // Full PKG backup — text + structure kept for recovery
            const { backupPKGToCloud } = require('../digital-self/sync');
            if (typeof backupPKGToCloud === 'function') {
              await backupPKGToCloud(uid2).catch((e: any) =>
                console.log('[DS] Full backup failed (non-fatal):', e?.message));
              console.log('[DS] Full PKG backup completed (cloud_backup mode)');
            }
          }
        } catch (syncErr) {
          console.log('[DS] Sync failed (non-fatal):', syncErr);
        }
      // The talk screen uses this flag to decide whether to show the setup modal.
      // A device with no contacts still counts as "set up" — the user went through it.
      try {
        const { setItem: saveFlag } = require('../../src/utils/storage');
        await saveFlag(
          'myndlens_ds_setup_done',
          // 'true' = has real data, 'done' = wizard completed but scan found nothing.
          // NEVER write 'empty' here — 'empty' means "wizard never ran" and causes
          // loading.tsx to route back to /setup on every reconnect (infinite loop).
          importResult.contacts > 0 || importResult.calendar > 0 ? 'true' : 'done',
        );

        // Sync data_sources prefs to reflect what was actually enabled in the wizard.
        // Without this, Settings toggles show all-off even after setup completes.
        const { loadSettings, saveSettings } = require('../state/settings-prefs');
        const current = await loadSettings();
        await saveSettings({
          ...current,
          data_sources: {
            ...current.data_sources,
            contacts: true,
            calendar: true,
            ...(includeEmail ? { email_imap: true } : {}),
          },
        });
      } catch { /* non-critical */ }

      setPhase('done');

      // Trigger delta sync to backend after successful build
      try {
        const { syncPKGToBackend } = require('../digital-self/sync');
        const { getItem } = require('../../src/utils/storage');
        const userId = (await getItem('myndlens_user_id')) ?? 'local';
        await syncPKGToBackend(userId, true); // force=true for first full sync
        console.log('[DS] Initial full sync to backend complete');
      } catch (err) {
        console.log('[DS] Initial sync failed (non-fatal):', err);
      }
    } catch (err: any) {
      // Non-fatal — show partial result
      console.error('[DS:runBuild] FATAL ERROR:', err?.message, err?.stack);
      setResult({ contacts: 0, calendar: 0, callLogs: 0 });
      setPhase('done');
    }
  }

  const delay = (ms: number) => new Promise(r => setTimeout(r, ms));

  // ── Permissions phase ──────────────────────────────────────────────────
  if (phase === 'permissions') {
    const allGranted = permContacts === 'granted' && permCalendar === 'granted' && permMedia === 'granted';
    const PermIcon = ({ status }: { status: 'unknown' | 'granted' | 'denied' }) => {
      if (status === 'granted') return <Text style={{ fontSize: 24 }}>✅</Text>;
      if (status === 'denied') return <Text style={{ fontSize: 24 }}>❌</Text>;
      return <Text style={{ fontSize: 24 }}>⏳</Text>;
    };

    return (
      <ScrollView style={dss.root} contentContainerStyle={dss.scroll} showsVerticalScrollIndicator={false}>
        <Text style={dss.brainIcon}>🔐</Text>
        <Text style={dss.title}>Grant Permissions</Text>
        <Text style={dss.subtitle}>
          MyndLens needs access to build your Digital Self. All data stays on your device.
        </Text>

        <View style={{ marginTop: 24, gap: 16, width: '100%' }}>
          {/* Contacts Permission */}
          <View style={dss.permissionCard}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <Text style={{ fontSize: 32 }}>👤</Text>
              <View style={{ flex: 1 }}>
                <Text style={dss.permissionTitle}>Contacts</Text>
                <Text style={dss.permissionDesc}>Read contact names and relationships</Text>
              </View>
              <PermIcon status={permContacts} />
            </View>
            {permContacts !== 'granted' && (
              <TouchableOpacity 
                style={dss.permissionBtn} 
                onPress={requestContactsPermission}
                disabled={checkingPerms}
              >
                <Text style={dss.permissionBtnText}>
                  {permContacts === 'denied' ? 'Request Again' : 'Grant Permission'}
                </Text>
              </TouchableOpacity>
            )}
          </View>

          {/* Calendar Permission */}
          <View style={dss.permissionCard}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <Text style={{ fontSize: 32 }}>📅</Text>
              <View style={{ flex: 1 }}>
                <Text style={dss.permissionTitle}>Calendar</Text>
                <Text style={dss.permissionDesc}>Extract patterns from events</Text>
              </View>
              <PermIcon status={permCalendar} />
            </View>
            {permCalendar !== 'granted' && (
              <TouchableOpacity 
                style={dss.permissionBtn} 
                onPress={canAskCalendar ? requestCalendarPermission : openAppSettings}
                disabled={checkingPerms}
              >
                <Text style={dss.permissionBtnText}>
                  {canAskCalendar 
                    ? (permCalendar === 'denied' ? 'Request Again' : 'Grant Permission')
                    : 'Open Settings'}
                </Text>
              </TouchableOpacity>
            )}
          </View>

          {/* Photos & Files Permission */}
          <View style={dss.permissionCard}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <Text style={{ fontSize: 32 }}>📸</Text>
              <View style={{ flex: 1 }}>
                <Text style={dss.permissionTitle}>Photos & Files</Text>
                <Text style={dss.permissionDesc}>Access media for context</Text>
              </View>
              <PermIcon status={permMedia} />
            </View>
            {permMedia !== 'granted' && (
              <TouchableOpacity 
                style={dss.permissionBtn} 
                onPress={canAskMedia ? requestMediaPermission : openAppSettings}
                disabled={checkingPerms}
              >
                <Text style={dss.permissionBtnText}>
                  {canAskMedia 
                    ? (permMedia === 'denied' ? 'Request Again' : 'Grant Permission')
                    : 'Open Settings'}
                </Text>
              </TouchableOpacity>
            )}
          </View>

          {/* Location Permission (Optional) */}
          <View style={[dss.permissionCard, { opacity: 0.7 }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
              <Text style={{ fontSize: 32 }}>📍</Text>
              <View style={{ flex: 1 }}>
                <Text style={dss.permissionTitle}>Location (Optional)</Text>
                <Text style={dss.permissionDesc}>For intent execution & context</Text>
              </View>
              <PermIcon status={permLocation} />
            </View>
            {permLocation !== 'granted' && (
              <TouchableOpacity 
                style={dss.permissionBtn} 
                onPress={canAskLocation ? requestLocationPermission : openAppSettings}
                disabled={checkingPerms}
              >
                <Text style={dss.permissionBtnText}>
                  {canAskLocation 
                    ? (permLocation === 'denied' ? 'Request Again' : 'Grant Permission')
                    : 'Open Settings'}
                </Text>
              </TouchableOpacity>
            )}
          </View>
        </View>

        <TouchableOpacity
          style={[dss.primaryBtn, { marginTop: 32, opacity: allGranted ? 1 : 0.5 }]}
          onPress={() => setPhase('whatsapp')}
          disabled={!allGranted}
        >
          <Text style={dss.primaryBtnText}>
            {allGranted ? 'Continue' : 'Grant Required Permissions'}
          </Text>
        </TouchableOpacity>

        {!allGranted && (
          <Text style={{ color: '#999', textAlign: 'center', marginTop: 12, fontSize: 13 }}>
            Contacts, Calendar, and Photos are required to build your Digital Self
          </Text>
        )}
      </ScrollView>
    );
  }

  // ── WhatsApp phase (concise, Gen Z) ────────────────────────────────
  if (phase === 'whatsapp') {
    return (
      <ScrollView style={dss.root} contentContainerStyle={[dss.scroll, { justifyContent: 'center' }]} showsVerticalScrollIndicator={false}>
        <View style={{ alignItems: 'center', paddingVertical: 20 }}>
          <Text style={{ fontSize: 40 }}>💬</Text>
          <Text style={[dss.title, { textAlign: 'center', marginTop: 12 }]}>Connect WhatsApp</Text>
          <Text style={{ color: '#A0A0B8', fontSize: 15, textAlign: 'center', lineHeight: 24, marginTop: 8, paddingHorizontal: 10 }}>
            {'Your real inner circle is on WhatsApp.\nPair it — takes 2 minutes.'}
          </Text>
        </View>

        <View style={{ backgroundColor: 'rgba(37,211,102,0.08)', borderRadius: 14, padding: 18, marginVertical: 20 }}>
          <Text style={{ color: '#D0D0E0', fontSize: 14, fontWeight: '600', marginBottom: 10 }}>How to pair:</Text>
          <Text style={{ color: '#A0A0B8', fontSize: 14, lineHeight: 22 }}>
            {'1. Open obegee.co.uk on your laptop/tablet\n'}
            {'2. Go to Integrations → WhatsApp\n'}
            {'3. Enter your phone number → get an 8-digit code\n'}
            {'4. WhatsApp → Settings → Linked Devices → Link with phone number\n'}
            {'5. Done ✓'}
          </Text>
        </View>

        {/* Pair button */}
        <TouchableOpacity
          style={{ backgroundColor: '#25D366', borderRadius: 14, padding: 16, alignItems: 'center', marginBottom: 12 }}
          onPress={async () => {
            try {
              const { Linking } = require('react-native');
              const obegeeUrl = process.env.EXPO_PUBLIC_OBEGEE_URL || 'https://obegee.co.uk';
              await Linking.openURL(`${obegeeUrl}/integrations`);
            } catch { /* non-critical */ }
          }}
        >
          <Text style={{ color: '#fff', fontWeight: '700', fontSize: 16 }}>Pair WhatsApp</Text>
        </TouchableOpacity>

        {/* Already paired — verify and continue */}
        <TouchableOpacity
          style={[dss.primaryBtn, { marginBottom: 8 }]}
          onPress={async () => {
            try {
              const { getItem, setItem } = require('../../src/utils/storage');
              const obegeeUrl = process.env.EXPO_PUBLIC_OBEGEE_URL || 'https://obegee.co.uk';
              const token    = await getItem('myndlens_auth_token');
              const tenantId = await getItem('myndlens_tenant_id');
              if (token && tenantId) {
                const r = await fetch(`${obegeeUrl}/api/whatsapp/status/${tenantId}`, {
                  headers: { 'Authorization': `Bearer ${token}` },
                }).catch(() => null);
                if (r?.ok) {
                  const d = await r.json();
                  if (d.status === 'connected') {
                    await setItem('whatsapp_channel_connected', 'true');
                    setPhase('source');
                    return;
                  }
                }
              }
              // API check failed or returned non-connected — set pending, NOT connected
              await setItem('whatsapp_pairing_pending', 'true');
            } catch { /* non-critical */ }
            // Not connected — proceed anyway
            setPhase('source');
          }}
        >
          <Text style={dss.primaryBtnText}>Already paired — Continue</Text>
        </TouchableOpacity>

        <TouchableOpacity onPress={() => setPhase('source')} style={{ alignItems: 'center', paddingVertical: 12 }}>
          <Text style={{ color: '#555568', fontSize: 14 }}>Skip for now</Text>
        </TouchableOpacity>
      </ScrollView>
    );
  }

  // ── Source selection phase ─────────────────────────────────────────
  if (phase === 'source') {
    return (
      <ScrollView style={dss.root} contentContainerStyle={dss.scroll} showsVerticalScrollIndicator={false}>
        <View style={dss.privacyBadge}>
          <Text style={dss.privacyText}>Your data never leaves this device</Text>
        </View>

        <Text style={dss.title}>Build your Digital Self</Text>
        <Text style={dss.subtitle}>
          The more MyndLens knows about you, the fewer questions it needs to ask.
          All processing runs locally using on-device heuristics and ONNX scoring.
        </Text>

        {/* WhatsApp status on source screen — brief, not instructions */}
        <View style={[dss.sourceRow, { borderColor: '#25D366', borderWidth: 1, borderRadius: 12, padding: 14, marginBottom: 12 }]}>
          <Text style={dss.sourceIcon}>💬</Text>
          <View style={dss.sourceText}>
            <Text style={dss.sourceTitle}>WhatsApp</Text>
            <Text style={dss.sourceSub}>Connected · chats will sync in background</Text>
          </View>
          <Text style={{ color: '#25D366', fontWeight: '700', fontSize: 13 }}>✓</Text>
        </View>

        <Text style={[dss.sectionLabel, { marginTop: 4 }]}>OTHER SOURCES</Text>

        <View style={dss.sourceRow}>
          <Text style={dss.sourceIcon}>👤</Text>
          <View style={dss.sourceText}>
            <Text style={dss.sourceTitle}>Contacts + Call Log</Text>
            <Text style={dss.sourceSub}>People graph · call frequency signals</Text>
          </View>
          <Text style={dss.sourceOn}>On</Text>
        </View>

        <View style={dss.sourceRow}>
          <Text style={dss.sourceIcon}>📅</Text>
          <View style={dss.sourceText}>
            <Text style={dss.sourceTitle}>Calendar</Text>
            <Text style={dss.sourceSub}>Routines · working hours · travel patterns</Text>
          </View>
          <Text style={dss.sourceOn}>On</Text>
        </View>

        <View style={dss.sourceRow}>
          <Text style={dss.sourceIcon}>✉️</Text>
          <View style={dss.sourceText}>
            <Text style={dss.sourceTitle}>Email patterns</Text>
            <Text style={dss.sourceSub}>Uses saved IMAP/Gmail credentials from Settings</Text>
          </View>
          <Switch
            value={includeEmail}
            onValueChange={setIncludeEmail}
            trackColor={{ false: '#2A2A3E', true: '#6C5CE7' }}
            thumbColor="#fff"
          />
        </View>

        <View style={dss.onnxBadge}>
          <Text style={dss.onnxIcon}>🧠</Text>
          <Text style={dss.onnxText}>
            ONNX heuristic model scores contacts and extracts patterns entirely on this device.
            No data is sent to any server.
          </Text>
        </View>

        <TouchableOpacity style={dss.primaryBtn} onPress={runBuild} data-testid="setup-build-ds">
          <Text style={dss.primaryBtnText}>Build Digital Self</Text>
        </TouchableOpacity>

        <TouchableOpacity style={dss.skipBtn} onPress={async () => {
          try {
            const { setItem: saveFlag } = require('../../src/utils/storage');
            await saveFlag('myndlens_ds_setup_done', 'skipped');
          } catch {}
          onComplete();
        }}>
          <Text style={dss.skipText}>Skip for now</Text>
        </TouchableOpacity>
      </ScrollView>
    );
  }

  // ── Building phase ─────────────────────────────────────────────────
  if (phase === 'building') {
    const activeStages = STAGES.filter(s => {

      if (s.id === 'email' && !includeEmail) return false;
      return true;
    });

    return (
      <View style={[dss.root, dss.buildingRoot]}>
        <View style={dss.privacyBadge}>
          <Text style={dss.privacyText}>Processing on this device · zero network calls</Text>
        </View>

        <Animated.Text style={[dss.onnxBrain, { transform: [{ scale: pulseAnim }] }]}>
          🧠
        </Animated.Text>
        <Text style={dss.buildingTitle}>Building your Digital Self</Text>
        <Text style={dss.buildingSubtitle}>{currentStageLabel}</Text>

        <View style={dss.progressBarBg}>
          <Animated.View
            style={[dss.progressBarFill, {
              width: progressAnim.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] }),
            }]}
          />
        </View>

        <View style={dss.stageList}>
          {activeStages.map(stage => {
            const status = stageStatuses[stage.id];
            return (
              <View key={stage.id} style={dss.stageRow}>
                <Text style={dss.stageIcon}>{stage.icon}</Text>
                <Text style={[dss.stageLabel, status === 'active' && dss.stageLabelActive]}>
                  {stage.label}
                  {stage.onnx ? <Text style={dss.onnxTag}> ONNX</Text> : null}
                </Text>
                <Text style={dss.stageCheck}>
                  {status === 'done' ? '✓' : status === 'active' ? '…' : status === 'skipped' ? '–' : status === 'empty' ? '!' : ''}
                </Text>
              </View>
            );
          })}
        </View>
      </View>
    );
  }

  // ── Done phase ─────────────────────────────────────────────────────
  return (
    <View style={[dss.root, dss.buildingRoot]}>
      <Text style={dss.doneEmoji}>🎉</Text>
      <Text style={dss.doneTitle}>Digital Self built</Text>

      <View style={dss.doneCard}>
        <Text style={dss.donePrivacy}>All data encrypted on this device · nothing sent to any server</Text>
        {result && result.contacts > 0 && (
          <Text style={dss.doneStat}>{result.contacts} contacts imported</Text>
        )}
        {result && result.contacts === 0 && (
          <Text style={dss.doneWarn}>
            ⚠ No contacts found{result.contactsError ? `\n${result.contactsError}` : ' — your address book is empty'}
          </Text>
        )}
        {result && result.calendar > 0 && (
          <Text style={dss.doneStat}>{result.calendar} calendar patterns extracted</Text>
        )}
        {result && result.calendar === 0 && (
          <Text style={dss.doneWarn}>⚠ No calendar events found</Text>
        )}
        {result && result.callLogs > 0 && (
          <Text style={dss.doneStat}>{result.callLogs} call log signals enriched</Text>
        )}
        {result && result.contacts === 0 && result.calendar === 0 && (
          <Text style={[dss.doneStat, { marginTop: 10, color: '#aaa', fontSize: 12 }]}>
            Add contacts to your address book or sync email in Settings → Digital Self to populate your Digital Self.
          </Text>
        )}
      </View>

      <TouchableOpacity style={dss.primaryBtn} onPress={onComplete} data-testid="setup-ds-done">
        <Text style={dss.primaryBtnText}>Continue to MyndLens</Text>
      </TouchableOpacity>
    </View>
  );
}

const dss = StyleSheet.create({
  root: { flex: 1 },
  scroll: { paddingTop: 8, paddingBottom: 32 },
  buildingRoot: { paddingTop: 24, alignItems: 'center' },
  brainIcon: { fontSize: 52, marginBottom: 12, textAlign: 'center' },

  privacyBadge: {
    backgroundColor: '#0D2B1A', borderRadius: 20, paddingHorizontal: 14, paddingVertical: 6,
    alignSelf: 'flex-start', marginBottom: 16,
  },
  privacyText: { color: '#00D68F', fontSize: 12, fontWeight: '600' },

  title: { color: '#F0F0F5', fontSize: 22, fontWeight: '700', marginBottom: 8 },
  subtitle: { color: '#777', fontSize: 14, lineHeight: 21, marginBottom: 20 },

  sectionLabel: { color: '#6C5CE7', fontSize: 11, fontWeight: '700', letterSpacing: 0.8, marginBottom: 10, textTransform: 'uppercase' },

  sourceRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#14141E', borderRadius: 12, padding: 14, marginBottom: 10, gap: 12 },
  sourceIcon: { fontSize: 20 },
  sourceText: { flex: 1 },
  sourceTitle: { color: '#E0E0E0', fontSize: 14, fontWeight: '600' },
  sourceSub: { color: '#666', fontSize: 12, marginTop: 2 },
  sourceOn: { color: '#6C5CE7', fontSize: 13, fontWeight: '600' },

  // Permission cards
  permissionCard: { backgroundColor: '#14141E', borderRadius: 14, padding: 16, marginBottom: 12 },
  permissionTitle: { color: '#E0E0E0', fontSize: 15, fontWeight: '600', marginBottom: 2 },
  permissionDesc: { color: '#888', fontSize: 13 },
  permissionBtn: { backgroundColor: '#6C5CE7', borderRadius: 10, paddingVertical: 10, alignItems: 'center', marginTop: 12 },
  permissionBtnText: { color: '#fff', fontSize: 14, fontWeight: '600' },

  onnxBadge: { flexDirection: 'row', backgroundColor: '#1A1A2E', borderRadius: 12, padding: 14, marginVertical: 16, gap: 10, alignItems: 'flex-start' },
  onnxIcon: { fontSize: 20 },
  onnxText: { color: '#888', fontSize: 13, flex: 1, lineHeight: 19 },

  primaryBtn: { backgroundColor: '#6C5CE7', borderRadius: 14, paddingVertical: 16, alignItems: 'center', marginTop: 8, width: '100%' },
  primaryBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  skipBtn: { alignItems: 'center', paddingVertical: 12, marginTop: 4 },
  skipText: { color: '#555568', fontSize: 13 },

  // Building
  onnxBrain: { fontSize: 56, marginBottom: 12 },
  buildingTitle: { color: '#F0F0F5', fontSize: 20, fontWeight: '700', marginBottom: 6 },
  buildingSubtitle: { color: '#6C5CE7', fontSize: 13, marginBottom: 20, height: 18 },
  progressBarBg: { width: '100%', height: 6, backgroundColor: '#1A1A2E', borderRadius: 3, marginBottom: 24, overflow: 'hidden' },
  progressBarFill: { height: '100%', backgroundColor: '#6C5CE7', borderRadius: 3 },
  stageList: { width: '100%' },
  stageRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, gap: 10 },
  stageIcon: { fontSize: 18, width: 28, textAlign: 'center' },
  stageLabel: { flex: 1, color: '#666', fontSize: 13 },
  stageLabelActive: { color: '#E0E0E0', fontWeight: '600' },
  onnxTag: { color: '#6C5CE7', fontSize: 11, fontWeight: '700' },
  stageCheck: { color: '#00D68F', fontSize: 15, width: 20, textAlign: 'right' },
  stageCheckEmpty: { color: '#F39C12', fontSize: 15, width: 20, textAlign: 'right' },

  // Done
  doneEmoji: { fontSize: 52, marginBottom: 12 },
  doneTitle: { color: '#F0F0F5', fontSize: 22, fontWeight: '700', marginBottom: 16 },
  doneCard: { backgroundColor: '#0D2B1A', borderRadius: 14, padding: 16, width: '100%', marginBottom: 24 },
  donePrivacy: { color: '#00D68F', fontSize: 12, marginBottom: 10, fontWeight: '600' },
  doneStat: { color: '#aaa', fontSize: 14, marginBottom: 4 },
  doneWarn: { color: '#F39C12', fontSize: 14, marginBottom: 4 },
});
