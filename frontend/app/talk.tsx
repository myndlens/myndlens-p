import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Alert,
  Platform,
  KeyboardAvoidingView,
  Keyboard,
  Image,
  ActivityIndicator,
  AppState,
  Modal,
  ScrollView,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useFocusEffect } from 'expo-router';
import { useCallback } from 'react';
import { wsClient, WSEnvelope, WSMessageType } from '../src/ws/client';
import { useSessionStore } from '../src/state/session-store';
import { useAudioStore } from '../src/audio/state-machine';
import { startRecording, stopRecording, stopAndGetAudio } from '../src/audio/recorder';
import * as TTS from '../src/tts/player';
import { buildContextCapsule } from '../src/digital-self';
import { MicIcon } from '../src/ui/icons';
import { vad } from '../src/audio/vad/local-vad';

const PIPELINE_STAGES = [
  { id: 'capture',      label: 'Intent captured',                 activeText: 'Listening\u2026' },
  { id: 'digital_self', label: 'Enriched with Digital Self',      activeText: 'Intent Processing via Your Digital Self\u2026' },
  { id: 'dimensions',   label: 'Dimensions extracted',            activeText: 'Extracting dimensions\u2026' },
  { id: 'mandate',      label: 'Mandate created',                 activeText: 'Creating mandate artefact\u2026' },
  { id: 'approval',     label: 'Oral approval received',          activeText: 'Waiting for your approval\u2026' },
  { id: 'agents',       label: 'Agents assigned',                 activeText: 'Assigning agents & skills\u2026' },
  { id: 'skills',       label: 'Skills & tools defined',          activeText: 'Defining skills & tools\u2026' },
  { id: 'auth',         label: 'Authorization granted',           activeText: 'Awaiting authorization\u2026' },
  { id: 'executing',    label: 'OpenClaw executing',              activeText: 'OpenClaw executing your intent\u2026' },
  { id: 'delivered',    label: 'Results delivered',               activeText: 'Delivering results\u2026' },
];

function getPipelineState(
  stageIndex: number, audioState: string, pendingAction: string | null, transcript: string | null,
): 'pending' | 'active' | 'done' {
  // Idle state — nothing active
  if (audioState === 'IDLE' && !pendingAction && !transcript) return 'pending';

  // Map audio states to pipeline progress
  if (audioState === 'CAPTURING') {
    if (stageIndex === 0) return 'active';
    return 'pending';
  }
  if (audioState === 'THINKING') {
    // Hold at stage 1 (digital_self) while waiting for backend pipeline_stage messages.
    // The backend emits stage 1 first (digital_self active) before stage 2 (dimensions).
    // Mapping to stage 2 here caused it to jump 1→2 before stage 1 was ever seen.
    if (stageIndex === 0) return 'done';
    if (stageIndex === 1) return 'active';
    return 'pending';
  }
  if (audioState === 'RESPONDING') {
    if (stageIndex < 4) return 'done';
    if (stageIndex === 4) return 'active';
    return 'pending';
  }
  // If pending action exists — waiting for approval
  if (pendingAction) {
    if (stageIndex < 4) return 'done';
    if (stageIndex === 4) return 'active';
    return 'pending';
  }
  // If we have a transcript but idle — first stages done
  if (transcript && audioState === 'IDLE') {
    if (stageIndex < 1) return 'done';
    if (stageIndex === 1) return 'active';
    return 'pending';
  }
  return 'pending';
}

// Waveform bar height profile — centre bar tallest (module constant, not recreated per render)
const WAVE_PROFILE = [0.55, 0.85, 1.0, 0.85, 0.55];

// ── ResultCard — routes to correct card type based on result_type ─────────────
const ResultCard = ({ msg }: { msg: { text: string; result_type?: string; structured?: Record<string, any> } }) => {
  const s = msg.structured || {};
  const rt = msg.result_type || 'generic';

  switch (rt) {
    case 'code_execution': {
      const ok = s.success !== false;
      return (
        <View>
          {s.code ? <Text style={cardStyles.codeBlock}>{s.code}</Text> : null}
          <View style={[cardStyles.badge, { backgroundColor: ok ? '#00D68F22' : '#FF444422' }]}>
            <Text style={{ color: ok ? '#00D68F' : '#FF6666', fontSize: 11, fontWeight: '700' }}>
              {ok ? '✓ Success' : '✗ Failed'}
            </Text>
          </View>
          {s.output ? <Text style={cardStyles.outputText}>{s.output}</Text> : null}
          {s.error ? <Text style={cardStyles.errorText}>{s.error}</Text> : null}
        </View>
      );
    }
    case 'travel_itinerary': {
      const legs: any[] = s.legs || [];
      const hotels: any[] = s.hotels || [];
      return (
        <View style={{ gap: 6 }}>
          {legs.map((l: any, i: number) => (
            <View key={i} style={cardStyles.travelRow}>
              <Text style={cardStyles.travelIcon}>✈️</Text>
              <Text style={cardStyles.travelText}>{l.from} → {l.to}  {l.date || ''}  {l.carrier || ''}</Text>
              {l.ref ? <Text style={cardStyles.refText}>{l.ref}</Text> : null}
            </View>
          ))}
          {hotels.map((h: any, i: number) => (
            <View key={i} style={cardStyles.travelRow}>
              <Text style={cardStyles.travelIcon}>🏨</Text>
              <Text style={cardStyles.travelText}>{h.name}  {h.checkin || ''} – {h.checkout || ''}</Text>
              {h.ref ? <Text style={cardStyles.refText}>{h.ref}</Text> : null}
            </View>
          ))}
          {s.total_cost ? <Text style={cardStyles.costText}>Total: {s.total_cost} {s.currency || ''}</Text> : null}
        </View>
      );
    }
    case 'transaction': {
      const ok = s.status === 'completed';
      return (
        <View style={{ gap: 4 }}>
          <Text style={cardStyles.txAction}>{s.action || 'Transaction'}</Text>
          {s.amount ? <Text style={cardStyles.txAmount}>{s.currency || ''} {s.amount}</Text> : null}
          <View style={[cardStyles.badge, { backgroundColor: ok ? '#00D68F22' : '#FF944422' }]}>
            <Text style={{ color: ok ? '#00D68F' : '#FF9444', fontSize: 12, fontWeight: '600' }}>
              {s.status || 'unknown'}
            </Text>
          </View>
          {s.reference ? <Text style={cardStyles.refText}>Ref: {s.reference}</Text> : null}
        </View>
      );
    }
    case 'creative_output': {
      return (
        <View style={{ gap: 4 }}>
          {s.title ? <Text style={cardStyles.creativeTitle}>{s.title}</Text> : null}
          <Text style={cardStyles.creativeType}>{s.content_type || 'content'}</Text>
          {s.content ? <Text style={cardStyles.creativeContent}>{s.content}</Text> : null}
          {s.url ? <Text style={cardStyles.linkText}>{s.url}</Text> : null}
        </View>
      );
    }
    case 'data_report': {
      const insights: string[] = s.insights || [];
      return (
        <View style={{ gap: 4 }}>
          {s.summary ? <Text style={cardStyles.reportSummary}>{s.summary}</Text> : null}
          {insights.map((ins: string, i: number) => (
            <Text key={i} style={cardStyles.insightText}>• {ins}</Text>
          ))}
        </View>
      );
    }
    default:
      return <Text style={{ color: '#C0E0D0', fontSize: 14, lineHeight: 20 }}>{msg.text}</Text>;
  }
};

const cardStyles = StyleSheet.create({
  codeBlock:      { fontFamily: 'monospace', fontSize: 12, color: '#A8FF78', backgroundColor: '#0A1A0A', padding: 8, borderRadius: 6, marginBottom: 6 },
  outputText:     { fontFamily: 'monospace', fontSize: 12, color: '#E0F0E0', marginTop: 4 },
  errorText:      { fontFamily: 'monospace', fontSize: 12, color: '#FF8888', marginTop: 4 },
  badge:          { alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, marginVertical: 4 },
  travelRow:      { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 4, borderBottomWidth: 1, borderBottomColor: '#1E2E1E' },
  travelIcon:     { fontSize: 16 },
  travelText:     { flex: 1, color: '#C0E0C0', fontSize: 13 },
  refText:        { color: '#888', fontSize: 11 },
  costText:       { color: '#00D68F', fontWeight: '700', fontSize: 14, marginTop: 6 },
  txAction:       { color: '#E0D0E0', fontWeight: '600', fontSize: 15, textTransform: 'capitalize' },
  txAmount:       { color: '#F0E0FF', fontSize: 22, fontWeight: '700' },
  creativeTitle:  { color: '#FFD700', fontWeight: '700', fontSize: 15 },
  creativeType:   { color: '#888', fontSize: 11, textTransform: 'uppercase', letterSpacing: 1 },
  creativeContent:{ color: '#D0D0E0', fontSize: 13, lineHeight: 20 },
  linkText:       { color: '#6C9CE7', fontSize: 12, textDecorationLine: 'underline' },
  reportSummary:  { color: '#E0E0D0', fontWeight: '600', fontSize: 14, marginBottom: 4 },
  insightText:    { color: '#C8D0C0', fontSize: 13, lineHeight: 19 },
});

export default function TalkScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const {
    connectionStatus, sessionId,
    setConnectionStatus, setSessionId, setHeartbeatSeq, setExecuteBlocked,
  } = useSessionStore();
  const {
    state: audioState, transcript, partialTranscript, ttsText,
    transition, setTranscript, setPartialTranscript, setTtsText,
    setIsSpeaking, reset: resetAudio,
  } = useAudioStore();

  const [textInput, setTextInput] = React.useState('');
  const [pendingAction, setPendingAction] = React.useState<string | null>(null);
  const [pendingDraftId, setPendingDraftId] = React.useState<string | null>(null);
  const [awaitingCommand, setAwaitingCommand] = React.useState<string>('none');
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [pipelineStageIndex, setPipelineStageIndex] = React.useState<number>(-1);
  const [pipelineSubStatus, setPipelineSubStatus] = React.useState<string>('');
  const [pipelineProgress, setPipelineProgress] = React.useState<number>(0);
  const [completedStages, setCompletedStages] = React.useState<string[]>([]);
  const completedStagesRef = useRef<string[]>([]);
  const pipelineStageIndexRef = useRef<number>(-1);
  const pendingDraftIdRef = useRef<string | null>(null);
  const recordingStartedAt = useRef<number>(0);  // track when recording began
  const micBusy = useRef(false);  // prevent re-entry into handleMic during TTS greeting
  // Keep refs in sync with state for AppState closure access
  useEffect(() => { completedStagesRef.current = completedStages; }, [completedStages]);
  useEffect(() => { pipelineStageIndexRef.current = pipelineStageIndex; }, [pipelineStageIndex]);
  useEffect(() => { pendingDraftIdRef.current = pendingDraftId; }, [pendingDraftId]);
  const [liveEnergy, setLiveEnergy] = useState(0);
  const [userNickname, setUserNickname] = useState('');
  const [waNotPaired, setWaNotPaired]   = useState(false);
  const [dsSyncStatus, setDsSyncStatus] = useState<string | null>(null); // 'syncing' | 'done' | null
  const [fragmentCount, setFragmentCount] = useState(0);  // pulsing dot counter
  const thoughtStreamTimer = useRef<ReturnType<typeof setTimeout> | null>(null);  // 12s stream end timer
  const lastTtsRef = useRef('');
  const lastTtsTimeRef = useRef(0);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = React.useState<Array<{
    role: 'user' | 'assistant' | 'result';
    text: string;
    result_type?: string;
    structured?: Record<string, any>;
    ts: number;
  }>>([]);
  const chatScrollRef = React.useRef<any>(null);
  const openChat = () => {
    setChatOpen(true);
    Animated.spring(chatSlideAnim, { toValue: 1, useNativeDriver: true, friction: 7 }).start();
    // Clear badge — user has read the content
    setTtsText('');
  };
  const closeChat = () => {
    Animated.timing(chatSlideAnim, { toValue: 0, duration: 280, useNativeDriver: true }).start(() => setChatOpen(false));
  };
  const [showDsModal, setShowDsModal] = useState(false);

  // Track whether THIS screen is focused — prevents talk.tsx WS handlers
  // from navigating to /loading while the user is in Settings or another screen.
  const isScreenFocused = useRef(true);
  const appInBackground = useRef(false);
  useFocusEffect(useCallback(() => {
    isScreenFocused.current = true;
    Keyboard.dismiss(); // Reset keyboard state when returning from other screens
    return () => { isScreenFocused.current = false; };
  }, []));

  // Poll DS sync status (WhatsApp messages downloading, etc.)
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    (async () => {
      try {
        const { getItem, setItem: storeItem } = require('../src/utils/storage');
        const token = await getItem('myndlens_auth_token');
        const tenantId = await getItem('myndlens_tenant_id');
        const dsImported = await getItem('whatsapp_ds_imported');
        const waConnected = await getItem('whatsapp_channel_connected');

        // Only show sync banner if: WA is connected AND DS not yet imported
        if (dsImported === 'true' || waConnected !== 'true' || !token || !tenantId) return;

        const obegeeUrl = process.env.EXPO_PUBLIC_OBEGEE_URL || 'https://obegee.co.uk';
        setDsSyncStatus('syncing');
        let pollCount = 0;

        timer = setInterval(async () => {
          pollCount++;
          try {
            const r = await fetch(`${obegeeUrl}/api/whatsapp/sync-progress/${tenantId}`, {
              headers: { Authorization: `Bearer ${token}` },
            });
            if (r.ok) {
              const d = await r.json();
              if (d.status === 'done') {
                setDsSyncStatus('done');
                await storeItem('whatsapp_ds_imported', 'true');
                if (timer) clearInterval(timer);
                setTimeout(() => setDsSyncStatus(null), 5000);
              } else if (d.status === 'not_started' && pollCount >= 3) {
                // No sync job running after 3 polls — stop showing banner
                setDsSyncStatus(null);
                if (timer) clearInterval(timer);
              }
            } else if (r.status === 401 || r.status === 403) {
              // Auth issue — stop polling
              setDsSyncStatus(null);
              if (timer) clearInterval(timer);
            }
          } catch { /* silent poll */ }
        }, 15000);
      } catch { /* silent */ }
    })();
    return () => { if (timer) clearInterval(timer); };
  }, []);

  const chatBubbleAnim = useRef(new Animated.Value(1)).current;
  const chatSlideAnim = useRef(new Animated.Value(0)).current;
  const micAnim = useRef(new Animated.Value(1)).current;
  const waveAnims = useRef([
    new Animated.Value(4),
    new Animated.Value(4),
    new Animated.Value(4),
    new Animated.Value(4),
    new Animated.Value(4),
  ]).current;

  // Request microphone permission immediately on mount.
  // Also check if Digital Self has been populated — gate mic if empty.
  useEffect(() => {
    (async () => {
      try {
        const { Audio } = require('expo-av');
        await Audio.requestPermissionsAsync();
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: true,
          playsInSilentModeIOS: true,
        });
      } catch { /* non-critical */ }

      // Check DS setup flag — show modal if user has never gone through DS setup.
      // Using a flag (not nodeCount) because a device with no contacts still counts
      // as "set up" — the user consciously went through the wizard.
      try {
        const { getItem } = require('../src/utils/storage');
        const dsSetupDone = await getItem('myndlens_ds_setup_done');
        if (!dsSetupDone || dsSetupDone === 'empty') {
          setShowDsModal(true);
        }
        // Check if WhatsApp is paired — show nudge if not
        const waPaired = await getItem('whatsapp_channel_connected');
        setWaNotPaired(!waPaired);
      } catch { /* non-critical */ }
    })();
  }, []);

  // Drive waveform bars from live VAD energy — each bar gets a different height multiplier
  const WAVE_PROFILE = [0.55, 0.85, 1.0, 0.85, 0.55]; // centre bar tallest
  useEffect(() => {
    if (audioState !== 'CAPTURING') {
      // Collapse all bars back to minimum
      waveAnims.forEach(a =>
        Animated.timing(a, { toValue: 4, duration: 250, useNativeDriver: false }).start(),
      );
      setLiveEnergy(0);
      return;
    }
    const poll = setInterval(() => {
      const energy = vad.lastEnergy;
      setLiveEnergy(energy);
      waveAnims.forEach((anim, i) => {
        const target = Math.max(4, energy * 44 * WAVE_PROFILE[i]);
        Animated.timing(anim, {
          toValue: target,
          duration: 80,
          useNativeDriver: false,
        }).start();
      });
    }, 80);
    return () => clearInterval(poll);
  }, [audioState]);

  // Pulse the chat bubble when new TTS or transcript arrives
  useEffect(() => {
    if (ttsText || transcript) {
      Animated.sequence([
        Animated.timing(chatBubbleAnim, { toValue: 1.25, duration: 180, useNativeDriver: true }),
        Animated.timing(chatBubbleAnim, { toValue: 1, duration: 180, useNativeDriver: true }),
      ]).start();
    }
  }, [ttsText, transcript]);

  // AppState: detect background → foreground transition.
  // Uses audioStateRef (not audioState) to avoid stale closures and prevent
  // the effect re-running on every state change — which caused a recording
  // restart loop on audio session resets (observed on OPPO devices).
  const audioStateRef = useRef(audioState);
  useEffect(() => { audioStateRef.current = audioState; }, [audioState]);

  useEffect(() => {
    let lastActiveTime = 0;

    const appStateSub = AppState.addEventListener('change', async (nextState) => {
      if (nextState === 'background' || nextState === 'inactive') {
        // ── Going to background ──────────────────────────────────────────────
        appInBackground.current = true;
        const state = audioStateRef.current;
        if (state === 'CAPTURING' || state === 'LISTENING') {
          await stopRecording().catch(() => {});
          transition('IDLE');
        }
        if (state === 'RESPONDING') {
          await TTS.stop().catch(() => {});
        }
        // Save pipeline visual state so it survives phone calls / foreground switches
        if (state === 'THINKING' || state === 'RESPONDING' || state === 'COMMITTING') {
          try {
            const { setItem } = require('../src/utils/storage');
            const saved = JSON.stringify({
              completedStages: completedStagesRef.current,
              pipelineStageIndex: pipelineStageIndexRef.current,
              pendingDraftId: pendingDraftIdRef.current,
            });
            await setItem('pipeline_resume_state', saved);
          } catch { /* non-critical */ }
        }
      } else if (nextState === 'active') {
        // ── Returning to foreground ──────────────────────────────────────────
        appInBackground.current = false;
        const now = Date.now();

        // Guard: ignore transient background/active cycles caused by audio
        // session resets on recording stop (< 1 second background duration).
        if (now - lastActiveTime < 1000) {
          return;
        }
        lastActiveTime = now;

        if (!wsClient.isAuthenticated) {
          const state = audioStateRef.current;
          if (state === 'CAPTURING' || state === 'LISTENING') {
            await stopRecording().catch(() => {});
          }
          await TTS.stop().catch(() => {});
          resetAudio();

          // Silent reconnect — do NOT show loading screen
          // The WS dropped during background (normal after 5+ min).
          // Just reconnect quietly. The user stays on the Talk screen.
          console.log('[Talk] WS disconnected during background — reconnecting silently');
          setConnectionStatus('connecting');
          try {
            const { getItem } = require('../src/utils/storage');
            const token = await getItem('myndlens_auth_token');
            if (token) {
              await wsClient.connect();
              console.log('[Talk] Silent reconnect successful');
            } else {
              router.replace('/loading');
            }
          } catch (e) {
            console.log('[Talk] Silent reconnect failed, going to loading:', e);
            router.replace('/loading');
          }
        }
      }
    });
    return () => appStateSub.remove();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);  // Mount once — audioState accessed via audioStateRef

  // Mic pulse
  useEffect(() => {
    if (audioState === 'CAPTURING') {
      const pulse = Animated.loop(
        Animated.sequence([
          Animated.timing(micAnim, { toValue: 1.15, duration: 600, useNativeDriver: true }),
          Animated.timing(micAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
        ])
      );
      pulse.start();
      return () => pulse.stop();
    } else if (audioState === 'ACCUMULATING') {
      // Gentle pulse — "processing your fragment, keep talking"
      const pulse = Animated.loop(
        Animated.sequence([
          Animated.timing(micAnim, { toValue: 1.08, duration: 800, useNativeDriver: true }),
          Animated.timing(micAnim, { toValue: 0.96, duration: 800, useNativeDriver: true }),
        ])
      );
      pulse.start();
      return () => pulse.stop();
    } else if (audioState === 'RESPONDING') {
      const glow = Animated.loop(
        Animated.sequence([
          Animated.timing(micAnim, { toValue: 1.06, duration: 1200, useNativeDriver: true }),
          Animated.timing(micAnim, { toValue: 0.94, duration: 1200, useNativeDriver: true }),
        ])
      );
      glow.start();
      return () => glow.stop();
    } else {
      micAnim.setValue(1);
    }
  }, [audioState]);

  // WS handlers
  useEffect(() => {
    const unsubs = [
      wsClient.on('heartbeat_ack', (env: WSEnvelope) => setHeartbeatSeq(env.payload.seq)),
      wsClient.on('auth_ok', async (env: WSEnvelope) => {
        // Set session ID in store — used by VAD callback to send audio
        setSessionId(wsClient.currentSessionId);
        const hasPendingMandate = env.payload?.has_pending_mandate ?? false;

        // Restore pipeline visual state if we went to background mid-execution
        try {
          const { getItem, setItem } = require('../src/utils/storage');
          const saved = await getItem('pipeline_resume_state');
          if (saved) {
            const { completedStages: cs, pipelineStageIndex: pi, pendingDraftId: pd } = JSON.parse(saved);
            if (cs?.length > 0) {
              setCompletedStages(cs);
              setPipelineStageIndex(pi ?? -1);
              if (pd) setPendingDraftId(pd);
              // Clear the saved state — it's been restored
              await setItem('pipeline_resume_state', '');
            }
          }
        } catch { /* non-critical */ }
        try {
          const { getItem, setItem } = require('../src/utils/storage');

          // Refresh user name from ObeGee to fix stale nicknames
          const token = await getItem('myndlens_auth_token');
          if (token) {
            try {
              const res = await fetch('https://obegee.co.uk/api/auth/me', {
                headers: { Authorization: `Bearer ${token}` },
              });
              if (res.ok) {
                const me = await res.json();
                if (me.name) await setItem('myndlens_user_name', me.name);
              }
            } catch { /* non-critical — use stored name */ }
          }

          const stored = await getItem('myndlens_user_name');
          const firstName = stored ? stored.split(' ')[0] : '';
          if (firstName) setUserNickname(firstName);

          // Skip local greeting if backend has a pending mandate to resume —
          // the backend will send its own TTS with the mandate summary.
          // Playing both causes conflicting audio (P1 fix).
          if (hasPendingMandate) {
            console.log('[Talk] Pending mandate — suppressing local greeting');
            return;
          }

          const hour = new Date().getHours();
          const word = hour >= 5 && hour < 12 ? 'Good morning'
                     : hour >= 12 && hour < 17 ? 'Good afternoon'
                     : hour >= 17 && hour < 21 ? 'Good evening'
                     : 'Hey';
          const greeting = firstName
            ? `${word}, ${firstName}. Ready when you are.`
            : `${word}. Ready when you are.`;

          setTtsText(greeting);
          transition('RESPONDING');
          setIsSpeaking(true);
          TTS.speak(greeting, {
            onComplete: () => { setIsSpeaking(false); transition('IDLE'); },
          });
        } catch { /* non-critical */ }
      }),
      wsClient.on('transcript_partial', (env: WSEnvelope) => setPartialTranscript(env.payload.text || '')),
      wsClient.on('fragment_ack' as WSMessageType, (env: WSEnvelope) => {
        // Path A — Capture Cycle: fragment processed (informational only)
        // Recording already restarted immediately — this just updates UI
        const { fragment_text, sub_intents, checklist_progress } = env.payload;
        console.log('[Talk] Fragment ACK:', fragment_text?.substring(0, 40), 'progress:', checklist_progress);
        if (fragment_text) {
          setChatMessages(prev => [...prev, { role: 'user', text: fragment_text, ts: Date.now() }]);
        }
      }),
      // Biometric gate — backend requests auth before execution
      wsClient.on('biometric_request' as WSMessageType, async (env: WSEnvelope) => {
        // TODO: Replace with actual biometric prompt (fingerprint/face)
        // For now: auto-approve (graceful degradation — matches backend 30s timeout behavior)
        console.log('[Talk] Biometric request received — auto-approving (biometric UI pending)');
        wsClient.send('biometric_response' as WSMessageType, {
          session_id: env.payload.session_id,
          success: true,
          method: 'auto_approved',
        });
      }),
      // WhatsApp pairing code pushed from backend
      wsClient.on('wa_pair_code' as WSMessageType, (env: WSEnvelope) => {
        const { status, pairing_code, instructions, error: waError } = env.payload;
        if (status === 'code_ready' && pairing_code) {
          Alert.alert(
            'WhatsApp Pairing Code',
            `${pairing_code}\n\n${instructions || 'Enter this code in WhatsApp → Linked Devices → Link with Phone Number'}`,
            [{ text: 'OK' }],
          );
        } else if (waError) {
          Alert.alert('WhatsApp Pairing', waError);
        }
      }),
      wsClient.on('transcript_final', (env: WSEnvelope) => {
        const text = env.payload.text || '';
        setTranscript(text);
        setPartialTranscript('');
        transition('THINKING');
        // Don't add to chat here — fragment_ack already adds each fragment
        // Adding again from transcript_final causes duplicate messages
      }),
      wsClient.on('draft_update', (env: WSEnvelope) => {
        const actionClass = env.payload.action_class || '';
        const draftId = env.payload.draft_id || '';
        const hypothesis = env.payload.hypothesis || '';
        // Always set pending — server decides when approval is needed, not confidence threshold
        if (draftId) {
          setPendingAction(_actionLabel(actionClass, hypothesis));
          setPendingDraftId(draftId);
        }
      }),
      wsClient.on('tts_audio', (env: WSEnvelope) => {
        const text = env.payload.text || '';
        const audioBase64: string = env.payload.audio || '';
        const isMock: boolean = env.payload.is_mock ?? true;
        const autoRecord: boolean = env.payload.auto_record ?? false;
        const uiMode: string = env.payload.ui_mode ?? '';
        const awCmd: string = env.payload.awaiting_command ?? 'none';
        const draftId: string = env.payload.draft_id ?? '';
        // Update server-driven command context
        if (awCmd !== 'none') {
          setAwaitingCommand(awCmd);
          if (draftId) setPendingDraftId(draftId);
          setPendingAction('approve');
        }
        setTtsText(text);
        // Dedup: skip if this exact text was just played (prevents double TTS)
        if (text === lastTtsRef.current && Date.now() - lastTtsTimeRef.current < 5000) {
          console.log('[Talk] Skipping duplicate TTS:', text.substring(0, 30));
          return;
        }
        lastTtsRef.current = text;
        lastTtsTimeRef.current = Date.now();
        transition('RESPONDING');
        setIsSpeaking(true);
        // Add MyndLens response to chat history
        if (text) {
          setChatMessages(prev => [...prev, { role: 'assistant', text, ts: Date.now() }]);
          setTimeout(() => chatScrollRef.current?.scrollToEnd({ animated: true }), 100);
        }
        const onComplete = () => {
          setIsSpeaking(false);
          transition('IDLE');
          // Auto-start recording after mandate summary ("Shall I proceed?")
          // Skip greeting — user is in context, they know to say Yes/No directly
          if (autoRecord) {
            // 800ms delay — gives the TTS audio (including room reverb) time to fully
            // decay before the mic opens. 400ms was too short: the recorder picked up
            // TTS echo and sent empty/junk audio to STT → backend got "" → silent return
            // → frontend stuck in THINKING forever.
            setTimeout(async () => {
              const sid = wsClient.currentSessionId;
              if (!sid) return;
              transition('LISTENING');
              transition('CAPTURING');
              recordingStartedAt.current = Date.now();
              await startRecording(
                async () => {
                  // Duration guard: ignore VAD triggers < 1s (noise/echo)
                  const dur = Date.now() - recordingStartedAt.current;
                  if (dur < 1000) {
                    console.log('[Talk] Auto-record VAD noise ignored (< 1s), continuing');
                    return;
                  }
                  const audioBase64r = await stopAndGetAudio();
                  const sid2 = wsClient.currentSessionId;
                  if (audioBase64r && sid2) {
                    wsClient.send('audio_chunk', {
                      session_id: sid2, audio: audioBase64r,
                      seq: 1, timestamp: Date.now(), duration_ms: dur,
                    });
                    wsClient.send('cancel', { session_id: sid2, reason: 'vad_end_of_utterance' });
                    transition('COMMITTING');
                    transition('THINKING');
                  } else {
                    transition('IDLE');
                  }
                },
                (rms: number) => setLiveEnergy(rms),
              );
            }, 800);
          }
        };
        // Play real ElevenLabs audio if available, else fall back to device TTS
        if (audioBase64 && !isMock) {
          TTS.speakFromAudio(audioBase64, { onComplete });
        } else {
          TTS.speak(text, { onComplete });
        }
      }),
      wsClient.on('clarification_question' as WSMessageType, (env: WSEnvelope) => {
        // Voice-first: the question is spoken via tts_audio with auto_record:true.
        // No visual Yes/No box — user speaks their answer.
        // Just log for debugging.
        console.log('[Talk] Clarification question (voice only):', env.payload.question);
      }),
      wsClient.on('execute_blocked', (env: WSEnvelope) => {
        if (env.payload.code === 'SUBSCRIPTION_INACTIVE' || env.payload.code === 'PRESENCE_STALE') {
          router.push('/softblock');
        }
        setExecuteBlocked(env.payload.reason);
        // Don't clear pendingAction here — let the user retry via Change button
      }),
      wsClient.on('session_terminated', async () => {
        // Clean up all active state before navigating away
        const state = audioStateRef.current;
        if (state === 'CAPTURING' || state === 'LISTENING') {
          await stopRecording().catch(() => {});
        }
        await TTS.stop().catch(() => {});
        resetAudio();
        setPendingAction(null);
        setPendingDraftId(null);
        setPipelineStageIndex(-1);
        setPipelineSubStatus('');
        setPipelineProgress(0);
        setConnectionStatus('disconnected');
        // Only navigate if this screen is focused AND the app is in the foreground.
        // Navigating while backgrounded causes the race condition where loading.tsx
        // mounts, reconnects, routes to talk — and then a stale event fires again.
        if (isScreenFocused.current && !appInBackground.current) {
          router.replace('/loading');
        }
      }),
      wsClient.on('pipeline_stage' as WSMessageType, (env: WSEnvelope) => {
        const idx = env.payload.stage_index ?? -1;
        const sub = env.payload.sub_status || env.payload.summary || '';
        const prog = env.payload.progress || 0;
        const status = env.payload.status || 'active';
        const deliveredTo: string[] = env.payload.delivered_to || [];
        const displayInChat = deliveredTo.includes('chat_display') || deliveredTo.includes('chat');
        const resultType: string = env.payload.result_type || 'generic';
        const structured = env.payload.structured_result || null;

        if (status === 'done' && idx >= 0 && idx < PIPELINE_STAGES.length) {
          const label = PIPELINE_STAGES[idx].label;
          setCompletedStages(prev => prev.includes(label) ? prev : [...prev, label]);
          if (idx >= 9 && sub) {
            setPipelineSubStatus(sub.substring(0, 200));
            setPendingAction(null);  // D6: results delivered — no pending approval/kill
            setChatMessages(prev => [...prev, {
              role: 'result',
              text: sub,
              result_type: resultType,
              structured: structured || undefined,
              ts: Date.now(),
            }]);
            setTimeout(() => chatScrollRef.current?.scrollToEnd({ animated: true }), 100);
            if (displayInChat) setChatOpen(true);
          }
        } else if (status === 'active') {
          setPipelineStageIndex(idx);
          setPipelineSubStatus(sub);
          setPipelineProgress(prog);
        }
      }),
    ];
    return () => unsubs.forEach((u) => u());
  }, []);

  // ---- MIC: Start/Stop voice conversation ----
  async function handleMic() {
    // Guard: prevent double-tap from entering this function twice while
    // the TTS greeting is playing (which causes empty intent processing).
    if (micBusy.current && audioStateRef.current !== 'CAPTURING' && audioStateRef.current !== 'LISTENING') {
      console.log('[Talk] handleMic blocked — mic is busy (greeting/setup in progress)');
      return;
    }
    const isBargeIn = audioState === 'RESPONDING';
    if (isBargeIn) {
      // Barge-in: user tapped while TTS was playing — stop it and start recording
      await TTS.stop();
      setIsSpeaking(false);
      transition('IDLE');
      // Note: audioState is stale (still 'RESPONDING') — use isBargeIn flag below
    }
    if (audioState === 'IDLE' || isBargeIn) {
      // Fresh session — clear pipeline state so it starts clean for the new command
      setCompletedStages([]);
      setPipelineStageIndex(-1);
      setPipelineSubStatus('');
      setPipelineProgress(0);
      setPendingAction(null);  // D6: clear stale approve/kill state from previous mandate
      setFragmentCount(0);    // Reset fragment counter for new conversation
      if (thoughtStreamTimer.current) { clearTimeout(thoughtStreamTimer.current); thoughtStreamTimer.current = null; }
      // Gate: if DS setup was never completed, surface the setup modal every tap
      try {
        const { getItem } = require('../src/utils/storage');
        const dsSetupDone = await getItem('myndlens_ds_setup_done');
        if (!dsSetupDone || dsSetupDone === 'empty') {
          setShowDsModal(true);
          return;
        }
      } catch { /* non-critical — proceed anyway */ }
      setPipelineStageIndex(-1);
      setPipelineSubStatus('');
      setPipelineProgress(0);
      micBusy.current = true;  // lock: prevent double-tap during greeting
      transition('LISTENING');
      transition('CAPTURING');

      // Greet the user before recording starts.
      // await TTS.speak() now resolves AFTER speech finishes (not immediately).
      // 400ms acoustic decay after greeting before mic opens — prevents the
      // device speaker audio being captured as user speech by the microphone.
      const greeting = userNickname
        ? `Hi ${userNickname}, what's on your mind?`
        : "What's on your mind?";
      await TTS.speak(greeting);
      await new Promise(r => setTimeout(r, 400));
      micBusy.current = false;  // unlock: greeting done, recording about to start
      recordingStartedAt.current = Date.now();

      await startRecording(
        async () => {
          // VAD auto-stop: sentence-level pause detected (1.5s silence)
          const duration = Date.now() - recordingStartedAt.current;
          if (duration < 1000) {
            console.log('[Talk] VAD noise trigger ignored (< 1s), continuing to record');
            return;
          }
          console.log('[Talk] VAD triggered fragment capture (duration=' + duration + 'ms)');
          const audioBase64 = await stopAndGetAudio();
          const sid = wsClient.currentSessionId;
          if (audioBase64 && sid) {
            // Send as fragment (Path A — Capture Cycle)
            wsClient.send('audio_chunk', {
              session_id: sid, audio: audioBase64,
              seq: 1, timestamp: Date.now(), duration_ms: duration,
            });
            wsClient.send('cancel', { session_id: sid, reason: 'fragment_captured' });
            setFragmentCount(prev => prev + 1);

            // IMMEDIATELY restart recording — don't wait for FRAGMENT_ACK.
            // Backend queues fragments and processes them sequentially.
            // This ensures no audio is lost if user keeps speaking.
            recordingStartedAt.current = Date.now();
            // Stay in CAPTURING (not ACCUMULATING) — mic is active
            await startRecording(
              async () => {
                // Recursive: same fragment capture logic
                const dur2 = Date.now() - recordingStartedAt.current;
                if (dur2 < 1000) { console.log('[Talk] VAD noise ignored, continuing'); return; }
                const audio2 = await stopAndGetAudio();
                const sid2 = wsClient.currentSessionId;
                if (audio2 && sid2) {
                  wsClient.send('audio_chunk', { session_id: sid2, audio: audio2, seq: 1, timestamp: Date.now(), duration_ms: dur2 });
                  wsClient.send('cancel', { session_id: sid2, reason: 'fragment_captured' });
                  setFragmentCount(prev => prev + 1);
                  recordingStartedAt.current = Date.now();
                  // Don't restart here — the fragment_ack handler or thought timer handles next step
                  transition('ACCUMULATING');
                } else { transition('IDLE'); }
              },
              (rms: number) => setLiveEnergy(rms),
            ).catch(() => {});

            // Reset thought-stream-end timer (6s from last speech)
            if (thoughtStreamTimer.current) clearTimeout(thoughtStreamTimer.current);
            thoughtStreamTimer.current = setTimeout(() => {
              const currentState = audioStateRef.current;
              if (currentState === 'ACCUMULATING' || currentState === 'CAPTURING') {
                console.log('[Talk] Thought stream ended (6s silence)');
                stopRecording().catch(() => {});
                wsClient.send('thought_stream_end', { session_id: sid });
                transition('THINKING');
              }
            }, 12000);
          } else {
            console.warn('[Talk] stopAndGetAudio null or no session — resetting to IDLE');
            transition('IDLE');
          }
        },
        (rms: number) => setLiveEnergy(rms),
      );
    } else if (audioState === 'CAPTURING' || audioState === 'LISTENING') {
      // Guard: if recording hasn't actually started yet (recordingStartedAt is 0 or very old),
      // treat as cancel — don't try to submit non-existent audio.
      const recordingAge = Date.now() - recordingStartedAt.current;
      if (recordingStartedAt.current === 0 || recordingAge < 1500) {
        console.log('[Talk] Recording cancelled (not started or < 1.5s) — resetting to IDLE');
        await stopRecording().catch(() => {});
        transition('IDLE');
        return;
      }
      // Manual stop after 1.5s → user finished speaking, submit
      const audioBase64 = await stopAndGetAudio();
      const sid = wsClient.currentSessionId;  // read live, not from stale closure
      if (audioBase64 && sid) {
        wsClient.send('audio_chunk', {
          session_id: sid, audio: audioBase64,
          seq: 1, timestamp: Date.now(), duration_ms: 0,
        });
        transition('COMMITTING');
        wsClient.send('cancel', { session_id: sid, reason: 'user_stop' });
        transition('THINKING');
      } else {
        console.warn('[Talk] stopAndGetAudio null or no session (manual stop) — resetting to IDLE');
        transition('IDLE');
      }
    }
  }

  // ---- KILL: Stop everything ----
  async function handleKill() {
    if (audioState === 'CAPTURING' || audioState === 'LISTENING') await stopRecording();
    await TTS.stop();
    setIsSpeaking(false);
    if (sessionId) wsClient.send('cancel', { session_id: sessionId, reason: 'kill_switch' });
    resetAudio();
    setPendingAction(null);
    setPendingDraftId(null);
    setTtsText('');
    setTranscript('');
  }

  // ---- APPROVE: Send to OpenClaw ----
  function handleApprove() {
    if (!pendingDraftId || !wsClient.isAuthenticated) return;
    wsClient.sendExecuteRequest(pendingDraftId);
    setPendingAction(null);
    setPendingDraftId(null);
  }

  // ---- TEXT SEND ----
  async function handleSendText() {
    if (!textInput.trim() || connectionStatus !== 'authenticated') return;
    Keyboard.dismiss();
    const text = textInput.trim();

    // Build on-device context capsule from local Digital Self PKG.
    // Only the summary string is transmitted — never raw nodes, never PII.
    let context_capsule: string | undefined;
    try {
      const userId = wsClient.userId ?? '';
      if (userId) {
        const capsule = await buildContextCapsule(userId, text);
        if (capsule.summary) {
          // Transmit only the summary — entities/traits/places stay on device
          context_capsule = JSON.stringify({ summary: capsule.summary });
        }
      }
    } catch (err) {
      console.warn('[Talk] Context capsule unavailable:', err);
    }

    wsClient.send('text_input', { session_id: sessionId, text, context_capsule });
    setTranscript(text);
    setTextInput('');
    transition('THINKING');
  }

  const connectionDot = connectionStatus === 'authenticated' ? '#00D68F' : '#E74C3C';
  const micColor = audioState === 'CAPTURING' ? '#E74C3C'
    : audioState === 'RESPONDING' ? '#00D68F'
    : audioState === 'THINKING' ? '#FFAA00'
    : '#6C5CE7';

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[styles.container, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 8 }]}>

        {/* ── Digital Self Setup Modal ─────────────────────────────────── */}
        <Modal visible={showDsModal} transparent animationType="fade">
          <View style={styles.dsModalOverlay}>
            <View style={styles.dsModalCard}>
              <Text style={styles.dsModalTitle}>Your Digital Self isn't set up yet</Text>
              <Text style={styles.dsModalBody}>
                Without it, MyndLens has no context about you — no contacts, no routines, no history. Every mandate starts from scratch and intent extraction will be significantly less accurate.{'\n\n'}
                Set it up in Settings. It takes 10 seconds and everything stays on your device.
              </Text>
              <TouchableOpacity
                style={styles.dsModalBtn}
                onPress={() => {
                  setShowDsModal(false);
                  router.push('/settings' as any);
                }}
              >
                <Text style={styles.dsModalBtnText}>Set up Digital Self</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.dsModalSkip}
                onPress={() => setShowDsModal(false)}
              >
                <Text style={styles.dsModalSkipText}>Continue anyway (degraded performance)</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>

        {/* Top bar */}
        <View style={styles.topBar}>
          <View style={[styles.dot, { backgroundColor: connectionDot }]} />
          <View style={{ flex: 1 }} />
          <TouchableOpacity onPress={() => setMenuOpen(!menuOpen)} hitSlop={{ top: 16, bottom: 16, left: 16, right: 16 }} data-testid="hamburger-menu-btn">
            <Text style={styles.gear}>{'\u2630'}</Text>
          </TouchableOpacity>
        </View>

        {/* Hamburger Menu Overlay */}
        {menuOpen && (
          <View style={styles.menuOverlay} data-testid="hamburger-menu">
            <TouchableOpacity style={styles.menuBackdrop} onPress={() => setMenuOpen(false)} activeOpacity={1} />
            <View style={styles.menuPanel}>
              <TouchableOpacity style={styles.menuItem} onPress={() => { setMenuOpen(false); router.push('/dashboard'); }} data-testid="menu-dashboard">
                <Text style={styles.menuIcon}>{'\u{1F4CA}'}</Text>
                <Text style={styles.menuText}>Dashboard</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.menuItem} onPress={() => { setMenuOpen(false); router.push('/persona' as any); }} data-testid="menu-persona">
                <Text style={styles.menuIcon}>🧠</Text>
                <Text style={styles.menuText}>Digital Self</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.menuItem} onPress={() => { setMenuOpen(false); router.push('/settings'); }} data-testid="menu-settings">
                <Text style={styles.menuIcon}>{'\u2699'}</Text>
                <Text style={styles.menuText}>Settings</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.menuItem} onPress={() => { setMenuOpen(false); router.push('/onboarding'); }} data-testid="menu-onboarding">
                <Text style={styles.menuIcon}>{'\u{1F464}'}</Text>
                <Text style={styles.menuText}>Edit Profile</Text>
              </TouchableOpacity>
              <View style={styles.menuDivider} />
              <TouchableOpacity style={styles.menuItem} onPress={() => setMenuOpen(false)} data-testid="menu-close">
                <Text style={styles.menuIcon}>{'\u2715'}</Text>
                <Text style={styles.menuText}>Close</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Logo at top */}
        <View style={styles.logoArea}>
          <Image
            source={require('../assets/images/myndlens-logo.png')}
            style={styles.logo}
            resizeMode="contain"
          />
        </View>

        {/* DS Sync Progress Banner */}
        {dsSyncStatus && (
          <View style={{ backgroundColor: dsSyncStatus === 'done' ? 'rgba(46,204,113,0.12)' : 'rgba(108,92,231,0.10)',
            borderRadius: 10, marginHorizontal: 20, marginBottom: 8, paddingHorizontal: 14, paddingVertical: 8,
            flexDirection: 'row', alignItems: 'center', gap: 8 }} data-testid="ds-sync-banner">
            {dsSyncStatus === 'syncing' && <ActivityIndicator size="small" color="#6C5CE7" />}
            <Text style={{ color: dsSyncStatus === 'done' ? '#2ECC71' : '#B0A0E0', fontSize: 12 }}>
              {dsSyncStatus === 'syncing' ? 'Building Digital Self — syncing messages...' : 'Digital Self updated'}
            </Text>
          </View>
        )}

        {/* Middle zone — card centered between logo and controls */}
        <View style={styles.middleZone}>

        {/* Clarification Question Card — shown when server needs more context */}
        {/* Clarification questions are voice-only — no visual box */}

        {/* ── Activity Window — Sequential live pipeline feed ── */}
        {(() => {
          const wsIdx = pipelineStageIndex;
          const activeIndex = wsIdx >= 0
            ? wsIdx
            : PIPELINE_STAGES.findIndex((_, i) => getPipelineState(i, audioState, pendingAction, transcript) === 'active');
          const activeStage = activeIndex >= 0 ? PIPELINE_STAGES[activeIndex] : null;
          const isIdle = !activeStage && audioState === 'IDLE' && completedStages.length === 0;

          const activeText = activeIndex === 0 && userNickname
            ? `Listening, ${userNickname}\u2026`
            : activeStage?.activeText ?? '';

          return (
            <View style={styles.pipelineWrapper} data-testid="pipeline-progress">
              {isIdle ? (
                <>
                  <View style={[styles.pipelineCard, styles.pipelineCardIdle]}>
                    <View style={styles.pipelineIdleInner}>
                      <Text style={styles.pipelineIdleTitle}>What's on Your Mind{'\n'}Right Now?</Text>
                      <Text style={styles.pipelineIdleSubtext}>Tap the mic to instruct me.</Text>
                    </View>
                  </View>
                </>
              ) : (
                <View style={styles.activityFeed}>
                  {/* Completed stages — last 4 only (sliding window keeps layout stable) */}
                  {completedStages.slice(-4).map((label, i) => (
                    <View key={i} style={styles.activityDone}>
                      <Text style={styles.activityDoneTick}>{'\u2713'}</Text>
                      <Text style={styles.activityDoneLabel}>{label}</Text>
                    </View>
                  ))}
                  {/* Current active stage */}
                  {activeStage && (
                    <View style={styles.activityActive}>
                      <ActivityIndicator size={16} color="#6C63FF" style={styles.activitySpinner} />
                      <View style={styles.activityActiveText}>
                        <Text style={styles.pipelineActiveText}>{activeText}</Text>
                        {pipelineSubStatus ? (
                          <Text style={styles.pipelineSubStatus}>{pipelineSubStatus}</Text>
                        ) : null}
                      </View>
                    </View>
                  )}
                </View>
              )}
            </View>
          );
        })()}

          {audioState === 'THINKING' ? (
            <View style={styles.thinkingRow}>
              <Text style={styles.thinkingText}>{'\u2026'}</Text>
            </View>
          ) : null}
        </View>

        {/* WhatsApp nudge — visible when WA not linked and no active pipeline */}
        {waNotPaired && audioState === 'IDLE' && pipelineStageIndex < 0 && (
          <View style={{ marginHorizontal: 20, marginTop: 8, backgroundColor: 'rgba(37,211,102,0.08)', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: 'rgba(37,211,102,0.25)' }}>
            <Text style={{ color: '#25D366', fontSize: 12, fontWeight: '700', marginBottom: 3 }}>
              Connect WhatsApp for full capability
            </Text>
            <Text style={{ color: '#555568', fontSize: 12, lineHeight: 17 }}>
              Go to obegee.co.uk → Integrations to link WhatsApp and enrich your Digital Self.
            </Text>
          </View>
        )}

        {/* Disconnected banner — visible when WS is not authenticated */}
        {connectionStatus === 'disconnected' && (
          <TouchableOpacity
            style={styles.reconnectBanner}
            onPress={() => router.replace('/loading')}
          >
            <Text style={styles.reconnectText}>Disconnected — tap to reconnect</Text>
          </TouchableOpacity>
        )}

        {/* PRIMARY: Large mic button */}
        <View style={styles.controlArea}>
          {/* VAD label — minimal hint below button only */}
          {audioState === 'CAPTURING' && (
            <Text style={styles.vadListeningLabel}>
              {liveEnergy >= 0.015 ? 'listening...' : 'waiting...'}
            </Text>
          )}
          <Animated.View style={{ transform: [{ scale: micAnim }] }}>
            <TouchableOpacity
              style={[styles.micButton, { backgroundColor: micColor }, audioState === 'THINKING' && styles.micThinking]}
              onPress={connectionStatus !== 'authenticated' ? () => router.replace('/loading') : handleMic}
              disabled={audioState === 'THINKING'}
              activeOpacity={0.85}
            >
              {audioState === 'CAPTURING' ? (
                /* Siri-style sympathetic waveform — 5 bars, energy-driven */
                <View style={styles.waveContainer}>
                  {waveAnims.map((anim, i) => (
                    <Animated.View
                      key={i}
                      style={[styles.waveBar, { height: anim }]}
                    />
                  ))}
                </View>
              ) : (
                <MicIcon size={40} color="#FFFFFF" />
              )}
            </TouchableOpacity>
          </Animated.View>

          {/* Secondary: Kill/Change + Done/Yes — server-driven via command_input */}
          <View style={styles.secondaryRow}>
            <TouchableOpacity style={styles.killButton} onPress={() => {
                const sid = wsClient.currentSessionId;
                console.log('[BTN:KILL/CHANGE] tap — sid=%s awaitingCommand=%s pendingAction=%s', sid, awaitingCommand, pendingAction);
                if (!sid) return;
                if (awaitingCommand === 'approve_or_change' || pendingAction) {
                  console.log('[BTN:CHANGE] sending DECLINE_CHANGE');
                  wsClient.send('command_input' as WSMessageType, { session_id: sid, command: 'DECLINE_CHANGE', source: 'button' });
                  setAwaitingCommand('none');
                  transition('THINKING');
                } else {
                  console.log('[BTN:KILL] calling handleKill');
                  handleKill();
                }
              }} activeOpacity={0.8} data-testid="kill-btn">
              <Text style={styles.smallBtnIcon}>{awaitingCommand === 'approve_or_change' || pendingAction ? '\u270E' : '\u2716'}</Text>
              <Text style={styles.smallBtnText}>{awaitingCommand === 'approve_or_change' || pendingAction ? 'Change' : 'Kill'}</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.approveButton,
                awaitingCommand === 'none' && !pendingAction && fragmentCount === 0 && styles.approveDisabled]}
              onPress={() => {
                const sid = wsClient.currentSessionId;
                console.log('[BTN:DONE/YES] tap — sid=%s fragmentCount=%d audioState=%s awaitingCommand=%s pendingAction=%s',
                  sid, fragmentCount, audioStateRef.current, awaitingCommand, pendingAction);
                if (!sid) return;
                if (fragmentCount > 0 && (audioStateRef.current === 'CAPTURING' || audioStateRef.current === 'ACCUMULATING')) {
                  // END_THOUGHT
                  console.log('[BTN:DONE] sending END_THOUGHT');
                  if (thoughtStreamTimer.current) { clearTimeout(thoughtStreamTimer.current); thoughtStreamTimer.current = null; }
                  stopRecording().catch(() => {});
                  wsClient.send('command_input' as WSMessageType, { session_id: sid, command: 'END_THOUGHT', source: 'button' });
                  transition('THINKING');
                } else if (awaitingCommand === 'approve_or_change' || pendingAction) {
                  // APPROVE
                  console.log('[BTN:YES] sending APPROVE draft=%s', pendingDraftId);
                  wsClient.send('command_input' as WSMessageType, { session_id: sid, command: 'APPROVE', source: 'button', draft_id: pendingDraftId || '' });
                  setAwaitingCommand('none');
                  setPendingAction(null);
                  transition('THINKING');
                } else {
                  console.log('[BTN:DONE/YES] no action — conditions not met');
                }
              }}
              disabled={awaitingCommand === 'none' && !pendingAction && fragmentCount === 0}
              activeOpacity={0.8}
              data-testid="approve-btn"
            >
              <Text style={styles.smallBtnIcon}>{fragmentCount > 0 && (audioState === 'CAPTURING' || audioState === 'ACCUMULATING') ? '\u2713' : '\u2714'}</Text>
              <Text style={styles.smallBtnText}>{fragmentCount > 0 && (audioState === 'CAPTURING' || audioState === 'ACCUMULATING') ? 'Done' : 'Yes'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Text fallback row removed — text input lives inside the Chat panel. */}

        {/* ── Bottom bar: left = RESERVED for future actions, right = Chat ── */}
        {/* This sits below Kill/Approve, eliminates the floating FAB overlap. */}
        <View style={styles.bottomBar}>
          {/* Left zone — reserved for future quick-action buttons */}
          <View style={styles.bottomBarLeft} />

          {/* Chat button — fixed, no longer draggable/floating */}
          <TouchableOpacity
            onPress={() => openChat()}
            style={[styles.chatBtn, (ttsText || transcript) && styles.chatBtnActive]}
            activeOpacity={0.85}
          >
            <Text style={styles.chatBtnIcon}>💬</Text>
            {(ttsText || transcript || chatMessages.length > 0) && !chatOpen && (
              <View style={styles.chatBadge} />
            )}
          </TouchableOpacity>
        </View>

        {/* ── Chat Modal — slides in full-screen ───────────────────────── */}
        <Modal
          visible={chatOpen}
          animationType="slide"
          transparent
          onRequestClose={() => setChatOpen(false)}
        >
          <View style={styles.chatModalOverlay}>
            <Animated.View style={[
              styles.chatModalSheet,
              { transform: [{ translateY: chatSlideAnim.interpolate({ inputRange: [0, 1], outputRange: [800, 0] }) }] },
            ]}>
              {/* Handle bar */}
              <View style={styles.chatHandle} />

              {/* Header */}
              <View style={styles.chatModalHeader}>
                <Text style={styles.chatModalTitle}>Chat Channel</Text>
                <TouchableOpacity
                  onPress={() => closeChat()}
                  style={styles.chatCloseBtn}
                  hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                >
                  <Text style={styles.chatCloseText}>✕</Text>
                </TouchableOpacity>
              </View>

              {/* Conversation history */}
              <ScrollView
                ref={chatScrollRef}
                style={styles.chatScrollView}
                contentContainerStyle={styles.chatScrollContent}
                showsVerticalScrollIndicator={false}
              >
                {chatMessages.length === 0 ? (
                  <Text style={{ color: '#444', textAlign: 'center', marginTop: 40, fontSize: 14 }}>
                    Your conversation will appear here.
                  </Text>
                ) : (
                  chatMessages.map((msg, i) => (
                    <View key={i} style={
                      msg.role === 'user'      ? styles.userBubble :
                      msg.role === 'assistant' ? styles.assistantBubble :
                      styles.resultBubble
                    }>
                      <Text style={
                        msg.role === 'user'      ? styles.userLabel :
                        msg.role === 'assistant' ? styles.assistantLabel :
                        styles.resultLabel
                      }>
                        {msg.role === 'user' ? 'You' :
                         msg.role === 'result' ? (msg.result_type === 'generic' ? 'Result' : msg.result_type!.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())) :
                         'MyndLens'}
                      </Text>
                      <ResultCard msg={msg} />
                    </View>
                  ))
                )}
                {audioState === 'THINKING' && (
                  <View style={styles.thinkingRow}>
                    <Text style={styles.thinkingText}>{'…'}</Text>
                  </View>
                )}
              </ScrollView>

              {/* ── Text input bar — only visible inside the chat panel ─────── */}
              <View style={styles.chatInputRow}>
                <TextInput
                  style={styles.chatTextInput}
                  value={textInput}
                  onChangeText={setTextInput}
                  placeholder="Type a command..."
                  placeholderTextColor="#888899"
                  returnKeyType="send"
                  onSubmitEditing={() => {
                    if (textInput.trim()) {
                      // Add to chat history immediately for visual feedback
                      setChatMessages(prev => [...prev, {
                        role: 'user', text: textInput.trim(), ts: Date.now()
                      }]);
                      setTimeout(() => chatScrollRef.current?.scrollToEnd({ animated: true }), 100);
                      handleSendText();
                    }
                  }}
                  editable={connectionStatus === 'authenticated'}
                  multiline={false}
                />
                <TouchableOpacity
                  style={[styles.chatSendBtn, !textInput.trim() && { opacity: 0.35 }]}
                  onPress={() => {
                    if (textInput.trim()) {
                      setChatMessages(prev => [...prev, {
                        role: 'user', text: textInput.trim(), ts: Date.now()
                      }]);
                      setTimeout(() => chatScrollRef.current?.scrollToEnd({ animated: true }), 100);
                      handleSendText();
                    }
                  }}
                  disabled={!textInput.trim()}
                >
                  <Text style={styles.chatSendIcon}>↑</Text>
                </TouchableOpacity>
              </View>

            </Animated.View>
          </View>
        </Modal>
      </View>
    </KeyboardAvoidingView>
  );
}

function _actionLabel(actionClass: string, hypothesis: string): string {
  // Never show raw hypothesis text — it's too long and confusing.
  // The full intent is shown in the chat bubble / ttsText.
  switch (actionClass) {
    case 'COMM_SEND':    return 'Send message';
    case 'SCHED_MODIFY': return 'Schedule';
    case 'INFO_RETRIEVE':return 'Look up';
    case 'DOC_EDIT':     return 'Edit doc';
    case 'FIN_TRANS':    return 'Transact';
    case 'SYS_CONFIG':   return 'Settings';
    default:             return 'Approve';  // ← never hypothesis.slice()
  }
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: '#0A0A0F' },
  container: { flex: 1, paddingHorizontal: 20, backgroundColor: '#0A0A0F' },

  // Digital Self modal
  dsModalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.72)', justifyContent: 'center', alignItems: 'center', padding: 24 },
  dsModalCard: { backgroundColor: '#12121E', borderRadius: 20, padding: 28, width: '100%', borderWidth: 1, borderColor: '#2A2A3E' },
  dsModalTitle: { color: '#fff', fontSize: 18, fontWeight: '700', marginBottom: 12 },
  dsModalBody: { color: '#888', fontSize: 14, lineHeight: 21, marginBottom: 24 },
  dsModalBtn: { backgroundColor: '#6C5CE7', borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginBottom: 10 },
  dsModalBtnText: { color: '#fff', fontSize: 15, fontWeight: '700' },
  dsModalSkip: { alignItems: 'center', paddingVertical: 8 },
  dsModalSkipText: { color: '#555568', fontSize: 13 },

  // Disconnected banner
  reconnectBanner: {
    backgroundColor: '#2A1A1A', borderRadius: 10, paddingVertical: 10,
    paddingHorizontal: 16, marginBottom: 8, alignItems: 'center',
    borderWidth: 1, borderColor: '#E74C3C33',
  },
  reconnectText: { color: '#E74C3C', fontSize: 13, fontWeight: '600' },

  topBar: { flexDirection: 'row', alignItems: 'center', marginBottom: 0 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  gear: { fontSize: 22, color: '#555568' },

  menuOverlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 100 },
  menuBackdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.5)' },
  menuPanel: { position: 'absolute', top: 56, right: 16, backgroundColor: '#1A1A2E', borderRadius: 14, paddingVertical: 8, minWidth: 200, borderWidth: 1, borderColor: '#2A2A3E', shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 8, elevation: 10 },
  menuItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: 14, paddingHorizontal: 20 },
  menuIcon: { fontSize: 18, marginRight: 14, width: 24, textAlign: 'center' },
  menuText: { color: '#D0D0E0', fontSize: 16 },
  menuDivider: { height: 1, backgroundColor: '#2A2A3E', marginVertical: 4, marginHorizontal: 16 },

  logoArea: { alignItems: 'center', paddingTop: 4, paddingBottom: 0 },
  logo: { width: 150, height: 150 },

  pipelineCard: { backgroundColor: 'rgba(20, 20, 34, 0.75)', borderRadius: 16, paddingVertical: 18, paddingHorizontal: 22, marginHorizontal: 16, borderWidth: 1, borderColor: '#1E1E2E' },
  pipelineCardIdle: { borderColor: '#1A1A28' },
  pipelineIdleInner: { alignItems: 'center', paddingVertical: 4 },
  pipelineIdleTitle: { color: '#D0D0E0', fontSize: 16, fontWeight: '600', textAlign: 'center' },
  pipelineIdleSubtext: { color: '#555568', fontSize: 15, textAlign: 'center', marginTop: 4, lineHeight: 22 },
  pipelineActiveInner: { alignItems: 'center' },
  pipelineTextBlock: { flex: 1 },
  pipelineActiveText: { color: '#E0E0F0', fontSize: 15, fontWeight: '600', lineHeight: 22 },
  pipelineSubStatus: { color: '#6C63FF', fontSize: 13, marginTop: 2, fontStyle: 'italic' },
  pipelineStepNum: { color: '#555568', fontSize: 12, marginTop: 4 },
  pipelineBarBg: { height: 3, backgroundColor: '#1A1A28', borderRadius: 2, marginTop: 10, overflow: 'hidden', width: '100%' },
  pipelineBarFill: { height: '100%', backgroundColor: '#6C63FF', borderRadius: 2 },

  middleZone: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  pipelineWrapper: { alignItems: 'flex-start', width: '100%', paddingHorizontal: 20 },
  pipelineSpinner: { marginBottom: 12 },

  // Sequential live activity feed
  activityFeed: { width: '100%', paddingVertical: 4, maxHeight: 120 },
  activityDone: { flexDirection: 'row', alignItems: 'center', paddingVertical: 5 },
  activityDoneTick: { color: '#4CAF50', fontSize: 13, marginRight: 10, fontWeight: '700' },
  activityDoneLabel: { color: '#555568', fontSize: 13, fontWeight: '500' },
  activityActive: { flexDirection: 'row', alignItems: 'flex-start', paddingVertical: 6, marginTop: 2 },
  activitySpinner: { marginRight: 10, marginTop: 3 },
  activityActiveText: { flex: 1 },

  // Controls
  controlArea: { alignItems: 'center', paddingHorizontal: 20, paddingTop: 8 },

  // ── Bottom bar — fixed row below Kill/Approve ───────────────────────────
  // Left zone reserved for future quick-actions. Right = Chat button.
  bottomBar:     { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingTop: 12, paddingBottom: 8 },
  bottomBarLeft: { flex: 1 },
  chatBtn:       { width: 52, height: 52, borderRadius: 26, backgroundColor: '#1A1A2E', alignItems: 'center', justifyContent: 'center', borderWidth: 1.5, borderColor: '#333350' },
  chatBtnActive: { backgroundColor: '#1E1040', borderColor: '#6C5CE7', elevation: 6 },
  chatBtnIcon:   { fontSize: 24 },
  chatBadge: {
    position: 'absolute', top: 6, right: 6,
    width: 10, height: 10, borderRadius: 5,
    backgroundColor: '#00D68F',
    borderWidth: 2, borderColor: '#0A0A14',
  },

  // ── Chat Modal ──────────────────────────────────────────────────────────
  chatModalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.88)',
  },
  chatModalSheet: {
    flex: 1,
    backgroundColor: '#0A0A14',
    borderTopLeftRadius: 24, borderTopRightRadius: 24,
    borderTopWidth: 1, borderColor: '#1E1E32',
    paddingBottom: 32,
  },
  chatHandle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: '#2A2A42',
    alignSelf: 'center', marginTop: 10, marginBottom: 4,
  },
  chatModalHeader: {
    flexDirection: 'row', alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: '#131326',
    backgroundColor: '#0A0A14',
  },
  chatModalTitle: { color: '#E0E0F0', fontSize: 16, fontWeight: '700', letterSpacing: 0.3 },
  chatCloseBtn: { padding: 4 },
  chatCloseText: { color: '#44445A', fontSize: 20, fontWeight: '300' },
  chatScrollView: { flex: 1 },
  chatScrollContent: { padding: 16, gap: 12 },

  assistantBubble: {
    backgroundColor: '#111128', borderRadius: 16, borderTopLeftRadius: 4,
    padding: 14, maxWidth: '88%',
    borderWidth: 1, borderColor: '#1E1E36',
  },
  assistantLabel: { color: '#6C5CE7', fontSize: 11, fontWeight: '700', marginBottom: 4 },
  assistantText: { color: '#C8C8E0', fontSize: 15, lineHeight: 22 },

  userBubble: {
    backgroundColor: '#16162A', borderRadius: 16, borderTopRightRadius: 4,
    padding: 14, alignSelf: 'flex-end', maxWidth: '88%',
    borderWidth: 1, borderColor: '#2A2A42',
  },
  userLabel: { color: '#6C5CE7', fontSize: 11, fontWeight: '700', marginBottom: 4, textAlign: 'right', opacity: 0.7 },
  userText: { color: '#E8E8F8', fontSize: 15, lineHeight: 22 },

  chatInputRow:   { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 10, borderTopWidth: 1, borderTopColor: '#1E1E2E', backgroundColor: '#0C0C1A' },
  chatTextInput:  { flex: 1, backgroundColor: '#111', borderWidth: 1, borderColor: '#2A2A3E', borderRadius: 22, paddingHorizontal: 16, paddingVertical: 10, color: '#E0E0E8', fontSize: 15 },
  chatSendBtn:    { width: 40, height: 40, borderRadius: 20, backgroundColor: '#6C5CE7', alignItems: 'center', justifyContent: 'center' },
  chatSendIcon:   { color: '#fff', fontSize: 18, fontWeight: '700' },
  thinkingText: { color: '#6C5CE7', fontSize: 28, letterSpacing: 4 },
  thinkingRow: { alignItems: 'center' as const, paddingVertical: 8 },
  resultBubble: { backgroundColor: '#0D2B1A', borderRadius: 12, padding: 12, marginBottom: 10, borderLeftWidth: 3, borderLeftColor: '#00D68F' },
  resultLabel:  { color: '#00D68F', fontSize: 11, fontWeight: '700', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  resultText:   { color: '#C0E0D0', fontSize: 14, lineHeight: 20 },

  // Siri-style waveform inside the mic button
  waveContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    height: 48,
  },
  waveBar: {
    width: 5,
    borderRadius: 3,
    backgroundColor: 'rgba(255,255,255,0.95)',
  },

  // Minimal state label below the button
  vadListeningLabel: {
    color: '#6C5CE7', fontSize: 11, letterSpacing: 0.8,
    marginBottom: 10, textTransform: 'lowercase',
  },

  micButton: {
    width: 90, height: undefined, aspectRatio: 1, borderRadius: 999,
    minWidth: 90, maxWidth: 90,
    alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden',
  },
  micThinking: { opacity: 0.5 },
  micIcon: { fontSize: 22, color: '#FFFFFF', fontWeight: '800', letterSpacing: 2 },

  secondaryRow: {
    flexDirection: 'row', gap: 12, marginTop: 12, width: '100%',
  },

  killButton: {
    flex: 1, backgroundColor: '#E74C3C', borderRadius: 12,
    paddingVertical: 10,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
  },
  approveButton: {
    flex: 1, backgroundColor: '#00B87A', borderRadius: 12,
    paddingVertical: 10,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
  },
  approveDisabled: { opacity: 0.5 },
  smallBtnIcon: { fontSize: 14, color: '#FFFFFF' },
  smallBtnText: { fontSize: 14, fontWeight: '700', color: '#FFFFFF' },

  // Clarification question card
});

