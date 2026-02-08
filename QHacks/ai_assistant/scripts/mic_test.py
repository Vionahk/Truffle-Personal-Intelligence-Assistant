"""Microphone test: lists devices and records a short sample, then attempts speech-to-text.

Usage:
  python scripts/mic_test.py

This uses `speech_recognition` (PyAudio) to capture audio. It will print available
microphones and attempt to transcribe a 5-second recording using Google STT.
"""
import time
import speech_recognition as sr


def list_devices():
    try:
        names = sr.Microphone.list_microphone_names()
        print("Available microphone devices:")
        for i, n in enumerate(names):
            print(f"  [{i}] {n}")
    except Exception as e:
        print("Could not list microphone devices:", e)


def record_and_transcribe(device_index=None, duration=5):
    r = sr.Recognizer()
    try:
        with sr.Microphone(device_index=device_index) as src:
            print(f"Recording for {duration} seconds... speak now")
            r.adjust_for_ambient_noise(src, duration=0.5)
            audio = r.record(src, duration=duration)
            print("Recording complete, transcribing...")
            try:
                text = r.recognize_google(audio)
                print("Transcription:", text)
            except sr.UnknownValueError:
                print("STT could not understand audio")
            except sr.RequestError as e:
                print("STT request failed (internet may be required):", e)
    except Exception as e:
        print("Microphone capture failed:", e)


def main():
    list_devices()
    print("")
    # default device
    record_and_transcribe(device_index=None, duration=5)


if __name__ == '__main__':
    main()
