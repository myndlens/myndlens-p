/**
 * Shared audio format constants.
 * Values are tied to Silero VAD model architecture (16kHz, 16-bit PCM)
 * and Android VOICE_COMMUNICATION audio source enum.
 * Named constants — not env vars — changing them requires a model swap.
 */
export const AUDIO_SAMPLE_RATE       = 16000;
export const AUDIO_BITRATE_MANDATE   = 32000;
export const AUDIO_BITRATE_WAKEWORD  = 256000;
export const AUDIO_CHANNELS          = 1;
export const AUDIO_SOURCE_ANDROID    = 7;   // VOICE_COMMUNICATION — hardware noise suppression
export const AUDIO_PCM_BIT_DEPTH     = 16;
