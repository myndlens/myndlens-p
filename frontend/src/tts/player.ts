/**
 * TTS Player — text-to-speech playback with interruption.
 *
 * Uses expo-speech on native, Web Speech API on web.
 * Supports interruption: calling stop() cancels current speech.
 */
import { Platform } from 'react-native';

let _isSpeaking = false;

/**
 * Speak text using TTS. Calls onComplete when finished.
 */
export async function speak(
  text: string,
  options?: {
    onStart?: () => void;
    onComplete?: () => void;
    rate?: number;
    pitch?: number;
  }
): Promise<void> {
  // Interrupt any current speech
  await stop();

  if (Platform.OS === 'web') {
    _speakWeb(text, options);
  } else {
    _speakNative(text, options);
  }
}

/**
 * Stop current speech immediately.
 */
export async function stop(): Promise<void> {
  _isSpeaking = false;

  if (Platform.OS === 'web') {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  } else {
    try {
      const Speech = require('expo-speech');
      await Speech.stop();
    } catch {
      // ignore
    }
  }
}

/**
 * Check if currently speaking.
 */
export function isSpeaking(): boolean {
  return _isSpeaking;
}

// ---- Web Speech API ----
function _speakWeb(
  text: string,
  options?: { onStart?: () => void; onComplete?: () => void; rate?: number; pitch?: number }
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

  utterance.onstart = () => {
    _isSpeaking = true;
    options?.onStart?.();
  };

  utterance.onend = () => {
    _isSpeaking = false;
    options?.onComplete?.();
  };

  utterance.onerror = () => {
    _isSpeaking = false;
    options?.onComplete?.();
  };

  window.speechSynthesis.speak(utterance);
}

// ---- Native (expo-speech) ----
function _speakNative(
  text: string,
  options?: { onStart?: () => void; onComplete?: () => void; rate?: number; pitch?: number }
): void {
  try {
    const Speech = require('expo-speech');
    _isSpeaking = true;
    options?.onStart?.();

    Speech.speak(text, {
      rate: options?.rate || 1.0,
      pitch: options?.pitch || 1.0,
      language: 'en-US',
      onDone: () => {
        _isSpeaking = false;
        options?.onComplete?.();
      },
      onError: () => {
        _isSpeaking = false;
        options?.onComplete?.();
      },
    });
  } catch (e) {
    console.error('[TTS] Native speech failed:', e);
    _isSpeaking = false;
    options?.onComplete?.();
  }
}
