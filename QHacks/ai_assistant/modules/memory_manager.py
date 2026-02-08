"""Persistent memory manager for cross-session conversational continuity.

Manages:
  - User profile (name, preferences, contacts)
  - Medications and taken log (with schedule checking)
  - Reminders (user-requested, time-based)
  - Activity log
  - Conversation memories (tagged, searchable)
  - User preferences (learned over time)
"""

import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional
import time
from datetime import datetime, timedelta


class MemoryManager:
    def __init__(self, data_dir: str = None):
        base = Path(data_dir) if data_dir else Path(__file__).resolve().parents[1] / "data"
        self.data_dir = base
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.user_profile_path = self.data_dir / "user_profile.json"
        self.medications_path = self.data_dir / "medications.json"
        self.activity_log_path = self.data_dir / "activity_log.json"

        # Initialize files if missing
        if not self.user_profile_path.exists():
            self._write_json(self.user_profile_path, {})
        if not self.medications_path.exists():
            self._write_json(self.medications_path, {"medications": [], "taken_log": []})
        if not self.activity_log_path.exists():
            self._write_json(self.activity_log_path, {})

    # ------------------------------------------------------------------
    # JSON helpers
    # ------------------------------------------------------------------

    def _read_json(self, path: Path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _write_json(self, path: Path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    # ------------------------------------------------------------------
    # User profile
    # ------------------------------------------------------------------

    def load_user_profile(self) -> Dict:
        return self._read_json(self.user_profile_path) or {}

    def save_user_profile(self, profile: Dict) -> None:
        self._write_json(self.user_profile_path, profile)

    # ------------------------------------------------------------------
    # Medications
    # ------------------------------------------------------------------

    def load_medications(self) -> Dict:
        return self._read_json(self.medications_path) or {"medications": [], "taken_log": []}

    def save_medications(self, meds: Dict) -> None:
        self._write_json(self.medications_path, meds)

    def log_medication_taken(
        self,
        medication_id: str,
        scheduled_time: str,
        actual_time: Optional[str] = None,
        status: str = "taken",
        notes: str = "",
    ):
        meds = self.load_medications()
        if actual_time is None:
            actual_time = time.strftime("%Y-%m-%dT%H:%M:%S")
        entry = {
            "medication_id": medication_id,
            "scheduled_time": scheduled_time,
            "actual_time": actual_time,
            "status": status,
            "notes": notes,
        }
        meds.setdefault("taken_log", []).append(entry)
        self.save_medications(meds)

    # ------------------------------------------------------------------
    # Activity log
    # ------------------------------------------------------------------

    def log_event(self, event_type: str, details: str = "", conversation_snippet: str = ""):
        log = self._read_json(self.activity_log_path) or {}
        today = time.strftime("%Y-%m-%d")
        day = log.setdefault(today, {"date": today, "events": [], "mood_logs": [], "summary": ""})
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "event_type": event_type,
            "details": details,
            "conversation_snippet": conversation_snippet,
        }
        day["events"].append(entry)
        self._write_json(self.activity_log_path, log)

    def get_primary_contact(self) -> Optional[Dict]:
        profile = self.load_user_profile()
        contacts = profile.get("emergency_contacts", [])
        for c in contacts:
            if c.get("is_primary"):
                return c
        return contacts[0] if contacts else None

    # ------------------------------------------------------------------
    # Persistent memories (tagged, searchable)
    # ------------------------------------------------------------------

    def _memories_path(self) -> Path:
        return self.data_dir / "memories.json"

    def add_memory(self, content: str, tags: Optional[list] = None, source: str = "assistant") -> None:
        path = self._memories_path()
        data = self._read_json(path) or {"memories": []}
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": source,
            "content": content,
            "tags": tags or [],
        }
        data.setdefault("memories", []).append(entry)
        self._write_json(path, data)

    def get_recent_memories(self, limit: int = 5) -> List[Dict]:
        path = self._memories_path()
        data = self._read_json(path) or {"memories": []}
        mems = data.get("memories", [])
        return list(reversed(mems))[:limit]

    def search_memories(self, query: str) -> List[Dict]:
        path = self._memories_path()
        data = self._read_json(path) or {"memories": []}
        mems = data.get("memories", [])
        q = query.lower()
        return [
            m for m in mems
            if q in m.get("content", "").lower()
            or any(q in t.lower() for t in m.get("tags", []))
        ]

    def get_memories_by_tag(self, tag: str) -> List[Dict]:
        """Retrieve all memories that have a specific tag."""
        path = self._memories_path()
        data = self._read_json(path) or {"memories": []}
        return [m for m in data.get("memories", []) if tag in m.get("tags", [])]

    def clear_memories(self) -> None:
        self._write_json(self._memories_path(), {"memories": []})

    # ------------------------------------------------------------------
    # User preferences (learned over time)
    # ------------------------------------------------------------------

    def _prefs_path(self) -> Path:
        return self.data_dir / "preferences.json"

    def add_preference(self, key: str, value: str) -> None:
        """Store or update a user preference."""
        path = self._prefs_path()
        prefs = self._read_json(path) or {}
        prefs[key] = {
            "value": value,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        self._write_json(path, prefs)

    def get_preferences(self) -> Dict:
        """Get all stored user preferences."""
        path = self._prefs_path()
        return self._read_json(path) or {}

    def get_preference(self, key: str, default: str = "") -> str:
        """Get a single preference value."""
        prefs = self.get_preferences()
        entry = prefs.get(key)
        if entry and isinstance(entry, dict):
            return entry.get("value", default)
        return default

    # ------------------------------------------------------------------
    # Reminders (user-requested, time-based)
    # ------------------------------------------------------------------

    def _reminders_path(self) -> Path:
        return self.data_dir / "reminders.json"

    def add_reminder(
        self,
        content: str,
        remind_time: str = "",
        recurring: bool = False,
        recurrence_interval: str = "",
    ) -> str:
        """Store a reminder. Returns the reminder ID.

        remind_time: "HH:MM" for daily, or "YYYY-MM-DDTHH:MM" for one-time.
        recurrence_interval: "daily", "weekly", etc.
        """
        path = self._reminders_path()
        data = self._read_json(path) or {"reminders": []}
        rid = f"rem-{uuid.uuid4().hex[:8]}"
        entry = {
            "id": rid,
            "content": content,
            "remind_time": remind_time,
            "recurring": recurring,
            "recurrence_interval": recurrence_interval or ("daily" if recurring else ""),
            "status": "active",
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "last_delivered": "",
        }
        data.setdefault("reminders", []).append(entry)
        self._write_json(path, data)
        return rid

    def get_active_reminders(self) -> List[Dict]:
        """Get all reminders with status 'active'."""
        path = self._reminders_path()
        data = self._read_json(path) or {"reminders": []}
        return [r for r in data.get("reminders", []) if r.get("status") == "active"]

    def get_due_reminders(self) -> List[Dict]:
        """Get reminders that are due now (within a 5-minute window)."""
        now = datetime.now()
        current_hhmm = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")
        due = []

        for rem in self.get_active_reminders():
            rt = rem.get("remind_time", "")
            last = rem.get("last_delivered", "")

            # Skip if already delivered today
            if last and last.startswith(today_str):
                continue

            # Check HH:MM format (daily or recurring)
            if len(rt) == 5 and ":" in rt:
                try:
                    scheduled = datetime.strptime(f"{today_str} {rt}", "%Y-%m-%d %H:%M")
                    diff = (now - scheduled).total_seconds()
                    # Due if within 0 to 5 minutes past the scheduled time
                    if 0 <= diff <= 300:
                        due.append(rem)
                except ValueError:
                    pass

            # Check full datetime format (one-time)
            elif "T" in rt:
                try:
                    scheduled = datetime.strptime(rt, "%Y-%m-%dT%H:%M")
                    diff = (now - scheduled).total_seconds()
                    if 0 <= diff <= 300:
                        due.append(rem)
                except ValueError:
                    pass

        return due

    def mark_reminder_delivered(self, reminder_id: str) -> None:
        """Mark a reminder as delivered. Deactivate one-time reminders."""
        path = self._reminders_path()
        data = self._read_json(path) or {"reminders": []}
        now_str = time.strftime("%Y-%m-%dT%H:%M:%S")
        for rem in data.get("reminders", []):
            if rem.get("id") == reminder_id:
                rem["last_delivered"] = now_str
                if not rem.get("recurring"):
                    rem["status"] = "completed"
                break
        self._write_json(path, data)

    def cancel_reminder(self, reminder_id: str) -> bool:
        """Cancel a reminder by ID."""
        path = self._reminders_path()
        data = self._read_json(path) or {"reminders": []}
        for rem in data.get("reminders", []):
            if rem.get("id") == reminder_id:
                rem["status"] = "cancelled"
                self._write_json(path, data)
                return True
        return False

    # ------------------------------------------------------------------
    # Medication schedule checking
    # ------------------------------------------------------------------

    def get_due_medications(self) -> List[Dict]:
        """Get medications that are due now (within a 10-minute window)."""
        meds_data = self.load_medications()
        meds = meds_data.get("medications", [])
        taken_log = meds_data.get("taken_log", [])
        if not meds:
            return []

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        due = []

        for med in meds:
            schedule = med.get("schedule", [])
            for sched_time in schedule:
                # Check if already taken today at this time
                already_taken = any(
                    entry.get("medication_id") == med.get("id")
                    and entry.get("scheduled_time") == sched_time
                    and entry.get("actual_time", "").startswith(today_str)
                    and entry.get("status") == "taken"
                    for entry in taken_log
                )
                if already_taken:
                    continue

                # Check if within the due window
                try:
                    scheduled = datetime.strptime(
                        f"{today_str} {sched_time}", "%Y-%m-%d %H:%M"
                    )
                    diff = (now - scheduled).total_seconds()
                    # Due if within 0 to 10 minutes past scheduled time
                    if 0 <= diff <= 600:
                        due.append({
                            "medication": med,
                            "scheduled_time": sched_time,
                            "overdue_minutes": int(diff / 60),
                        })
                except ValueError:
                    pass

        return due

    def get_upcoming_medications(self, within_minutes: int = 30) -> List[Dict]:
        """Get medications coming up within the next N minutes."""
        meds_data = self.load_medications()
        meds = meds_data.get("medications", [])
        taken_log = meds_data.get("taken_log", [])
        if not meds:
            return []

        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        upcoming = []

        for med in meds:
            for sched_time in med.get("schedule", []):
                already_taken = any(
                    entry.get("medication_id") == med.get("id")
                    and entry.get("scheduled_time") == sched_time
                    and entry.get("actual_time", "").startswith(today_str)
                    and entry.get("status") == "taken"
                    for entry in taken_log
                )
                if already_taken:
                    continue

                try:
                    scheduled = datetime.strptime(
                        f"{today_str} {sched_time}", "%Y-%m-%d %H:%M"
                    )
                    diff = (scheduled - now).total_seconds()
                    if 0 < diff <= within_minutes * 60:
                        upcoming.append({
                            "medication": med,
                            "scheduled_time": sched_time,
                            "minutes_until": int(diff / 60),
                        })
                except ValueError:
                    pass

        return upcoming
    # ------------------------------------------------------------------
    # Emotional learning — track what helps this specific user
    # ------------------------------------------------------------------

    def _emotional_learning_path(self) -> Path:
        return self.data_dir / "emotional_learning.json"

    def log_emotional_response(
        self,
        emotion_detected: str,
        user_statement: str,
        assistant_response: str,
        response_type: str,  # "statement", "question", "validation", etc.
        perceived_helpfulness: Optional[int] = None,  # 1-5 if known
    ) -> None:
        """Log an emotional exchange to learn what works for this user."""
        path = self._emotional_learning_path()
        data = self._read_json(path) or {"exchanges": []}
        
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "emotion_detected": emotion_detected,
            "user_input_sample": user_statement[:200],  # First 200 chars
            "assistant_response_sample": assistant_response[:200],
            "response_type": response_type,
            "helpfulness_rating": perceived_helpfulness,
        }
        
        data.setdefault("exchanges", []).append(entry)
        self._write_json(path, data)

    def get_emotional_patterns(self, emotion: str, limit: int = 10) -> List[Dict]:
        """Get past exchanges for a specific emotion to learn patterns."""
        path = self._emotional_learning_path()
        data = self._read_json(path) or {"exchanges": []}
        
        matching = [
            e for e in data.get("exchanges", [])
            if e.get("emotion_detected") == emotion
        ]
        
        return list(reversed(matching))[:limit]

    def track_coping_strategy(
        self,
        strategy_name: str,
        emotional_context: str,
        perceived_effectiveness: int,  # 1-5
        notes: str = "",
    ) -> None:
        """Track coping strategies that work for this user."""
        # Store in preferences with a special "coping_" prefix
        prefs = self.get_preferences()
        
        # Create or append to coping strategies list
        coping_key = f"coping_strategies"
        if coping_key not in prefs:
            prefs[coping_key] = {
                "value": [],
                "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        
        # Ensure it's a list
        if not isinstance(prefs[coping_key]["value"], list):
            prefs[coping_key]["value"] = []
        
        strategy = {
            "name": strategy_name,
            "context": emotional_context,
            "effectiveness": perceived_effectiveness,
            "noted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "notes": notes,
        }
        
        prefs[coping_key]["value"].append(strategy)
        prefs[coping_key]["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        
        path = self._prefs_path()
        self._write_json(path, prefs)

    def get_effective_coping_strategies(self, emotion: str) -> List[Dict]:
        """Get coping strategies known to be effective for a given emotion."""
        prefs = self.get_preferences()
        coping_key = "coping_strategies"
        
        if coping_key not in prefs:
            return []
        
        strategies = prefs[coping_key].get("value", [])
        if not isinstance(strategies, list):
            return []
        
        # Filter by emotion context and effectiveness > 3
        relevant = [
            s for s in strategies
            if emotion.lower() in s.get("context", "").lower()
            and s.get("effectiveness", 0) >= 3
        ]
        
        # Sort by effectiveness (highest first)
        return sorted(relevant, key=lambda s: s.get("effectiveness", 0), reverse=True)

    def log_communication_preference(
        self,
        preference_type: str,  # "direct", "gentle", "question-based", "validation-first", etc.
        description: str,
        context: str = "",
    ) -> None:
        """Track how this user prefers to be communicated with."""
        prefs = self.get_preferences()
        
        comm_key = "communication_preferences"
        if comm_key not in prefs:
            prefs[comm_key] = {
                "value": [],
                "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        
        pref = {
            "type": preference_type,
            "description": description,
            "context": context,
            "noted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        
        if not isinstance(prefs[comm_key]["value"], list):
            prefs[comm_key]["value"] = []
        
        prefs[comm_key]["value"].append(pref)
        prefs[comm_key]["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        
        path = self._prefs_path()
        self._write_json(path, prefs)

    def get_communication_preferences(self) -> List[Dict]:
        """Get user's stated communication preferences."""
        prefs = self.get_preferences()
        comm_key = "communication_preferences"
        
        if comm_key not in prefs:
            return []
        
        value = prefs[comm_key].get("value", [])
        if isinstance(value, list):
            return value
        return []