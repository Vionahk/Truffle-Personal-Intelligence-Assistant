"""Demo runner using mock hardware to exercise greeting and conversation flows."""
import sys
import os
import time
from threading import Thread

# ensure project modules importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.controller import AssistantController
from modules.mock_hardware import MockCamera, MockMicrophone, MockSpeaker


def demo_flow():
    controller = AssistantController()

    # replace real modules with mocks
    mock_cam = MockCamera()
    mock_mic = MockMicrophone()
    mock_spk = MockSpeaker()

    controller.camera = mock_cam
    controller.microphone = mock_mic
    controller.speaker = mock_spk

    # run controller in background thread
    t = Thread(target=controller.start, daemon=True)
    t.start()

    time.sleep(0.5)
    print("Demo: Simulating person entering frame...")
    mock_cam.simulate_person_enters()

    time.sleep(1.0)
    print("Demo: Simulating user response...")
    mock_mic.simulate_transcription("I'm doing well, thanks. Can you tell me a joke?")

    # give time for LLM response
    time.sleep(5.0)

    print("Demo: Simulating user says I'm done talking...")
    mock_mic.simulate_transcription("I'm done talking")

    time.sleep(2.0)
    print("Demo complete. Stopping controller...")
    controller.stop()
    t.join(timeout=2.0)


if __name__ == '__main__':
    demo_flow()
