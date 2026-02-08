# Truffle — AI Voice Companion

Truffle is a 3D cat AI assistant that listens to you, understands how you feel, and speaks back with a warm, emotionally adaptive voice. Built for QHacks.

---

## Quick Start

```powershell
cd C:\QHacks\ai_assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python website/server.py
```

Open **http://localhost:5000** in Chrome or Edge.

---

## How It Works

1. You speak into your microphone (or type)
2. Truffle detects your emotional state from what you said
3. An LLM generates a thoughtful, empathetic response
4. Truffle speaks back with a voice that adapts to your mood
5. The mic automatically listens again — one click to start, one click to stop

---

## Emotion Detection and Voice

Truffle reads your words and adjusts both the response and the voice tone:

| Emotion | Voice Style | Example Triggers |
|---------|------------|-----------------|
| Distress | Very slow and calm | "I can't do this", "help me" |
| Sadness | Slow and gentle | "I feel alone", "hopeless" |
| Anxiety | Measured and grounding | "I'm stressed", "overwhelmed" |
| Anger | Calm and steady | "I'm furious", "fed up" |
| Happiness | Bright and energetic | "I'm so excited", "best day" |
| Neutral | Warm and conversational | General chat |

The voice stays the same person (Abigail) — only the speed and expressiveness change so it always sounds natural.

### System Response per Emotion

| Emotion | Speed (padding_bonus) | Temperature | LLM Guidance Injected | TTS Effect |
|---------|----------------------|-------------|----------------------|------------|
| Distress | 1.8 | 0.25 | `[URGENT — DISTRESS DETECTED]` — max gentleness, grounding sentences, no minimizing | Slowest delivery, minimal pitch variation |
| Sadness | 1.2 | 0.35 | `[SADNESS]` — validate pain, no fix attempts, no cliches | Slow pace, gentle steady tone |
| Anxiety | 1.0 | 0.30 | `[ANXIETY / STRESS]` — grounding anchor, acknowledge specific worry, guide to one step | Measured pace, calm and controlled |
| Anger | 0.6 | 0.40 | `[ANGER / FRUSTRATION]` — validate without matching intensity, no lecturing | Moderate pace, level and stable |
| Happiness | -0.4 | 0.90 | `[HAPPINESS / EXCITEMENT]` — match energy, celebrate, ask what sparked it | Faster delivery, high expressiveness |
| Curiosity | 0.0 | 0.75 | `[CURIOSITY / EXPLORATION]` — engage thoughtfully, explore together | Natural pace, engaged variation |
| Neutral | 0.1 | 0.70 | None — default system prompt | Relaxed, natural conversational tone |

- **Speed (padding_bonus)**: Positive values slow the voice; negative values speed it up
- **Temperature**: Higher = more expressive variation; lower = steadier and calmer
- **LLM Guidance**: Emotion-specific instructions appended to the system prompt before each LLM call

---

## Memory

Truffle remembers across conversations:

- Your name, likes, dislikes, and concerns
- Emotional patterns over time
- Full conversation history (last 200 exchanges)

All stored locally in `website/data/`. No cloud, no third parties.

---

## What Was Improved

| Area | Before | After |
|------|--------|-------|
| Voice output | None | Gradium TTS with emotional variation |
| Voice input | Unreliable browser API | Server-side speech recognition |
| Emotion awareness | None | 7-category detection with voice modulation |
| Memory | Nothing persisted | Profile + chat log across sessions |
| Interface | Terminal only | 3D animated cat with breed customization |
| Conversation quality | Generic responses | Empathetic, personalized, no repetition |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No voice | Check `GRADIO_API_KEY` in `.env` |
| Mic blocked | Chrome → address bar lock icon → allow microphone |
| No AI response | Check `GEMINI_API_KEY` in `.env`, look at terminal logs |
| 3D not loading | Clear browser cache and refresh |

---

Built for QHacks.
