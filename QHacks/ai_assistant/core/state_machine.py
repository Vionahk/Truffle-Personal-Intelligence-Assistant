from enum import Enum
from typing import Callable, Dict, Optional
from dataclasses import dataclass
import time


class AssistantState(Enum):
    IDLE = "idle"
    GREETING = "greeting"
    ACTIVE_CONVERSATION = "active_conversation"
    PASSIVE_LISTENING = "passive_listening"
    OFFER_HELP = "offer_help"
    GOODBYE = "goodbye"
    MEDICATION_REMINDER = "medication_reminder"


@dataclass
class StateTransition:
    from_state: AssistantState
    to_state: AssistantState
    condition: str
    action: Optional[Callable] = None


class StateMachine:
    def __init__(self, initial_state: AssistantState):
        self._state = initial_state
        self._transitions = []
        self._state_enter_time = time.time()

    @property
    def current_state(self) -> AssistantState:
        return self._state

    def register_transition(self, from_state: AssistantState, to_state: AssistantState, condition: str, action: Callable = None) -> None:
        self._transitions.append(StateTransition(from_state, to_state, condition, action))

    def trigger(self, condition: str) -> bool:
        for t in self._transitions:
            if t.from_state == self._state and t.condition == condition:
                self._state = t.to_state
                self._state_enter_time = time.time()
                if t.action:
                    try:
                        t.action()
                    except Exception:
                        pass
                return True
        return False

    def get_time_in_state(self) -> float:
        return time.time() - self._state_enter_time
