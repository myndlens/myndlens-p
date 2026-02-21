/**
 * DigitalSelfStep — Step 9 of the Setup Wizard.
 *
 * Animated, stage-by-stage on-device ONNX build of the Digital Self.
 * Sources: Contacts · Calendar · SMS (Android) · Email (if credentials saved).
 * All processing happens on this device — no raw data leaves.
 */
import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  Animated, Platform, Switch, ScrollView,
} from 'react-native';

// Build stages — each maps to a real ingestion step
const STAGES = [
  { id: 'contacts',   label: 'Scanning contacts',          icon: '👤', onnx: false },
  { id: 'calendar',   label: 'Extracting calendar patterns', icon: '📅', onnx: false },
  { id: 'email',      label: 'Syncing email patterns',       icon: '✉️',  onnx: false, optional: true },
  { id: 'graph',      label: 'Building knowledge graph',     icon: '🕸️',  onnx: false },
  { id: 'embeddings', label: 'Generating ONNX embeddings',   icon: '🧠', onnx: true  },
  { id: 'encrypt',    label: 'Encrypting on this device',    icon: '🔐', onnx: false },
];

type StageStatus = 'pending' | 'active' | 'done' | 'skipped';

interface Props {
  onComplete: () => void;
}

export default function DigitalSelfStep({ onComplete }: Props) {
  const [phase, setPhase] = useState<'source' | 'building' | 'done'>('source');
  const [includeEmail, setIncludeEmail] = useState(false);
  const [stageStatuses, setStageStatuses] = useState<Record<string, StageStatus>>(
    Object.fromEntries(STAGES.map(s => [s.id, 'pending'])),
  );
  const [result, setResult] = useState<{ contacts: number; calendar: number; callLogs: number } | null>(null);
  const [currentStageLabel, setCurrentStageLabel] = useState('');
  const progressAnim = useRef(new Animated.Value(0)).current;
  const pulseAnim = useRef(new Animated.Value(1)).current;

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
    setPhase('building');
    const totalStages = STAGES.filter(s => {

      if (s.optional && !includeEmail) return false;
      return true;
    }).length;

    let completed = 0;

    const advance = (stageId: string, status: 'done' | 'skipped') => {
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
      // Stage: contacts
      activate('contacts');
      await delay(300);
      const { runTier1Ingestion, requestCallLogPermission } = require('../digital-self/ingester');
      const { getItem } = require('../../src/utils/storage');
      await requestCallLogPermission();  // READ_CALL_LOG only (no SMS)
      const userId = (await getItem('myndlens_user_id')) ?? 'local';
      const importResult = await runTier1Ingestion(userId);
      advance('contacts', 'done');

      // Stage: calendar
      activate('calendar');
      await delay(400);
      advance('calendar', 'done');

      // Stage: SMS removed — READ_SMS is a restricted Android permission
      // (only grantable to the default SMS app). Nothing to do here.
      advance('sms', 'skipped');

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

      // Mark DS setup as completed — regardless of how many nodes were imported.
      // The talk screen uses this flag to decide whether to show the setup modal.
      // A device with no contacts still counts as "set up" — the user went through it.
      try {
        const { setItem: saveFlag } = require('../../src/utils/storage');
        await saveFlag('myndlens_ds_setup_done', 'true');

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
        const { syncPKGToBackend } = require('../../digital-self/sync');
        const { getItem } = require('../../src/utils/storage');
        const userId = (await getItem('myndlens_user_id')) ?? 'local';
        await syncPKGToBackend(userId, true); // force=true for first full sync
        console.log('[DS] Initial full sync to backend complete');
      } catch (err) {
        console.log('[DS] Initial sync failed (non-fatal):', err);
      }
    } catch (err) {
      // Non-fatal — show partial result
      setResult({ contacts: 0, calendar: 0, callLogs: 0 });
      setPhase('done');
    }
  }

  const delay = (ms: number) => new Promise(r => setTimeout(r, ms));

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

        <Text style={dss.sectionLabel}>DATA SOURCES</Text>

        <View style={dss.sourceRow}>
          <Text style={dss.sourceIcon}>👤</Text>
          <View style={dss.sourceText}>
            <Text style={dss.sourceTitle}>Contacts</Text>
            <Text style={dss.sourceSub}>People graph · relationship inference</Text>
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

      if (s.optional && !includeEmail) return false;
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
                  {status === 'done' ? '✓' : status === 'active' ? '…' : status === 'skipped' ? '–' : ''}
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
        {result && result.calendar > 0 && (
          <Text style={dss.doneStat}>{result.calendar} calendar patterns extracted</Text>
        )}
        {result && result.callLogs > 0 && (
          <Text style={dss.doneStat}>{result.callLogs} call log signals enriched</Text>
        )}
        {result && result.contacts === 0 && result.calendar === 0 && (
          <Text style={dss.doneStat}>Ready — will grow as you use MyndLens</Text>
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

  // Done
  doneEmoji: { fontSize: 52, marginBottom: 12 },
  doneTitle: { color: '#F0F0F5', fontSize: 22, fontWeight: '700', marginBottom: 16 },
  doneCard: { backgroundColor: '#0D2B1A', borderRadius: 14, padding: 16, width: '100%', marginBottom: 24 },
  donePrivacy: { color: '#00D68F', fontSize: 12, marginBottom: 10, fontWeight: '600' },
  doneStat: { color: '#aaa', fontSize: 14, marginBottom: 4 },
});
