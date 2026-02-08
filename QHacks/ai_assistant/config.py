"""Configuration for the voice assistant.

All tunable parameters live here. Environment variables are loaded
from .env at import time via python-dotenv.
"""

from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Module configs
# ---------------------------------------------------------------------------

@dataclass
class AudioConfig:
    """Microphone / STT settings."""
    sample_rate: int = 16000
    chunk_size: int = 1024
    silence_threshold: float = 0.03
    silence_duration: float = 2.0        # Seconds of silence before phrase is considered complete
    max_recording_duration: float = 60.0  # Max seconds of continuous speech per turn


@dataclass
class TTSConfig:
    """Speaker / TTS settings."""
    engine: str = "gradium"                            # gradium > elevenlabs > pyttsx3 > text-only
    voice_rate: int = 145                            # pyttsx3 speech rate (if used)
    voice_volume: float = 0.9                        # pyttsx3 volume (if used)
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel — warm, calm voice


@dataclass
class LLMConfig:
    """LLM provider settings (provider-specific params read from env)."""
    timeout: float = 15.0
    max_history_length: int = 40


@dataclass
class ConversationConfig:
    """Conversation flow messages and timeouts."""
    greeting_message: str = "Hey. I'm here whenever you're ready."
    goodbye_message: str = "Take care. I'll be here if you need me."
    continue_prompt: str = "I'm still here if there's anything else on your mind."
    still_there_prompt: str = "Take your time. I'm not going anywhere."
    silence_timeout: float = 90.0        # Seconds of silence before first gentle prompt
    greeting_wait_timeout: float = 15.0  # Seconds to wait for user to begin after greeting


# ---------------------------------------------------------------------------
# Phrase lists for intent detection
# ---------------------------------------------------------------------------

TERMINATION_PHRASES = [
    "i'm done talking", "im done talking", "i am done talking",
    "that's all", "thats all", "goodbye", "bye bye",
    "see you later", "talk to you later", "i'm good for now",
    "that's it", "stop listening", "go to sleep",
    "never mind", "nevermind", "okay i'm done", "okay im done",
]

AFFIRMATIVE_RESPONSES = [
    "yes", "yeah", "yep", "sure", "okay", "ok",
    "please", "go ahead", "help me", "yes please",
]

NEGATIVE_RESPONSES = [
    "no", "nope", "nah", "no thanks",
    "i'm good", "im good", "not now", "maybe later",
]
