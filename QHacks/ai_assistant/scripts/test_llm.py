"""Lightweight LLM connectivity test.

This script loads config and attempts a small request via modules.llm_client.LLMClient.
It prints only pass/fail and a short message (no secrets).
"""
import sys
import os
# ensure project root is importable
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import LLMConfig
from modules.llm_client import LLMClient

def main():
    cfg = LLMConfig()
    client = LLMClient(cfg)
    ok = False
    try:
        ok = client.test_connection()
    except Exception as e:
        print("LLM connection test raised an exception:", str(e))
        return

    if ok:
        print("LLM connection: OK (Gradio client reachable)")
        # try a lightweight send_message if possible
        try:
            resp = client.send_message("Hello", conversation_history=[], system_prompt="You are a test assistant.")
            if resp.success:
                print("LLM ping response received (length):", len(resp.text))
            else:
                print("LLM ping call failed:", resp.error_message)
        except Exception as e:
            print("LLM ping raised:", str(e))
    else:
        # attempt HF inference fallback
        resp = client.send_message("Hello", conversation_history=[], system_prompt="You are a test assistant.")
        if resp.success:
            print("LLM via HF or fallback: OK (response length):", len(resp.text))
        else:
            print("LLM connection failed:", resp.error_message)

if __name__ == '__main__':
    main()
