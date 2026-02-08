"""Simple TTS smoke-test for Windows/Python environments.

Run with: `python scripts/tts_test.py` while your virtualenv is active.
Prints `TTS_OK` on success or `TTS_ERROR` + exception details on failure.
"""
import traceback


def main():
    try:
        import pyttsx3
    except Exception as e:
        print("TTS_ERROR pyttsx3 import failed:", e)
        traceback.print_exc()
        return

    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.say('Hello. This is a quick speaker test from the AI Care Assistant.')
        engine.runAndWait()
        print('TTS_OK')
    except Exception as ex:
        print('TTS_ERROR', ex)
        traceback.print_exc()


if __name__ == '__main__':
    main()
