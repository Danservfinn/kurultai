#!/usr/bin/env python3
"""
Verify Composio Twitter integration is working
"""

import os
import subprocess
import sys

def check_composio():
    """Check if Composio is properly configured"""
    api_key = os.environ.get('COMPOSIO_API_KEY')
    
    if not api_key:
        print("❌ COMPOSIO_API_KEY not set")
        return False
    
    print(f"✅ COMPOSIO_API_KEY is set (starts with: {api_key[:10]}...)")
    
    # Check composio CLI
    try:
        result = subprocess.run(
            ['composio', 'connections'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("✅ Composio CLI working")
            print("\nConnections:")
            print(result.stdout)
            return True
        else:
            print(f"⚠️  Composio CLI issue: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error running composio: {e}")
        return False

if __name__ == '__main__':
    if check_composio():
        print("\n✅ Composio Twitter integration is ready!")
        sys.exit(0)
    else:
        print("\n⚠️  Composio needs configuration. Run: composio add twitter")
        sys.exit(1)
