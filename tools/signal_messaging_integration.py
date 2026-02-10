#!/usr/bin/env python3
"""
Signal Messaging Integration
Automatically routes group messages through the working wrapper.
"""

import os
import sys
import json
import urllib.request

# Import the wrapper
sys.path.insert(0, os.path.dirname(__file__))
from signal_group_sender import SignalGroupSender, send_group_message

class SignalMessagingIntegration:
    """Integrates signal_group_sender with the main system."""
    
    def __init__(self):
        self.sender = SignalGroupSender()
        
    def is_group_target(self, target: str) -> bool:
        """Check if target is a Signal group."""
        return target.startswith("group:")
    
    def extract_group_id(self, target: str) -> str:
        """Extract clean group ID from target string."""
        # Handle formats like:
        # group:BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=
        # signal:group:BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=
        
        if target.startswith("signal:group:"):
            return target.replace("signal:group:", "")
        elif target.startswith("group:"):
            return target.replace("group:", "")
        return target
    
    def send_message(self, target: str, message: str, **kwargs) -> dict:
        """
        Send message via Signal.
        
        Automatically detects groups and uses the appropriate method.
        """
        if self.is_group_target(target):
            # Use our wrapper for groups (preserves case)
            group_id = self.extract_group_id(target)
            return self.sender.send_to_group(group_id, message)
        else:
            # Use standard OpenClaw for direct messages
            # (phone numbers SHOULD be lowercased)
            return self._send_via_openclaw(target, message, **kwargs)
    
    def _send_via_openclaw(self, target: str, message: str, **kwargs) -> dict:
        """Send via OpenClaw gateway (for direct messages)."""
        # This would call OpenClaw's normal message sending
        # For now, we use signal-cli directly
        
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "send",
            "params": {
                "recipient": target,
                "message": message
            }
        }
        
        req = urllib.request.Request(
            "http://127.0.0.1:8080/api/v1/rpc",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read())
                return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Global instance for easy access
_signal_integration = None

def get_signal_integration() -> SignalMessagingIntegration:
    """Get or create the global signal integration instance."""
    global _signal_integration
    if _signal_integration is None:
        _signal_integration = SignalMessagingIntegration()
    return _signal_integration


def send_signal_message(target: str, message: str, **kwargs) -> dict:
    """
    Send Signal message (works for both groups and direct messages).
    
    Usage:
        # Group message (bypasses OpenClaw bug)
        send_signal_message("group:BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=", "Hello group!")
        
        # Direct message (uses OpenClaw)
        send_signal_message("+19194133445", "Hello Danny!")
    """
    integration = get_signal_integration()
    return integration.send_message(target, message, **kwargs)


if __name__ == "__main__":
    # Test both group and direct message
    print("Testing Signal Messaging Integration")
    print("=" * 50)
    
    integration = SignalMessagingIntegration()
    
    # Test group detection
    test_targets = [
        "group:BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=",
        "signal:group:BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=",
        "+19194133445",
        "uuid:some-uuid-here"
    ]
    
    print("\nTarget detection test:")
    for target in test_targets:
        is_group = integration.is_group_target(target)
        print(f"  {target[:40]}... -> {'GROUP' if is_group else 'DIRECT'}")
    
    # Test group message
    print("\nSending test group message...")
    result = send_signal_message(
        "group:BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA=",
        "Integration test - this works! 🎉"
    )
    
    if result.get("success"):
        print("✅ Group message sent successfully!")
    else:
        print(f"❌ Failed: {result.get('error')}")
