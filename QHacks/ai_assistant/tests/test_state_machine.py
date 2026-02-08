import unittest
import time
import sys
import os
# make project modules importable when tests are run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.state_machine import StateMachine, AssistantState


class TestStateMachine(unittest.TestCase):
    def setUp(self):
        self.sm = StateMachine(initial_state=AssistantState.IDLE)
        # register simple transitions used in tests
        self.sm.register_transition(AssistantState.IDLE, AssistantState.GREETING, "person_detected")
        self.sm.register_transition(AssistantState.GREETING, AssistantState.ACTIVE_CONVERSATION, "user_responded")
        self.sm.register_transition(AssistantState.ACTIVE_CONVERSATION, AssistantState.GOODBYE, "termination_phrase")
        self.sm.register_transition(AssistantState.GREETING, AssistantState.PASSIVE_LISTENING, "greeting_timeout")
        self.sm.register_transition(AssistantState.PASSIVE_LISTENING, AssistantState.OFFER_HELP, "question_detected")

    def test_initial_state(self):
        self.assertEqual(self.sm.current_state, AssistantState.IDLE)

    def test_idle_to_greeting(self):
        res = self.sm.trigger("person_detected")
        self.assertTrue(res)
        self.assertEqual(self.sm.current_state, AssistantState.GREETING)

    def test_invalid_transition(self):
        res = self.sm.trigger("termination_phrase")
        self.assertFalse(res)
        self.assertEqual(self.sm.current_state, AssistantState.IDLE)

    def test_full_flow(self):
        self.sm.trigger("person_detected")
        self.assertEqual(self.sm.current_state, AssistantState.GREETING)
        self.sm.trigger("user_responded")
        self.assertEqual(self.sm.current_state, AssistantState.ACTIVE_CONVERSATION)
        self.sm.trigger("termination_phrase")
        self.assertEqual(self.sm.current_state, AssistantState.GOODBYE)

    def test_time_in_state(self):
        start = self.sm.get_time_in_state()
        time.sleep(0.05)
        self.assertGreater(self.sm.get_time_in_state(), start)


if __name__ == '__main__':
    unittest.main()
