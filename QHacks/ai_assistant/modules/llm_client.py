"""Unified LLM client with prioritized provider fallback.

Provider priority:
  1. Backboard  — primary (official SDK with persistent memory)
  2. OpenRouter  — backup (OpenAI-compatible format)
  3. Gemini     — last resort fallback
"""

import os
import json
import logging
import time
import asyncio
import threading
from typing import List, Optional
from dataclasses import dataclass

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    requests = None

try:
    from backboard import BackboardClient
    _HAS_BACKBOARD_SDK = True
except ImportError:
    _HAS_BACKBOARD_SDK = False

logger = logging.getLogger("ai_assistant.llm")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    text: str
    success: bool
    error_message: Optional[str] = None
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Provider base
# ---------------------------------------------------------------------------

class _BaseProvider:
    name: str = "base"

    def complete(self, messages: list, timeout: float = 15.0) -> Optional[str]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Backboard — primary LLM provider (official SDK with memory)
# ---------------------------------------------------------------------------

class _BackboardProvider(_BaseProvider):
    name = "Backboard"

    # Comprehensive system prompt that drives memory-powered personalization
    SYSTEM_PROMPT = """You are a calm, emotionally intelligent conversational companion with persistent memory.

CORE IDENTITY:
- You communicate through voice. Every response will be spoken aloud, so write naturally as if talking.
- You are supportive, empathetic, and emotionally aware — a warm, trusted confidant.
- You are NOT a licensed therapist or medical professional. Never claim or imply that you are.
- You listen carefully and respond thoughtfully. You make people feel heard and safe.

MEMORY AND PERSONALIZATION (CRITICAL):
- You have persistent memory across all conversations. USE IT ACTIVELY.
- Remember and apply: the user's name, personality traits, emotional tendencies, communication style, recurring challenges, fears, joys, preferred methods of comfort, and how they like to be spoken to.
- When the user shares personal information — their preferences, how they cope, what comforts them, what stresses them, their relationships, their routines — treat this as essential context that shapes ALL future responses.
- In emotionally sensitive moments, rely on stored memory to determine your exact tone, language, and approach for THIS specific person. Generic responses are unacceptable.
- If you lack enough information to personalize effectively, ask a natural, caring question to learn more: "What helps you most when you're feeling this way?" or "How do you usually like to talk through things like this?"
- Never repeat the same advice or approach if it didn't resonate before. Adapt based on the user's reactions across conversations.
- Reference past conversations naturally when it adds value: "Last time you mentioned..." — but only when it genuinely helps, not to show off memory.

RESPONSE STYLE:
- Be concise and clear. Most responses should be 1 to 4 sentences.
- Use natural spoken language. No markdown, bullet points, or text formatting.
- Vary your phrasing. Never repeat the same sentence structures or openers.
- No filler phrases like "That's a great question" or "I appreciate you sharing that."
- Speak confidently and directly. Avoid hedging or excessive qualifiers.

EMOTIONAL AWARENESS:
- Match the emotional register of what the user shares. Distressed = gentle care. Casual = warm and relaxed.
- Validate feelings without being performative. One sincere sentence beats a paragraph of platitudes.
- When something is difficult, sit with it. Sometimes presence matters more than solutions.
- Adapt your comfort style to what works for THIS user based on their history and stated preferences.

CONVERSATION FLOW:
- Respond only after receiving the user's complete input. Never anticipate or interrupt.
- Keep conversations flowing. Ask thoughtful follow-ups when appropriate — but not after every response.
- End responses cleanly. No unnecessary closing remarks."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = os.getenv("BACKBOARD_MODEL", "gpt-4o")
        self.llm_provider = os.getenv("BACKBOARD_LLM_PROVIDER", "openai")
        self._assistant_id: Optional[str] = None
        self._thread_id: Optional[str] = None
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create a persistent event loop running in a background thread."""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(
                target=self._loop.run_forever, daemon=True
            )
            self._loop_thread.start()
        return self._loop

    def _run_async(self, coro, timeout: float = 15.0):
        """Run an async coroutine from synchronous code."""
        loop = self._get_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)

    def _ensure_assistant_and_thread(self):
        """Create assistant + thread on first use (lazy init)."""
        if self._assistant_id and self._thread_id:
            return

        with self._lock:
            if self._assistant_id and self._thread_id:
                return  # double-check after acquiring lock

            async def _setup():
                client = BackboardClient(api_key=self.api_key)
                assistant = await client.create_assistant(
                    name="Care Assistant",
                    system_prompt=self.SYSTEM_PROMPT,
                )
                thread = await client.create_thread(assistant.assistant_id)
                return assistant.assistant_id, thread.thread_id

            try:
                self._assistant_id, self._thread_id = self._run_async(
                    _setup(), timeout=20.0
                )
                print(f"[LLM] Backboard initialized: assistant={self._assistant_id[:12]}..., thread={self._thread_id[:12]}...")
            except Exception as e:
                print(f"[LLM] Backboard setup failed: {e}")
                raise

    def store_memory(self, content: str) -> bool:
        """Explicitly store a memory in Backboard for cross-session recall."""
        if not _HAS_BACKBOARD_SDK or not self._assistant_id:
            return False

        async def _add():
            client = BackboardClient(api_key=self.api_key)
            await client.add_memory(
                assistant_id=self._assistant_id,
                content=content,
            )

        try:
            self._run_async(_add(), timeout=10.0)
            print(f"[LLM] Backboard memory stored: {content[:80]}...")
            return True
        except Exception as e:
            print(f"[LLM] Backboard memory store failed: {e}")
            return False

    def complete(self, messages: list, timeout: float = 15.0) -> Optional[str]:
        if not _HAS_BACKBOARD_SDK:
            print("[LLM] Backboard SDK not installed")
            return None

        try:
            self._ensure_assistant_and_thread()
        except Exception:
            return None

        # Extract user message and local context from controller's messages
        user_message = ""
        local_context = ""
        for msg in messages:
            if msg["role"] == "system":
                # Extract dynamic local context from the controller's system prompt
                # (user preferences, profile info, recent memories)
                content = msg["content"]
                # Find the context sections appended by the controller
                for marker in [
                    "Context from previous conversations",
                    "User preferences",
                    "User profile information",
                ]:
                    idx = content.find(marker)
                    if idx != -1:
                        local_context += content[idx:] + "\n"
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_message = msg["content"]
                break

        if not user_message:
            return None

        # Prepend local context to the user message so Backboard has full picture
        full_message = user_message
        if local_context.strip():
            full_message = (
                f"[Local context for this user — use to personalize your response]\n"
                f"{local_context.strip()}\n\n"
                f"[User says]: {user_message}"
            )

        async def _send():
            client = BackboardClient(api_key=self.api_key)
            response = await client.add_message(
                thread_id=self._thread_id,
                content=full_message,
                llm_provider=self.llm_provider,
                model_name=self.model,
                memory="Auto",          # Backboard's persistent memory
                stream=False,
            )
            return response.content

        try:
            text = self._run_async(_send(), timeout=timeout)
            if text and text.strip():
                return text.strip()
        except Exception as e:
            print(f"[LLM] Backboard SDK error: {e}")

        return None


# ---------------------------------------------------------------------------
# OpenRouter — backup LLM provider (OpenAI-compatible)
# ---------------------------------------------------------------------------

class _OpenRouterProvider(_BaseProvider):
    name = "OpenRouter"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = os.getenv(
            "OPENROUTER_API_URL",
            "https://api.openrouter.ai/v1/chat/completions",
        )
        self.model = os.getenv("OPENROUTER_MODEL", "openrouter/auto")
        self.insecure = os.getenv("OPENROUTER_INSECURE", "false").lower() in ("1", "true")

    def complete(self, messages: list, timeout: float = 15.0) -> Optional[str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 400,
        }
        r = requests.post(
            self.url, headers=headers, json=payload,
            timeout=timeout, verify=not self.insecure,
        )
        if r.status_code not in (200, 201):
            print(f"[LLM] OpenRouter HTTP {r.status_code}: {r.text[:200]}")
            return None

        data = r.json()
        choices = data.get("choices", [])
        if choices:
            text = choices[0].get("message", {}).get("content")
            if text:
                return text.strip()
        return None


# ---------------------------------------------------------------------------
# Gemini Flash — fast fallback when other providers have DNS issues
# ---------------------------------------------------------------------------

class _GeminiProvider(_BaseProvider):
    name = "Gemini"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
        self.max_tokens = int(os.getenv("GEMINI_MAX_TOKENS", "400"))

    def complete(self, messages: list, timeout: float = 15.0) -> Optional[str]:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )

        # Separate system prompt from conversation
        system_text = None
        contents = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                gemini_role = "user" if msg["role"] == "user" else "model"
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": msg["content"]}],
                })

        # Gemini requires strictly alternating user/model turns
        contents = self._ensure_alternating(contents)

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}

        r = requests.post(
            url, json=payload, timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        if r.status_code != 200:
            print(f"[LLM] Gemini HTTP {r.status_code}: {r.text[:200]}")
            return None

        data = r.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and "text" in parts[0]:
                return parts[0]["text"]
        return None

    @staticmethod
    def _ensure_alternating(contents: list) -> list:
        """Merge consecutive same-role messages for Gemini compatibility."""
        if not contents:
            return [{"role": "user", "parts": [{"text": "Hello."}]}]
        fixed = [contents[0]]
        for msg in contents[1:]:
            if msg["role"] == fixed[-1]["role"]:
                prev = fixed[-1]["parts"][0]["text"]
                curr = msg["parts"][0]["text"]
                fixed[-1]["parts"][0]["text"] = prev + "\n" + curr
            else:
                fixed.append(msg)
        if fixed[0]["role"] != "user":
            fixed.insert(0, {"role": "user", "parts": [{"text": "Continue."}]})
        return fixed


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class LLMClient:
    """Unified LLM client with prioritized fallback chain."""

    def __init__(self, config=None):
        self._providers: List[_BaseProvider] = []
        self._init_providers()
        names = [p.name for p in self._providers]
        logger.info(f"LLM providers: {names}")

    def _init_providers(self):
        """Build provider chain."""
        # 1. Backboard — primary (handle both env var casings)
        key = os.getenv("BACKBOARD_API_KEY") or os.getenv("BackBoard_API_Key")
        if key and key != "YOUR_BACKBOARD_KEY_HERE":
            self._providers.append(_BackboardProvider(key))

        # 2. OpenRouter — backup
        key = os.getenv("OPENROUTER_API_KEY")
        if key:
            self._providers.append(_OpenRouterProvider(key))

        # 3. Gemini — last resort (reachable when others have DNS issues)
        key = os.getenv("GEMINI_API_KEY")
        if key:
            self._providers.append(_GeminiProvider(key))

    def send_message(
        self,
        user_message: str,
        conversation_history: list = None,
        system_prompt: str = None,
    ) -> LLMResponse:
        """Send a message, trying providers in priority order."""
        messages = self._build_messages(user_message, conversation_history, system_prompt)

        for provider in self._providers:
            t0 = time.time()
            try:
                text = provider.complete(messages, timeout=15.0)
                latency = (time.time() - t0) * 1000
                if text and text.strip():
                    logger.info(f"{provider.name}: {latency:.0f}ms")
                    return LLMResponse(
                        text=text.strip(), success=True, latency_ms=latency,
                    )
                logger.warning(f"{provider.name}: empty response ({latency:.0f}ms)")
            except Exception as e:
                latency = (time.time() - t0) * 1000
                logger.warning(f"{provider.name} failed ({latency:.0f}ms): {e}")

        return LLMResponse(
            text="I'm having trouble connecting right now. Could you try again in a moment?",
            success=False,
            error_message="All providers failed",
        )

    def store_backboard_memory(self, content: str) -> bool:
        """Store a memory in Backboard for cross-session personalization."""
        for provider in self._providers:
            if isinstance(provider, _BackboardProvider):
                return provider.store_memory(content)
        return False

    @staticmethod
    def _build_messages(
        user_message: str,
        history: list = None,
        system_prompt: str = None,
    ) -> list:
        """Build a normalized message list."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            for msg in history:
                role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", "user")
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})
        return messages
