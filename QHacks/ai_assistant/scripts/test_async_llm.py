import sys, time
sys.path.insert(0, '.')
from core.controller import AssistantController
from types import SimpleNamespace

c = AssistantController()
# Patch LLM to return quickly
c.llm.send_message = lambda user_message, conversation_history=None, system_prompt=None: SimpleNamespace(success=True, text=f"Reply to: {user_message}")
print('Calling _process_user_input...')
c._process_user_input('How are you?')
print('Called; main thread sleeping 1.5s to allow background work...')
time.sleep(1.5)
print('Processing flag:', c._processing)
print('Assistant messages count:', c._assistant_message_count)
print('Recent conversation:', c.conversation.get_history())
