"""Enhanced emotional awareness system — voice tone analysis and cue detection.

Provides tools to:
  - Analyze emotional cues from speech/text
  - Detect voice characteristics (based on transcription metadata)
  - Track emotional patterns across conversations
  - Map detected emotions to appropriate responses
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class EmotionalCues:
    """Aggregated emotional signals from user input."""
    primary_emotion: str
    confidence: float  # 0.0-1.0
    secondary_emotions: List[Tuple[str, float]]  # List of (emotion, weight)
    vocal_characteristics: Dict[str, float]  # Tone, pace, etc.
    emotional_keywords: List[str]
    intensity_level: int  # 1-5, where 5 is most intense


class EnhancedEmotionalAwareness:
    """Advanced emotion detection and analysis."""

    def __init__(self):
        # Detailed emotion lexicon with intensities
        self.emotion_lexicon = {
            "distress": {
                "critical": [
                    ("i want to die", 5),
                    ("i can't go on", 5),
                    ("i'm falling apart", 5),
                    ("i can't take it anymore", 5),
                ],
                "severe": [
                    ("i can't do this", 4),
                    ("help me", 4),
                    ("emergency", 4),
                    ("can't breathe", 4),
                ],
                "moderate": [
                    ("overwhelmed", 3),
                    ("desperate", 3),
                    ("panic", 3),
                    ("breaking point", 3),
                ],
                "mild": [
                    ("stressed", 2),
                    ("struggling", 2),
                    ("difficult", 2),
                ],
            },
            "sadness": {
                "severe": [
                    ("i'm so sad", 4),
                    ("heartbroken", 4),
                    ("lost someone", 4),
                    ("grieving", 4),
                ],
                "moderate": [
                    ("sad", 2),
                    ("crying", 3),
                    ("depressed", 3),
                    ("empty inside", 3),
                    ("lonely", 2),
                ],
                "mild": [
                    ("down", 1),
                    ("blue", 1),
                    ("miss", 2),
                    ("miserable", 2),
                ],
            },
            "anxiety": {
                "severe": [
                    ("panicking", 4),
                    ("terrified", 4),
                    ("racing thoughts", 4),
                    ("can't stop worrying", 4),
                ],
                "moderate": [
                    ("anxious", 2),
                    ("worried", 2),
                    ("scared", 2),
                    ("overwhelmed", 3),
                    ("stressed", 2),
                ],
                "mild": [
                    ("nervous", 1),
                    ("concerned", 1),
                    ("uneasy", 1),
                ],
            },
            "anger": {
                "severe": [
                    ("furious", 4),
                    ("livid", 4),
                    ("enraged", 4),
                    ("hate it", 3),
                ],
                "moderate": [
                    ("angry", 2),
                    ("frustrated", 2),
                    ("irritated", 2),
                    ("fed up", 2),
                ],
                "mild": [
                    ("annoyed", 1),
                    ("bothered", 1),
                    ("upset", 2),
                ],
            },
            "happiness": {
                "severe": [
                    ("thrilled", 3),
                    ("overjoyed", 3),
                    ("ecstatic", 3),
                ],
                "moderate": [
                    ("happy", 2),
                    ("excited", 2),
                    ("grateful", 2),
                    ("wonderful", 2),
                ],
                "mild": [
                    ("good", 1),
                    ("nice", 1),
                    ("pleased", 1),
                ],
            },
            "hope_encouragement": {
                "strong": [
                    ("looking forward", 3),
                    ("hopeful", 3),
                    ("getting better", 3),
                    ("proud", 2),
                ],
                "moderate": [
                    ("feeling better", 2),
                    ("improving", 2),
                    ("positive", 2),
                ],
            },
        }

        # Vocal characteristic indicators (based on text patterns)
        self.vocal_indicators = {
            "rapid_speech": [
                "like", "um", "uh", "you know", "kind of", "i mean",
                "!!!", "???", "...",  # Multiple punctuation
            ],
            "slowed_speech": [
                "sigh", "pause", "taking a moment", "can't find the words",
            ],
            "raised_volume_indicators": [
                "!", "CAPS", "LOUD", "SHOUTING",
            ],
            "emotional_intensity": [
                "so", "really", "very", "extremely", "incredibly",
                "absolutely", "completely",
            ],
        }

    def analyze_emotional_cues(self, text: str) -> EmotionalCues:
        """Comprehensive emotional analysis of user input."""
        text_lower = text.lower()
        
        # Detect all emotions and their intensities
        emotion_scores = {}
        found_keywords = []
        
        for primary_emotion, intensity_levels in self.emotion_lexicon.items():
            total_score = 0
            keywords_for_emotion = []
            
            for intensity_class, phrases in intensity_levels.items():
                for phrase, weight in phrases:
                    if phrase in text_lower:
                        total_score += weight
                        keywords_for_emotion.append(phrase)
            
            if total_score > 0:
                emotion_scores[primary_emotion] = total_score
                found_keywords.extend(keywords_for_emotion)
        
        # Calculate primary and secondary emotions
        if not emotion_scores:
            return EmotionalCues(
                primary_emotion="neutral",
                confidence=1.0,
                secondary_emotions=[],
                vocal_characteristics=self._detect_vocal_characteristics(text),
                emotional_keywords=[],
                intensity_level=1,
            )
        
        # Sort by score
        sorted_emotions = sorted(emotion_scores.items(), key=lambda x: x[1], reverse=True)
        primary_emotion, primary_score = sorted_emotions[0]
        
        # Normalize confidence (0.0-1.0)
        max_possible_score = 15  # Rough maximum intensity
        confidence = min(primary_score / max_possible_score, 1.0)
        
        # Secondary emotions
        secondary = []
        if len(sorted_emotions) > 1:
            for emotion, score in sorted_emotions[1:]:
                secondary.append((emotion, min(score / max_possible_score, 1.0)))
        
        # Determine intensity level (1-5)
        intensity = min(5, max(1, int(primary_score / 2) + 1))
        
        # Override: distress is always high priority
        if primary_emotion == "distress":
            confidence = min(1.0, confidence + 0.2)
        
        return EmotionalCues(
            primary_emotion=primary_emotion,
            confidence=confidence,
            secondary_emotions=secondary,
            vocal_characteristics=self._detect_vocal_characteristics(text),
            emotional_keywords=found_keywords,
            intensity_level=intensity,
        )

    def _detect_vocal_characteristics(self, text: str) -> Dict[str, float]:
        """Infer vocal characteristics from text patterns."""
        characteristics = {}
        text_lower = text.lower()
        
        # Detect rapid speech patterns (fragmented, many connectors)
        rapid_indicators = sum(1 for indicator in self.vocal_indicators["rapid_speech"] 
                              if indicator in text_lower)
        characteristics["rapid_pace"] = min(1.0, rapid_indicators / 3.0)
        
        # Detect slowed/hesitant speech
        slowed_indicators = sum(1 for indicator in self.vocal_indicators["slowed_speech"]
                               if indicator in text_lower)
        characteristics["slow_pace"] = min(1.0, slowed_indicators / 2.0)
        
        # Detect emotional intensity markers (multiple exclamations, caps, etc.)
        intensity_markers = (
            text.count("!") + text.count("?") + 
            sum(1 for c in text if c.isupper()) / max(len(text), 1)
        )
        characteristics["high_intensity"] = min(1.0, intensity_markers / 5.0)
        
        # Detect hesitation/uncertainty
        hesitation_words = ["maybe", "i think", "i guess", "not sure", "kind of"]
        hesitation = sum(1 for word in hesitation_words if word in text_lower)
        characteristics["hesitant"] = min(1.0, hesitation / 2.0)
        
        return characteristics

    def determine_response_tone(self, emotional_cues: EmotionalCues) -> str:
        """Map emotional cues to appropriate response tone."""
        emotion = emotional_cues.primary_emotion
        intensity = emotional_cues.intensity_level
        
        # Safety override: distress always gets maximum care
        if emotion == "distress":
            return "distress"
        
        if emotion == "sadness":
            return "sadness" if intensity >= 3 else "encouragement"
        
        if emotion == "anxiety":
            return "anxiety"
        
        if emotion == "anger":
            return "anger"
        
        if emotion == "happiness" or emotion == "hope_encouragement":
            return "happiness" if intensity >= 3 else "encouragement"
        
        return "neutral"

    def should_ask_follow_up(self, emotional_cues: EmotionalCues) -> bool:
        """Determine if a follow-up question is appropriate.

        Don't ask follow-ups if:
          - User is in severe distress
          - User just shared something very vulnerable
          - High intensity emotional expression
        """
        if emotional_cues.primary_emotion == "distress":
            return False
        
        if emotional_cues.intensity_level >= 4:
            return False
        
        return True

    def get_emotional_context_summary(self, emotional_cues: EmotionalCues) -> str:
        """Create a brief summary of emotional state for logging/analysis."""
        primary = emotional_cues.primary_emotion
        intensity_word = ["minimal", "mild", "moderate", "strong", "critical"][
            emotional_cues.intensity_level - 1
        ]
        
        summary = f"{intensity_word.capitalize()} {primary}"
        
        if emotional_cues.secondary_emotions:
            secondary_str = ", ".join(e[0] for e in emotional_cues.secondary_emotions[:2])
            summary += f" (with {secondary_str})"
        
        return summary

    def track_emotional_pattern(
        self, 
        conversation_history: List[Dict],
        recent_window: int = 5
    ) -> Dict[str, float]:
        """Analyze emotional patterns across recent messages.

        Returns frequency of emotions in recent messages.
        """
        patterns = {}
        
        # Only look at user messages
        user_messages = [m["content"].lower() for m in conversation_history 
                        if m.get("role") == "user"][-recent_window:]
        
        for msg in user_messages:
            cues = self.analyze_emotional_cues(msg)
            emotion = cues.primary_emotion
            patterns[emotion] = patterns.get(emotion, 0) + 1
        
        # Normalize to 0-1 scale
        total = sum(patterns.values())
        if total > 0:
            patterns = {e: c / total for e, c in patterns.items()}
        
        return patterns

    def is_crisis_indicator(self, text: str) -> bool:
        """Detect potential crisis/safety-critical language."""
        crisis_phrases = [
            "i want to die", "i'm going to kill myself", "i'm going to hurt myself",
            "i can't go on", "end it all", "i'm a burden",
        ]
        
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in crisis_phrases)
