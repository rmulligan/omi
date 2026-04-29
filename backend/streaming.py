# Stubbed functions for local development (omi-fork).
# These replace the real implementations that depend on Firebase, GCS, etc.
# so the pusher's WebSocket handler can run without cloud dependencies.

# Stub: return a default STT service configuration
def get_stt_service_for_language(language: str):
    from utils.speech_to_text.deepgram import STTService
    return (STTService.deepgram, 'en', 'nova-3')


# Stub: return None (no real transcription in local mode)
def process_audio_dg(language: str, audio_data: bytes, conversation_id: str):
    return None
