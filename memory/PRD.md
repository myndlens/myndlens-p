# MyndLens — Product Requirements Document

## Original Problem Statement
Build "MyndLens," a sophisticated voice-driven personal assistant (Siri-like UX) for Android.
Core: Privacy-first "Digital Self" on-device PKG. LLM-driven intent parsing (zero hardcoding).
When uncertain, the system engages in conversational clarification.

## Architecture
- **Frontend**: React Native (Expo SDK 54, expo-router), Android production APK via EAS build
- **Backend**: FastAPI + MongoDB + ChromaDB (vector store), WebSocket gateway
- **STT**: Deepgram (nova-2, pre-recorded REST API, batch chunking)
- **TTS**: ElevenLabs → expo-av MP3 playback (primary); expo-speech (fallback)
- **LLM**: Gemini via EMERGENT_LLM_KEY
- **Auth**: ObeGee SSO (HS256 JWT) + legacy MyndLens device-pairing JWT
- **Digital Self PKG**: On-device, stored in expo-secure-store, never leaves device

## Production URLs
- Frontend (EAS production): `EXPO_PUBLIC_BACKEND_URL=https://app.myndlens.com` (stale — needs redeploy)
- Emergent preview backend: `https://openclaw-tenant.preview.emergentagent.com`
- GitHub: `git@github.com:myndlens/myndlens-p.git`

## Key File Map
- `frontend/android/app/src/main/AndroidManifest.xml` — all Android permissions
- `frontend/android/app/src/main/java/com/myndlens/app/MainApplication.kt` — native module registration
- `frontend/app/talk.tsx` — main voice UI + WS handlers
- `frontend/src/audio/recorder.ts` — audio capture + VAD + stopAndGetAudio()
- `frontend/src/audio/vad/local-vad.ts` — energy-based VAD (threshold=0.015, silence=2000ms)
- `frontend/src/audio/state-machine.ts` — FSM: IDLE→LISTENING→CAPTURING→COMMITTING→THINKING→RESPONDING
- `frontend/src/tts/player.ts` — speakFromAudio() (ElevenLabs) + speak() (expo-speech fallback)
- `frontend/src/digital-self/ingester.ts` — contacts (200 cap), calendar, call log ingestion
- `backend/gateway/ws_server.py` — WS auth, audio_chunk, cancel, text_input, execute_request handlers
- `backend/stt/orchestrator.py` — MAX_CHUNK_SIZE_BYTES=512KB, routes to Deepgram or Mock
- `backend/stt/provider/deepgram.py` — batch transcription via Deepgram REST API
- `backend/tts/provider/elevenlabs.py` — ElevenLabs synthesis
- `backend/l1/scout.py` — Gemini intent classification (_mock_l1 still exists)
- `backend/config/settings.py` — MOCK_STT/TTS/LLM flags (all False in prod .env)
- `frontend/eas.json` — EAS build config; production points to app.myndlens.com

## What's Been Implemented

### Feb 2026 — Voice Pipeline Fixes
- **Bug 1 FIXED**: Removed fake `_startSimulatedRecording` from native audio path.
  Real audio now captured via expo-av at 32kbps/16kHz, read as base64 on stop.
- **Bug 2 FIXED**: VAD auto-stop callback now sends `cancel` to server (was missing).
  Server's `_handle_stream_end` now triggers on both VAD and manual stop.
- **Bug 3 FIXED**: `tts_audio` handler now plays ElevenLabs base64 MP3 via expo-av (`speakFromAudio()`).
  expo-speech is now fallback only (when `is_mock=true`).
- **Bug 4 FIXED**: `clarification_question` WS message now handled in talk.tsx.
  UI card shows question + tappable options. Option tap → `text_input` → re-runs pipeline.
- **Contact cap raised**: 50 → 200 in `ingester.ts`.
- **Backend chunk limit raised**: 64KB → 512KB in `stt/orchestrator.py`.
- **expo-file-system v19 installed** (required for `stopAndGetAudio()`).

### Previous Sessions — Android Build Fixes
- Moved all Android permissions to `AndroidManifest.xml` (source of truth)
- Added: WRITE_CALENDAR, ACCESS_BACKGROUND_LOCATION, READ_MEDIA_IMAGES, ACTIVITY_RECOGNITION, BLUETOOTH_CONNECT
- SMS permissions DISABLED (commented out) to bypass Google Play Protect installation block
- Fixed `crypto` polyfill (expo-crypto) and `Buffer` polyfill (Uint8Array)
- Added "Grant Permissions" screen before Digital Self build (DigitalSelfStep.tsx)
- Added AppState listener to auto-refresh permission status

## Prioritized Backlog

### P0 — Blockers
- **EAS Build + Deploy**: Run new `eas build --platform android --profile production` to pick up voice pipeline fixes. Then deploy updated backend to `app.myndlens.com`.
- **Verify voice round-trip**: After new build — tap mic, speak, confirm: Deepgram transcribes, Gemini classifies, ElevenLabs audio plays back.

### P1 — Critical Features
- **THINKING timeout**: If server never responds (empty transcript from Deepgram), client is stuck in THINKING. Add 15s auto-reset to IDLE.
- **Voice clarification response**: `_handle_stream_end` on server doesn't check `_clarification_state`. Voice answers to clarification questions start a fresh pipeline. Fix: check clarification state in `_handle_stream_end`.
- **Verify permissions**: Calendar, Location, Photos after installable build.

### P2 — Improvements
- Re-integrate SMS ingestion (was disabled to bypass Play Protect). Use SMS Retriever API instead of Default SMS App role.
- Remove `_mock_l1` function from `backend/l1/scout.py`.
- Add auth to `/api/onboarding/*` endpoints.

### P3 — Future
- Implement Notification Access (NotificationListenerService)
- Implement Digital Twin Module
- Implement Explainability UI for Digital Self
- Long-term SMS strategy decision
- Fix ObeGee `workspace_slug` incorrect value
- `DigitalSelfStep.tsx` refactor — too large, split into smaller components

## Credentials
- Deepgram API Key: in `backend/.env` as DEEPGRAM_API_KEY
- ElevenLabs API Key: in `backend/.env` as ELEVENLABS_API_KEY  
- Gemini (LLM): EMERGENT_LLM_KEY in `backend/.env`
- Pairing: code generated from ObeGee dashboard
