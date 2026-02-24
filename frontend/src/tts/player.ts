/**
 * TTS Player — text-to-speech and audio-bytes playback.
 *
 * speakFromAudio(): plays real ElevenLabs MP3 bytes via expo-av (primary path).
 * speak():          falls back to expo-speech when no audio bytes available.
 * stop():           interrupts either mode.
 */
import { Audio } from 'expo-av';
// expo-file-system used via require to avoid TypeScript declaration mismatches
const FileSystem = require('expo-file-system/legacy') as any;

let _isSpeaking = false;
let _currentSound: any = null; // expo-av Sound instance (native only)

/**
 * Play audio from base64-encoded bytes (ElevenLabs MP3).
 * Writes to a temp file and plays via expo-av Sound.
 */
export async function speakFromAudio(
  base64Audio: string,
  options?: { onComplete?: () => void },
): Promise<void> {
  await stop();

  // Native: write to temp file, play with expo-av
  try {

    const tempPath = `${FileSystem.documentDirectory}myndlens_tts_${Date.now()}.mp3`;
    await FileSystem.writeAsStringAsync(tempPath, base64Audio, {
      encoding: 'base64',
    });

    // Switch audio mode to playback (not recording)
    await Audio.setAudioModeAsync({
      allowsRecordingIOS: false,
      playsInSilentModeIOS: true,
    });

    const { sound } = await Audio.Sound.createAsync({ uri: tempPath });
    _currentSound = sound;
    _isSpeaking = true;

    sound.setOnPlaybackStatusUpdate((status: any) => {
      if (status.didJustFinish) {
        _isSpeaking = false;
        _currentSound = null;
        sound.unloadAsync().catch(() => {});
        FileSystem.deleteAsync(tempPath, { idempotent: true }).catch(() => {});
        options?.onComplete?.();
      }
      if (status.error) {
        console.warn('[TTS] Playback error:', status.error);
        _isSpeaking = false;
        _currentSound = null;
        FileSystem.deleteAsync(tempPath, { idempotent: true }).catch(() => {});
        options?.onComplete?.();
      }
    });

    await sound.playAsync();
    console.log('[TTS] Playing ElevenLabs audio');
  } catch (err) {
    console.warn('[TTS] speakFromAudio failed, falling back to expo-speech:', err);
    _isSpeaking = false;
    _currentSound = null;
    options?.onComplete?.();
  }
}

/**
 * Speak text using device TTS (expo-speech). Fallback when no audio bytes.
 */
export async function speak(
  text: string,
  options?: {
    onStart?: () => void;
    onComplete?: () => void;
    rate?: number;
    pitch?: number;
  },
): Promise<void> {
  await stop();

  _speakNative(text, options);
}

/**
 * Stop current speech or audio playback immediately.
 */
export async function stop(): Promise<void> {
  _isSpeaking = false;

  // Stop expo-av Sound if playing
  if (_currentSound) {
    try { await _currentSound.stopAsync(); } catch { /* ignore */ }
    try { await _currentSound.unloadAsync(); } catch { /* ignore */ }
    _currentSound = null;
  }

  try {
    const Speech = require('expo-speech');
    await Speech.stop();
  } catch { /* ignore */ }
}

export function isSpeaking(): boolean {
  return _isSpeaking;
}

// ---- Native (expo-speech) ----
function _speakNative(
  text: string,
  options?: { onStart?: () => void; onComplete?: () => void; rate?: number; pitch?: number },
): void {
  try {
    const Speech = require('expo-speech');
    _isSpeaking = true;
    options?.onStart?.();
    Speech.speak(text, {
      rate: options?.rate || 1.0,
      pitch: options?.pitch || 1.0,
      language: 'en-US',
      onDone: () => { _isSpeaking = false; options?.onComplete?.(); },
      onError: () => { _isSpeaking = false; options?.onComplete?.(); },
    });
  } catch (e) {
    console.error('[TTS] Native speech failed:', e);
    _isSpeaking = false;
    options?.onComplete?.();
  }
}
