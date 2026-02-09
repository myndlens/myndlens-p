/**
 * Audio State Machine — controls the voice interaction lifecycle.
 *
 * States: IDLE → LISTENING → CAPTURING → THINKING → RESPONDING → IDLE
 */
import { create } from 'zustand';

export type AudioState = 'IDLE' | 'LISTENING' | 'CAPTURING' | 'THINKING' | 'RESPONDING';

// Valid transitions
const VALID_TRANSITIONS: Record<AudioState, AudioState[]> = {
  IDLE:       ['LISTENING'],
  LISTENING:  ['CAPTURING', 'IDLE'],
  CAPTURING:  ['THINKING', 'LISTENING', 'IDLE'],
  THINKING:   ['RESPONDING', 'IDLE', 'LISTENING'],
  RESPONDING: ['LISTENING', 'IDLE', 'CAPTURING'],
};

interface AudioStore {
  state: AudioState;
  transcript: string;
  partialTranscript: string;
  ttsText: string;
  isSpeaking: boolean;
  chunksSent: number;
  error: string | null;

  transition: (to: AudioState) => boolean;
  setTranscript: (text: string) => void;
  setPartialTranscript: (text: string) => void;
  setTtsText: (text: string) => void;
  setIsSpeaking: (speaking: boolean) => void;
  incrementChunks: () => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useAudioStore = create<AudioStore>((set, get) => ({
  state: 'IDLE',
  transcript: '',
  partialTranscript: '',
  ttsText: '',
  isSpeaking: false,
  chunksSent: 0,
  error: null,

  transition: (to: AudioState) => {
    const current = get().state;
    const valid = VALID_TRANSITIONS[current];
    if (valid.includes(to)) {
      set({ state: to, error: null });
      return true;
    }
    console.warn(`[AudioFSM] Invalid transition: ${current} → ${to}`);
    return false;
  },

  setTranscript: (text) => set({ transcript: text }),
  setPartialTranscript: (text) => set({ partialTranscript: text }),
  setTtsText: (text) => set({ ttsText: text }),
  setIsSpeaking: (speaking) => set({ isSpeaking: speaking }),
  incrementChunks: () => set((s) => ({ chunksSent: s.chunksSent + 1 })),
  setError: (error) => set({ error }),
  reset: () => set({
    state: 'IDLE',
    transcript: '',
    partialTranscript: '',
    ttsText: '',
    isSpeaking: false,
    chunksSent: 0,
    error: null,
  }),
}));
