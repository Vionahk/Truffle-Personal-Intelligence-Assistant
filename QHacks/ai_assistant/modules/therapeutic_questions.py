"""Therapeutic question generator — context-aware, empathetic inquiry system.

Provides thoughtful, open-ended questions similar to a therapist's approach.
Questions are:
  - Natural and conversational (not clinical or robotic)
  - Context-aware (based on emotional state, conversation history, user profile)
  - Non-repetitive (track asked questions, vary phrasing)
  - Emotionally intelligent (match the user's registration)
  - Memory-integrated (reference past shares when appropriate)

Design inspired by motivational interviewing, solution-focused therapy, and
person-centered counseling approaches.
"""

from typing import List, Optional, Dict
from enum import Enum
import random
import time
from dataclasses import dataclass


class QuestionContext(Enum):
    """Question category based on conversation context."""
    GENERAL_WELLBEING = "general_wellbeing"
    EMOTIONAL_EXPLORATION = "emotional_exploration"
    COPING_AND_RESILIENCE = "coping_and_resilience"
    VALUES_AND_MEANING = "values_and_meaning"
    RELATIONSHIPS = "relationships"
    GOALS_AND_ASPIRATIONS = "goals_and_aspirations"
    PROBLEM_SOLVING = "problem_solving"
    REFLECTION = "reflection"


@dataclass
class TherapeuticQuestion:
    """A single therapeutic question with metadata."""
    text: str
    context: QuestionContext
    emotional_fit: List[str]  # Emotions this fits (e.g., ["sadness", "grief"])
    intensity: int  # 1=gentle, 5=deep/challenging
    variability_id: str  # For grouping similar questions for variation


class TherapeuticQuestionGenerator:
    """Generate contextual, empathetic self-reflective questions."""

    def __init__(self, memory_manager=None, conversation_history=None):
        self.memory = memory_manager
        self.conversation = conversation_history
        self._asked_questions: Dict[str, float] = {}  # Track recently asked questions
        self._cooldown_seconds = 300  # Don't repeat same base question for 5 minutes
        self._random = random.Random()

    # =========================================================================
    # Question banks — organized by context and emotional fit
    # =========================================================================

    _GENERAL_WELLBEING_QUESTIONS = [
        TherapeuticQuestion(
            text="How are you doing with everything today?",
            context=QuestionContext.GENERAL_WELLBEING,
            emotional_fit=["neutral", "happiness", "encouragement"],
            intensity=1,
            variability_id="check_in_basic"
        ),
        TherapeuticQuestion(
            text="What's been on your mind lately?",
            context=QuestionContext.GENERAL_WELLBEING,
            emotional_fit=["neutral", "anxiety", "sadness"],
            intensity=1,
            variability_id="check_in_basic"
        ),
        TherapeuticQuestion(
            text="Tell me what a typical day is like for you right now.",
            context=QuestionContext.GENERAL_WELLBEING,
            emotional_fit=["neutral", "happiness"],
            intensity=2,
            variability_id="routine_exploration"
        ),
        TherapeuticQuestion(
            text="What's something small that made you feel better this week?",
            context=QuestionContext.GENERAL_WELLBEING,
            emotional_fit=["sadness", "anxiety", "neutral"],
            intensity=2,
            variability_id="wellbeing_anchor"
        ),
    ]

    _EMOTIONAL_EXPLORATION_QUESTIONS = [
        TherapeuticQuestion(
            text="Can you tell me more about what that feels like?",
            context=QuestionContext.EMOTIONAL_EXPLORATION,
            emotional_fit=["sadness", "anxiety", "anger", "distress"],
            intensity=2,
            variability_id="deepen_emotion"
        ),
        TherapeuticQuestion(
            text="What was the hardest part of that for you?",
            context=QuestionContext.EMOTIONAL_EXPLORATION,
            emotional_fit=["sadness", "distress", "anger"],
            intensity=3,
            variability_id="difficulty_focus"
        ),
        TherapeuticQuestion(
            text="When did you first notice you were feeling this way?",
            context=QuestionContext.EMOTIONAL_EXPLORATION,
            emotional_fit=["sadness", "anxiety", "anger"],
            intensity=2,
            variability_id="emotion_timeline"
        ),
        TherapeuticQuestion(
            text="How long has this been going on?",
            context=QuestionContext.EMOTIONAL_EXPLORATION,
            emotional_fit=["sadness", "anxiety", "distress"],
            intensity=1,
            variability_id="duration_check"
        ),
        TherapeuticQuestion(
            text="What made you decide to talk about this with me?",
            context=QuestionContext.EMOTIONAL_EXPLORATION,
            emotional_fit=["sadness", "anxiety", "distress"],
            intensity=2,
            variability_id="sharing_decision"
        ),
    ]

    _COPING_AND_RESILIENCE_QUESTIONS = [
        TherapeuticQuestion(
            text="What helps you get through difficult moments like this?",
            context=QuestionContext.COPING_AND_RESILIENCE,
            emotional_fit=["sadness", "anxiety", "anger", "distress"],
            intensity=2,
            variability_id="coping_strategies"
        ),
        TherapeuticQuestion(
            text="When things have been hard before, what helped you move forward?",
            context=QuestionContext.COPING_AND_RESILIENCE,
            emotional_fit=["sadness", "distress"],
            intensity=3,
            variability_id="past_resilience"
        ),
        TherapeuticQuestion(
            text="Who or what do you lean on when you need support?",
            context=QuestionContext.COPING_AND_RESILIENCE,
            emotional_fit=["sadness", "anxiety", "distress"],
            intensity=2,
            variability_id="support_system"
        ),
        TherapeuticQuestion(
            text="What's something you're proud of managing, even if it felt small?",
            context=QuestionContext.COPING_AND_RESILIENCE,
            emotional_fit=["sadness", "anxiety"],
            intensity=2,
            variability_id="small_wins"
        ),
        TherapeuticQuestion(
            text="Have you been able to do anything that usually makes you feel better?",
            context=QuestionContext.COPING_AND_RESILIENCE,
            emotional_fit=["sadness", "anxiety"],
            intensity=1,
            variability_id="self_care_check"
        ),
    ]

    _VALUES_AND_MEANING_QUESTIONS = [
        TherapeuticQuestion(
            text="What matters most to you right now?",
            context=QuestionContext.VALUES_AND_MEANING,
            emotional_fit=["neutral", "sadness", "happiness"],
            intensity=3,
            variability_id="values_clarity"
        ),
        TherapeuticQuestion(
            text="When do you feel most like yourself?",
            context=QuestionContext.VALUES_AND_MEANING,
            emotional_fit=["sadness", "neutral"],
            intensity=2,
            variability_id="authentic_self"
        ),
        TherapeuticQuestion(
            text="What would help you feel more at peace?",
            context=QuestionContext.VALUES_AND_MEANING,
            emotional_fit=["anxiety", "sadness", "distress"],
            intensity=3,
            variability_id="peace_seeking"
        ),
        TherapeuticQuestion(
            text="If things could be different, what would that look like?",
            context=QuestionContext.VALUES_AND_MEANING,
            emotional_fit=["sadness", "anxiety", "anger"],
            intensity=3,
            variability_id="future_vision"
        ),
    ]

    _RELATIONSHIPS_QUESTIONS = [
        TherapeuticQuestion(
            text="How are the people closest to you doing with all of this?",
            context=QuestionContext.RELATIONSHIPS,
            emotional_fit=["sadness", "anxiety", "distress"],
            intensity=2,
            variability_id="relationship_impact"
        ),
        TherapeuticQuestion(
            text="Is there someone you'd like to talk to about what you're going through?",
            context=QuestionContext.RELATIONSHIPS,
            emotional_fit=["sadness", "loneliness", "distress"],
            intensity=2,
            variability_id="support_seeking"
        ),
        TherapeuticQuestion(
            text="What does support look like for you? How do people best help you?",
            context=QuestionContext.RELATIONSHIPS,
            emotional_fit=["sadness", "anxiety"],
            intensity=2,
            variability_id="support_preferences"
        ),
    ]

    _GOALS_AND_ASPIRATIONS_QUESTIONS = [
        TherapeuticQuestion(
            text="What's something you'd like to work toward, even just a small step?",
            context=QuestionContext.GOALS_AND_ASPIRATIONS,
            emotional_fit=["neutral", "sadness", "anxiety"],
            intensity=2,
            variability_id="next_steps"
        ),
        TherapeuticQuestion(
            text="What would make a difference for you this week?",
            context=QuestionContext.GOALS_AND_ASPIRATIONS,
            emotional_fit=["sadness", "anxiety"],
            intensity=2,
            variability_id="weekly_win"
        ),
        TherapeuticQuestion(
            text="If you could focus on one thing, what would be most helpful right now?",
            context=QuestionContext.GOALS_AND_ASPIRATIONS,
            emotional_fit=["anxiety", "overwhelm"],
            intensity=2,
            variability_id="priority_focus"
        ),
    ]

    _PROBLEM_SOLVING_QUESTIONS = [
        TherapeuticQuestion(
            text="What's the part of this you have the most control over?",
            context=QuestionContext.PROBLEM_SOLVING,
            emotional_fit=["anxiety", "distress"],
            intensity=2,
            variability_id="control_focus"
        ),
        TherapeuticQuestion(
            text="Have you tried anything to address this? What happened?",
            context=QuestionContext.PROBLEM_SOLVING,
            emotional_fit=["anxiety", "anger"],
            intensity=2,
            variability_id="attempted_solutions"
        ),
        TherapeuticQuestion(
            text="What would help right now — some practical idea, or just someone to listen?",
            context=QuestionContext.PROBLEM_SOLVING,
            emotional_fit=["anxiety", "sadness", "distress"],
            intensity=2,
            variability_id="support_type"
        ),
    ]

    _REFLECTION_QUESTIONS = [
        TherapeuticQuestion(
            text="Looking back, what do you notice about how you handled that?",
            context=QuestionContext.REFLECTION,
            emotional_fit=["neutral", "happiness"],
            intensity=3,
            variability_id="experience_reflection"
        ),
        TherapeuticQuestion(
            text="What's one thing you've learned about yourself recently?",
            context=QuestionContext.REFLECTION,
            emotional_fit=["neutral", "happiness"],
            intensity=2,
            variability_id="self_learning"
        ),
        TherapeuticQuestion(
            text="If you were talking to a friend in this situation, what would you tell them?",
            context=QuestionContext.REFLECTION,
            emotional_fit=["sadness", "anxiety", "distress"],
            intensity=3,
            variability_id="perspective_shift"
        ),
    ]

    # =========================================================================
    # Public API
    # =========================================================================

    def should_ask_question(self, conversation_length: int, last_was_question: bool) -> bool:
        """Determine if now is a good time to ask a question.

        Strategy:
          - Usually 30-40% of the time we respond with a question
          - Never ask back-to-back questions
          - More likely to ask after 2+ exchanges (give context)
        """
        # Don't ask if we just asked
        if last_was_question:
            return False

        # Need at least 2 exchanges of user input to generate context
        if conversation_length < 2:
            return False

        # Probabilistic — aim for ~35% of responses to be questions
        return self._random.random() < 0.35

    def generate_question(
        self,
        emotion: str,
        context: Optional[QuestionContext] = None,
        conversation_history: Optional[List[Dict]] = None,
        user_profile: Optional[Dict] = None,
    ) -> Optional[str]:
        """Generate a contextually appropriate question.

        Args:
            emotion: Detected emotion ("sadness", "anxiety", "anger", "happiness", etc.)
            context: Optionally specify the question context
            conversation_history: Recent conversation messages
            user_profile: User's stored profile info

        Returns:
            A natural, open-ended question, or None if no appropriate question found.
        """
        # Select applicable question banks based on emotion context
        banks = self._select_question_banks(emotion, context)
        if not banks:
            return None

        # Filter out recently asked questions
        eligible = self._filter_eligible_questions(banks)
        if not eligible:
            return None

        # Pick one
        question = self._random.choice(eligible)

        # Personalize if possible
        personalized = self._personalize_question(
            question, user_profile, conversation_history
        )

        # Mark as asked
        self._mark_question_asked(question.variability_id)

        return personalized

    # =========================================================================
    # Internal methods
    # =========================================================================

    def _select_question_banks(
        self, emotion: str, context: Optional[QuestionContext]
    ) -> List[List[TherapeuticQuestion]]:
        """Select which question banks to draw from.

        Returns list of question lists to sample from.
        """
        # If context specified, use it; otherwise infer from emotion
        if context:
            bank_map = {
                QuestionContext.GENERAL_WELLBEING: [self._GENERAL_WELLBEING_QUESTIONS],
                QuestionContext.EMOTIONAL_EXPLORATION: [self._EMOTIONAL_EXPLORATION_QUESTIONS],
                QuestionContext.COPING_AND_RESILIENCE: [self._COPING_AND_RESILIENCE_QUESTIONS],
                QuestionContext.VALUES_AND_MEANING: [self._VALUES_AND_MEANING_QUESTIONS],
                QuestionContext.RELATIONSHIPS: [self._RELATIONSHIPS_QUESTIONS],
                QuestionContext.GOALS_AND_ASPIRATIONS: [self._GOALS_AND_ASPIRATIONS_QUESTIONS],
                QuestionContext.PROBLEM_SOLVING: [self._PROBLEM_SOLVING_QUESTIONS],
                QuestionContext.REFLECTION: [self._REFLECTION_QUESTIONS],
            }
            return bank_map.get(context, [])

        # Infer from emotion
        if emotion in ("sadness", "distress", "anxiety"):
            # For distressed states: prioritize coping, emotional exploration
            return [
                self._EMOTIONAL_EXPLORATION_QUESTIONS,
                self._COPING_AND_RESILIENCE_QUESTIONS,
                self._PROBLEM_SOLVING_QUESTIONS,
            ]
        elif emotion == "anger":
            return [
                self._COPING_AND_RESILIENCE_QUESTIONS,
                self._PROBLEM_SOLVING_QUESTIONS,
                self._REFLECTION_QUESTIONS,
            ]
        elif emotion == "happiness":
            return [
                self._REFLECTION_QUESTIONS,
                self._GOALS_AND_ASPIRATIONS_QUESTIONS,
                self._VALUES_AND_MEANING_QUESTIONS,
            ]
        else:  # neutral, encouragement
            return [
                self._GENERAL_WELLBEING_QUESTIONS,
                self._COPING_AND_RESILIENCE_QUESTIONS,
            ]

    def _filter_eligible_questions(
        self, banks: List[List[TherapeuticQuestion]]
    ) -> List[TherapeuticQuestion]:
        """Filter out recently asked questions and construct eligible pool."""
        now = time.time()
        eligible = []

        for bank in banks:
            for q in bank:
                # Skip if asked recently
                last_asked = self._asked_questions.get(q.variability_id, 0)
                if (now - last_asked) < self._cooldown_seconds:
                    continue
                eligible.append(q)

        return eligible

    def _personalize_question(
        self,
        question: TherapeuticQuestion,
        user_profile: Optional[Dict],
        conversation_history: Optional[List[Dict]],
    ) -> str:
        """Optionally personalize the question with user info.

        For now, just return the base question. In future, could:
          - Reference the user's name
          - Substitute specific details from their profile
          - Tailor intensity based on relationship strength
        """
        return question.text

    def _mark_question_asked(self, variability_id: str) -> None:
        """Record that a question was asked (cooldown tracking)."""
        self._asked_questions[variability_id] = time.time()

    # =========================================================================
    # Utility methods for emotional fit
    # =========================================================================

    def get_questions_for_emotion(self, emotion: str) -> List[str]:
        """Get all question options that fit a given emotion."""
        all_banks = [
            self._GENERAL_WELLBEING_QUESTIONS,
            self._EMOTIONAL_EXPLORATION_QUESTIONS,
            self._COPING_AND_RESILIENCE_QUESTIONS,
            self._VALUES_AND_MEANING_QUESTIONS,
            self._RELATIONSHIPS_QUESTIONS,
            self._GOALS_AND_ASPIRATIONS_QUESTIONS,
            self._PROBLEM_SOLVING_QUESTIONS,
            self._REFLECTION_QUESTIONS,
        ]
        
        matching = []
        for bank in all_banks:
            for q in bank:
                if emotion in q.emotional_fit:
                    matching.append(q.text)
        return matching
