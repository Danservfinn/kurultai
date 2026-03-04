#!/usr/bin/env python3
"""
Chat Message Executor

Called when user sends a chat message.
Classifies and executes immediately without queue wait.

Usage:
    python3 chat-execute.py "Build a login feature"
"""

import sys
import os
from datetime import datetime

SCRIPTS_DIR = "/Users/kublai/.openclaw/agents/main/scripts"
sys.path.insert(0, SCRIPTS_DIR)

from direct_execute import execute_task

def handle_chat_message(message):
    """Handle incoming chat message - classify and execute immediately"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Chat message received: {message[:50]}...")
    
    # Classify and execute immediately (no queue wait)
    result = execute_task(message)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Execution complete")
    
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 chat-execute.py <message>")
        sys.exit(1)
    
    message = " ".join(sys.argv[1:])
    handle_chat_message(message)
