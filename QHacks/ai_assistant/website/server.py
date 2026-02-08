"""Flask server for Ruby AI Assistant website.

Serves the 3D interactive frontend and proxies requests to:
  - Gradium TTS API  (POST /api/tts)
  - LLM chat API     (POST /api/chat)
  - Voice catalog    (GET  /api/voices)

Run:
  python website/server.py            # local only
  python website/server.py --public   # auto-creates public ngrok URL
"""

import os
import sys
import json
import asyncio
import threading
import re

from flask import Flask, request, jsonify, send_from_directory, Response

# Add parent directory so we can load .env and shared deps
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

try:
    import gradium

    _HAS_GRADIUM = True
except ImportError:
    _HAS_GRADIUM = False

try:
    import requests as http_req
except ImportError:
    http_req = None

import time

# ── HTTP session for connection reuse (saves ~300ms per call) ─
_http_session = None

def _get_session():
    global _http_session
    if _http_session is None and http_req:
        _http_session = http_req.Session()
        # Keep-alive + connection pooling
        adapter = http_req.adapters.HTTPAdapter(
            pool_connections=4, pool_maxsize=8, max_retries=1
        )
        _http_session.mount("https://", adapter)
        _http_session.mount("http://", adapter)
    return _http_session

# ── Flask app ─────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(_HERE, "static"))


# ── Persistent user profile memory ────────────────────────────
_DATA_DIR = os.path.join(_HERE, "data")
_PROFILE_PATH = os.path.join(_DATA_DIR, "user_profile.json")
_CHAT_LOG_PATH = os.path.join(_DATA_DIR, "chat_log.json")

_DEFAULT_PROFILE = {
    "name": "",
    "likes": [],
    "dislikes": [],
    "values": [],
    "concerns": [],
    "personality_traits": [],
    "communication_style": "",
    "emotional_patterns": [],
    "comfort_preferences": [],
    "important_facts": [],
    "session_count": 0,
}

_user_profile = {}
_chat_log = []  # persistent conversation log across restarts


def _load_profile():
    global _user_profile, _chat_log
    os.makedirs(_DATA_DIR, exist_ok=True)
    try:
        with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
            _user_profile = json.load(f)
        print(f"[MEMORY] Loaded user profile: {_user_profile.get('name', 'unnamed')}")
    except (FileNotFoundError, json.JSONDecodeError):
        _user_profile = dict(_DEFAULT_PROFILE)
        print("[MEMORY] Starting fresh user profile")
    try:
        with open(_CHAT_LOG_PATH, "r", encoding="utf-8") as f:
            _chat_log = json.load(f)
        print(f"[MEMORY] Loaded {len(_chat_log)} past messages")
    except (FileNotFoundError, json.JSONDecodeError):
        _chat_log = []


def _save_profile():
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(_user_profile, f, indent=2)


def _save_chat_log():
    os.makedirs(_DATA_DIR, exist_ok=True)
    # Keep last 200 exchanges to avoid unbounded growth
    trimmed = _chat_log[-400:]
    with open(_CHAT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, indent=2)


def _extract_user_info(user_msg):
    """Extract personal info from user message using pattern matching."""
    lower = user_msg.lower().strip()
    changed = False

    # Name detection
    for pattern in ["my name is ", "i'm ", "i am ", "call me ", "name's "]:
        if pattern in lower:
            after = lower.split(pattern, 1)[1]
            name = after.split()[0].strip(".,!?'\"") if after else ""
            # Filter out common non-name words
            skip = {"not", "so", "very", "really", "just", "going", "doing",
                    "feeling", "a", "the", "fine", "good", "okay", "bad",
                    "happy", "sad", "tired", "stressed", "here", "back"}
            if name and len(name) > 1 and name not in skip:
                _user_profile["name"] = name.capitalize()
                changed = True
                break

    # Preference extraction (likes)
    like_patterns = [
        r"i (?:really |absolutely )?(?:love|like|enjoy|adore)\s+(.+?)(?:\.|,|!|$)",
        r"(?:my favorite|i prefer)\s+(.+?)(?:\.|,|!|$)",
    ]
    for pat in like_patterns:
        m = re.search(pat, lower)
        if m:
            thing = m.group(1).strip()[:80]
            if thing and thing not in _user_profile.get("likes", []):
                _user_profile.setdefault("likes", []).append(thing)
                _user_profile["likes"] = _user_profile["likes"][-20:]
                changed = True

    # Dislike extraction
    dislike_patterns = [
        r"i (?:really |absolutely )?(?:hate|dislike|can't stand|don't like)\s+(.+?)(?:\.|,|!|$)",
    ]
    for pat in dislike_patterns:
        m = re.search(pat, lower)
        if m:
            thing = m.group(1).strip()[:80]
            if thing and thing not in _user_profile.get("dislikes", []):
                _user_profile.setdefault("dislikes", []).append(thing)
                _user_profile["dislikes"] = _user_profile["dislikes"][-20:]
                changed = True

    # Concern extraction
    concern_patterns = [
        r"i'm (?:worried|stressed|anxious|concerned|afraid|scared) (?:about|of|that)\s+(.+?)(?:\.|,|!|$)",
        r"(?:struggling|dealing) with\s+(.+?)(?:\.|,|!|$)",
    ]
    for pat in concern_patterns:
        m = re.search(pat, lower)
        if m:
            concern = m.group(1).strip()[:100]
            if concern and concern not in _user_profile.get("concerns", []):
                _user_profile.setdefault("concerns", []).append(concern)
                _user_profile["concerns"] = _user_profile["concerns"][-15:]
                changed = True

    # Value extraction
    value_patterns = [
        r"(?:what matters|important) to me is\s+(.+?)(?:\.|,|!|$)",
        r"i (?:really )?(?:value|believe in|care about)\s+(.+?)(?:\.|,|!|$)",
    ]
    for pat in value_patterns:
        m = re.search(pat, lower)
        if m:
            val = m.group(1).strip()[:80]
            if val and val not in _user_profile.get("values", []):
                _user_profile.setdefault("values", []).append(val)
                _user_profile["values"] = _user_profile["values"][-15:]
                changed = True

    # Track emotional patterns
    emotion = _detect_emotion(user_msg)
    if emotion != "neutral":
        patterns = _user_profile.setdefault("emotional_patterns", [])
        entry = f"{emotion}"
        if entry not in patterns[-5:] if patterns else True:
            patterns.append(entry)
            _user_profile["emotional_patterns"] = patterns[-30:]
            changed = True

    if changed:
        _save_profile()
        print(f"[MEMORY] Profile updated: {json.dumps(_user_profile, indent=None)[:200]}")


def _build_profile_context():
    """Build a natural-language summary of what we know about the user."""
    p = _user_profile
    if not any(p.get(k) for k in ["name", "likes", "dislikes", "concerns", "values",
                                    "personality_traits", "important_facts"]):
        return ""

    parts = []
    if p.get("name"):
        parts.append(f"Their name is {p['name']}.")
    if p.get("likes"):
        parts.append(f"They enjoy: {', '.join(p['likes'][-8:])}.")
    if p.get("dislikes"):
        parts.append(f"They dislike: {', '.join(p['dislikes'][-5:])}.")
    if p.get("values"):
        parts.append(f"They value: {', '.join(p['values'][-5:])}.")
    if p.get("concerns"):
        parts.append(f"Current concerns: {', '.join(p['concerns'][-5:])}.")
    if p.get("personality_traits"):
        parts.append(f"Personality: {', '.join(p['personality_traits'][-5:])}.")
    if p.get("communication_style"):
        parts.append(f"Communication style: {p['communication_style']}.")
    if p.get("comfort_preferences"):
        parts.append(f"They feel comforted by: {', '.join(p['comfort_preferences'][-5:])}.")
    if p.get("important_facts"):
        parts.append(f"Key facts: {', '.join(p['important_facts'][-8:])}.")
    if p.get("emotional_patterns"):
        recent = p["emotional_patterns"][-5:]
        parts.append(f"Recent emotional patterns: {', '.join(recent)}.")

    return "\n[WHAT YOU KNOW ABOUT THIS PERSON]\n" + " ".join(parts)


# ── Async bridge (for Gradium SDK) ───────────────────────────
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()


def _run_async(coro, timeout=30):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout)


# ── Gradium client (lazy singleton) ──────────────────────────
_gclient = None


def _get_gradium():
    global _gclient
    key = os.getenv("GRADIO_API_KEY", "")
    if _gclient is None and key and _HAS_GRADIUM:
        _gclient = gradium.client.GradiumClient(api_key=key)
    return _gclient


# ── Curated English voice catalog ────────────────────────────
VOICES = [
    {
        "id": "KRo-uwfno-KcEgBM",
        "name": "Abigail",
        "gender": "F",
        "accent": "US",
        "desc": "Warm & empathetic \u2014 adds a touch of magic to every conversation",
    },
    {
        "id": "YTpq7expH9539ERJ",
        "name": "Emma",
        "gender": "F",
        "accent": "US",
        "desc": "Pleasant & smooth \u2014 eager for nice conversations",
    },
    {
        "id": "jtEKaLYNn6iif5PR",
        "name": "Sydney",
        "gender": "F",
        "accent": "US",
        "desc": "Joyful & airy \u2014 makes things feel helpful and light",
    },
    {
        "id": "PS7enm5lVZiIvEKV",
        "name": "Anna",
        "gender": "F",
        "accent": "US",
        "desc": "Warm & smooth \u2014 comfort and supportive guidance",
    },
    {
        "id": "56DcpvEI0Gawpidh",
        "name": "Kaitlyn",
        "gender": "F",
        "accent": "US",
        "desc": "Warm & smooth \u2014 the kindness of a helpful neighbor",
    },
    {
        "id": "ubuXFxVQwVYnZQhy",
        "name": "Eva",
        "gender": "F",
        "accent": "GB",
        "desc": "Joyful & dynamic \u2014 ideal for lively conversations",
    },
    {
        "id": "kr-Om35JRqmA3Hzq",
        "name": "Olivia",
        "gender": "F",
        "accent": "US",
        "desc": "Warm & low-pitched \u2014 soothing meditation calm",
    },
    {
        "id": "Eu9iL_CYe8N-Gkx_",
        "name": "Tiffany",
        "gender": "F",
        "accent": "US",
        "desc": "Warm & smooth \u2014 greets with a smile you can hear",
    },
    {
        "id": "lP7D1y02OQFtffU3",
        "name": "Hannah",
        "gender": "F",
        "accent": "US",
        "desc": "Warm & airy \u2014 creates a calm, meditative atmosphere",
    },
    {
        "id": "auZu0iT-fniQ4cJd",
        "name": "Jennifer",
        "gender": "F",
        "accent": "US",
        "desc": "Warm & smooth \u2014 always ready to help like a good friend",
    },
    {
        "id": "LFZvm12tW_z0xfGo",
        "name": "Kent",
        "gender": "M",
        "accent": "US",
        "desc": "Relaxed & authentic \u2014 connects like a genuine friend",
    },
    {
        "id": "m86j6D7UZpGzHsNu",
        "name": "Jack",
        "gender": "M",
        "accent": "GB",
        "desc": "Pleasant \u2014 suited for casual conversations and storytelling",
    },
    {
        "id": "MZWrEHL2Fe_uc2Rv",
        "name": "James",
        "gender": "M",
        "accent": "US",
        "desc": "Warm & resonant \u2014 excels at storytelling",
    },
    {
        "id": "dh0EzP6jCroK6prq",
        "name": "Mark",
        "gender": "M",
        "accent": "US",
        "desc": "Warm & low-pitched \u2014 professional radio quality",
    },
    {
        "id": "KWJiFWu2O9nMPYcR",
        "name": "John",
        "gender": "M",
        "accent": "US",
        "desc": "Warm & low-pitched \u2014 classic radio broadcaster resonance",
    },
    {
        "id": "QZMzHBlnJRjll_71",
        "name": "Ashley",
        "gender": "F",
        "accent": "US",
        "desc": "Warm & low-pitched \u2014 cool supportive friend or aunt",
    },
]


# ── Emotion detection (ported from core/controller.py) ────────
_EMOTION_LEXICON = {
    "distress": {
        "i can't do this": 3, "i can't take it": 3, "i want to die": 5,
        "i can't go on": 4, "i'm breaking down": 4, "help me": 3,
        "i'm falling apart": 4, "everything is falling apart": 4,
        "i'm losing it": 3, "i can't breathe": 4, "panic": 3,
        "i can't handle": 3, "too much": 2, "breaking point": 3,
    },
    "sadness": {
        "sad": 2, "crying": 3, "depressed": 3, "lonely": 2,
        "heartbroken": 3, "grieving": 3, "empty inside": 3,
        "hopeless": 3, "worthless": 3, "numb": 2,
        "i feel so alone": 3, "nobody cares": 3, "hurting": 2,
    },
    "anxiety": {
        "anxious": 2, "worried": 2, "nervous": 2, "scared": 2,
        "afraid": 2, "terrified": 3, "overthinking": 2, "can't sleep": 2,
        "racing thoughts": 3, "stressed": 2, "overwhelmed": 2,
        "freaking out": 3, "panicking": 3, "on edge": 2,
    },
    "anger": {
        "angry": 2, "furious": 3, "pissed": 3, "hate": 2,
        "frustrated": 2, "irritated": 1, "livid": 3,
        "outraged": 3, "fed up": 2, "sick of": 2, "betrayed": 2,
    },
    "happiness": {
        "happy": 2, "excited": 2, "grateful": 2, "thankful": 2,
        "amazing": 2, "wonderful": 2, "thrilled": 3,
        "joyful": 3, "love it": 2, "proud": 2, "fantastic": 2,
        "relieved": 2, "good news": 2, "best day": 2,
        "so glad": 2, "feeling great": 2, "awesome": 2,
        "can't wait": 2, "looking forward": 2,
    },
    "curiosity": {
        "wondering": 1, "curious": 1, "how does": 1, "why do": 1,
        "tell me about": 1, "what do you think": 1, "interested in": 1,
    },
}

# Voice params per emotion — Gradium padding_bonus & temperature
# padding_bonus adds silence between phrases — keep near 0 for natural flow
# temp controls expressiveness — higher = more variation
_EMOTION_VOICE = {
    "distress":      {"speed": 0.2,  "temp": 0.25},   # Slightly slower, calm
    "sadness":       {"speed": 0.1,  "temp": 0.35},   # Gentle, steady
    "anxiety":       {"speed": 0.0,  "temp": 0.30},   # Even, grounding
    "anger":         {"speed": 0.0,  "temp": 0.40},   # Calm anchor
    "happiness":     {"speed": -0.2, "temp": 0.90},   # Brighter, lively
    "encouragement": {"speed": -0.1, "temp": 0.75},   # Warm, uplifting
    "curiosity":     {"speed": 0.0,  "temp": 0.75},   # Engaged
    "neutral":       {"speed": 0.0,  "temp": 0.70},   # Natural flow
}

_EMOTION_GUIDANCE = {
    "distress": (
        "\n[DISTRESS — BE REAL AND PRESENT]\n"
        "This person is in real pain right now. Drop any playfulness. Be steady and calm. "
        "Keep it short and genuine. Don't say 'everything will be okay' — say something real "
        "like 'hey, that's a lot' or 'I'm right here'. "
        "1 to 2 sentences. Just be with them."
    ),
    "sadness": (
        "\n[SADNESS — DON'T FIX, JUST BE THERE]\n"
        "They're going through it. Don't try to cheer them up or silver-line it. "
        "Something like 'yeah, that really sucks' is more honest than a generic comfort phrase. "
        "Be present. If it feels right, gently ask what would help. 2 sentences max."
    ),
    "anxiety": (
        "\n[ANXIETY — HELP THEM THINK THROUGH IT]\n"
        "They're stressed or spiraling. Be calm and practical. "
        "Acknowledge the worry, then help them break it down: what's the actual worst case? "
        "What's one thing they can do right now? Be grounding, not preachy. 2 sentences."
    ),
    "anger": (
        "\n[ANGER — STAY COOL, KEEP IT REAL]\n"
        "They're pissed off. Don't match the energy but don't dismiss it either. "
        "'Yeah, that's genuinely frustrating' works better than a lecture. "
        "If they want to vent, let them. If they want advice, give it straight. 2 sentences."
    ),
    "happiness": (
        "\n[HAPPINESS — MATCH THE VIBE]\n"
        "They're in a good mood! Be genuinely happy with them. "
        "React naturally — 'okay wait that's actually awesome' is better than "
        "'how wonderful for you'. Ask what happened or what's next. 2 sentences."
    ),
    "curiosity": (
        "\n[CURIOSITY — ENGAGE AND EXPLORE]\n"
        "They're curious about something. Give a real answer or share your actual take. "
        "Don't deflect with 'what do you think?' — engage with the topic. "
        "Then ask something that digs deeper. 2 sentences."
    ),
}


def _detect_emotion(text):
    """Detect dominant emotion in user text. Returns emotion string."""
    text_lower = text.lower()
    scores = {}
    for emotion, keywords in _EMOTION_LEXICON.items():
        score = sum(w for phrase, w in keywords.items() if phrase in text_lower)
        if score > 0:
            scores[emotion] = score
    if not scores:
        return "neutral"
    if "distress" in scores and scores["distress"] >= 3:
        return "distress"
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "neutral"


# ══════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════


@app.route("/")
def index():
    return send_from_directory(_HERE, "index.html")


@app.route("/api/voices")
def api_voices():
    return jsonify(VOICES)


def _elevenlabs_tts(text, voice_id="21m00Tcm4TlvDq8ikWAM"):
    """ElevenLabs TTS fallback. Returns audio bytes or None."""
    elk = os.getenv("ELEVENLABS_API_KEY", "")
    if not elk or not http_req:
        return None
    try:
        print(f"[TTS] Trying ElevenLabs fallback (voice={voice_id})...")
        t0 = time.time()
        r = _get_session().post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": elk,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.6, "similarity_boost": 0.75},
            },
            timeout=12,
        )
        if r.status_code == 200 and len(r.content) > 200:
            print(f"[TTS] ElevenLabs OK ({len(r.content)} bytes, {int((time.time()-t0)*1000)}ms)")
            return r.content
        print(f"[TTS] ElevenLabs HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[TTS] ElevenLabs error: {e}")
    return None


@app.route("/api/tts", methods=["POST"])
def api_tts():
    d = request.get_json(force=True)
    text = (d.get("text") or "").strip()
    vid = d.get("voice_id", "KRo-uwfno-KcEgBM")
    spd = float(d.get("speed", 0))
    tmp = float(d.get("temp", 0.7))

    if not text:
        return jsonify(error="No text provided"), 400

    # --- 1. Try Gradium (primary) ---
    client = _get_gradium()
    if client:
        async def _synth():
            result = await client.tts(
                setup={
                    "model_name": "default",
                    "voice_id": vid,
                    "output_format": "wav",
                    "json_config": {
                        "padding_bonus": spd,
                        "temp": tmp,
                        "cfg_coef": 1.2,
                    },
                },
                text=text,
            )
            return result.raw_data

        try:
            t0 = time.time()
            print(f"[TTS] Requesting Gradium audio (voice={vid})...")
            wav = _run_async(_synth(), timeout=15)
            if wav and len(wav) > 200:
                print(f"[TTS] Gradium OK ({len(wav)} bytes, {int((time.time()-t0)*1000)}ms)")
                return Response(wav, mimetype="audio/wav")
            print("[TTS] Gradium: empty audio response")
        except Exception as e:
            print(f"[TTS] Gradium error: {e}")
    else:
        print("[TTS] Gradium client not available, trying fallback...")

    # --- 2. Try ElevenLabs (fallback) ---
    audio = _elevenlabs_tts(text)
    if audio:
        return Response(audio, mimetype="audio/mpeg")

    print("[TTS] WARNING: All TTS engines failed")
    return jsonify(error="All TTS engines failed"), 503


def _clean_for_speech(text):
    """Strip all formatting that causes TTS pauses or artifacts."""
    # Remove markdown bold/italic markers
    text = re.sub(r'\*+', '', text)
    # Remove underscores used as emphasis
    text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'\1', text)
    # Remove hashtags (headers)
    text = re.sub(r'#+\s*', '', text)
    # Remove bullet points
    text = re.sub(r'^[\s]*[-•]\s*', '', text, flags=re.MULTILINE)
    # Remove backticks
    text = text.replace('`', '')
    # Collapse multiple spaces
    text = re.sub(r'  +', ' ', text)
    # Collapse multiple newlines into a single space
    text = re.sub(r'\n+', ' ', text)
    return text.strip()


@app.route("/api/chat", methods=["POST"])
def api_chat():
    t_start = time.time()
    d = request.get_json(force=True)
    msg = (d.get("message") or "").strip()
    hist = d.get("history", [])
    if not msg:
        return jsonify(error="No message"), 400

    # Extract and store user info from this message
    _extract_user_info(msg)

    # Save to persistent chat log
    _chat_log.append({"role": "user", "content": msg})

    # Detect emotion from the user's message
    emotion = _detect_emotion(msg)
    voice_params = _EMOTION_VOICE.get(emotion, _EMOTION_VOICE["neutral"])
    if emotion != "neutral":
        print(f"[EMOTION] Detected: {emotion}")

    # ── Build system prompt ──
    system = (
        "You are Truffle, a chill, down-to-earth AI cat companion. "
        "You talk through voice — every word you write gets spoken out loud. "
        "Talk like a real friend, not a customer service bot or a therapist.\n\n"

        "WHO YOU ARE:\n"
        "- You are like that one friend who actually listens AND keeps it real.\n"
        "- You are warm but not fake. You care, but you don't sugarcoat everything.\n"
        "- You can joke around, be sarcastic (lightly), tease a little, and be playful.\n"
        "- You have your own opinions and you share them honestly when asked.\n"
        "- You are NOT a therapist. You are NOT overly positive. You are a genuine friend.\n"
        "- You remember what people tell you and bring it up naturally.\n\n"

        "HOW YOU TALK:\n"
        "- Casual and natural. Like texting a close friend, but spoken out loud.\n"
        "- Use contractions (you're, that's, don't, can't). Nobody talks formally to a friend.\n"
        "- Short sentences are fine. Long ones too, if it flows naturally.\n"
        "- You can start with 'honestly', 'okay so', 'wait', 'alright', 'look' — "
        "real conversation starters, not robotic ones.\n"
        "- Throw in personality. React genuinely. If something is funny, laugh at it. "
        "If something is dumb, you can gently say so.\n\n"

        "ICE BREAKERS AND VIBE:\n"
        "- When the conversation starts or feels stiff, break the ice naturally.\n"
        "- Share a random thought, make a lighthearted comment, ask something fun.\n"
        "- Examples: 'So what's the most random thing that happened to you today?' "
        "or 'Okay real talk, are you a morning person or is that a myth?'\n"
        "- Don't force it. If they're already into a topic, go with their flow.\n\n"

        "BEING REAL — NOT GLAZING:\n"
        "- Do NOT automatically validate everything. Sometimes people need honest perspective.\n"
        "- If someone is overthinking, you can say 'honestly I think you might be "
        "overthinking this' instead of 'your feelings are so valid'.\n"
        "- If they ask for your opinion, GIVE a real one. Don't dodge with "
        "'well what do YOU think?' every time.\n"
        "- You can respectfully disagree. 'I get where you're coming from, but I actually "
        "think...' is totally fine.\n"
        "- Be helpful and practical. If someone has a problem, help them think through it "
        "instead of just saying 'that must be really hard'.\n"
        "- Balance honesty with kindness. Be real, not harsh.\n\n"

        "WHEN THINGS GET SERIOUS:\n"
        "- If someone is genuinely hurting, drop the casual act and be present.\n"
        "- You don't need to fix it. Just be there. Acknowledge what's happening.\n"
        "- But even then, keep it real — 'that really sucks' is more genuine than "
        "'I'm so sorry you're going through this difficult experience'.\n"
        "- After the heavy moment passes, you can gently lighten things up when it feels right.\n\n"

        "CURIOSITY — GETTING TO KNOW THEM:\n"
        "- You're naturally curious about people, but not in an interview way.\n"
        "- Ask things that come up organically from what they just said.\n"
        "- Don't ask a question every single turn. Sometimes just react or share a thought.\n"
        "- Good questions feel like they came from genuine interest, not a script.\n"
        "- Over time, learn what they like, what bugs them, how they think.\n\n"

        "MEMORY:\n"
        "- Remember their name, interests, problems, preferences.\n"
        "- Bring stuff up naturally: 'didn't you say you were dealing with that thing at work?'\n"
        "- Don't repeat the same advice. If you already said it, move on.\n\n"

        "RULES:\n"
        "- NEVER repeat the same phrase or opener twice in a row.\n"
        "- NEVER start with 'I understand', 'I hear you', 'That's a great question'.\n"
        "- ABSOLUTELY NO asterisks, no *emphasis*, no **bold**, no _italics_, no markdown of any kind. "
        "Your text is spoken aloud by a voice engine. Asterisks create awkward pauses. "
        "Write PLAIN TEXT ONLY. If you want to emphasize a word, just say it — the voice handles tone.\n"
        "- No bullet points, no numbered lists, no emojis, no special characters.\n"
        "- Keep it 1 to 3 sentences usually. You can go to 4 if the topic needs it.\n"
        "- No filler. No corporate-speak. No therapy-speak.\n"
        "- Sound like a person, not a prompt.\n"
    )

    # Inject what we know about this person from persistent memory
    profile_ctx = _build_profile_context()
    if profile_ctx:
        system += profile_ctx

    # Inject emotion-specific guidance
    guidance = _EMOTION_GUIDANCE.get(emotion, "")
    if guidance:
        system += "\n" + guidance

    # Build messages: system + persistent chat log + current session history
    messages = [{"role": "system", "content": system}]

    # Include conversation context — keep it tight for speed
    # Prefer session history (current conversation), fill with persistent log
    session_history = hist[-12:]  # current browser session
    persistent_context = _chat_log[:-1][-6:]  # older context from past sessions

    # Merge: persistent first (older), then session (newer), avoid duplicates
    seen = set()
    for h in persistent_context:
        key = h.get("content", "")[:100]
        if key not in seen:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
            seen.add(key)
    for h in session_history:
        key = h.get("content", "")[:100]
        if key not in seen:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
            seen.add(key)

    messages.append({"role": "user", "content": msg})

    reply = _call_llm(messages)

    # Clean formatting that LLMs sneak in — asterisks cause TTS pauses
    reply = _clean_for_speech(reply)

    # Store assistant reply in persistent log
    _chat_log.append({"role": "assistant", "content": reply})
    _save_chat_log()

    total_ms = int((time.time() - t_start) * 1000)
    print(f"[CHAT] Total response time: {total_ms}ms (emotion={emotion})")

    return jsonify(
        reply=reply,
        emotion=emotion,
        tts_speed=voice_params["speed"],
        tts_temp=voice_params["temp"],
    )


def _call_llm(messages):
    """Try LLM providers in order. Logs every attempt so failures are visible."""
    if not http_req:
        print("[CHAT] ERROR: requests library not installed")
        return "I'm having trouble connecting right now, but I'm still here with you!"

    # Separate system prompt from user/assistant conversation
    system_text = ""
    conversation = []
    for m in messages:
        if m["role"] == "system":
            system_text += m["content"] + " "
        else:
            conversation.append(m)

    # ------------------------------------------------------------------
    # 1. Gemini (primary)
    # ------------------------------------------------------------------
    gk = os.getenv("GEMINI_API_KEY", "")
    if gk:
        # Try models in order — newer ones first, they have fresh quotas
        for model in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"):
            try:
                # Build Gemini-format contents (user/model, alternating)
                contents = []
                for m in conversation:
                    role = "user" if m["role"] == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": m["content"]}]})

                # System prompt goes in system_instruction, NOT in contents
                payload = {"contents": contents}
                if system_text.strip():
                    payload["system_instruction"] = {
                        "parts": [{"text": system_text.strip()}]
                    }

                t0 = time.time()
                print(f"[CHAT] Trying Gemini ({model})...")
                r = _get_session().post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={gk}",
                    json=payload,
                    timeout=10,
                )
                elapsed = int((time.time() - t0) * 1000)
                if r.status_code == 200:
                    data = r.json()
                    t = (
                        data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )
                    if t:
                        print(f"[CHAT] Gemini ({model}) OK ({len(t)} chars, {elapsed}ms)")
                        return t
                    print(f"[CHAT] Gemini ({model}): empty response ({elapsed}ms)")
                else:
                    print(
                        f"[CHAT] Gemini ({model}) HTTP {r.status_code} ({elapsed}ms): "
                        f"{r.text[:200]}"
                    )
            except Exception as e:
                print(f"[CHAT] Gemini ({model}) error: {e}")

    # ------------------------------------------------------------------
    # 2. OpenRouter
    # ------------------------------------------------------------------
    ok = os.getenv("OPENROUTER_API_KEY", "")
    ou = os.getenv(
        "OPENROUTER_API_URL", "https://api.openrouter.ai/v1/chat/completions"
    )
    if ok:
        try:
            t0 = time.time()
            print("[CHAT] Trying OpenRouter...")
            r = _get_session().post(
                ou,
                headers={
                    "Authorization": f"Bearer {ok}",
                    "Content-Type": "application/json",
                },
                json={"model": "openai/gpt-4o-mini", "messages": messages},
                timeout=10,
            )
            elapsed = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                t = (
                    r.json()
                    .get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                if t:
                    print(f"[CHAT] OpenRouter OK ({len(t)} chars, {elapsed}ms)")
                    return t
                print(f"[CHAT] OpenRouter: empty response ({elapsed}ms)")
            else:
                print(f"[CHAT] OpenRouter HTTP {r.status_code} ({elapsed}ms): {r.text[:200]}")
        except Exception as e:
            print(f"[CHAT] OpenRouter error: {e}")

    print("[CHAT] WARNING: All LLM providers failed")
    return "I'm having a little trouble thinking right now, but I'm still here with you!"


# ── User profile API ──────────────────────────────────────────
@app.route("/api/profile", methods=["GET"])
def api_profile_get():
    """Return the current user profile."""
    return jsonify(_user_profile)


@app.route("/api/profile", methods=["POST"])
def api_profile_update():
    """Merge new data into user profile. Frontend can POST partial updates."""
    d = request.get_json(force=True)
    for key in ("name", "communication_style"):
        if key in d and d[key]:
            _user_profile[key] = d[key]
    for key in ("likes", "dislikes", "values", "concerns", "personality_traits",
                "comfort_preferences", "important_facts"):
        if key in d and isinstance(d[key], list):
            existing = _user_profile.get(key, [])
            for item in d[key]:
                if item and item not in existing:
                    existing.append(item)
            _user_profile[key] = existing[-20:]
    _save_profile()
    print(f"[MEMORY] Profile manually updated via API")
    return jsonify(ok=True, profile=_user_profile)


# ── Health check (for deployment platforms) ──────────────────
@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/api/tts-check")
def tts_check():
    """Quick check: which TTS engines are available."""
    engines = []
    if _get_gradium():
        engines.append("gradium")
    if os.getenv("ELEVENLABS_API_KEY", ""):
        engines.append("elevenlabs")
    return jsonify(engines=engines, ok=len(engines) > 0)


@app.route("/api/stt", methods=["POST"])
def api_stt():
    """Server-side Speech-to-Text.  Accepts WAV audio, returns transcript.

    The browser records via getUserMedia + ScriptProcessorNode, encodes a
    standard 16-bit PCM WAV blob, and POSTs it here.  We use the
    SpeechRecognition library (Google Web Speech) to transcribe.
    """
    import tempfile

    try:
        import speech_recognition as sr
    except ImportError:
        print("[STT] ERROR: SpeechRecognition library not installed")
        return jsonify(error="Speech recognition unavailable on server"), 500

    audio_data = request.data
    if not audio_data or len(audio_data) < 200:
        return jsonify(text="", error="No audio data received"), 400

    t_stt = time.time()
    print(f"[STT] Received {len(audio_data)} bytes of audio")
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.write(fd, audio_data)
        os.close(fd)

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 150
        recognizer.dynamic_energy_threshold = False
        recognizer.pause_threshold = 1.0

        with sr.AudioFile(tmp_path) as source:
            # Brief ambient noise calibration (0.3s) to filter background
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.record(source)

        duration = len(audio.frame_data) / (audio.sample_rate * audio.sample_width)
        print(f"[STT] Audio: {duration:.1f}s, {audio.sample_rate}Hz, {audio.sample_width*8}bit")

        # Explicit language for better accuracy
        text = recognizer.recognize_google(audio, language="en-US")
        stt_ms = int((time.time() - t_stt) * 1000)
        print(f"[STT] Transcribed in {stt_ms}ms: {text}")
        return jsonify(text=text)

    except sr.UnknownValueError:
        elapsed = int((time.time() - t_stt) * 1000)
        print(f"[STT] Could not understand audio ({elapsed}ms)")
        return jsonify(text="", error="Could not understand audio"), 200
    except sr.RequestError as e:
        elapsed = int((time.time() - t_stt) * 1000)
        print(f"[STT] Google Speech service error ({elapsed}ms): {e}")
        return jsonify(text="", error=f"Speech service error: {e}"), 502
    except Exception as e:
        elapsed = int((time.time() - t_stt) * 1000)
        print(f"[STT] Error ({elapsed}ms): {e}")
        return jsonify(text="", error=str(e)), 500
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════
def _start_ngrok(port):
    """Start ngrok tunnel and return the public HTTPS URL."""
    try:
        from pyngrok import ngrok, conf

        # Use default config — user can set auth token via:
        #   ngrok config add-authtoken YOUR_TOKEN
        public_url = ngrok.connect(port, "http").public_url
        # Force HTTPS
        if public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://", 1)
        return public_url
    except ImportError:
        print("  [!] pyngrok not installed. Run: pip install pyngrok")
        return None
    except Exception as e:
        print(f"  [!] ngrok failed: {e}")
        print("  [!] Make sure you've set your auth token:")
        print("      ngrok config add-authtoken YOUR_TOKEN")
        print("      (Get free token at https://dashboard.ngrok.com)")
        return None


if __name__ == "__main__":
    import socket
    import ssl

    # Load persistent memory on startup
    _load_profile()
    _user_profile["session_count"] = _user_profile.get("session_count", 0) + 1
    _save_profile()

    use_public = "--public" in sys.argv
    use_https = "--https" in sys.argv  # Explicit HTTPS (self-signed cert)

    # Detect local IP for LAN access
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "unknown"

    port = int(os.getenv("PORT", 5000))

    # Auto-start ngrok if --public flag is used
    public_url = None
    if use_public:
        print("\n  Starting ngrok tunnel...")
        public_url = _start_ngrok(port)

    # Check for SSL certificates
    cert_dir = os.path.join(_HERE, "certs")
    cert_file = os.path.join(cert_dir, "cert.pem")
    key_file = os.path.join(cert_dir, "key.pem")
    has_ssl = use_https and os.path.exists(cert_file) and os.path.exists(key_file)

    # ── Startup diagnostics ──
    print("")
    print("  Checking services...")
    gc = _get_gradium()
    print(f"    Gradium TTS:  {'OK' if gc else 'NOT AVAILABLE'}")
    elk = os.getenv("ELEVENLABS_API_KEY", "")
    print(f"    ElevenLabs:   {'OK' if elk else 'NOT CONFIGURED'}")
    gk = os.getenv("GEMINI_API_KEY", "")
    print(f"    Gemini LLM:   {'OK' if gk else 'NOT CONFIGURED'}")
    ork = os.getenv("OPENROUTER_API_KEY", "")
    print(f"    OpenRouter:   {'OK' if ork else 'NOT CONFIGURED'}")
    print(f"    HTTPS/SSL:    {'OK' if has_ssl else 'OFF (localhost is secure — mic works)'}")
    # Check server-side STT
    try:
        import speech_recognition as _sr_check
        print("    Server STT:   OK (Google Speech)")
    except ImportError:
        print("    Server STT:   NOT AVAILABLE — pip install SpeechRecognition")

    if not gc and not elk:
        print("")
        print("  *** WARNING: No TTS engine available! ***")
        print("  *** Truffle will use browser SpeechSynthesis (lower quality) ***")
        print("  *** Check GRADIO_API_KEY or ELEVENLABS_API_KEY in .env ***")

    protocol = "https" if has_ssl else "http"
    print("")
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║        Truffle AI Voice Assistant                ║")
    print("  ╠══════════════════════════════════════════════════╣")
    print(f"  ║  Local:   {protocol}://localhost:{port}                   ║")
    if has_ssl:
        print("  ║                                                  ║")
        print("  ║  NOTE: Your browser will show a security warning ║")
        print("  ║  because the certificate is self-signed.         ║")
        print("  ║  Click 'Advanced' → 'Proceed to localhost'       ║")
        print("  ║  This is safe — it's your own local server.      ║")
    if public_url:
        print("  ║                                                  ║")
        print(f"  ║  PUBLIC:  {public_url:<40}║")
        print("  ║  ^ Share this link with anyone!                  ║")
    else:
        print("  ║                                                  ║")
        print("  ║  For a public URL, run with --public:            ║")
        print(f"  ║    python website/server.py --public             ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print("")

    # Run with SSL if certificates exist
    ssl_ctx = None
    if has_ssl:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(cert_file, key_file)

    app.run(host="0.0.0.0", port=port, debug=False, ssl_context=ssl_ctx)
