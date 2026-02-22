/**
 * TTS Player — text-to-speech and audio-bytes playback.
 *
 * speakFromAudio(): plays real ElevenLabs MP3 bytes via expo-av (primary path).
 * speak():          falls back to expo-speech when no audio bytes available.
 * stop():           interrupts either mode.
 */
import { Platform } from 'react-native';

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

  if (Platform.OS === 'web') {
    // Web: decode base64 → Blob → Object URL → Audio element
    try {
      const binary = atob(base64Audio);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes], { type: 'audio/mpeg' });
      const url = URL.createObjectURL(blob);
      const audio = new window.Audio(url);
      _isSpeaking = true;
      audio.onended = () => {
        _isSpeaking = false;
        URL.revokeObjectURL(url);
        options?.onComplete?.();
      };
      audio.onerror = () => {
        _isSpeaking = false;
        URL.revokeObjectURL(url);
        options?.onComplete?.();
      };
      await audio.play();
    } catch (err) {
      console.warn('[TTS] Web audio playback failed:', err);
      _isSpeaking = false;
      options?.onComplete?.();
    }
    return;
  }

  // Native: write to temp file, play with expo-av
  try {
    const { Audio } = require('expo-av');
    const FileSystem = require('expo-file-system');

    const tempPath = `${FileSystem.cacheDirectory}myndlens_tts_${Date.now()}.mp3`;
    await FileSystem.writeAsStringAsync(tempPath, base64Audio, {
      encoding: FileSystem.EncodingType.Base64,
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

  if (Platform.OS === 'web') {
    _speakWeb(text, options);
  } else {
    _speakNative(text, options);
  }
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

  if (Platform.OS === 'web') {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  } else {
    try {
      const Speech = require('expo-speech');
      await Speech.stop();
    } catch { /* ignore */ }
  }
}

export function isSpeaking(): boolean {
  return _isSpeaking;
}

// ---- Web Speech API ----
function _speakWeb(
  text: string,
  options?: { onStart?: () => void; onComplete?: () => void; rate?: number; pitch?: number },
): void {
  if (typeof window === 'undefined' || !window.speechSynthesis) {
    console.warn('[TTS] Web Speech API not available');
    options?.onComplete?.();
    return;
  }
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = options?.rate || 1.0;
  utterance.pitch = options?.pitch || 1.0;
  utterance.lang = 'en-US';
  utterance.onstart = () => { _isSpeaking = true; options?.onStart?.(); };
  utterance.onend = () => { _isSpeaking = false; options?.onComplete?.(); };
  utterance.onerror = () => { _isSpeaking = false; options?.onComplete?.(); };
  window.speechSynthesis.speak(utterance);
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
