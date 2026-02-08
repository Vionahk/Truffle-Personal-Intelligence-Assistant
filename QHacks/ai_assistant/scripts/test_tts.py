#!/usr/bin/env python3
"""Test TTS (Text-to-Speech) integration with Gemini LLM."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.speaker import SpeakerModule
from modules.llm_client import LLMClient
from config import TTSConfig, LLMConfig

print("[TEST] Starting TTS + Gemini LLM Integration Test\n")

# Initialize speaker
print("[INIT] Initializing speaker...")
tts_config = TTSConfig()
speaker = SpeakerModule(tts_config)
speaker.start()
print(f"[INIT] Speaker started. Audio available: {speaker.is_output_available()}\n")

# Initialize LLM client
print("[INIT] Initializing LLM client...")
llm_config = LLMConfig()
llm = LLMClient(llm_config)

# Test 1: Direct TTS
print("[TEST 1] Testing direct TTS...")
speaker.speak("Hello! I am the AI assistant. This is a text to speech test.")
speaker.wait_until_done()
print("[TEST 1] ✓ Direct TTS test complete\n")

# Test 2: LLM + TTS Integration
print("[TEST 2] Testing Gemini + TTS Integration...")
test_messages = [
    "What is 2 plus 2?",
    "Tell me a short joke",
    "How are you today?"
]

for user_input in test_messages:
    print(f"\n[INPUT] User: {user_input}")
    
    # Get response from Gemini
    response = llm.send_message(user_input)
    
    if response and response.success:
        text = response.text
        print(f"[GEMINI] {text[:100]}...")
        
        # Speak the response
        print("[TTS] Speaking Gemini response...")
        speaker.speak(text)
        speaker.wait_until_done()
        print("[TTS] ✓ Speech complete\n")
    else:
        print("[ERROR] LLM failed to respond\n")

# Cleanup
speaker.stop()
print("\n[DONE] Test complete!")
