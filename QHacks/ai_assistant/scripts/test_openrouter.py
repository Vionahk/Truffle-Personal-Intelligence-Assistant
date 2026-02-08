#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from modules.llm_client import LLMClient
from config import LLMConfig

load_dotenv()

print("Testing OpenRouter connection...")
print(f"OPENROUTER_API_KEY present: {bool(os.getenv('OPENROUTER_API_KEY'))}")

config = LLMConfig()
llm = LLMClient(config)

print(f"LLM OpenRouter key: {bool(llm.openrouter_api_key)}")

# Test message
response = llm.send_message(
    "Hello, can you tell me who you are?",
    conversation_history=[],
    system_prompt="You are a helpful AI assistant."
)

print(f"\nResponse success: {response.success}")
print(f"Response text: {response.text}")
if response.error_message:
    print(f"Error: {response.error_message}")
