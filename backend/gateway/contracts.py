"""WS protocol contracts — version registry."""

WS_PROTOCOL_VERSION = "v1"

# All supported message types for v1
SUPPORTED_CLIENT_MESSAGES = {
    "auth", "heartbeat", "audio_chunk",
    "execute_request", "cancel", "text_input",
}

SUPPORTED_SERVER_MESSAGES = {
    "auth_ok", "auth_fail", "heartbeat_ack",
    "transcript_partial", "transcript_final",
    "draft_update", "tts_audio",
    "execute_blocked", "execute_ok",
    "error", "session_terminated",
}
