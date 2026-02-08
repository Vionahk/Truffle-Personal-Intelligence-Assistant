#!/usr/bin/env python3
"""
Quick Groq setup verification with sample prompt
"""
import sys
import os
sys.path.insert(0, '.')

print("\n" + "="*70)
print("GROQ PRIMARY LLM - QUICK SETUP")
print("="*70 + "\n")

# Check Groq key
groq_key = os.getenv('GROQ_API_KEY', '').strip()
if groq_key and groq_key.startswith('gsk_'):
    print(f"✓ GROQ_API_KEY is set: {groq_key[:15]}...{groq_key[-5:]}")
else:
    print("✗ GROQ_API_KEY not set or invalid (must start with 'gsk_')")
    print("\n  SETUP STEPS:")
    print("  1. Visit https://console.groq.com/ (free tier)")
    print("  2. Create account and copy your API key")
    print("  3. In PowerShell, run:")
    print("     $env:GROQ_API_KEY = 'gsk_your_key_here'")
    print("  4. Then start the assistant:")
    print("     python scripts/run_live.py\n")

# Show API priority
print("\nAPI PRIORITY ORDER:")
print("  1. ✨ Groq (PRIMARY - fastest, free)")
print("  2.    Gemini (fallback)")
print("  3.    OpenRouter (fallback)")
print("  4.    OpenAI (fallback)")
print("  5.    Local fallback (last resort)\n")

# Show anti-repetition system prompt
print("ANTI-REPETITION SYSTEM PROMPT:")
print("-" * 70)
print("""CRITICAL RULE - NEVER REPEAT:
- Do NOT use the same words, phrases, or sentence structures in consecutive responses
- Vary HOW you respond, not just WHAT you say
- If you've said something before, say it a completely different way
- Change sentence structure, vocabulary, and tone across messages

Recent responses are included in system prompt, with explicit:
❌ DO NOT SAY THESE (from previous responses)
✓ INSTEAD: Use completely different phrasing
""")
print("-" * 70)

print("\n✓ Implementation complete!")
print("\nNEXT STEPS:")
print("  1. Set GROQ_API_KEY environment variable (see above)")
print("  2. Start the assistant: python scripts/run_live.py")
print("  3. Test: Ask repeated questions to verify varied responses\n")
