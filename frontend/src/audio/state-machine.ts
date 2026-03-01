/**
 * Audio State Machine — controls the voice interaction lifecycle.
 *
 * Spec §3.5 locked FSM (updated for Capture Cycle):
 *   IDLE → LISTENING → CAPTURING → COMMITTING → ACCUMULATING → CAPTURING (loop)
 *   ACCUMULATING → THINKING (on thought_stream_end)
 *   THINKING → RESPONDING → IDLE
 *
 * ACCUMULATING is the capture cycle state:
 *   - Fragment sent to backend for lightweight processing
 *   - Backend sends FRAGMENT_ACK
 *   - Mic restarts → back to CAPTURING for next fragment
 *   - Extended silence (5-8s) → thought_stream_end → THINKING
 */
import { create } from 'zustand';

export type AudioState =
  | 'IDLE'
  | 'LISTENING'
  | 'CAPTURING'
  | 'COMMITTING'
  | 'ACCUMULATING'
  | 'THINKING'
  | 'RESPONDING';

// Valid transitions per spec §3.5
const VALID_TRANSITIONS: Record<AudioState, AudioState[]> = {
  IDLE:          ['LISTENING'],
  LISTENING:     ['CAPTURING', 'IDLE'],
  CAPTURING:     ['COMMITTING', 'ACCUMULATING', 'IDLE', 'RESPONDING'],
  COMMITTING:    ['THINKING', 'IDLE'],
  ACCUMULATING:  ['CAPTURING', 'THINKING', 'IDLE'],  // CAPTURING=next fragment, THINKING=stream end
  THINKING:      ['RESPONDING', 'IDLE', 'LISTENING'],
  RESPONDING:    ['LISTENING', 'IDLE', 'CAPTURING'],
};

interface AudioStore {
  state: AudioState;
  transcript: string;
  partialTranscript: string;
  ttsText: string;
  isSpeaking: boolean;
  chunksSent: number;
  vadActive: boolean;
  vadEnergy: number;
  error: string | null;

  transition: (to: AudioState) => boolean;
  setTranscript: (text: string) => void;
  setPartialTranscript: (text: string) => void;
  setTtsText: (text: string) => void;
  setIsSpeaking: (speaking: boolean) => void;
  incrementChunks: () => void;
  setVadActive: (active: boolean) => void;
  setVadEnergy: (energy: number) => void;
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
  vadActive: false,
  vadEnergy: 0,
  error: null,

  transition: (to: AudioState) => {
    const current = get().state;
    const valid = VALID_TRANSITIONS[current];
    if (valid.includes(to)) {
      set({ state: to, error: null });
      return true;
    }
    console.warn(`[AudioFSM] Invalid transition: ${current} \u2192 ${to}`);
    return false;
  },

  setTranscript: (text) => set({ transcript: text }),
  setPartialTranscript: (text) => set({ partialTranscript: text }),
  setTtsText: (text) => set({ ttsText: text }),
  setIsSpeaking: (speaking) => set({ isSpeaking: speaking }),
  incrementChunks: () => set((s) => ({ chunksSent: s.chunksSent + 1 })),
  setVadActive: (active) => set({ vadActive: active }),
  setVadEnergy: (energy) => set({ vadEnergy: energy }),
  setError: (error) => set({ error }),
  reset: () => set({
    state: 'IDLE',
    transcript: '',
    partialTranscript: '',
    ttsText: '',
    isSpeaking: false,
    chunksSent: 0,
    vadActive: false,
    vadEnergy: 0,
    error: null,
  }),
}));
