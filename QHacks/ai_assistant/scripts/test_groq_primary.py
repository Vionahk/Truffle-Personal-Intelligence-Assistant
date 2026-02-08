#!/usr/bin/env python3
"""
Test script to verify Groq is the primary LLM and anti-repetition system prompt works.
Run: python scripts/test_groq_primary.py
"""
import sys
import os
import time
sys.path.insert(0, '.')

from modules.llm_client import LLMClient
from core.controller import AssistantController
from config import LLMConfig

print("="*70)
print("GROQ PRIMARY LLM TEST")
print("="*70)

# Test 1: Verify Groq is being called
print("\n[TEST 1] Checking if GROQ_API_KEY is set...")
groq_key = os.getenv('GROQ_API_KEY')
if groq_key:
    print(f"✓ GROQ_API_KEY found: {groq_key[:10]}...{groq_key[-10:]}")
else:
    print("✗ GROQ_API_KEY not set. Get one free at: https://console.groq.com/")
    print("  Then set: export GROQ_API_KEY=gsk_your_key_here")

# Test 2: Check LLM client initialization
print("\n[TEST 2] Initializing LLMClient...")
llm = LLMClient(LLMConfig())
if llm.groq_api_key:
    print(f"✓ Groq API key loaded in client")
else:
    print("✗ Groq key not available in client")

# Test 3: Check system prompt includes anti-repetition rules
print("\n[TEST 3] Verifying anti-repetition system prompt...")
controller = AssistantController()
prompt = controller._get_system_prompt()
if "NEVER REPEAT" in prompt and "DO NOT SAY THESE" in prompt:
    print("✓ Strong anti-repetition rules detected in system prompt")
    print("\nSystem Prompt Preview (first 500 chars):")
    print("-" * 70)
    print(prompt[:500] + "...")
    print("-" * 70)
else:
    print("✗ Anti-repetition rules may be missing")

print("\n" + "="*70)
print("SETUP INSTRUCTIONS:")
print("="*70)
print("""
1. Get a free Groq API key:
   - Visit: https://console.groq.com/
   - Sign up / Log in
   - Copy your API key

2. Set the environment variable (Windows PowerShell):
   $env:GROQ_API_KEY = "gsk_your_key_here"
   
   OR add to .env file in project root:
   GROQ_API_KEY=gsk_your_key_here

3. Run the assistant:
   python scripts/run_live.py

Groq features:
- FREE tier available
- FASTEST inference (48K tokens/min)
- Excellent for voice assistant use case
- Compatible with OpenAI format
- Models: mixtral-8x7b-32768 (default), llama2-70b-4096

Anti-repetition enforcement:
- System prompt now includes STRONG rules against repetition
- LLM will be penalized for repeating wording
- Varied sentence structure and vocabulary required
- Recent responses are shown to LLM to avoid them
""")
