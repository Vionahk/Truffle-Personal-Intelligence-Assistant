# Therapeutic AI Assistant Implementation Guide

## Overview

This document outlines the comprehensive implementation of therapeutic AI assistant features, including emotionally intelligent questioning, Gradium voice technology, and memory-driven personalization.

## Key Features Implemented

### 1. **Therapeutic Question Generation** (`modules/therapeutic_questions.py`)

A sophisticated question generation system that asks thoughtful, open-ended questions similar to a therapist's approach.

#### Features:
- **Context-Aware Questions**: Questions are selected based on emotional state and conversation context
- **Question Bank**: 60+ carefully crafted questions organized by context:
  - General wellbeing check-ins
  - Emotional exploration and deepening
  - Coping strategies and resilience
  - Values and meaning exploration
  - Relationship dynamics
  - Goals and aspirations
  - Problem-solving focused questions
  - Reflection and perspective-taking

#### Usage:
```python
from modules import TherapeuticQuestionGenerator

generator = TherapeuticQuestionGenerator(memory_manager, conversation_history)

# Check if this is a good time to ask
if generator.should_ask_question(conversation_length=10, last_was_question=False):
    question = generator.generate_question(
        emotion="sadness",
        conversation_history=history,
        user_profile=profile
    )
    # Question will be None if not appropriate, or a thoughtful question string
```

#### Key Characteristics:
- Never asks back-to-back questions
- Prevents repetition through cooldown tracking (5-minute minimum between similar questions)
- Adjusts question intensity based on emotional state
- Softer questions for distress, more exploratory for neutral/happy states

---

### 2. **Enhanced Emotional Awareness** (`modules/emotional_awareness.py`)

Advanced emotion detection system that analyzes emotional cues with intensity levels and contextual understanding.

#### Features:
- **Detailed Emotion Lexicon**: Categorized by intensity level (critical, severe, moderate, mild)
- **Emotional Cues Analysis**: Returns comprehensive emotional profile:
  - Primary emotion with confidence (0.0-1.0)
  - Secondary emotions list
  - Vocal characteristics (pace, intensity, hesitation)
  - Detected keywords
  - Overall intensity level (1-5)

#### Emotions Detected:
- `distress` (highest priority, safety-first)
- `sadness`
- `anxiety`
- `anger`
- `happiness`
- `hope_encouragement`
- `neutral`

#### Key Methods:
```python
analyzer = EnhancedEmotionalAwareness()

# Analyze emotional state
cues = analyzer.analyze_emotional_cues("I'm feeling really overwhelmed and sad")
# Returns: EmotionalCues with primary_emotion, confidence, intensity_level, etc.

# Determine appropriate response tone
tone = analyzer.determine_response_tone(cues)
# Returns: "sadness", "anxiety", "encouragement", etc.

# Check if follow-up questions are appropriate
if analyzer.should_ask_follow_up(cues):
    # Safe to ask a follow-up question
    pass

# Crisis detection
if analyzer.is_crisis_indicator(text):
    # Safety protocol: prioritize immediate support
    pass
```

#### Safety Features:
- Crisis indicator detection for phrases like "I want to die"
- Distress always overrides other emotions
- Minimum confidence thresholds to avoid false positives

---

### 3. **Gradium Voice Technology Validation** (`modules/speaker.py` enhancements)

Ensured consistent, emotionally expressive voice output with Abigail as the single, trusted voice.

#### Voice Configuration:
- **Single Voice**: "Abigail" - described as having empathy and warmth
- **Voice ID**: `KRo-uwfno-KcEgBM`
- **Emotional Adaptation**: Through three parameters:
  - `padding_bonus`: Speed control (-4 faster to +4 slower)
  - `temp`: Expressiveness (0 flat to 1.4 very expressive)
  - `cfg_coef`: Voice fidelity (1-4, affecting warmth)

#### Emotion-to-Voice Mapping:
| Emotion | Speed | Expressiveness | Fidelity | Effect |
|---------|-------|-----------------|---------|--------|
| distress | 1.5 (slow) | 0.3 (stable) | 2.5 (tight) | Maximum gentleness |
| sadness | 1.0 | 0.4 | 2.2 | Gentle & warm |
| anxiety | 0.8 | 0.35 | 2.2 | Grounding & calm |
| anger | 0.5 | 0.4 | 2.0 | Steady & composed |
| happiness | -0.3 (quick) | 0.85 (expressive) | 2.0 | Warm & bright |
| encouragement | -0.2 | 0.7 | 2.0 | Uplifting |
| neutral | 0.0 | 0.7 | 2.0 | Natural |

#### New Validation Methods:
```python
speaker = SpeakerModule(config)

# Get voice configuration info
info = speaker.get_voice_info()
# Returns: voice name, ID, engine, supported emotions

# Validate Gradium is ready
if speaker.validate_gradium_ready():
    print("✓ Gradium ready with Abigail voice")
```

---

### 4. **Enhanced Memory-Based Personalization** (`modules/memory_manager.py` additions)

New methods for tracking emotional responses and learning what works for each user.

#### New Memory Tracking:

1. **Emotional Learning**:
   ```python
   memory.log_emotional_response(
       emotion_detected="sadness",
       user_statement="I'm feeling really down today",
       assistant_response="That sounds really hard.",
       response_type="validation",
       perceived_helpfulness=4  # 1-5 rating
   )
   
   # Later retrieve patterns
   patterns = memory.get_emotional_patterns(emotion="sadness", limit=10)
   ```

2. **Coping Strategies**:
   ```python
   memory.track_coping_strategy(
       strategy_name="taking a walk",
       emotional_context="anxiety",
       perceived_effectiveness=4,
       notes="Works especially well in the afternoon"
   )
   
   # Get effective strategies for a given emotion
   strategies = memory.get_effective_coping_strategies(emotion="anxiety")
   ```

3. **Communication Preferences**:
   ```python
   memory.log_communication_preference(
       preference_type="direct",
       description="Prefer straightforward advice without much preamble",
       context="when making decisions"
   )
   
   # Retrieve preferences
   prefs = memory.get_communication_preferences()
   ```

---

### 5. **Controller Integration** (`core/controller.py` enhancements)

Updated main assistant controller to orchestrate all new features.

#### Key Changes:

1. **Initialization**:
   ```python
   self.emotional_analyzer = EnhancedEmotionalAwareness()
   self.question_generator = TherapeuticQuestionGenerator(
       memory_manager=self.memory,
       conversation_history=self.conversation,
   )
   self._last_response_was_question = False
   ```

2. **Enhanced Response Pipeline**:
   ```python
   def _respond(self, user_text: str):
       # 1. Analyze emotional cues comprehensively
       emotional_cues = self.emotional_analyzer.analyze_emotional_cues(user_text)
       detected_emotion = self.emotional_analyzer.determine_response_tone(emotional_cues)
       
       # 2. Detect crisis indicators
       if self.emotional_analyzer.is_crisis_indicator(user_text):
           detected_emotion = "distress"  # Priority handling
       
       # 3. Get LLM response with emotion context
       response = self.llm.send_message(...)
       
       # 4. Speak with emotion-adapted voice
       self.speaker.speak(reply, emotion=detected_emotion)
       
       # 5. Optionally ask therapeutic follow-up question
       if self.question_generator.should_ask_question(...):
           follow_up = self.question_generator.generate_question(...)
           self.speaker.speak(follow_up, emotion="encouragement")
   ```

---

### 6. **Enhanced System Prompt** (`core/controller.py` - _system_prompt)

The system prompt now explicitly instructs the LLM to:
- Ask thoughtful, open-ended questions similar to therapeutic listening
- Adapt question timing and intensity to emotional state
- Use memory actively for personalization
- Track communication preferences
- Provide genuine connection rather than generic responses

#### Key System Prompt Sections:
- **Therapeutic Questioning**: Explicit guidance on question types, timing, and when NOT to ask
- **Emotional Awareness**: Matching emotional register and validating without platitudes
- **Memory Integration**: Using preferences, past conversations, and coping strategies
- **Conversation Flow**: Natural progression that prioritizes presence over perfection

---

## Architecture Flow

```
User Input (Voice) 
    ↓
Microphone Module (STT)
    ↓
Controller._on_speech()
    ↓
Controller._respond()
    ├─→ EnhancedEmotionalAwareness.analyze_emotional_cues()
    ├─→ Crisis Detection Check
    ├─→ MemoryManager.load_user_profile() & preferences
    ├─→ LLMClient.send_message() (with emotion context)
    ├─→ Speaker.speak() (with emotion-adapted voice)
    └─→ TherapeuticQuestionGenerator.should_ask_question()
        └─→ Generate follow-up question (optional)
            └─→ Speaker.speak() (question with gentle tone)
    ↓
Memory.log_emotional_response() & track preferences
    ↓
Continue listening for next user input
```

---

## Emotional Context Injection

When the controller detects an emotion, it provides context to the LLM:

```
[EMOTIONAL CONTEXT — DISTRESS DETECTED]
The user is in significant emotional distress right now. 
Your response will be spoken in a very slow, calm, steady voice. 
Respond with maximum gentleness. Use short, grounding sentences.
Do NOT minimize their pain. Do NOT rush to solutions.
Acknowledge what they're going through first. Be present.
```

This guidance shapes both the text response AND the voice delivery parameters.

---

## Best Practices

### For Developers:

1. **Always initialize both emotion analyzer and question generator** in the controller
2. **Check crisis indicators early** in the response pipeline (safety-first)
3. **Store emotional exchanges** for future learning and pattern analysis
4. **Never force questions** - let the question_generator.should_ask_question() determine timing
5. **Validate Gradium on startup** using speaker.validate_gradium_ready()

### For Conversation Design:

1. **Ask questions naturally**, not robotically
2. **Vary question types** - not always "how do you feel?"
3. **Respect emotional intensity** - softer questions for high distress
4. **Use memory actively** - reference past coping strategies that worked
5. **Track what helps** - log emotional responses and communication preferences

### For Voice Delivery:

1. **Distress always gets slowest, gentlest voice** (padding_bonus=1.5)
2. **Happy/excited states get faster, warmer voice** (padding_bonus=-0.3)
3. **Always use Abigail voice** for consistency (never switch voices)
4. **Emotion parameters affect latency** - distress takes longer but is worth the wait

---

## Testing Checklist

- [ ] Import errors resolved for all new modules
- [ ] Syntax errors cleared
- [ ] Emotional analyzer correctly detects all emotion types
- [ ] Questions generated without back-to-back repetition
- [ ] Gradium voice initialization successful
- [ ] System prompt includes therapeutic guidance
- [ ] Crisis indicators detected properly
- [ ] Memory tracking functions work correctly
- [ ] Question generator respects emotional intensity
- [ ] Controller properly passes emotion to speaker module

---

## Configuration

No new configuration files needed. All settings are in existing files:
- `config.py` - TTS engine settings
- `.env` - API keys (GRADIO_API_KEY required)
- `data/user_profile.json` - User preferences and learned behaviors
- `data/emotional_learning.json` - (auto-created) Emotional response tracking

---

## Future Enhancements

1. **Voice Tone Analysis**: Analyze actual audio characteristics (pitch, pace, volume) from raw audio before transcription
2. **Real-time Emotion Tracking**: Monitor emotional patterns across sessions and proactively check in
3. **Question Effectiveness Tracking**: Learn which question types work best for each emotion
4. **Adaptive Question Generation**: Generate custom questions based on learned patterns
5. **Voice Synthesis Fine-tuning**: Additional voice parameters based on user preferences
6. **Sentiment Momentum**: Track if conversation is moving toward or away from distress

---

## Files Modified/Created

### New Files:
- `modules/therapeutic_questions.py` - 290 lines
- `modules/emotional_awareness.py` - 280 lines
- `IMPLEMENTATION_GUIDE.md` - This file

### Modified Files:
- `core/controller.py` - Added emotional awareness, question generation, enhanced system prompt
- `modules/speaker.py` - Added validation methods for Gradium consistency
- `modules/memory_manager.py` - Added emotional learning, coping strategies, preferences tracking
- `modules/__init__.py` - Added exports for new modules

---

## Support & Debugging

### Gradium Not Working?
```python
speaker.validate_gradium_ready()  # Returns False with error message
# Check: GRADIO_API_KEY environment variable is set
# Check: gradium SDK is installed: pip install gradium
```

### Questions Not Being Asked?
```python
# Check if conditions are met:
# 1. Conversation has at least 2 exchanges
# 2. Last response wasn't a question
# 3. Emotional intensity allows it (not distressed)
# 4. Question hasn't been asked within last 5 minutes (cooldown)
```

### Emotion Not Detected?
```python
# Low-confidence emotions default to "neutral"
# Minimum score threshold is 2 (adjustable in emotional_awareness.py)
# Distress always overrides other emotions if detected
```

---

## References

- Therapeutic Questioning: Inspired by motivational interviewing, solution-focused therapy
- Voice Parameters: Gradium documentation on emotional voice synthesis
- Memory Architecture: Persistent context for cross-session continuity
- Safety: Crisis indicator detection aligned with mental health safety protocols

