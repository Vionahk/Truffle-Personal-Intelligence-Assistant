"""Microphone module — Speech-to-Text with silence-aware input capture.

Waits for the user to fully finish speaking (configurable pause_threshold)
before delivering a transcription. This ensures complete sentences and
paragraphs are captured as single inputs, preventing premature responses.
"""

from typing import Optional
from dataclasses import dataclass
from queue import Queue
import threading
import time

try:
    import speech_recognition as sr
except Exception:
    sr = None


@dataclass
class TranscriptionResult:
    text: str
    confidence: float = 1.0
    is_final: bool = True
    timestamp: float = time.time()


class MicrophoneModule:
    def __init__(self, config, stt_engine: str = "google"):
        self.config = config
        self.stt_engine = stt_engine
        self._queue: Queue = Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._recognizer = sr.Recognizer() if sr else None
        self._mic = None

    def start(self) -> bool:
        if sr is None:
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            return True

        try:
            self._mic = sr.Microphone()

            # --- Key silence-detection tuning ---
            # pause_threshold: how long (seconds) of silence after speech before
            # the phrase is considered complete. Higher values let users pause
            # mid-thought without being cut off.
            self._recognizer.pause_threshold = self.config.silence_duration  # 2.0s

            # non_speaking_duration: minimum silence at the start before speech
            # detection begins. Keep low to avoid clipping first words.
            self._recognizer.non_speaking_duration = 0.5

            # Dynamic energy threshold adapts to ambient noise over the session.
            self._recognizer.dynamic_energy_threshold = True

            # Calibrate ambient energy baseline
            with self._mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=1)

            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            print("[MIC] Listening — ready for input.")
            return True

        except Exception as e:
            print(f"[MIC] Init warning: {e}")
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            return False

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def pause(self) -> None:
        """Pause listening (e.g., during TTS playback to prevent feedback)."""
        self._pause_event.set()

    def resume(self) -> None:
        """Resume listening."""
        self._pause_event.clear()

    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def get_transcription(self, timeout: float = None) -> Optional[TranscriptionResult]:
        try:
            return self._queue.get(timeout=timeout)
        except Exception:
            return None

    def clear_queue(self) -> None:
        """Drain any pending transcriptions to prevent stale processing."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                break

    def _listen_loop(self) -> None:
        if sr is None or self._mic is None:
            while not self._stop_event.is_set():
                time.sleep(0.1)
            return

        with self._mic as source:
            while not self._stop_event.is_set():
                # Skip if paused (speaker is playing)
                if self._pause_event.is_set():
                    time.sleep(0.1)
                    continue

                try:
                    # timeout: max seconds to wait for speech to START
                    # phrase_time_limit: max seconds of continuous speech
                    audio = self._recognizer.listen(
                        source,
                        timeout=10.0,
                        phrase_time_limit=self.config.max_recording_duration,
                    )

                    # Try preferred STT engine, fall back to Google
                    text = None
                    if self.stt_engine == "sphinx":
                        try:
                            text = self._recognizer.recognize_sphinx(audio)
                        except Exception:
                            text = None
                    if not text:
                        try:
                            text = self._recognizer.recognize_google(audio)
                        except Exception:
                            text = None

                    if text:
                        result = TranscriptionResult(
                            text=text, confidence=1.0,
                            is_final=True, timestamp=time.time(),
                        )
                        print(f"[MIC] \"{text}\"")
                        self._queue.put(result)

                except sr.WaitTimeoutError:
                    continue
                except Exception:
                    continue
