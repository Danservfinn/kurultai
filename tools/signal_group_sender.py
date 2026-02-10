#!/usr/bin/env python3
"""
Signal Group Message Wrapper
Bypasses OpenClaw's broken group ID handling by using signal-cli directly.
"""

import os
import json
import urllib.request
from typing import Optional

class SignalGroupSender:
    """Sends messages to Signal groups bypassing OpenClaw's lowercasing bug."""
    
    def __init__(self, account: str = "+15165643945", daemon_url: str = "http://127.0.0.1:8080"):
        self.account = account
        self.daemon_url = daemon_url
        
    def send_to_group(self, group_id: str, message: str) -> dict:
        """Send message to Signal group using raw signal-cli API."""
        # Note: group_id should be the raw base64 ID, NOT lowercased
        
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "send",
            "params": {
                "account": self.account,
                "groupId": group_id,  # Preserve case!
                "message": message
            }
        }
        
        req = urllib.request.Request(
            f"{self.daemon_url}/api/v1/rpc",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read())
                return {
                    "success": True,
                    "result": result,
                    "group_id": group_id,
                    "message": message
                }
        except urllib.error.HTTPError as e:
            return {
                "success": False,
                "error": str(e),
                "response": e.read().decode() if e.fp else None
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def list_groups(self) -> list:
        """List available Signal groups."""
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "listGroups",
            "params": {}
        }
        
        req = urllib.request.Request(
            f"{self.daemon_url}/api/v1/rpc",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read())
                return result.get("result", [])
        except Exception as e:
            print(f"Error listing groups: {e}")
            return []


# Convenience function for quick group sends
def send_group_message(group_id: str, message: str, account: str = "+15165643945") -> dict:
    """Send message to Signal group (bypasses OpenClaw bug)."""
    sender = SignalGroupSender(account=account)
    return sender.send_to_group(group_id, message)


if __name__ == "__main__":
    # Test with Kublai Klub
    GROUP_ID = "BROemHVncLgSz8tReUKBz6V3BeDhDB0EXaJd+sRp6oA="
    
    print("Testing Signal Group Sender...")
    print(f"Group ID: {GROUP_ID}")
    print()
    
    sender = SignalGroupSender()
    
    # List groups first
    print("Available groups:")
    groups = sender.list_groups()
    for group in groups:
        print(f"  - {group.get('name', 'Unknown')}: {group.get('id', 'N/A')}")
    print()
    
    # Send test message
    print("Sending test message...")
    result = sender.send_to_group(GROUP_ID, "Test from SignalGroupSender wrapper!")
    
    if result["success"]:
        print("✅ Message sent successfully!")
        print(f"Result: {result['result']}")
    else:
        print(f"❌ Failed: {result.get('error')}")
        if 'response' in result:
            print(f"Response: {result['response']}")
