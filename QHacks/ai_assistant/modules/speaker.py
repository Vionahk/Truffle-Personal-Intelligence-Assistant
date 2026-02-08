"""Speaker module — Text-to-Speech with emotionally adaptive Gradium voice.

Engine priority:
  1. Gradium SDK  — primary (low-latency, emotionally adaptive voice)
  2. ElevenLabs   — secondary fallback
  3. Text-only    — last resort (prints to console)

Emotional voice adaptation (single voice — Abigail):
  One consistent voice identity so the user never feels confused by voice
  changes.  Emotional variation is achieved entirely through Gradium's
  json_config parameters:
    - padding_bonus (speed): slower for distress/sadness, normal for casual
    - temp (expressiveness): lower = stable/calm, higher = lively/warm
    - cfg_coef (voice fidelity): higher keeps Abigail's natural warmth

Audio playback uses pygame (MP3 + WAV) with winsound as WAV-only fallback.
"""

from typing import Optional, Callable, Dict
from queue import Queue
import threading
import asyncio
import time
import os
import tempfile

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests = None

# Pre-import pygame at module level so it's ready immediately
try:
    import pygame
    pygame.mixer.init(frequency=48000, size=-16, channels=1)
    _PYGAME_OK = True
    print("[SPEAKER] pygame mixer initialized (48kHz)")
except Exception as _e:
    _PYGAME_OK = False
    print(f"[SPEAKER] pygame not available: {_e}")

# Gradium SDK
try:
    import gradium
    _HAS_GRADIUM_SDK = True
except ImportError:
    _HAS_GRADIUM_SDK = False


# ---------------------------------------------------------------------------
# Single voice — Abigail
# ---------------------------------------------------------------------------
# "A warm and airy American adult voice that adds a touch of magic and
#  empathy to any story."  The only Gradium voice whose description
#  explicitly mentions EMPATHY — ideal for emotionally intelligent support.
_VOICE_ID = "KRo-uwfno-KcEgBM"   # Abigail
_VOICE_NAME = "Abigail"

# ---------------------------------------------------------------------------
# Emotion → parameter mapping (same voice, different delivery)
# ---------------------------------------------------------------------------
# All entries use Abigail.  Emotional variation comes from:
#   padding_bonus  — speed  (-4 faster … 0 normal … +4 slower)
#   temp           — expressiveness  (0 flat … 0.7 natural … 1.4 very expressive)
#   cfg_coef       — voice fidelity  (1 loose … 2 default … 4 tight)

_EMOTION_PARAMS: Dict[str, Dict] = {
    "distress": {
        # Maximum gentleness: slow, very stable, tight voice fidelity
        "padding_bonus": 1.5,
        "temp": 0.3,
        "cfg_coef": 2.5,
        "desc": "slow & steady",
    },
    "sadness": {
        # Tender pace, stable with slight warmth
        "padding_bonus": 1.0,
        "temp": 0.4,
        "cfg_coef": 2.2,
        "desc": "gentle & warm",
    },
    "anxiety": {
        # Measured, grounding — unhurried, very consistent
        "padding_bonus": 0.8,
        "temp": 0.35,
        "cfg_coef": 2.2,
        "desc": "grounding & calm",
    },
    "anger": {
        # Calm, steady — does not escalate
        "padding_bonus": 0.5,
        "temp": 0.4,
        "cfg_coef": 2.0,
        "desc": "steady & composed",
    },
    "happiness": {
        # Slightly quicker, more expressive — matches positive energy
        "padding_bonus": -0.3,
        "temp": 0.85,
        "cfg_coef": 2.0,
        "desc": "warm & bright",
    },
    "encouragement": {
        # Gently uplifting, balanced expressiveness
        "padding_bonus": -0.2,
        "temp": 0.7,
        "cfg_coef": 2.0,
        "desc": "uplifting",
    },
    "neutral": {
        # Natural conversational baseline
        "padding_bonus": 0.0,
        "temp": 0.7,
        "cfg_coef": 2.0,
        "desc": "natural",
    },
}


class SpeakerModule:
    def __init__(self, config, microphone=None):
        self.config = config
        self.microphone = microphone
        self._text_queue: Queue = Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._speaking = False
        self._speaking_lock = threading.Lock()

        # Gradium (primary TTS — official SDK, single voice: Abigail)
        self.gradium_api_key = os.getenv("GRADIO_API_KEY", "")
        self.gradium_voice_id = os.getenv("GRADIUM_VOICE_ID", _VOICE_ID)
        self.gradium_region = os.getenv("GRADIUM_REGION", "us")
        self._gradium_client = None

        # ElevenLabs (secondary TTS — gentle Rachel voice)
        self.elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY", "")
        self.elevenlabs_voice_id = getattr(
            config, "elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM"
        )
        self.elevenlabs_model = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2")

        # Async event loop for Gradium SDK (runs in background thread)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Async bridge
    # ------------------------------------------------------------------

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create a persistent event loop running in a background thread."""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(
                target=self._loop.run_forever, daemon=True
            )
            self._loop_thread.start()
        return self._loop

    def _run_async(self, coro, timeout: float = 30.0):
        """Run an async coroutine from synchronous code."""
        loop = self._get_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def _get_gradium_client(self):
        """Lazy-init Gradium client."""
        if self._gradium_client is None and self.gradium_api_key:
            self._gradium_client = gradium.client.GradiumClient(
                api_key=self.gradium_api_key
            )
        return self._gradium_client

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

        engines = []
        if _HAS_GRADIUM_SDK and self.gradium_api_key:
            engines.append(f"Gradium ({_VOICE_NAME})")
        if self.elevenlabs_api_key:
            engines.append("ElevenLabs (Rachel)")
        if _PYGAME_OK:
            engines.append("pygame")
        engines.append("winsound")
        print(f"[SPEAKER] Ready — TTS engines: {', '.join(engines)}")
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        try:
            if _PYGAME_OK:
                pygame.mixer.quit()
        except Exception:
            pass
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def is_output_available(self) -> bool:
        return True

    def get_voice_info(self) -> Dict:
        """Get information about the current voice configuration."""
        return {
            "primary_voice": _VOICE_NAME,
            "voice_id": self.gradium_voice_id,
            "engine": "Gradium SDK",
            "requires_api_key": bool(self.gradium_api_key),
            "emotions_supported": list(_EMOTION_PARAMS.keys()),
        }

    def validate_gradium_ready(self) -> bool:
        """Verify that Gradium is properly configured and ready."""
        if not _HAS_GRADIUM_SDK:
            print("[SPEAKER] WARNING: Gradium SDK not available")
            return False
        
        if not self.gradium_api_key:
            print("[SPEAKER] WARNING: GRADIO_API_KEY not set")
            return False
        
        client = self._get_gradium_client()
        if client is None:
            print("[SPEAKER] WARNING: Failed to initialize Gradium client")
            return False
        
        print(f"[SPEAKER] ✓ Gradium ready ({_VOICE_NAME}, {len(_EMOTION_PARAMS)} emotions)")
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def speak(self, text: str, callback: Optional[Callable] = None,
              emotion: str = "neutral") -> None:
        """Queue text for speech with optional emotion for voice adaptation.

        emotion: one of "distress", "sadness", "anxiety", "anger",
                 "happiness", "encouragement", "neutral"
        """
        if not text or not text.strip():
            return
        self._text_queue.put((text, callback, emotion))

    def is_speaking(self) -> bool:
        with self._speaking_lock:
            return self._speaking

    def wait_until_done(self, timeout: float = None) -> bool:
        start = time.time()
        while True:
            if self._text_queue.empty() and not self.is_speaking():
                time.sleep(0.2)
                return True
            time.sleep(0.1)
            if timeout and (time.time() - start) > timeout:
                return False

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._text_queue.get(timeout=0.5)
                # Handle both old (text, callback) and new (text, callback, emotion) formats
                if len(item) == 3:
                    text, callback, emotion = item
                else:
                    text, callback = item
                    emotion = "neutral"

                with self._speaking_lock:
                    self._speaking = True
                try:
                    self._synthesize(text, emotion)
                except Exception as e:
                    print(f"[SPEAKER] CRITICAL synthesis error: {e}")
                with self._speaking_lock:
                    self._speaking = False
                if callback:
                    try:
                        callback()
                    except Exception:
                        pass
            except Exception:
                continue

    # ------------------------------------------------------------------
    # Synthesis pipeline
    # ------------------------------------------------------------------

    def _synthesize(self, text: str, emotion: str = "neutral") -> None:
        """Try each TTS engine in order until one succeeds."""
        # 1. Gradium (PRIMARY — emotionally adaptive voice)
        if _HAS_GRADIUM_SDK and self.gradium_api_key:
            try:
                if self._gradium(text, emotion):
                    return
            except Exception as e:
                print(f"[SPEAKER] Gradium crashed: {e}")

        # 2. ElevenLabs (secondary fallback — emotion mapped to voice settings)
        if self.elevenlabs_api_key and requests:
            try:
                if self._elevenlabs(text, emotion):
                    return
            except Exception as e:
                print(f"[SPEAKER] ElevenLabs crashed: {e}")

        # 3. No TTS engine worked
        print(f"[SPEAKER] WARNING: All TTS engines failed for: \"{text[:60]}...\"")
        print(f"[SPEAKER] [SPOKEN TEXT] {text}")

    # ------------------------------------------------------------------
    # Gradium TTS — emotionally adaptive voice
    # ------------------------------------------------------------------

    def _gradium(self, text: str, emotion: str = "neutral") -> bool:
        """Primary TTS via Gradium SDK — single voice (Abigail) with emotional
        adaptation through speed, temperature, and voice fidelity parameters."""
        params = _EMOTION_PARAMS.get(emotion, _EMOTION_PARAMS["neutral"])
        desc = params["desc"]

        print(
            f"[SPEAKER] Gradium/{_VOICE_NAME}: "
            f"emotion={emotion} ({desc}), "
            f"speed={params['padding_bonus']:+.1f}, "
            f"temp={params['temp']:.2f}..."
        )
        t0 = time.time()

        client = self._get_gradium_client()
        if client is None:
            print("[SPEAKER] Gradium: client not available")
            return False

        # Same voice every time — only the delivery parameters change
        setup = {
            "model_name": "default",
            "voice_id": self.gradium_voice_id,
            "output_format": "wav",
            "json_config": {
                "padding_bonus": params["padding_bonus"],
                "temp": params["temp"],
                "cfg_coef": params["cfg_coef"],
            },
        }

        async def _synthesize_async():
            result = await client.tts(setup=setup, text=text)
            return result.raw_data

        try:
            audio_bytes = self._run_async(_synthesize_async(), timeout=25.0)
        except Exception as e:
            print(f"[SPEAKER] Gradium SDK error: {e}")
            return False

        if not audio_bytes or len(audio_bytes) < 200:
            print("[SPEAKER] Gradium: empty or too-small response")
            return False

        latency_ms = (time.time() - t0) * 1000
        print(
            f"[SPEAKER] Gradium/{_VOICE_NAME}: "
            f"{len(audio_bytes)} bytes in {latency_ms:.0f}ms"
        )

        # Save and play
        tmp = tempfile.mktemp(suffix=".wav")
        with open(tmp, "wb") as f:
            f.write(audio_bytes)

        self._play_file(tmp)
        print(f"[SPEAKER] Gradium/{_VOICE_NAME}: done")

        try:
            os.remove(tmp)
        except Exception:
            pass
        return True

    # ------------------------------------------------------------------
    # ElevenLabs TTS — emotion-adaptive fallback
    # ------------------------------------------------------------------

    def _elevenlabs(self, text: str, emotion: str = "neutral") -> bool:
        """Secondary TTS via ElevenLabs with emotion-mapped voice settings."""
        # Map emotion to ElevenLabs voice settings
        el_settings = self._elevenlabs_emotion_settings(emotion)

        print(f"[SPEAKER] ElevenLabs: requesting audio (emotion: {emotion})...")
        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/"
            f"{self.elevenlabs_voice_id}"
        )
        headers = {
            "xi-api-key": self.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": self.elevenlabs_model,
            "voice_settings": el_settings,
        }

        r = requests.post(url, headers=headers, json=payload, timeout=20)

        if r.status_code != 200:
            print(f"[SPEAKER] ElevenLabs HTTP {r.status_code}: {r.text[:200]}")
            return False
        if len(r.content) < 200:
            print(f"[SPEAKER] ElevenLabs: response too small ({len(r.content)} bytes)")
            return False

        print(f"[SPEAKER] ElevenLabs: {len(r.content)} bytes (emotion: {emotion})")

        temp = tempfile.mktemp(suffix=".mp3")
        with open(temp, "wb") as f:
            f.write(r.content)

        self._play_file(temp)
        print(f"[SPEAKER] ElevenLabs: done")

        try:
            os.remove(temp)
        except Exception:
            pass
        return True

    @staticmethod
    def _elevenlabs_emotion_settings(emotion: str) -> dict:
        """Map emotion to ElevenLabs voice_settings parameters."""
        if emotion in ("distress", "anxiety"):
            return {"stability": 0.85, "similarity_boost": 0.8, "style": 0.05}
        elif emotion == "sadness":
            return {"stability": 0.8, "similarity_boost": 0.75, "style": 0.1}
        elif emotion == "anger":
            return {"stability": 0.8, "similarity_boost": 0.7, "style": 0.1}
        elif emotion == "happiness":
            return {"stability": 0.6, "similarity_boost": 0.65, "style": 0.3}
        elif emotion == "encouragement":
            return {"stability": 0.65, "similarity_boost": 0.7, "style": 0.25}
        else:  # neutral
            return {"stability": 0.7, "similarity_boost": 0.7, "style": 0.15}

    # ------------------------------------------------------------------
    # Audio file playback — pygame primary, winsound fallback
    # ------------------------------------------------------------------

    def _play_file(self, filepath: str) -> None:
        """Play audio file. Pauses mic during playback to prevent feedback."""
        if self.microphone:
            self.microphone.pause()

        try:
            if not os.path.exists(filepath):
                print(f"[SPEAKER] PLAY ERROR: file missing: {filepath}")
                return
            fsize = os.path.getsize(filepath)
            if fsize < 100:
                print(f"[SPEAKER] PLAY ERROR: file too small ({fsize} bytes)")
                return

            # --- Try pygame (handles MP3 + WAV) ---
            if _PYGAME_OK:
                try:
                    if filepath.endswith(".mp3"):
                        pygame.mixer.music.load(filepath)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.05)
                    else:
                        sound = pygame.mixer.Sound(filepath)
                        channel = sound.play()
                        while channel and channel.get_busy():
                            time.sleep(0.05)
                    return  # Success
                except Exception as e:
                    print(f"[SPEAKER] pygame playback error: {e}")

            # --- Fallback: winsound (WAV only, Windows built-in) ---
            if filepath.endswith(".wav"):
                try:
                    import winsound
                    print(f"[SPEAKER] Using winsound fallback...")
                    winsound.PlaySound(filepath, winsound.SND_FILENAME)
                    return  # Success
                except Exception as e:
                    print(f"[SPEAKER] winsound error: {e}")

            print(f"[SPEAKER] PLAY ERROR: no audio backend could play {filepath}")

        finally:
            if self.microphone:
                self.microphone.resume()
