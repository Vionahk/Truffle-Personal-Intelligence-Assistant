import unittest
import time
from modules.memory_manager import MemoryManager
from core.scheduler import Scheduler


class TestScheduler(unittest.TestCase):
    def test_scheduler_triggers_callback(self):
        mem = MemoryManager(data_dir=".")
        # prepare a medication scheduled for current minute
        now = time.strftime("%H:%M")
        meds = {"medications": [{"id": "tmed1", "name": "TestMed", "dosage": "1 pill", "schedule": [now], "instructions": "with water"}], "taken_log": []}
        mem.save_medications(meds)

        called = {"count": 0, "payload": None}

        def cb(payload):
            called["count"] += 1
            called["payload"] = payload

        sched = Scheduler(mem, cb, poll_interval=1.0)
        sched.start()
        # wait up to 5 seconds for callback
        for _ in range(6):
            if called["count"] > 0:
                break
            time.sleep(1)
        sched.stop()

        self.assertGreater(called["count"], 0)
        self.assertIsNotNone(called["payload"])


if __name__ == '__main__':
    unittest.main()
