import React, { useEffect, useRef, useCallback } from 'react';
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
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { wsClient, WSEnvelope } from '../src/ws/client';
import { useSessionStore } from '../src/state/session-store';
import { useAudioStore, AudioState } from '../src/audio/state-machine';
import { startRecording, stopRecording } from '../src/audio/recorder';
import * as TTS from '../src/tts/player';

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
  const [isSessionActive, setIsSessionActive] = React.useState(false);
  const [killTriggered, setKillTriggered] = React.useState(false);
  const micAnim = useRef(new Animated.Value(1)).current;

  // Mic pulse animation
  useEffect(() => {
    if (audioState === 'CAPTURING') {
      const pulse = Animated.loop(
        Animated.sequence([
          Animated.timing(micAnim, { toValue: 1.12, duration: 700, useNativeDriver: true }),
          Animated.timing(micAnim, { toValue: 1, duration: 700, useNativeDriver: true }),
        ])
      );
      pulse.start();
      return () => pulse.stop();
    } else if (audioState === 'RESPONDING') {
      const glow = Animated.loop(
        Animated.sequence([
          Animated.timing(micAnim, { toValue: 1.05, duration: 1200, useNativeDriver: true }),
          Animated.timing(micAnim, { toValue: 0.95, duration: 1200, useNativeDriver: true }),
        ])
      );
      glow.start();
      return () => glow.stop();
    } else {
      micAnim.setValue(1);
    }
  }, [audioState]);

  // WS message handlers
  useEffect(() => {
    const unsubs = [
      wsClient.on('heartbeat_ack', (env: WSEnvelope) => {
        setHeartbeatSeq(env.payload.seq);
      }),
      wsClient.on('transcript_partial', (env: WSEnvelope) => {
        setPartialTranscript(env.payload.text || '');
      }),
      wsClient.on('transcript_final', (env: WSEnvelope) => {
        setTranscript(env.payload.text || '');
        setPartialTranscript('');
        transition('THINKING');
      }),
      wsClient.on('draft_update', (env: WSEnvelope) => {
        // L1 Scout returned a hypothesis — show approval button if actionable
        const hypothesis = env.payload.hypothesis || '';
        const actionClass = env.payload.action_class || '';
        const confidence = env.payload.confidence || 0;
        const draftId = env.payload.draft_id || '';

        if (confidence > 0.6 && actionClass !== 'DRAFT_ONLY') {
          // Derive human-readable action label
          const label = _actionLabel(actionClass, hypothesis);
          setPendingAction(label);
          setPendingDraftId(draftId);
        }
      }),
      wsClient.on('tts_audio', (env: WSEnvelope) => {
        const text = env.payload.text || '';
        setTtsText(text);
        transition('RESPONDING');
        setIsSpeaking(true);
        TTS.speak(text, {
          onComplete: () => {
            setIsSpeaking(false);
            transition('IDLE');
          },
        });
      }),
      wsClient.on('execute_blocked', (env: WSEnvelope) => {
        const code = env.payload.code;
        if (code === 'SUBSCRIPTION_INACTIVE' || code === 'PRESENCE_STALE') {
          router.push('/softblock');
        }
        setExecuteBlocked(env.payload.reason);
        setPendingAction(null);
        setPendingDraftId(null);
      }),
      wsClient.on('execute_ok', () => {
        setPendingAction(null);
        setPendingDraftId(null);
      }),
      wsClient.on('session_terminated', () => {
        setConnectionStatus('disconnected');
        setIsSessionActive(false);
        router.replace('/loading');
      }),
    ];

    return () => {
      unsubs.forEach((u) => u());
    };
  }, []);

  // ---- START: Begin conversation session ----
  function handleStart() {
    setIsSessionActive(true);
    setKillTriggered(false);
    setPendingAction(null);
    setPendingDraftId(null);
    resetAudio();
    setTtsText('');
    setTranscript('');
  }

  // ---- KILL SWITCH: Stop all execution immediately ----
  async function handleKill() {
    setKillTriggered(true);
    setPendingAction(null);
    setPendingDraftId(null);

    // Stop recording if active
    if (audioState === 'CAPTURING' || audioState === 'LISTENING') {
      await stopRecording();
    }
    // Stop TTS
    await TTS.stop();
    setIsSpeaking(false);

    // Cancel on server
    if (sessionId) {
      wsClient.send('cancel', { session_id: sessionId, reason: 'kill_switch' });
    }

    // Reset audio state
    resetAudio();
    setIsSessionActive(false);
  }

  // ---- APPROVE: Instruct OpenClaw to execute ----
  function handleApprove() {
    if (!pendingDraftId || !wsClient.isAuthenticated) return;
    wsClient.sendExecuteRequest(pendingDraftId);
    setPendingAction(null);
    setPendingDraftId(null);
  }

  // ---- Mic press ----
  async function handleMic() {
    if (!isSessionActive) return;

    if (audioState === 'RESPONDING') {
      await TTS.stop();
      setIsSpeaking(false);
      transition('IDLE');
      return;
    }

    if (audioState === 'IDLE') {
      transition('LISTENING');
      transition('CAPTURING');
      await startRecording((chunk) => {
        incrementChunks();
        wsClient.send('audio_chunk', {
          session_id: sessionId,
          audio: chunk.data,
          seq: chunk.seq,
          timestamp: chunk.timestamp,
          duration_ms: chunk.durationMs,
        });
      });
    } else if (audioState === 'CAPTURING' || audioState === 'LISTENING') {
      await stopRecording();
      transition('COMMITTING');
      wsClient.send('cancel', { session_id: sessionId, reason: 'user_stop' });
      transition('THINKING');
    }
  }

  // ---- Text send ----
  function handleSendText() {
    if (!textInput.trim() || connectionStatus !== 'authenticated' || !isSessionActive) return;
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

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <View style={[styles.container, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 8 }]}>

        {/* Top bar */}
        <View style={styles.topBar}>
          <View style={[styles.dot, { backgroundColor: connectionDot }]} />
          <View style={{ flex: 1 }} />
          <TouchableOpacity onPress={() => router.push('/settings')} hitSlop={{ top: 16, bottom: 16, left: 16, right: 16 }}>
            <Text style={styles.gear}>{'\u2699'}</Text>
          </TouchableOpacity>
        </View>

        {/* Conversation area */}
        <ScrollView style={styles.conversation} contentContainerStyle={styles.conversationContent}>
          {ttsText ? (
            <View style={styles.assistantBubble}>
              <Text style={styles.assistantText}>{ttsText}</Text>
            </View>
          ) : null}

          {(transcript || partialTranscript) ? (
            <View style={styles.userBubble}>
              <Text style={styles.userText}>{partialTranscript || transcript}</Text>
            </View>
          ) : !isSessionActive ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyTitle}>Ready</Text>
              <Text style={styles.emptyText}>Tap Start to begin a conversation</Text>
            </View>
          ) : audioState === 'IDLE' ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyText}>Tap the mic to speak</Text>
            </View>
          ) : null}

          {audioState === 'THINKING' ? (
            <View style={styles.thinkingDots}>
              <Text style={styles.thinkingText}>{'\u2026'}</Text>
            </View>
          ) : null}

          {killTriggered ? (
            <View style={styles.killConfirm}>
              <Text style={styles.killConfirmText}>Execution stopped</Text>
            </View>
          ) : null}
        </ScrollView>

        {/* ============================================ */}
        {/*  3 PRIMARY CONTROLS                         */}
        {/* ============================================ */}

        {/* 3. APPROVAL BUTTON — appears only when L1 has an actionable intent */}
        {pendingAction && isSessionActive && !killTriggered ? (
          <TouchableOpacity style={styles.approveButton} onPress={handleApprove} activeOpacity={0.8}>
            <Text style={styles.approveIcon}>{'\u2713'}</Text>
            <Text style={styles.approveText}>{pendingAction}</Text>
          </TouchableOpacity>
        ) : null}

        {/* Mic (visible only during active session) */}
        {isSessionActive && !killTriggered ? (
          <View style={styles.micRow}>
            <Animated.View style={{ transform: [{ scale: micAnim }] }}>
              <TouchableOpacity
                style={[styles.micButton, { backgroundColor: micColor }, audioState === 'THINKING' && styles.micThinking]}
                onPress={handleMic}
                disabled={audioState === 'THINKING'}
                activeOpacity={0.7}
              >
                <Text style={styles.micIcon}>
                  {audioState === 'CAPTURING' ? '\u23F9' : audioState === 'RESPONDING' ? '\u23F9' : '\uD83C\uDF99'}
                </Text>
              </TouchableOpacity>
            </Animated.View>
          </View>
        ) : null}

        {/* Text fallback (visible only during active session) */}
        {isSessionActive && !killTriggered ? (
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
        ) : null}

        {/* 1. START BUTTON + 2. KILL SWITCH */}
        <View style={styles.controlRow}>
          {!isSessionActive ? (
            /* 1. START BUTTON */
            <TouchableOpacity
              style={[styles.startButton, connectionStatus !== 'authenticated' && styles.buttonDisabled]}
              onPress={handleStart}
              disabled={connectionStatus !== 'authenticated'}
              activeOpacity={0.8}
            >
              <Text style={styles.startIcon}>{'\u25B6'}</Text>
              <Text style={styles.startText}>Start</Text>
            </TouchableOpacity>
          ) : (
            /* 2. KILL SWITCH */
            <TouchableOpacity
              style={styles.killButton}
              onPress={handleKill}
              activeOpacity={0.8}
            >
              <Text style={styles.killIcon}>{'\u26D4'}</Text>
              <Text style={styles.killText}>Stop</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

function _actionLabel(actionClass: string, hypothesis: string): string {
  switch (actionClass) {
    case 'COMM_SEND': return 'Send message';
    case 'SCHED_MODIFY': return 'Schedule meeting';
    case 'INFO_RETRIEVE': return 'Look up info';
    case 'DOC_EDIT': return 'Edit document';
    case 'FIN_TRANS': return 'Process transaction';
    case 'SYS_CONFIG': return 'Update settings';
    default: return hypothesis.slice(0, 30) || 'Proceed';
  }
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: '#0A0A0F' },
  container: { flex: 1, paddingHorizontal: 20, backgroundColor: '#0A0A0F' },

  topBar: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  gear: { fontSize: 22, color: '#555568' },

  conversation: { flex: 1 },
  conversationContent: { flexGrow: 1, justifyContent: 'flex-end', paddingBottom: 16 },

  assistantBubble: {
    backgroundColor: '#1A1A2E',
    borderRadius: 16, borderTopLeftRadius: 4,
    padding: 16, marginBottom: 12, maxWidth: '85%',
  },
  assistantText: { color: '#D0D0E0', fontSize: 16, lineHeight: 24 },

  userBubble: {
    backgroundColor: '#6C5CE722',
    borderRadius: 16, borderTopRightRadius: 4,
    padding: 16, marginBottom: 12, alignSelf: 'flex-end', maxWidth: '85%',
  },
  userText: { color: '#FFFFFF', fontSize: 16, lineHeight: 24 },

  emptyState: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  emptyTitle: { color: '#666680', fontSize: 20, fontWeight: '600', marginBottom: 8 },
  emptyText: { color: '#444455', fontSize: 16 },

  thinkingDots: { marginBottom: 12 },
  thinkingText: { color: '#6C5CE7', fontSize: 32, letterSpacing: 4 },

  killConfirm: {
    backgroundColor: '#2D1B1B', borderRadius: 12,
    padding: 14, alignItems: 'center', marginBottom: 12,
    borderWidth: 1, borderColor: '#E74C3C44',
  },
  killConfirmText: { color: '#E74C3C', fontSize: 14, fontWeight: '600' },

  // 3. APPROVAL BUTTON
  approveButton: {
    backgroundColor: '#00D68F',
    borderRadius: 14, paddingVertical: 16,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 10, marginBottom: 12,
  },
  approveIcon: { fontSize: 18, color: '#FFFFFF', fontWeight: '700' },
  approveText: { color: '#FFFFFF', fontSize: 16, fontWeight: '700' },

  // Mic
  micRow: { alignItems: 'center', marginBottom: 12 },
  micButton: {
    width: 64, height: 64, borderRadius: 32,
    alignItems: 'center', justifyContent: 'center',
  },
  micThinking: { opacity: 0.5 },
  micIcon: { fontSize: 24, color: '#FFFFFF' },

  // Text fallback
  textRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
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

  // Control row (Start / Kill)
  controlRow: { marginBottom: 4 },

  // 1. START BUTTON
  startButton: {
    backgroundColor: '#6C5CE7',
    borderRadius: 14, paddingVertical: 16,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 10,
  },
  startIcon: { fontSize: 16, color: '#FFFFFF' },
  startText: { color: '#FFFFFF', fontSize: 17, fontWeight: '700' },

  // 2. KILL SWITCH
  killButton: {
    backgroundColor: '#E74C3C',
    borderRadius: 14, paddingVertical: 16,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 10,
  },
  killIcon: { fontSize: 16, color: '#FFFFFF' },
  killText: { color: '#FFFFFF', fontSize: 17, fontWeight: '700' },

  buttonDisabled: { opacity: 0.4 },
});
