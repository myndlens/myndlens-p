/**
 * Local Voice Activity Detection — RMS energy-based.
 *
 * Spec §3.2: Local VAD is MANDATORY for UX quality.
 * Only sends audio chunks when voice is detected.
 * Detects end-of-utterance (silence after speech) to trigger stream_end.
 *
 * Algorithm:
 *   1. Compute RMS energy of audio buffer
 *   2. Compare against configurable threshold
 *   3. Track speech/silence transitions
 *   4. Emit "speechStart" when energy crosses above threshold
 *   5. Emit "speechEnd" after SILENCE_DURATION_MS of continuous silence
 */

export type VADEvent = 'speechStart' | 'speechEnd' | 'none';

export interface VADConfig {
  /** RMS threshold (0-1 scale). Below = silence, above = speech. */
  energyThreshold: number;
  /** How many ms of continuous silence before declaring end-of-utterance. */
  silenceDurationMs: number;
  /** Minimum speech duration before we allow silence to end it. */
  minSpeechDurationMs: number;
}

export const DEFAULT_VAD_CONFIG: VADConfig = {
  energyThreshold: 0.015,
  silenceDurationMs: 3500,  // 3.5s — avoids firing on natural thinking pauses mid-thought
  minSpeechDurationMs: 300,
};

export class LocalVAD {
  private config: VADConfig;
  private _isSpeech: boolean = false;
  private _speechStartTime: number = 0;
  private _silenceStartTime: number = 0;
  private _lastEnergy: number = 0;

  // Web Audio API refs (web only)
  private _dataArray: Float32Array | null = null;

  constructor(config?: Partial<VADConfig>) {
    this.config = { ...DEFAULT_VAD_CONFIG, ...config };
  }

  get isSpeech(): boolean {
    return this._isSpeech;
  }

  get lastEnergy(): number {
    return this._lastEnergy;
  }

  /**
   * Detach from the stream and cleanup.
   */




  /**
   * Process an energy value (from any source) and return VAD event.
   * Use this for native platforms where you compute energy yourself.
   */
  processEnergy(rms: number): VADEvent {
    this._lastEnergy = rms;
    const now = Date.now();
    const isAboveThreshold = rms > this.config.energyThreshold;

    if (isAboveThreshold) {
      if (!this._isSpeech) {
        // Transition: silence → speech
        this._isSpeech = true;
        this._speechStartTime = now;
        this._silenceStartTime = 0;
        return 'speechStart';
      }
      // Already in speech, reset silence timer
      this._silenceStartTime = 0;
    } else {
      if (this._isSpeech) {
        // In speech, but silence detected
        if (this._silenceStartTime === 0) {
          this._silenceStartTime = now;
        }

        const speechDuration = now - this._speechStartTime;
        const silenceDuration = now - this._silenceStartTime;

        // Only end if: minimum speech met AND silence long enough
        if (
          speechDuration >= this.config.minSpeechDurationMs &&
          silenceDuration >= this.config.silenceDurationMs
        ) {
          this._isSpeech = false;
          this._speechStartTime = 0;
          this._silenceStartTime = 0;
          return 'speechEnd';
        }
      }
    }

    return 'none';
  }

  /**
   * Process raw audio bytes to compute energy (for chunk-based VAD).
   */
  processChunk(audioBytes: Uint8Array): VADEvent {
    const rms = computeRMSFromBytes(audioBytes);
    return this.processEnergy(rms);
  }

  /**
   * Reset VAD state.
   */
  reset(): void {
    this._isSpeech = false;
    this._speechStartTime = 0;
    this._silenceStartTime = 0;
    this._lastEnergy = 0;
  }
}

export const vad = new LocalVAD();

export function computeRMSFromBytes(bytes: Uint8Array): number {
  let sum = 0;
  const n = Math.floor(bytes.length / 2);
  if (n === 0) return 0;
  for (let i = 0; i < n; i++) {
    const s16 = ((bytes[i * 2 + 1] << 8) | bytes[i * 2]) << 16 >> 16;
    sum += (s16 / 32768) ** 2;
  }
  return Math.sqrt(sum / n);
}
