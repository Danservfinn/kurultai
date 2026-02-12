#!/usr/bin/env python3
"""
Verify Composio X/Twitter connection
"""

import os
import subprocess
import sys

def verify_connection():
    """Verify Composio Twitter connection"""
    
    # Check environment variables
    api_key = os.environ.get('COMPOSIO_API_KEY')
    user_id = os.environ.get('COMPOSIO_USER_ID')
    
    print("=== COMPOSIO X/TWITTER VERIFICATION ===")
    print()
    
    if not api_key:
        print("❌ COMPOSIO_API_KEY not set")
        return False
    
    if not user_id:
        print("❌ COMPOSIO_USER_ID not set")
        return False
    
    print(f"✅ COMPOSIO_API_KEY: {api_key[:15]}...")
    print(f"✅ COMPOSIO_USER_ID: {user_id}")
    print()
    
    # Try to list connections
    print("Checking Composio connections...")
    try:
        result = subprocess.run(
            ['composio', 'connections'],
            capture_output=True, text=True, timeout=10,
            env={**os.environ, 'COMPOSIO_API_KEY': api_key}
        )
        
        if 'twitter' in result.stdout.lower() or 'x' in result.stdout.lower():
            print("✅ Twitter/X connection found!")
            print()
            print("Connection output:")
            print(result.stdout)
            return True
        else:
            print("⚠️  No Twitter/X connection found in list")
            print("Output:", result.stdout[:200])
            return False
            
    except Exception as e:
        print(f"❌ Error checking connections: {e}")
        return False

if __name__ == '__main__':
    if verify_connection():
        print("\n✅ Composio X/Twitter is ready to use!")
        sys.exit(0)
    else:
        print("\n⚠️  Connection needs verification")
        sys.exit(1)
