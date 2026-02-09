import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Platform,
  ScrollView,
  KeyboardAvoidingView,
  Keyboard,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { wsClient, WSEnvelope } from '../src/ws/client';
import { useSessionStore } from '../src/state/session-store';
import { useAudioStore, AudioState } from '../src/audio/state-machine';
import { startRecording, stopRecording, isRecording } from '../src/audio/recorder';
import * as TTS from '../src/tts/player';

const STATE_COLORS: Record<AudioState, string> = {
  IDLE: '#333340',
  LISTENING: '#6C5CE7',
  CAPTURING: '#E74C3C',
  THINKING: '#FFAA00',
  RESPONDING: '#00D68F',
};

const STATE_LABELS: Record<AudioState, string> = {
  IDLE: 'Tap to speak',
  LISTENING: 'Listening...',
  CAPTURING: 'Recording',
  THINKING: 'Processing...',
  RESPONDING: 'Speaking...',
};

export default function TalkScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const {
    connectionStatus,
    sessionId,
    lastHeartbeatSeq,
    presenceOk,
    lastExecuteBlockReason,
    setConnectionStatus,
    setSessionId,
    setHeartbeatSeq,
    setPresenceOk,
    setExecuteBlocked,
  } = useSessionStore();

  const {
    state: audioState,
    transcript,
    partialTranscript,
    ttsText,
    chunksSent,
    error: audioError,
    transition,
    setTranscript,
    setPartialTranscript,
    setTtsText,
    setIsSpeaking,
    incrementChunks,
    setError: setAudioError,
    reset: resetAudio,
  } = useAudioStore();

  const [textInput, setTextInput] = useState('');
  const [statusMessages, setStatusMessages] = useState<string[]>([]);
  const [isConnecting, setIsConnecting] = useState(false);
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const micScaleAnim = useRef(new Animated.Value(1)).current;

  // Pulse animation
  useEffect(() => {
    if (audioState === 'CAPTURING' || audioState === 'LISTENING') {
      const pulse = Animated.loop(
        Animated.sequence([
          Animated.timing(micScaleAnim, { toValue: 1.15, duration: 600, useNativeDriver: true }),
          Animated.timing(micScaleAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
        ])
      );
      pulse.start();
      return () => pulse.stop();
    } else {
      micScaleAnim.setValue(1);
    }
  }, [audioState]);

  // Presence pulse
  useEffect(() => {
    if (connectionStatus === 'authenticated') {
      const pulse = Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 0.4, duration: 2500, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 2500, useNativeDriver: true }),
        ])
      );
      pulse.start();
      return () => pulse.stop();
    }
  }, [connectionStatus]);

  const addStatus = useCallback((msg: string) => {
    setStatusMessages((prev) => [...prev.slice(-14), `[${new Date().toLocaleTimeString()}] ${msg}`]);
  }, []);

  // WS handlers
  useEffect(() => {
    connectWS();

    const unsubs = [
      wsClient.on('heartbeat_ack', (env: WSEnvelope) => {
        setHeartbeatSeq(env.payload.seq);
      }),
      wsClient.on('transcript_partial', (env: WSEnvelope) => {
        const text = env.payload.text || env.payload.message || '';
        setPartialTranscript(text);
        addStatus(`Transcript: "${text}"`);
      }),
      wsClient.on('transcript_final', (env: WSEnvelope) => {
        const text = env.payload.text || env.payload.message || '';
        setTranscript(text);
        setPartialTranscript('');
        addStatus(`Final: "${text}"`);
        transition('THINKING');
      }),
      wsClient.on('tts_audio', (env: WSEnvelope) => {
        const text = env.payload.text || env.payload.message || '';
        setTtsText(text);
        addStatus(`TTS: "${text}"`);
        transition('RESPONDING');
        setIsSpeaking(true);

        TTS.speak(text, {
          onStart: () => setIsSpeaking(true),
          onComplete: () => {
            setIsSpeaking(false);
            transition('IDLE');
          },
        });
      }),
      wsClient.on('execute_blocked', (env: WSEnvelope) => {
        setExecuteBlocked(env.payload.reason);
        addStatus(`BLOCKED: ${env.payload.code}`);
      }),
      wsClient.on('error', (env: WSEnvelope) => {
        addStatus(`ERROR: ${env.payload.code} - ${env.payload.message}`);
      }),
      wsClient.on('session_terminated', () => {
        setConnectionStatus('disconnected');
        setSessionId(null);
        setPresenceOk(false);
        resetAudio();
        addStatus('Session terminated');
      }),
    ];

    return () => {
      unsubs.forEach((u) => u());
      wsClient.disconnect();
      stopRecording();
      TTS.stop();
    };
  }, []);

  async function connectWS() {
    setIsConnecting(true);
    setConnectionStatus('connecting');
    addStatus('Connecting...');
    try {
      await wsClient.connect();
      setConnectionStatus('authenticated');
      setSessionId(wsClient.currentSessionId);
      setPresenceOk(true);
      addStatus(`Connected: ${wsClient.currentSessionId?.slice(0, 8)}...`);
    } catch (err: any) {
      setConnectionStatus('error');
      addStatus(`Failed: ${err.message}`);
    } finally {
      setIsConnecting(false);
    }
  }

  // ---- Mic Button Handler ----
  async function handleMicPress() {
    if (connectionStatus !== 'authenticated') return;

    if (audioState === 'RESPONDING') {
      // Interrupt TTS
      await TTS.stop();
      setIsSpeaking(false);
      transition('IDLE');
      addStatus('TTS interrupted');
      return;
    }

    if (audioState === 'IDLE') {
      // Start listening/recording
      transition('LISTENING');
      transition('CAPTURING');
      addStatus('Recording started');

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
      // Stop recording
      await stopRecording();
      transition('THINKING');
      addStatus(`Recording stopped (${chunksSent} chunks)`);

      // Signal end of stream
      wsClient.send('cancel', { session_id: sessionId });
    }
  }

  // ---- Text Input ----
  function handleSendText() {
    if (!textInput.trim() || connectionStatus !== 'authenticated') return;
    Keyboard.dismiss();

    wsClient.send('text_input', {
      session_id: sessionId,
      text: textInput.trim(),
    });

    addStatus(`Sent: "${textInput.trim()}"`);
    setTextInput('');
    transition('THINKING');
  }

  // ---- Execute ----
  function handleExecute() {
    if (!wsClient.isAuthenticated) return;
    setExecuteBlocked(null);
    addStatus('Execute request...');
    wsClient.sendExecuteRequest('draft-' + Date.now());
  }

  const statusColor = connectionStatus === 'authenticated' ? '#00D68F'
    : connectionStatus === 'connecting' ? '#FFAA00'
    : connectionStatus === 'error' ? '#E74C3C' : '#555568';

  const micColor = STATE_COLORS[audioState];
  const isActive = audioState !== 'IDLE';

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      <View style={[styles.container, { paddingTop: insets.top + 8, paddingBottom: insets.bottom + 8 }]}>
        {/* Top Bar */}
        <View style={styles.topBar}>
          <View style={styles.topBarLeft}>
            <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
            <Text style={styles.statusText}>
              {connectionStatus === 'authenticated' ? 'Connected' : connectionStatus}
            </Text>
            <Text style={styles.hbText}>HB:{lastHeartbeatSeq}</Text>
          </View>
          <TouchableOpacity onPress={() => router.push('/settings')} style={styles.settingsBtn}>
            <Text style={styles.settingsIcon}>{'\u2699'}</Text>
          </TouchableOpacity>
        </View>

        {/* Transcript Area */}
        <View style={styles.transcriptArea}>
          {(transcript || partialTranscript) ? (
            <>
              {partialTranscript ? (
                <Text style={styles.partialText}>{partialTranscript}</Text>
              ) : null}
              {transcript ? (
                <Text style={styles.transcriptText}>{transcript}</Text>
              ) : null}
            </>
          ) : (
            <Text style={styles.placeholderText}>
              {audioState === 'IDLE' ? 'Tap the mic to start speaking' : STATE_LABELS[audioState]}
            </Text>
          )}
          {ttsText ? (
            <View style={styles.ttsBox}>
              <Text style={styles.ttsLabel}>ASSISTANT</Text>
              <Text style={styles.ttsTextContent}>{ttsText}</Text>
            </View>
          ) : null}
        </View>

        {/* Mic Button */}
        <View style={styles.micSection}>
          <Animated.View style={{ transform: [{ scale: micScaleAnim }] }}>
            <TouchableOpacity
              style={[
                styles.micButton,
                { backgroundColor: micColor },
                connectionStatus !== 'authenticated' && styles.micDisabled,
              ]}
              onPress={handleMicPress}
              disabled={connectionStatus !== 'authenticated' || audioState === 'THINKING'}
              activeOpacity={0.7}
            >
              <Text style={styles.micIcon}>
                {audioState === 'CAPTURING' ? '\u23F9' : audioState === 'RESPONDING' ? '\u23F9' : '\uD83C\uDF99'}
              </Text>
            </TouchableOpacity>
          </Animated.View>
          <Text style={[styles.micLabel, { color: micColor }]}>
            {STATE_LABELS[audioState]}
          </Text>
          {chunksSent > 0 && audioState === 'CAPTURING' && (
            <Text style={styles.chunkCount}>{chunksSent} chunks</Text>
          )}
        </View>

        {/* Text Input Fallback */}
        <View style={styles.textInputRow}>
          <TextInput
            style={styles.textInput}
            value={textInput}
            onChangeText={setTextInput}
            placeholder="Or type a message..."
            placeholderTextColor="#555568"
            editable={connectionStatus === 'authenticated'}
            returnKeyType="send"
            onSubmitEditing={handleSendText}
          />
          <TouchableOpacity
            style={[styles.sendBtn, !textInput.trim() && styles.sendBtnDisabled]}
            onPress={handleSendText}
            disabled={!textInput.trim()}
          >
            <Text style={styles.sendBtnText}>{'\u2191'}</Text>
          </TouchableOpacity>
        </View>

        {/* Execute + Block */}
        <View style={styles.executeRow}>
          <TouchableOpacity
            style={[styles.executeBtn, connectionStatus !== 'authenticated' && styles.executeBtnDisabled]}
            onPress={handleExecute}
            disabled={connectionStatus !== 'authenticated'}
          >
            <Text style={styles.executeBtnText}>{'\u25B6'} Execute</Text>
          </TouchableOpacity>
          {lastExecuteBlockReason && (
            <Text style={styles.blockText} numberOfLines={2}>{lastExecuteBlockReason}</Text>
          )}
        </View>

        {/* Log */}
        <ScrollView style={styles.logBox} nestedScrollEnabled>
          {statusMessages.map((msg, i) => (
            <Text key={i} style={styles.logEntry}>{msg}</Text>
          ))}
        </ScrollView>

        {/* Reconnect */}
        {connectionStatus !== 'authenticated' && !isConnecting && (
          <TouchableOpacity style={styles.reconnectBtn} onPress={connectWS}>
            <Text style={styles.reconnectText}>Reconnect</Text>
          </TouchableOpacity>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: '#0A0A0F' },
  container: { flex: 1, paddingHorizontal: 16, backgroundColor: '#0A0A0F' },
  topBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  topBarLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { fontSize: 12, color: '#A0A0B8', fontWeight: '600' },
  hbText: { fontSize: 10, color: '#555568', fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  settingsBtn: { padding: 8 },
  settingsIcon: { fontSize: 20, color: '#8B8B9E' },

  transcriptArea: {
    backgroundColor: '#12121E',
    borderRadius: 12,
    padding: 16,
    minHeight: 100,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#1A1A2E',
  },
  placeholderText: { color: '#555568', fontSize: 15, fontStyle: 'italic', textAlign: 'center', marginTop: 24 },
  partialText: { color: '#8B8B9E', fontSize: 16, lineHeight: 24, fontStyle: 'italic' },
  transcriptText: { color: '#FFFFFF', fontSize: 16, lineHeight: 24, fontWeight: '500' },
  ttsBox: { marginTop: 12, padding: 12, backgroundColor: '#1A1A30', borderRadius: 8, borderLeftWidth: 3, borderLeftColor: '#6C5CE7' },
  ttsLabel: { fontSize: 10, fontWeight: '700', color: '#6C5CE7', letterSpacing: 1, marginBottom: 4 },
  ttsTextContent: { color: '#C0C0D8', fontSize: 14, lineHeight: 20 },

  micSection: { alignItems: 'center', marginBottom: 12 },
  micButton: {
    width: 72,
    height: 72,
    borderRadius: 36,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 6,
  },
  micDisabled: { backgroundColor: '#333340', elevation: 0 },
  micIcon: { fontSize: 28, color: '#FFFFFF' },
  micLabel: { fontSize: 12, fontWeight: '600', marginTop: 6 },
  chunkCount: { fontSize: 10, color: '#555568', marginTop: 2, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },

  textInputRow: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  textInput: {
    flex: 1,
    backgroundColor: '#1A1A2E',
    borderRadius: 24,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 14,
    color: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#2A2A3E',
  },
  sendBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: '#6C5CE7', alignItems: 'center', justifyContent: 'center' },
  sendBtnDisabled: { backgroundColor: '#333340' },
  sendBtnText: { fontSize: 18, color: '#FFFFFF', fontWeight: '700' },

  executeRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  executeBtn: { backgroundColor: '#6C5CE7', borderRadius: 8, paddingVertical: 10, paddingHorizontal: 16 },
  executeBtnDisabled: { backgroundColor: '#333340' },
  executeBtnText: { color: '#FFFFFF', fontSize: 13, fontWeight: '700' },
  blockText: { flex: 1, color: '#E74C3C', fontSize: 11 },

  logBox: {
    flex: 1,
    backgroundColor: '#0D0D18',
    borderRadius: 8,
    padding: 8,
    borderWidth: 1,
    borderColor: '#1A1A2E',
  },
  logEntry: {
    color: '#666680',
    fontSize: 10,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    lineHeight: 16,
  },
  reconnectBtn: { backgroundColor: '#1A1A2E', borderRadius: 8, paddingVertical: 10, alignItems: 'center', marginTop: 8, borderWidth: 1, borderColor: '#2A2A3E' },
  reconnectText: { color: '#6C5CE7', fontSize: 13, fontWeight: '600' },
});
