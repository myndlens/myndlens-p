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

const DEFAULT_CONFIG: VADConfig = {
  energyThreshold: 0.015,
  silenceDurationMs: 2000,
  minSpeechDurationMs: 300,
};

export class LocalVAD {
  private config: VADConfig;
  private _isSpeech: boolean = false;
  private _speechStartTime: number = 0;
  private _silenceStartTime: number = 0;
  private _lastEnergy: number = 0;

  // Web Audio API refs (web only)
  private _analyser: AnalyserNode | null = null;
  private _audioCtx: AudioContext | null = null;
  private _sourceNode: MediaStreamAudioSourceNode | null = null;
  private _dataArray: Float32Array | null = null;

  constructor(config?: Partial<VADConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  get isSpeech(): boolean {
    return this._isSpeech;
  }

  get lastEnergy(): number {
    return this._lastEnergy;
  }

  /**
   * Attach to a MediaStream (web) for real-time energy analysis.
   */
  attachStream(stream: MediaStream): void {
    try {
      this._audioCtx = new AudioContext();
      this._analyser = this._audioCtx.createAnalyser();
      this._analyser.fftSize = 512;
      this._sourceNode = this._audioCtx.createMediaStreamSource(stream);
      this._sourceNode.connect(this._analyser);
      this._dataArray = new Float32Array(this._analyser.fftSize);
      console.log('[VAD] Attached to audio stream');
    } catch (err) {
      console.error('[VAD] Failed to attach stream:', err);
    }
  }

  /**
   * Detach from the stream and cleanup.
   */
  detach(): void {
    if (this._sourceNode) {
      this._sourceNode.disconnect();
      this._sourceNode = null;
    }
    if (this._audioCtx) {
      this._audioCtx.close().catch(() => {});
      this._audioCtx = null;
    }
    this._analyser = null;
    this._dataArray = null;
    this._isSpeech = false;
    this._speechStartTime = 0;
    this._silenceStartTime = 0;
  }

  /**
   * Sample current energy from the live stream (web only).
   * Returns the VAD event.
   */
  sampleStream(): VADEvent {
    if (!this._analyser || !this._dataArray) {
      return 'none';
    }
    this._analyser.getFloatTimeDomainData(this._dataArray as Float32Array<ArrayBuffer>);
    const rms = computeRMS(this._dataArray);
    return this.processEnergy(rms);
  }

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

/**
 * Compute RMS energy from Float32Array (Web Audio time-domain data).
 */
export function computeRMS(data: Float32Array): number {
  let sumSquares = 0;
  for (let i = 0; i < data.length; i++) {
    sumSquares += data[i] * data[i];
  }
  return Math.sqrt(sumSquares / data.length);
}

/**
 * Compute RMS energy from raw audio bytes (assumes 16-bit PCM or normalized).
 */
export function computeRMSFromBytes(bytes: Uint8Array): number {
  if (bytes.length === 0) return 0;
  let sumSquares = 0;
  for (let i = 0; i < bytes.length; i++) {
    // Normalize byte (0-255) to -1..1 range
    const normalized = (bytes[i] - 128) / 128;
    sumSquares += normalized * normalized;
  }
  return Math.sqrt(sumSquares / bytes.length);
}

// Singleton for app-wide use
export const vad = new LocalVAD();
