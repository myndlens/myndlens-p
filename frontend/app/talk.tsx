import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Animated,
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
  { id: 'capture', label: 'Intent captured', activeText: 'Capturing your intent...' },
  { id: 'digital_self', label: 'Enriched with Digital Self', activeText: 'Expanding with your Digital Self...' },
  { id: 'dimensions', label: 'Dimensions extracted', activeText: 'Extracting dimensions...' },
  { id: 'mandate', label: 'Mandate created', activeText: 'Creating mandate artefact...' },
  { id: 'approval', label: 'Oral approval received', activeText: 'Waiting for your approval...' },
  { id: 'agents', label: 'Agents assigned', activeText: 'Assigning agents & skills...' },
  { id: 'skills', label: 'Skills & tools defined', activeText: 'Defining skills & tools...' },
  { id: 'auth', label: 'Authorization granted', activeText: 'Awaiting authorization...' },
  { id: 'executing', label: 'OpenClaw executing', activeText: 'OpenClaw executing your intent...' },
  { id: 'delivered', label: 'Results delivered', activeText: 'Delivering results...' },
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
    if (stageIndex < 2) return 'done';
    if (stageIndex === 2) return 'active';
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

export default function TalkScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const {
    connectionStatus, sessionId,
    setConnectionStatus, setHeartbeatSeq, setExecuteBlocked,
  } = useSessionStore();
  const {
    state: audioState, transcript, partialTranscript, ttsText,
    transition, setTranscript, setPartialTranscript, setTtsText,
    setIsSpeaking, incrementChunks, reset: resetAudio,
  } = useAudioStore();

  const [textInput, setTextInput] = React.useState('');
  const [pendingAction, setPendingAction] = React.useState<string | null>(null);
  const [pendingDraftId, setPendingDraftId] = React.useState<string | null>(null);
  const [menuOpen, setMenuOpen] = React.useState(false);
  const [pipelineStageIndex, setPipelineStageIndex] = React.useState<number>(-1);
  const [pipelineSubStatus, setPipelineSubStatus] = React.useState<string>('');
  const [pipelineProgress, setPipelineProgress] = React.useState<number>(0);
  const [liveEnergy, setLiveEnergy] = useState(0);
  const [chatOpen, setChatOpen] = useState(false);
  const [showDsModal, setShowDsModal] = useState(false);
  const [clarificationQuestion, setClarificationQuestion] = useState<{
    question: string;
    options: string[];
  } | null>(null);

  // Track whether THIS screen is focused — prevents talk.tsx WS handlers
  // from navigating to /loading while the user is in Settings or another screen.
  const isScreenFocused = useRef(true);
  const appInBackground = useRef(false);
  useFocusEffect(useCallback(() => {
    isScreenFocused.current = true;
    return () => { isScreenFocused.current = false; };
  }, []));
  const chatBubbleAnim = useRef(new Animated.Value(1)).current;
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
      } catch { /* graceful fallback for web builds */ }

      // Check DS setup flag — show modal if user has never gone through DS setup.
      // Using a flag (not nodeCount) because a device with no contacts still counts
      // as "set up" — the user consciously went through the wizard.
      try {
        const { getItem } = require('../src/utils/storage');
        const dsSetupDone = await getItem('myndlens_ds_setup_done');
        if (!dsSetupDone || dsSetupDone === 'empty') {
          setShowDsModal(true);
        }
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

  // AppState: detect background → foreground transition
  useEffect(() => {
    const appStateSub = AppState.addEventListener('change', async (nextState) => {
      if (nextState === 'background' || nextState === 'inactive') {
        // ── Going to background ──────────────────────────────────────────────
        appInBackground.current = true;
        // Stop active media to free resources and avoid recording in background
        if (audioState === 'CAPTURING' || audioState === 'LISTENING') {
          await stopRecording().catch(() => {});
          transition('IDLE');
        }
        if (audioState === 'RESPONDING') {
          await TTS.stop().catch(() => {});
        }
      } else if (nextState === 'active') {
        // ── Returning to foreground ──────────────────────────────────────────
        appInBackground.current = false;
        if (!wsClient.isAuthenticated) {
          // WS dropped while in background — reset audio state and show
          // the disconnected banner. The user can tap mic or the banner to reconnect.
          if (audioState === 'CAPTURING' || audioState === 'LISTENING') {
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
          // Navigate to loading for reconnect only if we're sure the session
          // is gone and the app is now in the foreground.
          if (isScreenFocused.current) {
            router.replace('/loading');
          }
        }
      }
    });
    return () => appStateSub.remove();
  }, [audioState]);

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
      wsClient.on('transcript_partial', (env: WSEnvelope) => setPartialTranscript(env.payload.text || '')),
      wsClient.on('transcript_final', (env: WSEnvelope) => {
        setTranscript(env.payload.text || '');
        setPartialTranscript('');
        setClarificationQuestion(null); // clear any pending clarification
        transition('THINKING');
      }),
      wsClient.on('draft_update', (env: WSEnvelope) => {
        const actionClass = env.payload.action_class || '';
        const confidence = env.payload.confidence || 0;
        const draftId = env.payload.draft_id || '';
        const hypothesis = env.payload.hypothesis || '';
        if (confidence > 0.6 && actionClass !== 'DRAFT_ONLY') {
          setPendingAction(_actionLabel(actionClass, hypothesis));
          setPendingDraftId(draftId);
        }
      }),
      wsClient.on('tts_audio', (env: WSEnvelope) => {
        const text = env.payload.text || '';
        const audioBase64: string = env.payload.audio || '';
        const isMock: boolean = env.payload.is_mock ?? true;
        setTtsText(text);
        transition('RESPONDING');
        setIsSpeaking(true);
        const onComplete = () => { setIsSpeaking(false); transition('IDLE'); };
        // Play real ElevenLabs audio if available, else fall back to device TTS
        if (audioBase64 && !isMock) {
          TTS.speakFromAudio(audioBase64, { onComplete });
        } else {
          TTS.speak(text, { onComplete });
        }
      }),
      wsClient.on('clarification_question' as WSMessageType, (env: WSEnvelope) => {
        // Server paused the pipeline and is asking for more info — show options to user
        const question = env.payload.question || '';
        const options: string[] = env.payload.options || [];
        setClarificationQuestion({ question, options });
        console.log('[Talk] Clarification question received:', question);
      }),
      wsClient.on('execute_blocked', (env: WSEnvelope) => {
        if (env.payload.code === 'SUBSCRIPTION_INACTIVE' || env.payload.code === 'PRESENCE_STALE') {
          router.push('/softblock');
        }
        setExecuteBlocked(env.payload.reason);
        setPendingAction(null);
      }),
      wsClient.on('session_terminated', async () => {
        // Clean up all active state before navigating away
        if (audioState === 'CAPTURING' || audioState === 'LISTENING') {
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
        if (isScreenFocused.current) {
          router.replace('/loading');
        }
      }),
      wsClient.on('pipeline_stage' as WSMessageType, (env: WSEnvelope) => {
        const idx = env.payload.stage_index ?? -1;
        const sub = env.payload.sub_status || '';
        const prog = env.payload.progress || 0;
        setPipelineStageIndex(idx);
        setPipelineSubStatus(sub);
        setPipelineProgress(prog);
      }),
    ];
    return () => unsubs.forEach((u) => u());
  }, []);

  // ---- MIC: Start/Stop voice conversation ----
  async function handleMic() {
    if (audioState === 'RESPONDING') {
      await TTS.stop();
      setIsSpeaking(false);
      transition('IDLE');
      return;
    }
    if (audioState === 'IDLE') {
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
      transition('LISTENING');
      transition('CAPTURING');
      await startRecording(
        (chunk) => {
          incrementChunks();
          wsClient.send('audio_chunk', {
            session_id: sessionId, audio: chunk.data,
            seq: chunk.seq, timestamp: chunk.timestamp, duration_ms: chunk.durationMs,
          });
        },
        async () => {
          // VAD auto-stop: user finished speaking
          // 1. Stop recording and read the real audio file
          console.log('[Talk] VAD triggered auto-stop');
          const audioBase64 = await stopAndGetAudio();
          // 2. Send the real audio to the server
          if (audioBase64 && sessionId) {
            wsClient.send('audio_chunk', {
              session_id: sessionId,
              audio: audioBase64,
              seq: 1,
              timestamp: Date.now(),
              duration_ms: 0,
            });
          }
          // 3. Signal server to finalize transcript and run pipeline
          wsClient.send('cancel', { session_id: sessionId, reason: 'vad_end_of_utterance' });
          transition('COMMITTING');
          transition('THINKING');
        },
      );
    } else if (audioState === 'CAPTURING' || audioState === 'LISTENING') {
      // Manual stop: read the real audio and send to server before signalling
      const audioBase64 = await stopAndGetAudio();
      if (audioBase64 && sessionId) {
        wsClient.send('audio_chunk', {
          session_id: sessionId,
          audio: audioBase64,
          seq: 1,
          timestamp: Date.now(),
          duration_ms: 0,
        });
      }
      transition('COMMITTING');
      wsClient.send('cancel', { session_id: sessionId, reason: 'user_stop' });
      transition('THINKING');
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
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
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

        {/* Middle zone — card centered between logo and controls */}
        <View style={styles.middleZone}>

        {/* Clarification Question Card — shown when server needs more context */}
        {clarificationQuestion && (
          <View style={styles.clarifyCard}>
            <Text style={styles.clarifyTitle}>{clarificationQuestion.question}</Text>
            {clarificationQuestion.options.length > 0 && (
              <View style={styles.clarifyOptions}>
                {clarificationQuestion.options.map((opt, i) => (
                  <TouchableOpacity
                    key={i}
                    style={styles.clarifyOption}
                    onPress={() => {
                      setClarificationQuestion(null);
                      wsClient.send('text_input', { session_id: sessionId, text: opt });
                      setTranscript(opt);
                      transition('THINKING');
                    }}
                    activeOpacity={0.8}
                  >
                    <Text style={styles.clarifyOptionText}>{opt}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}
            <Text style={styles.clarifyHint}>Or tap the mic to answer by voice</Text>
          </View>
        )}

        {/* Intent Pipeline — Current Stage Card */}
        {(() => {
            const wsIdx = pipelineStageIndex;
            const activeIndex = wsIdx >= 0 ? wsIdx : PIPELINE_STAGES.findIndex((_, i) => getPipelineState(i, audioState, pendingAction, transcript) === 'active');
            const stage = activeIndex >= 0 ? PIPELINE_STAGES[activeIndex] : null;
            const isIdle = !stage && audioState === 'IDLE';
            return (
              <View style={styles.pipelineWrapper} data-testid="pipeline-progress">
                {!isIdle && (
                  <ActivityIndicator size={28} color="#6C63FF" style={styles.pipelineSpinner} />
                )}
                <View style={[styles.pipelineCard, isIdle && styles.pipelineCardIdle]}>
                  {isIdle ? (
                    <View style={styles.pipelineIdleInner}>
                      <Text style={styles.pipelineIdleTitle}>What's on Your Mind Right Now?</Text>
                      <Text style={styles.pipelineIdleSubtext}>Tap the mic to instruct me.</Text>
                    </View>
                  ) : (
                    <View style={styles.pipelineActiveInner}>
                      <Text style={styles.pipelineActiveText}>{stage?.activeText ?? ''}</Text>
                      {pipelineSubStatus ? (
                        <Text style={styles.pipelineSubStatus}>{pipelineSubStatus}</Text>
                      ) : null}
                      <Text style={styles.pipelineStepNum}>Step {activeIndex + 1} of {PIPELINE_STAGES.length}</Text>
                      <View style={styles.pipelineBarBg}>
                        <View style={[styles.pipelineBarFill, { width: `${pipelineProgress > 0 ? pipelineProgress : ((activeIndex + 1) / PIPELINE_STAGES.length) * 100}%` }]} />
                      </View>
                    </View>
                  )}
                </View>
              </View>
            );
          })()}

          {audioState === 'THINKING' ? (
            <View style={styles.thinkingRow}>
              <Text style={styles.thinkingText}>{'\u2026'}</Text>
            </View>
          ) : null}
        </View>

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

          {/* Secondary: Kill + Approve side by side below mic */}
          <View style={styles.secondaryRow}>
            <TouchableOpacity style={styles.killButton} onPress={handleKill} activeOpacity={0.8}>
              <Text style={styles.smallBtnIcon}>{'\u2716'}</Text>
              <Text style={styles.smallBtnText}>Kill</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.approveButton, !pendingAction && styles.approveDisabled]}
              onPress={handleApprove}
              disabled={!pendingAction}
              activeOpacity={0.8}
            >
              <Text style={styles.smallBtnIcon}>{'\u2714'}</Text>
              <Text style={styles.smallBtnText}>{pendingAction || 'Approve'}</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Text fallback */}
        <View style={styles.textRow}>
          <TextInput
            style={styles.textInput}
            value={textInput}
            onChangeText={setTextInput}
            placeholder="Type instead..."
            placeholderTextColor="#444455"
            returnKeyType="send"
            onSubmitEditing={handleSendText}
            editable={connectionStatus === 'authenticated'}
          />
          {textInput.trim() ? (
            <TouchableOpacity style={styles.sendBtn} onPress={handleSendText}>
              <Text style={styles.sendIcon}>{'\u2191'}</Text>
            </TouchableOpacity>
          ) : null}
        </View>

        {/* ── Floating Chat Bubble — always visible, glows when content present ── */}
        <Animated.View style={[
          styles.chatFAB,
          { transform: [{ scale: chatBubbleAnim }] },
          (ttsText || transcript) && styles.chatFABActive,
        ]}>
          <TouchableOpacity
            onPress={() => setChatOpen(true)}
            style={[styles.chatFABInner, (ttsText || transcript) ? styles.chatFABInnerActive : null]}
            activeOpacity={0.85}
          >
            <Text style={styles.chatFABIcon}>💬</Text>
            {(ttsText || transcript) && !chatOpen && (
              <View style={styles.chatBadge} />
            )}
          </TouchableOpacity>
        </Animated.View>

        {/* ── Chat Modal — slides in full-screen ───────────────────────── */}
        <Modal
          visible={chatOpen}
          animationType="slide"
          transparent
          onRequestClose={() => setChatOpen(false)}
        >
          <View style={styles.chatModalOverlay}>
            <View style={styles.chatModalSheet}>
              {/* Handle bar */}
              <View style={styles.chatHandle} />

              {/* Header */}
              <View style={styles.chatModalHeader}>
                <Text style={styles.chatModalTitle}>Conversation</Text>
                <TouchableOpacity
                  onPress={() => setChatOpen(false)}
                  style={styles.chatCloseBtn}
                  hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                >
                  <Text style={styles.chatCloseText}>✕</Text>
                </TouchableOpacity>
              </View>

              {/* Conversation content */}
              <ScrollView
                style={styles.chatScrollView}
                contentContainerStyle={styles.chatScrollContent}
                showsVerticalScrollIndicator={false}
              >
                {ttsText ? (
                  <View style={styles.assistantBubble}>
                    <Text style={styles.assistantLabel}>MyndLens</Text>
                    <Text style={styles.assistantText}>{ttsText}</Text>
                  </View>
                ) : null}
                {(transcript || partialTranscript) ? (
                  <View style={styles.userBubble}>
                    <Text style={styles.userLabel}>You</Text>
                    <Text style={styles.userText}>{partialTranscript || transcript}</Text>
                  </View>
                ) : null}
                {audioState === 'THINKING' && (
                  <View style={styles.thinkingRow}>
                    <Text style={styles.thinkingText}>{'\u2026'}</Text>
                  </View>
                )}
              </ScrollView>

              {/* Minimise tap area */}
              <TouchableOpacity
                style={styles.chatMinimiseBtn}
                onPress={() => setChatOpen(false)}
              >
                <Text style={styles.chatMinimiseText}>Minimise  ↓</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>
      </View>
    </KeyboardAvoidingView>
  );
}

function _actionLabel(actionClass: string, hypothesis: string): string {
  switch (actionClass) {
    case 'COMM_SEND': return 'Send message';
    case 'SCHED_MODIFY': return 'Schedule';
    case 'INFO_RETRIEVE': return 'Look up';
    case 'DOC_EDIT': return 'Edit doc';
    case 'FIN_TRANS': return 'Transact';
    case 'SYS_CONFIG': return 'Settings';
    default: return hypothesis.slice(0, 20) || 'Proceed';
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
  pipelineActiveText: { color: '#E0E0F0', fontSize: 15, fontWeight: '600', textAlign: 'center', lineHeight: 22 },
  pipelineSubStatus: { color: '#6C63FF', fontSize: 13, textAlign: 'center', marginTop: 2, fontStyle: 'italic' },
  pipelineStepNum: { color: '#555568', fontSize: 12, marginTop: 4, textAlign: 'center' },
  pipelineBarBg: { height: 3, backgroundColor: '#1A1A28', borderRadius: 2, marginTop: 10, overflow: 'hidden', width: '100%' },
  pipelineBarFill: { height: '100%', backgroundColor: '#6C63FF', borderRadius: 2 },

  middleZone: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  pipelineWrapper: { alignItems: 'center', width: '100%' },
  pipelineSpinner: { marginBottom: 12 },

  // Controls
  controlArea: { alignItems: 'center', paddingHorizontal: 20, paddingTop: 8 },

  // ── Floating Chat Bubble ────────────────────────────────────────────────
  chatFAB: {
    position: 'absolute',
    bottom: 120,
    right: 20,
    zIndex: 99,
  },
  chatFABActive: {
    // no additional positioning — glow is on chatFABInner
  },
  chatFABInner: {
    width: 52, height: 52, borderRadius: 26,
    backgroundColor: '#1A1A2E',
    borderWidth: 1.5, borderColor: '#333350',
    alignItems: 'center', justifyContent: 'center',
  },
  chatFABInnerActive: {
    backgroundColor: '#1E1040',
    borderColor: '#6C5CE7',
    shadowColor: '#6C5CE7',
    shadowOffset: { width: 0, height: 0 },
    shadowRadius: 14,
    shadowOpacity: 0.9,
    elevation: 10,
  },
  chatFABIcon: { fontSize: 24 },
  chatBadge: {
    position: 'absolute', top: 6, right: 6,
    width: 10, height: 10, borderRadius: 5,
    backgroundColor: '#00D68F',
    borderWidth: 2, borderColor: '#0A0A14',
  },

  // ── Chat Modal ──────────────────────────────────────────────────────────
  chatModalOverlay: {
    flex: 1, justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.82)',
  },
  chatModalSheet: {
    backgroundColor: '#0A0A14',
    borderTopLeftRadius: 24, borderTopRightRadius: 24,
    borderTopWidth: 1, borderColor: '#1E1E32',
    paddingBottom: 32, maxHeight: '85%', minHeight: '50%',
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

  thinkingRow: { paddingLeft: 4 },
  thinkingText: { color: '#6C5CE7', fontSize: 28, letterSpacing: 4 },

  chatMinimiseBtn: {
    alignItems: 'center', paddingVertical: 14,
    borderTopWidth: 1, borderTopColor: '#131326',
    backgroundColor: '#0A0A14',
  },
  chatMinimiseText: { color: '#333350', fontSize: 13, letterSpacing: 0.5 },

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

  // Text fallback
  textRow: { flexDirection: 'row', gap: 8, marginTop: 10, marginBottom: 12, paddingHorizontal: 0 },
  textInput: {
    flex: 1, backgroundColor: '#14141E', borderRadius: 24,
    paddingHorizontal: 16, paddingVertical: 10, fontSize: 14,
    color: '#FFFFFF', borderWidth: 1, borderColor: '#1E1E2E',
  },
  sendBtn: {
    width: 38, height: 38, borderRadius: 19,
    backgroundColor: '#6C5CE7', alignItems: 'center', justifyContent: 'center',
  },
  sendIcon: { fontSize: 16, color: '#FFFFFF', fontWeight: '700' },

  // Clarification question card
  clarifyCard: {
    backgroundColor: 'rgba(108, 92, 231, 0.12)',
    borderRadius: 16, borderWidth: 1, borderColor: '#6C5CE744',
    paddingVertical: 16, paddingHorizontal: 18,
    marginHorizontal: 16, marginBottom: 14, width: '100%',
  },
  clarifyTitle: { color: '#E0D8FF', fontSize: 15, fontWeight: '600', lineHeight: 22, marginBottom: 10 },
  clarifyOptions: { gap: 8 },
  clarifyOption: {
    backgroundColor: '#1E1A3A', borderRadius: 10, borderWidth: 1,
    borderColor: '#6C5CE766', paddingVertical: 10, paddingHorizontal: 14,
  },
  clarifyOptionText: { color: '#C8C0F8', fontSize: 14, fontWeight: '500' },
  clarifyHint: { color: '#44445A', fontSize: 12, marginTop: 10, textAlign: 'center' },
});
