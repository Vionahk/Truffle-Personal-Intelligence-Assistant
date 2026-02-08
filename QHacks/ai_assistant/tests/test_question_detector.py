import unittest
import sys
import os
# make project modules importable when tests are run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.question_detector import QuestionDetector, ResponseType
from config import TERMINATION_PHRASES, AFFIRMATIVE_RESPONSES, NEGATIVE_RESPONSES


class TestQuestionDetector(unittest.TestCase):
    def setUp(self):
        self.detector = QuestionDetector(TERMINATION_PHRASES, AFFIRMATIVE_RESPONSES, NEGATIVE_RESPONSES)

    def test_question_mark(self):
        self.assertEqual(self.detector.analyze("What's up?"), ResponseType.QUESTION)

    def test_starter_word(self):
        self.assertEqual(self.detector.analyze("How are you doing"), ResponseType.QUESTION)

    def test_termination(self):
        self.assertEqual(self.detector.analyze("I'm done talking"), ResponseType.TERMINATION)

    def test_affirmative(self):
        self.assertEqual(self.detector.analyze("Yes please"), ResponseType.AFFIRMATIVE)

    def test_negative(self):
        self.assertEqual(self.detector.analyze("No thanks"), ResponseType.NEGATIVE)


if __name__ == '__main__':
    unittest.main()
