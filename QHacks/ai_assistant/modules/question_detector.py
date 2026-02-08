from typing import List
from enum import Enum


class ResponseType(Enum):
    QUESTION = "question"
    AFFIRMATIVE = "affirmative"
    NEGATIVE = "negative"
    TERMINATION = "termination"
    STATEMENT = "statement"


class QuestionDetector:
    def __init__(
        self,
        termination_phrases: List[str],
        affirmative_phrases: List[str],
        negative_phrases: List[str],
    ):
        self.termination = [p.lower() for p in termination_phrases]
        self.affirmative = [p.lower() for p in affirmative_phrases]
        self.negative = [p.lower() for p in negative_phrases]

    def analyze(self, text: str) -> ResponseType:
        if not text:
            return ResponseType.STATEMENT

        txt = text.lower().strip()

        if self.is_termination(txt):
            return ResponseType.TERMINATION

        if self.is_affirmative(txt):
            return ResponseType.AFFIRMATIVE

        if self.is_negative(txt):
            return ResponseType.NEGATIVE

        if self.is_question(txt):
            return ResponseType.QUESTION

        return ResponseType.STATEMENT

    def is_question(self, text: str) -> bool:
        if not text:
            return False

        text_lower = text.strip().lower()
        if text_lower.endswith("?"):
            return True

        question_starters = [
            "what",
            "why",
            "how",
            "when",
            "where",
            "who",
            "which",
            "is",
            "are",
            "am",
            "was",
            "were",
            "can",
            "could",
            "would",
            "should",
            "will",
            "do",
            "does",
            "did",
            "have",
            "has",
            "had",
        ]

        parts = text_lower.split()
        first = parts[0] if parts else ""
        if first in question_starters:
            return True

        wondering_phrases = ["i wonder", "i don't know", "i'm not sure", "what if"]
        for p in wondering_phrases:
            if p in text_lower:
                return True

        return False

    def is_termination(self, text: str) -> bool:
        txt = text.lower()
        return any(p in txt for p in self.termination)

    def is_affirmative(self, text: str) -> bool:
        txt = text.lower()
        return any(txt == p or txt.startswith(p + " ") for p in self.affirmative)

    def is_negative(self, text: str) -> bool:
        txt = text.lower()
        return any(txt == p or txt.startswith(p + " ") for p in self.negative)
