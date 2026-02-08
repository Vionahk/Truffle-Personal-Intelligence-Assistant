# modules/__init__.py
from .microphone import MicrophoneModule, TranscriptionResult
from .speaker import SpeakerModule
from .llm_client import LLMClient
from .question_detector import QuestionDetector, ResponseType
from .memory_manager import MemoryManager
from .therapeutic_questions import TherapeuticQuestionGenerator, QuestionContext
from .emotional_awareness import EnhancedEmotionalAwareness, EmotionalCues
