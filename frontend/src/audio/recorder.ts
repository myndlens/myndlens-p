/**
 * Audio Recorder — cross-platform audio capture with VAD auto-stop.
 *
 * Native: expo-av records to a local file. VAD drives auto-stop via metering.
 * On stop, the file is read as base64 and returned for a single WS upload.
 *
 * FIX: Removed _startSimulatedRecording from native path. Real audio is now
 * captured by expo-av, read after stop, and sent as one chunk to the server.
 */
import { Platform } from 'react-native';
import { vad } from './vad/local-vad';

export type AudioChunk = {
  data: string; // base64
  seq: number;
  timestamp: number;
  durationMs: number;
};


let _recording = false;
let _stopping = false;  // guard against concurrent stop calls
let _seq = 0;
let _onSpeechEnd: (() => void) | null = null;
let _onEnergy: ((rms: number) => void) | null = null;

// Native expo-av Recording instance
let _expoRecording: any = null;

/**
 * Start audio recording.
 * Native: starts expo-av recording + VAD via metering. No chunks emitted.
 *   Call stopAndGetAudio() when done to retrieve the recorded audio as base64.
 *
 * onSpeechEnd is called when VAD detects end-of-utterance (Siri-like auto-stop).
 */
export async function startRecording(
  onSpeechEnd?: () => void,
  onEnergyCallback?: (rms: number) => void,
): Promise<void> {
  if (_recording) return;

  _recording = true;
  _onSpeechEnd = onSpeechEnd || null;
  _onEnergy = onEnergyCallback || null;
  vad.reset();

  {
    // Native: Use expo-av for real audio capture + VAD via metering.
    // No simulated chunks. Audio is read from the file on stop.
    try {
      const { Audio } = require('expo-av');

      // Clean up any stale recording from a previous interrupted session.
      if (_expoRecording) {
        const _rec3 = _expoRecording;
        _expoRecording = null;
        try { await _rec3.stopAndUnloadAsync(); } catch { /* ignore */ }
      }

      // Permission is requested once at Talk screen mount (useEffect).
      // Do NOT call requestPermissionsAsync() here — on some devices it triggers
      // GrantPermissionsActivity which causes onHostPause → AppState background
      // handler → stopRecording() + transition(IDLE) mid-recording.
      const { granted } = await Audio.getPermissionsAsync();
      if (!granted) {
        console.warn('[Recorder] Microphone permission not granted');
        _recording = false;
        return;
      }

      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const recording = new Audio.Recording();
      // 32kbps mono 16kHz — ideal for STT, keeps file small (<40KB for 10s)
      await recording.prepareToRecordAsync({
        android: {
          extension: '.m4a',
          outputFormat: 2,   // MPEG_4
          audioEncoder: 3,   // AAC
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 32000,
        },
        ios: {
          extension: '.m4a',
          audioQuality: 32,  // medium
          sampleRate: 16000,
          numberOfChannels: 1,
          bitRate: 32000,
          linearPCMBitDepth: 16,
          linearPCMIsBigEndian: false,
          linearPCMIsFloat: false,
        },
        isMeteringEnabled: true,
      });

      // Drive VAD from expo-av metering (100ms updates).
      // Defer _onSpeechEnd via setTimeout to exit the status-update callback cleanly.
      recording.setProgressUpdateInterval(100);
      recording.setOnRecordingStatusUpdate((status: any) => {
        if (!_recording) return;
        if (status.metering !== undefined) {
          const rms = Math.pow(10, status.metering / 20);
          const event = vad.processEnergy(rms);
          if (event === 'speechEnd' && _onSpeechEnd) {
            console.log('[Recorder] VAD: speechEnd detected (native)');
            const cb = _onSpeechEnd;
            _onSpeechEnd = null; // prevent double-fire
            setTimeout(() => cb(), 0);
          }
        }
      });

      await recording.startAsync();
      _expoRecording = recording;
      console.log('[Recorder] Native recording started');
    } catch (err) {
      console.warn('[Recorder] Native recording failed:', (err as Error)?.message || err);
      // Unload the locally-created recording to release expo-av's internal singleton lock.
      // Without this, the next prepareToRecordAsync() throws "Only one Recording object
      // can be prepared at a given time."
      if (_expoRecording) {
        const _rec4 = _expoRecording;
        _expoRecording = null;
        try { await _rec4.stopAndUnloadAsync(); } catch { /* ignore */ }
      }
      _recording = false;
    }
  }
}

/**
 * Stop recording, read the captured audio file, and return it as base64.
 * This is the primary stop method for voice mandates.
 *
 * Returns base64 string of the audio file, or null on failure.
 */
export async function stopAndGetAudio(): Promise<string | null> {
  if (_stopping) return null;  // concurrent stop already in progress
  _stopping = true;
  _recording = false;
  _onSpeechEnd = null;

  // Clear web intervals
  vad.reset();

  // Native: stop recording and read the file
  if (_expoRecording) {
    try {
      const uri = _expoRecording.getURI();
      const _rec1 = _expoRecording;
      _expoRecording = null; // clear before stop — prevents double-stop on OPPO/Android
      await _rec1.stopAndUnloadAsync();

      if (!uri) {
        console.warn('[Recorder] No recording URI available');
        return null;
      }

      const FileSystem = require('expo-file-system/legacy');
      const base64 = await FileSystem.readAsStringAsync(uri, {
        encoding: 'base64',
      });

      // Clean up the temp file
      FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {});

      // Switch audio mode back to playback so TTS can play immediately after
      try {
        const { Audio } = require('expo-av');
        await Audio.setAudioModeAsync({
          allowsRecordingIOS: false,
          playsInSilentModeIOS: true,
        });
      } catch { /* non-critical */ }

      console.log(`[Recorder] Audio read: ${Math.round(base64.length * 0.75 / 1024)}KB`);
      _stopping = false;
      return base64;
    } catch (err) {
      console.warn('[Recorder] stopAndGetAudio failed:', err);
      _expoRecording = null;
    }
  }

  _stopping = false;
  return null;
}

/**
 * Stop recording without reading the audio (for kill-switch / error paths).
 */
export async function stopRecording(): Promise<void> {
  if (_stopping) return;  // concurrent stop already in progress
  _stopping = true;
  _recording = false;
  _onSpeechEnd = null;


  if (_expoRecording) {
    try {
      const _rec2 = _expoRecording;
      _expoRecording = null; // clear before stop
      await _rec2.stopAndUnloadAsync();
    } catch { /* ignore */ }
    _expoRecording = null;
  }
  _stopping = false;
}

export function isRecording(): boolean {
  return _recording;
}

