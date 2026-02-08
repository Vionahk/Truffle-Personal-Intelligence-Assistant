"""Run the assistant using real hardware and load personal profile/medications.

This script starts `AssistantController()` and prints a small startup summary
showing the loaded profile and medications. Use Ctrl+C to stop and view a
session summary.
"""
import sys
import os
import time
from threading import Thread

# ensure imports work when running from scripts/
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.controller import AssistantController


def live_run():
    controller = AssistantController()

    # load and display brief profile summary
    profile = controller.memory.load_user_profile()
    meds = controller.memory.load_medications()
    name = profile.get('Viona') or profile.get('viona') or 'viona'
    print(f"Starting Toopy's Care Assistant for: {name}")
    print("Medications loaded:")
    for m in meds.get('medications', []):
        print(f" - {m.get('name')} @ {', '.join(m.get('schedule', []))} ({m.get('dosage')})")

    t = Thread(target=controller.start, daemon=True)
    t.start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("Stopping assistant...")
        controller.stop()
        t.join(timeout=2.0)


if __name__ == '__main__':
    live_run()
