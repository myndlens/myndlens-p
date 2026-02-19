import React, { useEffect, useRef, useCallback, useState } from 'react';
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
  ScrollView,
  Image,
  ActivityIndicator,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { wsClient, WSEnvelope } from '../src/ws/client';
import { useSessionStore } from '../src/state/session-store';
import { useAudioStore, AudioState } from '../src/audio/state-machine';
import { startRecording, stopRecording } from '../src/audio/recorder';
import * as TTS from '../src/tts/player';
import { MicIcon, StopIcon } from '../src/ui/icons';
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

export default function TalkScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const {
    connectionStatus, sessionId,
    setConnectionStatus, setSessionId, setPresenceOk,
    setHeartbeatSeq, setExecuteBlocked, lastExecuteBlockReason,
  } = useSessionStore();
  const {
    state: audioState, transcript, partialTranscript, ttsText, chunksSent,
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
  const micAnim = useRef(new Animated.Value(1)).current;

  // Poll VAD energy during CAPTURING for visual indicator
  useEffect(() => {
    if (audioState !== 'CAPTURING') {
      setLiveEnergy(0);
      return;
    }
    const poll = setInterval(() => setLiveEnergy(vad.lastEnergy), 80);
    return () => clearInterval(poll);
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
        setTtsText(text);
        transition('RESPONDING');
        setIsSpeaking(true);
        TTS.speak(text, {
          onComplete: () => { setIsSpeaking(false); transition('IDLE'); },
        });
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
        router.replace('/loading');
      }),
      wsClient.on('pipeline_stage', (env: WSEnvelope) => {
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
          // VAD auto-stop: user finished speaking — stop recorder, let server transcribe
          console.log('[Talk] VAD triggered auto-stop');
          await stopRecording();
          transition('COMMITTING');
          transition('THINKING');
        },
      );
    } else if (audioState === 'CAPTURING' || audioState === 'LISTENING') {
      await stopRecording();
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
  function handleSendText() {
    if (!textInput.trim() || connectionStatus !== 'authenticated') return;
    Keyboard.dismiss();
    wsClient.send('text_input', { session_id: sessionId, text: textInput.trim() });
    setTranscript(textInput.trim());
    setTextInput('');
    transition('THINKING');
  }

  const connectionDot = connectionStatus === 'authenticated' ? '#00D68F' : '#E74C3C';
  const micColor = audioState === 'CAPTURING' ? '#E74C3C'
    : audioState === 'RESPONDING' ? '#00D68F'
    : audioState === 'THINKING' ? '#FFAA00'
    : '#6C5CE7';
  const isActive = audioState !== 'IDLE';

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <View style={[styles.container, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 8 }]}>

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
                      <Text style={styles.pipelineActiveText}>{stage.activeText}</Text>
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

          {/* Conversation bubbles overlay */}
          {(ttsText || transcript || partialTranscript) && (
            <View style={styles.conversationOverlay}>
              {ttsText ? (
                <View style={styles.assistantBubble}>
                  <Text style={styles.assistantText}>{ttsText}</Text>
                </View>
              ) : null}
              {(transcript || partialTranscript) ? (
                <View style={styles.userBubble}>
                  <Text style={styles.userText}>{partialTranscript || transcript}</Text>
                </View>
              ) : null}
            </View>
          )}

          {audioState === 'THINKING' ? (
            <View style={styles.thinkingDots}>
              <Text style={styles.thinkingText}>{'\u2026'}</Text>
            </View>
          ) : null}
        </View>

        {/* PRIMARY: Large mic button */}
        <View style={styles.controlArea}>
          {/* VAD Energy Bar — visible only during CAPTURING */}
          {audioState === 'CAPTURING' && (
            <View style={styles.vadBar}>
              {[0.003, 0.008, 0.015, 0.03, 0.06].map((threshold, i) => {
                const active = liveEnergy >= threshold;
                return (
                  <View
                    key={i}
                    style={[
                      styles.vadDot,
                      active && styles.vadDotActive,
                      active && { opacity: 0.4 + i * 0.15 },
                    ]}
                  />
                );
              })}
              <Text style={styles.vadLabel}>
                {liveEnergy >= 0.015 ? 'speaking' : 'silence'}
              </Text>
            </View>
          )}
          <Animated.View style={{ transform: [{ scale: micAnim }] }}>
            <TouchableOpacity
              style={[styles.micButton, { backgroundColor: micColor }, audioState === 'THINKING' && styles.micThinking]}
              onPress={handleMic}
              disabled={connectionStatus !== 'authenticated' || audioState === 'THINKING'}
              activeOpacity={0.7}
            >
              {audioState === 'CAPTURING' ? <StopIcon size={32} color="#FFFFFF" /> : <MicIcon size={40} color="#FFFFFF" />}
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
  conversationOverlay: { marginTop: 16, width: '100%', paddingHorizontal: 8 },

  assistantBubble: {
    backgroundColor: '#1A1A2E', borderRadius: 16, borderTopLeftRadius: 4,
    padding: 16, marginBottom: 10, maxWidth: '85%',
  },
  assistantText: { color: '#D0D0E0', fontSize: 16, lineHeight: 24 },

  userBubble: {
    backgroundColor: '#6C5CE722', borderRadius: 16, borderTopRightRadius: 4,
    padding: 16, marginBottom: 10, alignSelf: 'flex-end', maxWidth: '85%',
  },
  userText: { color: '#FFFFFF', fontSize: 16, lineHeight: 24 },

  thinkingDots: { marginBottom: 10 },
  thinkingText: { color: '#6C5CE7', fontSize: 32, letterSpacing: 4 },

  // Controls
  controlArea: { alignItems: 'center', paddingHorizontal: 20, paddingTop: 8 },

  vadBar: {
    flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 14,
  },
  vadDot: {
    width: 10, height: 10, borderRadius: 5,
    backgroundColor: '#2A2A3E',
  },
  vadDotActive: {
    backgroundColor: '#E74C3C',
  },
  vadLabel: {
    fontSize: 11, color: '#555568', marginLeft: 8, letterSpacing: 0.5,
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
});
