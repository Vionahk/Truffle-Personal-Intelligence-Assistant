"""Conversation history with automatic trimming.

Maintains a sliding window of messages so the LLM always receives
a focused, relevant context without unbounded growth.
"""

from typing import List, Dict
import time


class ConversationHistory:
    def __init__(self, max_messages: int = 40):
        self._messages: List[Dict] = []
        self._max = max_messages

    def add_user_message(self, text: str) -> None:
        self._messages.append({
            "role": "user",
            "content": text,
            "timestamp": time.time(),
        })
        self._trim()

    def add_assistant_message(self, text: str) -> None:
        self._messages.append({
            "role": "assistant",
            "content": text,
            "timestamp": time.time(),
        })
        self._trim()

    def get_history(self) -> List[Dict]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def message_count(self) -> int:
        return len(self._messages)

    def _trim(self) -> None:
        """Keep only the most recent messages."""
        if len(self._messages) > self._max:
            self._messages = self._messages[-self._max:]
