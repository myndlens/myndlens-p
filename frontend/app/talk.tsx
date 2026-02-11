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
  Image,
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
  const micAnim = useRef(new Animated.Value(1)).current;

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
      wsClient.on('session_terminated', () => {
        setConnectionStatus('disconnected');
        router.replace('/loading');
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
      transition('LISTENING');
      transition('CAPTURING');
      await startRecording((chunk) => {
        incrementChunks();
        wsClient.send('audio_chunk', {
          session_id: sessionId, audio: chunk.data,
          seq: chunk.seq, timestamp: chunk.timestamp, duration_ms: chunk.durationMs,
        });
      });
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
          {/* Logo at top when idle */}
          {!isActive && !ttsText && !transcript ? (
            <View style={styles.logoArea}>
              <Image
                source={require('../assets/images/myndlens-logo.png')}
                style={styles.logo}
                resizeMode="contain"
              />
            </View>
          ) : null}

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

          {audioState === 'THINKING' ? (
            <View style={styles.thinkingDots}>
              <Text style={styles.thinkingText}>{'\u2026'}</Text>
            </View>
          ) : null}
        </ScrollView>

        {/* PRIMARY: Large mic button */}
        <View style={styles.controlArea}>
          <Animated.View style={{ transform: [{ scale: micAnim }] }}>
            <TouchableOpacity
              style={[styles.micButton, { backgroundColor: micColor }, audioState === 'THINKING' && styles.micThinking]}
              onPress={handleMic}
              disabled={connectionStatus !== 'authenticated' || audioState === 'THINKING'}
              activeOpacity={0.7}
            >
              <Text style={styles.micIcon}>
                {audioState === 'CAPTURING' ? '\u23F9' : '\uD83C\uDF99'}
              </Text>
            </TouchableOpacity>
          </Animated.View>

          {/* Secondary: Kill + Approve side by side below mic */}
          <View style={styles.secondaryRow}>
            <TouchableOpacity style={styles.killButton} onPress={handleKill} activeOpacity={0.8}>
              <Text style={styles.smallBtnIcon}>{'\u26D4'}</Text>
              <Text style={styles.smallBtnText}>Stop</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.approveButton, !pendingAction && styles.approveDisabled]}
              onPress={handleApprove}
              disabled={!pendingAction}
              activeOpacity={0.8}
            >
              <Text style={styles.smallBtnIcon}>{'\u2713'}</Text>
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

  topBar: { flexDirection: 'row', alignItems: 'center', marginBottom: 4 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  gear: { fontSize: 22, color: '#555568' },

  conversation: { flex: 1 },
  conversationContent: { flexGrow: 1, justifyContent: 'flex-end', paddingBottom: 8 },

  logoArea: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  logo: { width: 140, height: 140 },

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
  controlArea: { alignItems: 'center', marginBottom: 16, paddingHorizontal: 20 },

  micButton: {
    width: 88, height: 88, borderRadius: 44,
    aspectRatio: 1,
    alignItems: 'center', justifyContent: 'center',
  },
  micThinking: { opacity: 0.5 },
  micIcon: { fontSize: 32, color: '#FFFFFF' },

  secondaryRow: {
    flexDirection: 'row', gap: 12, marginTop: 20, width: '100%',
  },

  killButton: {
    flex: 1, backgroundColor: '#E74C3C', borderRadius: 14,
    paddingVertical: 14,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
  },
  approveButton: {
    flex: 1, backgroundColor: '#00D68F', borderRadius: 14,
    paddingVertical: 14,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
  },
  approveDisabled: { opacity: 0.25 },
  smallBtnIcon: { fontSize: 16, color: '#FFFFFF', fontWeight: '700' },
  smallBtnText: { fontSize: 15, fontWeight: '700', color: '#FFFFFF' },

  // Text fallback
  textRow: { flexDirection: 'row', gap: 8, marginBottom: 8, paddingHorizontal: 0 },
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
