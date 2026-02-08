"""Simple medication scheduler.

Schedules medication reminders based on medications.json in MemoryManager.
Runs a background thread and calls a callback when a reminder is due.
"""
from threading import Thread, Event
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List


class Scheduler:
    def __init__(self, memory_manager, callback: Callable[[Dict], None], poll_interval: float = 30.0):
        self.memory_manager = memory_manager
        self.callback = callback
        self.poll_interval = poll_interval
        self._stop = Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _now_minutes(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _run(self):
        last_triggered = set()
        while not self._stop.is_set():
            try:
                meds = self.memory_manager.load_medications().get("medications", [])
                now = self._now_minutes()
                for med in meds:
                    schedules = med.get("schedule", [])
                    med_id = med.get("id") or med.get("name")
                    key = f"{med_id}:{now}"
                    if now in schedules and key not in last_triggered:
                        # call callback with medication info
                        try:
                            self.callback({"medication": med, "time": now})
                        except Exception:
                            pass
                        last_triggered.add(key)

                # prune last_triggered for keys older than 2 minutes
                cutoff = (datetime.now() - timedelta(minutes=2)).strftime("%H:%M")
                last_triggered = {k for k in last_triggered if not k.endswith(f":{cutoff}")}
            except Exception:
                pass
            # sleep until next poll
            self._stop.wait(self.poll_interval)
