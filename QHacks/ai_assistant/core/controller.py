"""Main assistant controller — streamlined voice conversation loop.

Architecture:
  Microphone (STT) → Controller → LLM → Speaker (TTS)

Design principles:
  - Wait for complete user input before processing (no interruption)
  - Process LLM + TTS asynchronously to minimize perceived latency
  - Gentle, escalating silence handling
  - Cross-session memory for personalization
  - No dead code — every path serves the conversation
"""

import threading
import time
import os
import re

from modules.microphone import MicrophoneModule
from modules.speaker import SpeakerModule
from modules.llm_client import LLMClient
from modules.question_detector import QuestionDetector
from modules.memory_manager import MemoryManager
from modules.therapeutic_questions import TherapeuticQuestionGenerator
from modules.emotional_awareness import EnhancedEmotionalAwareness
from core.conversation import ConversationHistory
from config import (
    AudioConfig, TTSConfig, LLMConfig, ConversationConfig,
    TERMINATION_PHRASES, AFFIRMATIVE_RESPONSES, NEGATIVE_RESPONSES,
)


class AssistantController:
    """Voice assistant with emotionally intelligent conversation loop."""

    def __init__(self):
        # Configuration
        self.audio_config = AudioConfig()
        self.tts_config = TTSConfig()
        self.llm_config = LLMConfig()
        self.conv_config = ConversationConfig()

        # Modules
        self.microphone = MicrophoneModule(self.audio_config)
        self.speaker = SpeakerModule(self.tts_config, microphone=self.microphone)
        self.llm = LLMClient(self.llm_config)
        self.memory = MemoryManager()
        self.conversation = ConversationHistory(max_messages=self.llm_config.max_history_length)
        self.question_detector = QuestionDetector(
            TERMINATION_PHRASES, AFFIRMATIVE_RESPONSES, NEGATIVE_RESPONSES,
        )
        # Enhanced emotional awareness and therapeutic questions
        self.emotional_analyzer = EnhancedEmotionalAwareness()
        self.question_generator = TherapeuticQuestionGenerator(
            memory_manager=self.memory,
            conversation_history=self.conversation,
        )

        # Conversation state
        self._running = False
        self._processing = False
        self._last_activity = time.time()
        self._silence_prompts = 0
        self._last_response_was_question = False  # Track for therapeutic questioning

        # Deduplication
        self._last_text = None
        self._last_text_time = 0.0

        # Session metrics
        self._session_start = None
        self._user_count = 0
        self._assistant_count = 0

        # Proactive monitoring
        self._monitor_thread: threading.Thread = None
        self._pending_med_prompt: str = ""  # Track pending medication prompt for confirmation

    # ==================================================================
    # Lifecycle
    # ==================================================================

    def start(self):
        """Initialize modules and enter the main conversation loop."""
        print("[SYSTEM] Starting assistant...")
        self.speaker.start()
        time.sleep(0.1)
        self.microphone.start()

        # Warm greeting
        self._greet()

        self._running = True
        self._session_start = time.time()
        self._last_activity = time.time()

        # Start proactive monitor (medication reminders, user reminders)
        self._monitor_thread = threading.Thread(
            target=self._proactive_monitor, daemon=True
        )
        self._monitor_thread.start()
        print("[SYSTEM] Ready — listening. Proactive monitor active.")

        try:
            self._loop()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Gracefully shut down."""
        if not self._running:
            return
        self._running = False
        self._save_session_memory()
        self.microphone.stop()
        self.speaker.stop()
        self._print_summary()

    # ==================================================================
    # Greeting
    # ==================================================================

    def _greet(self):
        try:
            profile = self.memory.load_user_profile()
            name = profile.get("preferred_name") or profile.get("full_name") or ""

            # Check if this is a returning user (has session memories)
            recent_mems = self.memory.get_recent_memories(limit=1)
            is_returning = bool(recent_mems)

            if name and is_returning:
                greeting = f"Hey {name}. Good to have you back. I'm here whenever you're ready."
            elif name:
                greeting = f"Hey {name}. I'm here whenever you're ready."
            elif is_returning:
                greeting = "Hey, welcome back. I'm here whenever you're ready."
            else:
                greeting = self.conv_config.greeting_message

            self.speaker.speak(greeting, emotion="encouragement")
            self.speaker.wait_until_done(timeout=10.0)
        except Exception:
            pass

    # ==================================================================
    # Main loop
    # ==================================================================

    def _loop(self):
        while self._running:
            transcription = self.microphone.get_transcription(timeout=0.1)

            if transcription and transcription.text.strip():
                self._on_speech(transcription.text.strip())
            elif not self._processing:
                self._check_silence()

            time.sleep(0.02)

    # ==================================================================
    # Speech handling
    # ==================================================================

    def _on_speech(self, text: str):
        """Handle a complete transcription from the microphone."""
        text_lower = text.lower()

        # Deduplication — ignore identical text within 2 seconds
        now = time.time()
        if (
            self._last_text
            and text_lower == self._last_text.lower()
            and now - self._last_text_time < 2.0
        ):
            return

        # Skip if already processing a response
        if self._processing:
            return

        # Check for termination
        if self.question_detector.is_termination(text_lower):
            self._goodbye()
            return

        # Check for medication confirmation (quick response, no LLM needed)
        if self._check_medication_confirmation(text):
            self._last_text = text
            self._last_text_time = now
            self._last_activity = time.time()
            confirm_msg = "Got it, I've noted that down. Good job staying on track."
            print(f"[USER] {text}")
            print(f"[ASSISTANT] {confirm_msg}")
            self.conversation.add_user_message(text)
            self.conversation.add_assistant_message(confirm_msg)
            self.speaker.speak(confirm_msg, emotion="encouragement")
            return

        self._last_text = text
        self._last_text_time = now
        self._dispatch(text)

    def _dispatch(self, text: str):
        """Accept user input and start the async response pipeline."""
        self._processing = True
        self.microphone.clear_queue()

        self.conversation.add_user_message(text)
        self._user_count += 1
        print(f"[USER] {text}")

        # Run LLM + TTS in a background thread so the main loop stays responsive
        threading.Thread(
            target=self._respond, args=(text,), daemon=True,
        ).start()

    # ==================================================================
    # Response pipeline (background thread)
    # ==================================================================

    def _respond(self, user_text: str):
        """Call LLM, detect emotion, speak with adapted voice, extract preferences."""
        try:
            # Enhanced emotion detection with detailed cue analysis
            emotional_cues = self.emotional_analyzer.analyze_emotional_cues(user_text)
            detected_emotion = self.emotional_analyzer.determine_response_tone(emotional_cues)
            
            if detected_emotion != "neutral":
                emotion_summary = self.emotional_analyzer.get_emotional_context_summary(emotional_cues)
                print(f"[EMOTION] {emotion_summary}")
            
            # Detect crisis indicators (safety check)
            if self.emotional_analyzer.is_crisis_indicator(user_text):
                print("[ALERT] Crisis language detected — prioritizing immediate support")
                detected_emotion = "distress"

            # Build system prompt with emotion context injected
            sys_prompt = self._system_prompt()
            if detected_emotion != "neutral":
                sys_prompt += self._emotion_guidance(detected_emotion)

            response = self.llm.send_message(
                user_message=user_text,
                conversation_history=self.conversation.get_history(),
                system_prompt=sys_prompt,
            )

            if response and response.success and response.text:
                reply = response.text
                self.conversation.add_assistant_message(reply)
                self._assistant_count += 1
                print(f"[ASSISTANT] {reply}")

                # Drain any stale queued audio before speaking the new response
                while not self.speaker._text_queue.empty():
                    try:
                        self.speaker._text_queue.get_nowait()
                    except Exception:
                        break

                # Speak with emotionally adapted voice
                self.speaker.speak(reply, emotion=detected_emotion)
                self.speaker.wait_until_done(timeout=60)
                self._last_response_was_question = False

                # Extract and store user preferences and reminders from this exchange
                self._extract_and_store_preferences(user_text, reply)
                self._extract_and_store_reminders(user_text)
                
                # Optionally ask a follow-up therapeutic question
                should_ask = (
                    self.question_generator.should_ask_question(
                        conversation_length=len(self.conversation.get_history()),
                        last_was_question=self._last_response_was_question
                    )
                    and self.emotional_analyzer.should_ask_follow_up(emotional_cues)
                )
                
                if should_ask:
                    follow_up = self.question_generator.generate_question(
                        emotion=detected_emotion,
                        conversation_history=self.conversation.get_history(),
                        user_profile=self.memory.load_user_profile(),
                    )
                    
                    if follow_up:
                        print(f"[THERAPEUTIC QUESTION] {follow_up}")
                        # Brief pause before the follow-up question
                        time.sleep(0.5)
                        # Ask with a thoughtful, gentle emotion
                        question_emotion = "encouragement" if detected_emotion != "distress" else "neutral"
                        self.speaker.speak(follow_up, emotion=question_emotion)
                        self.speaker.wait_until_done(timeout=30)
                        self._last_response_was_question = True
                        self.conversation.add_assistant_message(follow_up)
            else:
                fallback = "I'm sorry, I didn't quite catch that. Could you try again?"
                print(f"[ASSISTANT] {fallback}")
                self.speaker.speak(fallback, emotion="neutral")
                self.speaker.wait_until_done(timeout=15)
                self._last_response_was_question = False

            self._last_activity = time.time()
            self._silence_prompts = 0

        except Exception as e:
            print(f"[ERROR] Response pipeline: {e}")
        finally:
            self._processing = False

    # ==================================================================
    # Silence handling
    # ==================================================================

    def _check_silence(self):
        elapsed = time.time() - self._last_activity
        if elapsed < self.conv_config.silence_timeout:
            return

        self._silence_prompts += 1

        if self._silence_prompts == 1:
            self.speaker.speak(self.conv_config.continue_prompt, emotion="neutral")
        elif self._silence_prompts == 2:
            self.speaker.speak(self.conv_config.still_there_prompt, emotion="encouragement")
        else:
            self._goodbye()
            return

        self._last_activity = time.time()

    # ==================================================================
    # Goodbye
    # ==================================================================

    def _goodbye(self):
        self.speaker.speak(self.conv_config.goodbye_message, emotion="encouragement")
        self.speaker.wait_until_done(timeout=10)
        self._running = False

    # ==================================================================
    # Proactive monitoring — medications, reminders, scheduled actions
    # ==================================================================

    def _proactive_monitor(self):
        """Background thread that checks for due medications and reminders every 30s."""
        while self._running:
            try:
                # Don't interrupt if currently processing a response or speaking
                if not self._processing and not self.speaker.is_speaking():
                    self._check_medications()
                    self._check_reminders()
            except Exception as e:
                print(f"[MONITOR] Error: {e}")
            # Sleep in small increments so we can exit quickly
            for _ in range(60):  # 30 seconds total (60 x 0.5s)
                if not self._running:
                    return
                time.sleep(0.5)

    def _check_medications(self):
        """Check if any medications are due and prompt the user."""
        try:
            due_meds = self.memory.get_due_medications()
            for entry in due_meds:
                med = entry["medication"]
                sched = entry["scheduled_time"]
                name = med.get("name", "your medication")
                dosage = med.get("dosage", "")
                instructions = med.get("instructions", "")

                # Build a natural, specific prompt
                prompt = f"Hey, just a gentle reminder — it's time to take your {name}"
                if dosage:
                    prompt += f", {dosage}"
                prompt += "."
                if instructions:
                    prompt += f" Remember: {instructions}"

                print(f"[MONITOR] Medication due: {name} at {sched}")
                self._deliver_proactive_prompt(prompt)
                self._pending_med_prompt = med.get("id", "")

                # Log the reminder event
                self.memory.log_event(
                    "medication_reminder",
                    details=f"Reminded user about {name} ({dosage}) at {sched}",
                )

                # Only deliver one medication reminder at a time
                break
        except Exception as e:
            print(f"[MONITOR] Medication check error: {e}")

    def _check_reminders(self):
        """Check if any user-set reminders are due."""
        try:
            due = self.memory.get_due_reminders()
            for rem in due:
                content = rem.get("content", "something")
                prompt = f"Hey, you asked me to remind you: {content}"

                print(f"[MONITOR] Reminder due: {content}")
                self._deliver_proactive_prompt(prompt)

                # Mark as delivered
                self.memory.mark_reminder_delivered(rem["id"])

                # Log the event
                self.memory.log_event(
                    "reminder_delivered",
                    details=f"Delivered reminder: {content}",
                )

                # Only deliver one reminder at a time to avoid overwhelming
                break
        except Exception as e:
            print(f"[MONITOR] Reminder check error: {e}")

    def _deliver_proactive_prompt(self, text: str, emotion: str = "encouragement"):
        """Speak a proactive prompt when the user is not actively talking."""
        # Wait for any current speech to finish
        self.speaker.wait_until_done(timeout=10)
        # Add to conversation history so the LLM knows what was said
        self.conversation.add_assistant_message(text)
        self._assistant_count += 1
        print(f"[ASSISTANT] {text}")
        self.speaker.speak(text, emotion=emotion)
        self.speaker.wait_until_done(timeout=30)
        self._last_activity = time.time()

    # ==================================================================
    # Reminder extraction from conversation
    # ==================================================================

    _REMINDER_SIGNALS = [
        "remind me", "reminder", "don't let me forget",
        "don't forget to", "remember to tell me", "alert me",
        "wake me", "tell me when", "let me know when",
    ]

    _TIME_WORDS = {
        "morning": "08:00", "noon": "12:00", "afternoon": "14:00",
        "evening": "18:00", "night": "21:00", "tonight": "20:00",
        "bedtime": "22:00",
    }

    def _extract_and_store_reminders(self, user_text: str):
        """Detect reminder requests in user speech and store them."""
        text_lower = user_text.lower()
        is_reminder = any(sig in text_lower for sig in self._REMINDER_SIGNALS)
        if not is_reminder:
            return

        # Extract time if mentioned
        remind_time = ""
        for word, t in self._TIME_WORDS.items():
            if word in text_lower:
                remind_time = t
                break

        # Try to extract HH:MM pattern (e.g., "at 3:00", "at 15:00")
        if not remind_time:
            time_match = re.search(r'\b(\d{1,2}):(\d{2})\b', text_lower)
            if time_match:
                h, m = int(time_match.group(1)), int(time_match.group(2))
                # Handle AM/PM hints
                if "pm" in text_lower and h < 12:
                    h += 12
                if 0 <= h <= 23 and 0 <= m <= 59:
                    remind_time = f"{h:02d}:{m:02d}"

        # Extract what to remind about (everything after the trigger phrase)
        content = user_text  # Default: store the full request
        for sig in self._REMINDER_SIGNALS:
            if sig in text_lower:
                idx = text_lower.index(sig) + len(sig)
                remainder = user_text[idx:].strip(" .,!?")
                if remainder and len(remainder) > 3:
                    content = remainder
                break

        # Check if recurring
        recurring = any(w in text_lower for w in ["every day", "daily", "each day", "every morning", "every night"])

        rid = self.memory.add_reminder(
            content=content,
            remind_time=remind_time,
            recurring=recurring,
        )
        print(f"[MEMORY] Stored reminder: '{content}' at {remind_time or 'unspecified'} (id={rid})")

        # Also store in Backboard for cross-session memory
        bb_content = f"User requested reminder: '{content}'"
        if remind_time:
            bb_content += f" at {remind_time}"
        if recurring:
            bb_content += " (recurring daily)"
        threading.Thread(
            target=self.llm.store_backboard_memory,
            args=(bb_content,),
            daemon=True,
        ).start()

    # ==================================================================
    # Medication confirmation detection
    # ==================================================================

    _MED_CONFIRM_PHRASES = [
        "i took it", "i've taken it", "ive taken it", "took my medication",
        "took my medicine", "took my meds", "already took it", "done",
        "i took them", "taken it", "just took it", "yes i took it",
        "took the pill", "took the pills", "i did", "already did",
    ]

    def _check_medication_confirmation(self, text: str) -> bool:
        """Check if user is confirming they took their medication."""
        text_lower = text.lower()
        if not self._pending_med_prompt:
            return False

        is_confirm = any(phrase in text_lower for phrase in self._MED_CONFIRM_PHRASES)
        # Also check simple affirmatives right after a medication prompt
        is_affirm = text_lower.strip() in ("yes", "yeah", "yep", "done", "ok", "okay", "yup")

        if is_confirm or is_affirm:
            med_id = self._pending_med_prompt
            now_str = time.strftime("%H:%M")
            self.memory.log_medication_taken(
                medication_id=med_id,
                scheduled_time=now_str,
                status="taken",
                notes="Confirmed via voice",
            )
            self._pending_med_prompt = ""
            print(f"[MEMORY] Medication {med_id} logged as taken")

            # Store in Backboard
            threading.Thread(
                target=self.llm.store_backboard_memory,
                args=(f"User confirmed taking medication {med_id} at {now_str}",),
                daemon=True,
            ).start()
            return True
        return False

    # ==================================================================
    # Emotion detection — analyze user speech for emotional cues
    # ==================================================================

    # Emotion keywords mapped to emotion categories with intensity weights.
    # Higher weight = stronger signal of that emotion.
    _EMOTION_LEXICON = {
        "distress": {
            # Crisis-level indicators
            "i can't do this": 3, "i can't take it": 3, "i want to die": 5,
            "i can't go on": 4, "i'm breaking down": 4, "help me": 3,
            "i'm falling apart": 4, "everything is falling apart": 4,
            "i'm losing it": 3, "i can't breathe": 4, "panic": 3,
            "i don't know what to do": 2, "i'm desperate": 3,
            "i can't handle": 3, "too much": 2, "breaking point": 3,
            "crisis": 3, "emergency": 3, "i'm shaking": 3,
        },
        "sadness": {
            "sad": 2, "crying": 3, "depressed": 3, "lonely": 2,
            "heartbroken": 3, "grieving": 3, "miss them": 2, "miss him": 2,
            "miss her": 2, "lost someone": 3, "empty inside": 3,
            "hopeless": 3, "pointless": 2, "worthless": 3, "numb": 2,
            "i feel so alone": 3, "nobody cares": 3, "i'm so tired of": 2,
            "hurting": 2, "pain": 1, "tears": 2, "broke my heart": 3,
        },
        "anxiety": {
            "anxious": 2, "worried": 2, "nervous": 2, "scared": 2,
            "afraid": 2, "terrified": 3, "overthinking": 2, "can't sleep": 2,
            "racing thoughts": 3, "what if": 1, "dreading": 2,
            "stress": 1, "stressed": 2, "overwhelmed": 2, "freaking out": 3,
            "panicking": 3, "on edge": 2, "tense": 1, "uneasy": 1,
            "fear": 2, "fearful": 2, "restless": 1,
        },
        "anger": {
            "angry": 2, "furious": 3, "pissed": 3, "hate": 2,
            "frustrated": 2, "irritated": 1, "annoyed": 1, "livid": 3,
            "outraged": 3, "fed up": 2, "sick of": 2, "tired of": 1,
            "unfair": 1, "betrayed": 2, "enraged": 3, "resentful": 2,
            "bitter": 2, "disgusted": 2,
        },
        "happiness": {
            "happy": 2, "excited": 2, "grateful": 2, "thankful": 2,
            "amazing": 2, "wonderful": 2, "great news": 2, "thrilled": 3,
            "joyful": 3, "love it": 2, "celebrate": 2, "proud": 2,
            "fantastic": 2, "blessed": 2, "overjoyed": 3, "ecstatic": 3,
            "relieved": 2, "good news": 2, "best day": 2,
        },
    }

    def _detect_emotion(self, text: str) -> str:
        """Detect the dominant emotion in user text (legacy method for compatibility).

        Now uses the enhanced emotional analyzer for more accurate detection.
        
        Returns one of: distress, sadness, anxiety, anger, happiness,
                        encouragement, neutral
        """
        emotional_cues = self.emotional_analyzer.analyze_emotional_cues(text)
        return self.emotional_analyzer.determine_response_tone(emotional_cues)

    @staticmethod
    def _emotion_guidance(emotion: str) -> str:
        """Return LLM prompt guidance for responding to a specific emotional state.

        This tells the LLM how to shape its text response (word choice, length,
        approach) to align with the voice that will be used for delivery.
        """
        guides = {
            "distress": (
                "\n\n[EMOTIONAL CONTEXT — DISTRESS DETECTED]\n"
                "The user is in significant emotional distress right now. "
                "Your response will be spoken in a very slow, calm, steady voice. "
                "Respond with maximum gentleness. Use short, grounding sentences. "
                "Do NOT minimize their pain. Do NOT rush to solutions. "
                "Acknowledge what they're going through first. Be present. "
                "If appropriate, gently remind them they don't have to face this alone. "
                "Keep the response brief — 1 to 3 sentences maximum."
            ),
            "sadness": (
                "\n\n[EMOTIONAL CONTEXT — SADNESS DETECTED]\n"
                "The user sounds sad or hurt. "
                "Your response will be spoken in a warm, gentle, slightly slower voice. "
                "Be tender and validating. Let them know it's okay to feel this way. "
                "Don't try to fix it immediately — sit with them emotionally. "
                "Use soft, compassionate language. 2 to 4 sentences."
            ),
            "anxiety": (
                "\n\n[EMOTIONAL CONTEXT — ANXIETY DETECTED]\n"
                "The user is feeling anxious, nervous, or worried. "
                "Your response will be spoken in a calm, measured, grounding voice. "
                "Help them feel anchored. Use steady, reassuring language. "
                "Avoid adding new worries. If helpful, gently guide toward "
                "what they can control right now. 2 to 4 sentences."
            ),
            "anger": (
                "\n\n[EMOTIONAL CONTEXT — ANGER/FRUSTRATION DETECTED]\n"
                "The user is expressing anger or frustration. "
                "Your response will be spoken in a steady, non-escalating voice. "
                "Do NOT match their intensity. Don't dismiss their feelings. "
                "Validate that frustration is understandable. "
                "Use calm, direct language. Don't be patronizing. 2 to 4 sentences."
            ),
            "happiness": (
                "\n\n[EMOTIONAL CONTEXT — HAPPINESS DETECTED]\n"
                "The user sounds happy, excited, or positive. "
                "Your response will be spoken in a warm, slightly upbeat voice. "
                "Match their positive energy naturally. Share in their joy. "
                "Be genuine — not performatively excited. 2 to 4 sentences."
            ),
            "encouragement": (
                "\n\n[EMOTIONAL CONTEXT — NEEDS ENCOURAGEMENT]\n"
                "The user may benefit from encouragement right now. "
                "Your response will be spoken in a warm, uplifting voice. "
                "Offer genuine, specific support — not generic cheerleading. "
                "2 to 4 sentences."
            ),
        }
        return guides.get(emotion, "")

    # ==================================================================
    # Preference extraction — learn user traits from conversation
    # ==================================================================

    # Signals that indicate user preferences or personality traits
    _PREFERENCE_SIGNALS = {
        "comfort_method": [
            "when i'm stressed", "when i'm sad", "what helps me",
            "i usually", "i prefer", "i like when", "i feel better when",
            "it helps when", "what comforts me", "i cope by",
            "that makes me feel", "i need", "i want",
        ],
        "communication_style": [
            "don't lecture me", "just listen", "give me advice",
            "be direct", "be gentle", "tell me straight",
            "i like it when you", "don't sugarcoat", "be honest",
        ],
        "emotional_state": [
            "i'm feeling", "i feel", "i've been", "lately i",
            "today was", "today i", "this week", "struggling with",
            "worried about", "anxious about", "happy about", "excited about",
        ],
        "personal_info": [
            "my name is", "i'm from", "i live", "i work",
            "my job", "my family", "my partner", "my kids",
            "my friend", "i go to", "i study",
        ],
    }

    def _extract_and_store_preferences(self, user_text: str, reply: str):
        """Extract personality traits and preferences from conversation, store them."""
        try:
            text_lower = user_text.lower()

            # Detect preference signals
            for category, signals in self._PREFERENCE_SIGNALS.items():
                for signal in signals:
                    if signal in text_lower:
                        # Store the user's statement as a memory tagged with the category
                        self.memory.add_memory(
                            content=user_text,
                            tags=[category, "auto_extracted"],
                            source="user",
                        )

                        # Also store in Backboard's cloud memory for cross-session persistence
                        memory_content = f"[{category}] User said: {user_text}"
                        threading.Thread(
                            target=self.llm.store_backboard_memory,
                            args=(memory_content,),
                            daemon=True,
                        ).start()

                        break  # Only store once per category per message

            # Detect name introduction
            if "my name is" in text_lower or "i'm " in text_lower[:20] or "call me" in text_lower:
                # Try to extract name
                for prefix in ["my name is ", "i'm ", "i am ", "call me "]:
                    if prefix in text_lower:
                        name_part = text_lower.split(prefix, 1)[1].split()[0].strip(".,!?")
                        if name_part and len(name_part) > 1:
                            name_cap = name_part.capitalize()
                            self.memory.add_preference("preferred_name", name_cap)
                            # Update profile
                            profile = self.memory.load_user_profile()
                            profile["preferred_name"] = name_cap
                            self.memory.save_user_profile(profile)
                            print(f"[MEMORY] Learned user name: {name_cap}")

                            # Store in Backboard
                            threading.Thread(
                                target=self.llm.store_backboard_memory,
                                args=(f"User's preferred name is {name_cap}",),
                                daemon=True,
                            ).start()
                            break

        except Exception as e:
            print(f"[MEMORY] Preference extraction error: {e}")

    # ==================================================================
    # Session memory — enriched with personality and emotional patterns
    # ==================================================================

    def _save_session_memory(self):
        """Persist a rich summary of this session for future recall."""
        try:
            hist = self.conversation.get_history()
            user_msgs = [m["content"] for m in hist if m.get("role") == "user"]
            if not user_msgs:
                return

            # Build a rich session summary
            summary_parts = []

            # Topics discussed
            topics = " | ".join(user_msgs[-6:])
            summary_parts.append(f"Topics: {topics}")

            # Emotional patterns detected
            emotional_keywords = {
                "stressed": "stress", "anxious": "anxiety", "worried": "worry",
                "sad": "sadness", "happy": "joy", "excited": "excitement",
                "tired": "fatigue", "frustrated": "frustration", "lonely": "loneliness",
                "grateful": "gratitude", "scared": "fear", "angry": "anger",
                "overwhelmed": "overwhelm", "calm": "calm", "hopeful": "hope",
            }
            emotions_found = set()
            all_user_text = " ".join(m.lower() for m in user_msgs)
            for keyword, emotion in emotional_keywords.items():
                if keyword in all_user_text:
                    emotions_found.add(emotion)
            if emotions_found:
                summary_parts.append(f"Emotions expressed: {', '.join(emotions_found)}")

            # Store locally
            summary = " | ".join(summary_parts)
            self.memory.add_memory(
                content=summary,
                tags=["session_summary", "user_concerns", "emotional_patterns"],
                source="assistant",
            )

            # Store in Backboard for cross-session persistence
            bb_summary = f"Session summary: {summary}"
            try:
                self.llm.store_backboard_memory(bb_summary)
            except Exception:
                pass

        except Exception:
            pass

    # ==================================================================
    # System prompt
    # ==================================================================

    def _system_prompt(self) -> str:
        """Build the system prompt — emotionally intelligent with active memory use."""
        profile = {}
        try:
            profile = self.memory.load_user_profile()
        except Exception:
            pass

        name = profile.get("preferred_name") or profile.get("full_name") or ""
        address = name if name else "there"

        prompt = f"""You are a calm, emotionally intelligent conversational assistant speaking with {address}.

CORE IDENTITY:
- You communicate through voice. Every response will be spoken aloud, so write naturally as if talking.
- You are supportive, empathetic, and emotionally aware — a warm, trusted confidant.
- You are NOT a licensed therapist, counselor, or medical professional. Never claim or imply that you are.
- You listen carefully and respond thoughtfully. You make people feel heard and safe.
- Your approach is inspired by therapeutic listening: you ask thoughtful, open-ended questions that help users reflect, understand themselves better, and feel genuinely heard.

RESPONSE STYLE:
- Respond with one complete, coherent answer that fully addresses what the user said.
- Be concise and clear. Most responses should be 1 to 4 sentences.
- Use natural spoken language. No markdown, bullet points, numbered lists, or text formatting.
- Vary your phrasing. Never repeat the same sentence structures, openers, or wording.
- No filler phrases like "That's a great question" or "I appreciate you sharing that."
- Do not restate what the user just said unless it adds clarity.
- Speak confidently and directly. Avoid hedging.

EMOTIONAL AWARENESS AND ATTUNEMENT:
- Match the emotional register precisely. Distressed = gentle, grounding care. Casual = warm and relaxed.
- Validate feelings without being performative. One sincere sentence beats a paragraph of platitudes.
- When something is difficult, sit with it rather than rushing to fix it. Presence matters more than solutions.
- If the user seems to need encouragement, offer it naturally — not as a formula.
- Detect emotional shifts within a conversation and adjust your approach accordingly.
- Respond to what the person is expressing, not what you think they should be expressing.

THERAPEUTIC QUESTIONING (CORE APPROACH):
- Ask thoughtful, open-ended questions that invite reflection (not yes/no questions).
- Timing: Ask questions when meaningful, but not robotically after every response.
- Question types you use naturally:
  * Deepening: "Can you tell me more about that?" / "What was that like for you?"
  * Exploring coping: "What helps you when you're feeling this way?" / "How have you handled this before?"
  * Values and meaning: "What matters most to you about this?" / "If things could be different, what would that look like?"
  * Perspective: "What would you tell a friend in this situation?" / "What have you learned from going through this?"
  * Gentle curiosity: "What's been on your mind?" / "Tell me more about that."
- Never ask a question just to ask — each question should serve the conversation naturally.
- Adapt question intensity to emotional state: softer for distress, more exploratory for neutral/happy states.

MEMORY AND PERSONALIZATION (CRITICAL):
- You have access to persistent memory from previous conversations. USE IT ACTIVELY to personalize every interaction.
- Remember: the user's personality traits, emotional tendencies, communication style, recurring challenges, fears, joys, preferred methods of comfort, and how they prefer to be spoken to.
- When the user shares personal information — preferences, coping strategies, stressors, relationships, routines — treat this as essential context that shapes ALL future responses.
- In emotionally sensitive moments, rely on stored memory to determine your exact tone, language, and approach for THIS specific person. Generic responses are NOT acceptable.
- If you lack enough information to personalize effectively, ask a natural, caring question that learns something new: "What helps you most when you're feeling this way?" or "How do you usually like to talk through things like this?"
- Never repeat the same advice if it didn't resonate before. Adapt based on the user's reactions over time.
- Reference past conversations naturally when it adds value, but only when it genuinely helps.
- Track and honor communication preferences: some people need validation first, others prefer direct advice. Adapt to what works for THIS person.

ACTIONABLE MEMORY AND PROACTIVE SUPPORT (CRITICAL):
- When the user tells you something actionable — a medication schedule, a reminder, a task, a commitment — remember it and act on it.
- You have access to the user's medication schedule and active reminders. Reference them specifically, not generically.
- If the user asks "what medications do I take?" or "when is my next dose?", answer with exact details from their stored data.
- If you reminded the user about medication and they confirm taking it, acknowledge warmly and move on.
- When the user asks you to remind them about something, confirm what you'll remind them about and when.
- Never respond with generic uncertainty about information you already have stored. If you have it, use it.

CONVERSATION FLOW AND PRESENCE:
- Respond only after receiving complete input. Never anticipate or interrupt.
- Keep conversation flowing naturally — sometimes this means a statement, sometimes a question, sometimes just acknowledgment.
- Where appropriate and natural, ask open-ended follow-up questions to deepen understanding.
- End responses cleanly. No unnecessary closing remarks.
- The goal is genuine connection and understanding, not filling silence."""

        # Inject user profile information
        try:
            profile_lines = []
            if name:
                profile_lines.append(f"- Name: {name}")
            if profile.get("daily_routine"):
                routine = profile["daily_routine"]
                if routine.get("wake_time"):
                    profile_lines.append(f"- Wake time: {routine['wake_time']}")
                if routine.get("notes"):
                    profile_lines.append(f"- Routine notes: {routine['notes']}")
            if profile.get("medical_info", {}).get("conditions"):
                profile_lines.append(f"- Health conditions: {', '.join(profile['medical_info']['conditions'])}")
            if profile_lines:
                prompt += (
                    "\n\nUser profile information:\n"
                    + "\n".join(profile_lines)
                )
        except Exception:
            pass

        # Inject medication schedule
        try:
            meds_data = self.memory.load_medications()
            meds = meds_data.get("medications", [])
            if meds:
                med_lines = []
                for med in meds:
                    name = med.get("name", "Unknown")
                    dosage = med.get("dosage", "")
                    schedule = ", ".join(med.get("schedule", []))
                    instructions = med.get("instructions", "")
                    line = f"- {name} ({dosage}) at {schedule}"
                    if instructions:
                        line += f" — {instructions}"
                    med_lines.append(line)
                prompt += (
                    "\n\nUser's medication schedule "
                    "(use this to answer medication questions and confirm reminders):\n"
                    + "\n".join(med_lines)
                )
        except Exception:
            pass

        # Inject active reminders
        try:
            reminders = self.memory.get_active_reminders()
            if reminders:
                rem_lines = []
                for rem in reminders:
                    content = rem.get("content", "")
                    rtime = rem.get("remind_time", "unspecified")
                    recurring = " (daily)" if rem.get("recurring") else ""
                    rem_lines.append(f"- {content} at {rtime}{recurring}")
                prompt += (
                    "\n\nUser's active reminders "
                    "(reference these when relevant):\n"
                    + "\n".join(rem_lines)
                )
        except Exception:
            pass

        # Inject persistent memories for cross-session context
        try:
            mems = self.memory.get_recent_memories(limit=8)
            if mems:
                lines = [f"- [{m.get('timestamp', 'unknown')}] {m.get('content')}" for m in mems]
                prompt += (
                    "\n\nContext from previous conversations "
                    "(use actively to personalize your responses and avoid repetition):\n"
                    + "\n".join(lines)
                )
        except Exception:
            pass

        # Inject user preferences (personality traits, comfort methods, communication style)
        try:
            prefs = self.memory.get_preferences()
            if prefs:
                pref_lines = [f"- {k}: {v.get('value', v)}" for k, v in prefs.items()]
                prompt += (
                    "\n\nUser preferences and personality "
                    "(adapt your tone, language, approach, and question style based on these):\n"
                    + "\n".join(pref_lines)
                )
        except Exception:
            pass

        # Inject recent assistant replies to prevent verbatim repetition
        try:
            hist = self.conversation.get_history()
            replies = [m["content"] for m in hist if m.get("role") == "assistant"]
            if replies:
                recent = replies[-3:]
                lines = [f'- "{r}"' for r in recent]
                prompt += (
                    "\n\nYour recent responses "
                    "(do NOT repeat — rephrase entirely if revisiting the same idea):\n"
                    + "\n".join(lines)
                )
        except Exception:
            pass

        return prompt

    # ==================================================================
    # Session summary
    # ==================================================================

    def _print_summary(self):
        try:
            duration = time.time() - (self._session_start or time.time())
            mins, secs = int(duration // 60), int(duration % 60)
            print(f"\n{'=' * 50}")
            print("SESSION SUMMARY")
            print(f"{'=' * 50}")
            print(f"Duration: {mins}m {secs}s")
            print(f"User messages: {self._user_count}")
            print(f"Assistant messages: {self._assistant_count}")
            print(f"{'=' * 50}\n")
        except Exception:
            pass
