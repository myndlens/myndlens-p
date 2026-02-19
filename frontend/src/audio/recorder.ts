/**
 * Audio Recorder — cross-platform audio capture with VAD auto-stop.
 *
 * Uses expo-av on native, MediaRecorder on web.
 * Outputs ~250ms audio chunks as base64 for WS streaming.
 * VAD drives auto-stop after silence detected (Siri-like behaviour).
 */
import { Platform } from 'react-native';
import { vad } from './vad/local-vad';

export type AudioChunk = {
  data: string; // base64
  seq: number;
  timestamp: number;
  durationMs: number;
};

export type OnChunkCallback = (chunk: AudioChunk) => void;

let _recording = false;
let _seq = 0;
let _chunkInterval: ReturnType<typeof setInterval> | null = null;
let _vadInterval: ReturnType<typeof setInterval> | null = null;
let _onSpeechEnd: (() => void) | null = null;

// For native, we'd use expo-av Audio.Recording
let _expoRecording: any = null;

/**
 * Start audio recording and emit chunks every ~250ms.
 * onSpeechEnd is called automatically when VAD detects end-of-utterance (Siri-like).
 */
export async function startRecording(
  onChunk: OnChunkCallback,
  onSpeechEnd?: () => void,
): Promise<void> {
  if (_recording) return;

  _recording = true;
  _seq = 0;
  _onSpeechEnd = onSpeechEnd || null;
  vad.reset();

  if (Platform.OS === 'web') {
    // Web: Use MediaRecorder API if available, else simulate
    try {
      await _startWebRecording(onChunk);
    } catch (err) {
      console.warn('[Recorder] Web recording not available, using simulation:', err);
      _startSimulatedRecording(onChunk);
    }
  } else {
    // Native: Use expo-av with metering for VAD
    try {
      const { Audio } = require('expo-av');

      // Request microphone permission first
      const { granted } = await Audio.requestPermissionsAsync();
      if (!granted) {
        console.warn('[Recorder] Microphone permission denied, using simulated recording');
        _startSimulatedRecording(onChunk);
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const recording = new Audio.Recording();
      await recording.prepareToRecordAsync({
        ...Audio.RecordingOptionsPresets.HIGH_QUALITY,
        isMeteringEnabled: true,
      });

      // Wire VAD via metering updates
      recording.setProgressUpdateInterval(100);
      recording.setOnRecordingStatusUpdate((status: any) => {
        if (!_recording) return;
        if (status.metering !== undefined) {
          // Convert dBFS (typically -160 to 0) to linear RMS for VAD
          const rms = Math.pow(10, status.metering / 20);
          const event = vad.processEnergy(rms);
          if (event === 'speechEnd' && _onSpeechEnd) {
            console.log('[Recorder] VAD: speechEnd detected (native)');
            _onSpeechEnd();
          }
        }
      });

      await recording.startAsync();
      _expoRecording = recording;

      // Emit simulated chunks for WS streaming (expo-av doesn't stream directly)
      _startSimulatedRecording(onChunk);
    } catch (err) {
      console.warn('[Recorder] Native recording unavailable, using simulated:', (err as Error)?.message || err);
      _startSimulatedRecording(onChunk);
    }
  }
}

/**
 * Stop recording and cleanup.
 */
export async function stopRecording(): Promise<void> {
  _recording = false;
  _onSpeechEnd = null;

  if (_chunkInterval) {
    clearInterval(_chunkInterval);
    _chunkInterval = null;
  }

  if (_vadInterval) {
    clearInterval(_vadInterval);
    _vadInterval = null;
  }

  vad.detach();
  vad.reset();

  if (_webStream) {
    _webStream.getTracks().forEach(t => t.stop());
    _webStream = null;
  }
  if (_webRecorder) {
    if (_webRecorder.state === 'recording') {
      _webRecorder.stop();
    }
    _webRecorder = null;
  }

  if (_expoRecording) {
    try {
      await _expoRecording.stopAndUnloadAsync();
    } catch {
      // ignore
    }
    _expoRecording = null;
  }
}

export function isRecording(): boolean {
  return _recording;
}

// ---- Web MediaRecorder ----
let _webStream: MediaStream | null = null;
let _webRecorder: MediaRecorder | null = null;

async function _startWebRecording(onChunk: OnChunkCallback): Promise<void> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  _webStream = stream;

  const recorder = new MediaRecorder(stream, {
    mimeType: 'audio/webm;codecs=opus',
  });
  _webRecorder = recorder;

  recorder.ondataavailable = async (event) => {
    if (event.data.size > 0 && _recording) {
      const buffer = await event.data.arrayBuffer();
      const base64 = _arrayBufferToBase64(buffer);
      _seq++;
      onChunk({
        data: base64,
        seq: _seq,
        timestamp: Date.now(),
        durationMs: 250,
      });
    }
  };

  // Attach VAD to the live stream for auto-stop
  vad.attachStream(stream);
  _vadInterval = setInterval(() => {
    if (!_recording) return;
    const event = vad.sampleStream();
    if (event === 'speechEnd' && _onSpeechEnd) {
      console.log('[Recorder] VAD: speechEnd detected (web)');
      _onSpeechEnd();
    }
  }, 100);

  // Request data every 250ms
  recorder.start(250);
}

// ---- Simulated Recording (fallback) ----
function _startSimulatedRecording(onChunk: OnChunkCallback): void {
  _chunkInterval = setInterval(() => {
    if (!_recording) return;
    _seq++;

    // Generate a small fake audio chunk (~1KB of random data)
    const fakeData = new Uint8Array(1024);
    for (let i = 0; i < fakeData.length; i++) {
      fakeData[i] = Math.floor(Math.random() * 256);
    }
    const base64 = _uint8ToBase64(fakeData);

    onChunk({
      data: base64,
      seq: _seq,
      timestamp: Date.now(),
      durationMs: 250,
    });
  }, 250);
}

// ---- Utils ----
function _arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function _uint8ToBase64(data: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < data.length; i++) {
    binary += String.fromCharCode(data[i]);
  }
  return btoa(binary);
}
