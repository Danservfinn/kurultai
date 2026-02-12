#!/usr/bin/env python3
"""
Composio Twitter Integration Setup

This script sets up the Composio integration for Twitter/X access.
It installs required packages and provides instructions for authentication.

Usage:
    python3 setup_composio_twitter.py

Prerequisites:
    - Composio account (sign up at https://platform.composio.dev)
    - Composio API key
    - Twitter/X account
"""

import os
import sys
import subprocess
import json

def install_composio():
    """Install Composio core package."""
    print("📦 Installing Composio packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "composio-core"])
        print("   ✅ composio-core installed")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Failed to install composio-core: {e}")
        return False
    return True

def check_api_key():
    """Check if COMPOSIO_API_KEY is set."""
    api_key = os.environ.get('COMPOSIO_API_KEY')
    if api_key:
        print("   ✅ COMPOSIO_API_KEY is set")
        return True
    else:
        print("   ⚠️  COMPOSIO_API_KEY not set")
        return False

def create_env_template():
    """Create a template for .env file."""
    env_path = "/data/workspace/souls/main/.env.composio"
    if os.path.exists(env_path):
        print(f"   ℹ️  {env_path} already exists")
        return
    
    content = """# Composio Configuration
# Get your API key from: https://platform.composio.dev
COMPOSIO_API_KEY=your_composio_api_key_here

# Twitter/X Integration
# After setting up, connect with: composio add twitter
"""
    with open(env_path, 'w') as f:
        f.write(content)
    print(f"   ✅ Created {env_path} template")

def print_setup_instructions():
    """Print instructions for completing setup."""
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    COMPOSIO TWITTER SETUP INSTRUCTIONS                       ║
╠══════════════════════════════════════════════════════════════════════════════╣

1. GET YOUR API KEY
   ─────────────────
   • Visit: https://platform.composio.dev
   • Sign up or log in to your account
   • Go to Settings → API Keys
   • Copy your API key

2. CONFIGURE ENVIRONMENT
   ──────────────────────
   Option A - Add to .env file:
   echo "COMPOSIO_API_KEY=your_key_here" >> /data/workspace/souls/main/.env
   
   Option B - Export in shell:
   export COMPOSIO_API_KEY=your_key_here

3. CONNECT TWITTER ACCOUNT
   ────────────────────────
   Run the following command to authenticate:
   
   composio add twitter
   
   This will open a browser window for OAuth authentication.

4. VERIFY CONNECTION
   ──────────────────
   Run the verification script:
   
   python3 verify_composio_twitter.py

═══════════════════════════════════════════════════════════════════════════════

📚 RESOURCES:
   • Composio Docs: https://docs.composio.dev
   • Twitter Toolkit: https://composio.dev/toolkits/twitter
   • Support: https://discord.gg/composio

═══════════════════════════════════════════════════════════════════════════════
""")

def main():
    """Main setup function."""
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║              COMPOSIO TWITTER INTEGRATION SETUP                              ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print()
    
    # Install packages
    if not install_composio():
        print("\n❌ Setup failed: Could not install required packages")
        sys.exit(1)
    
    print()
    
    # Check API key
    has_key = check_api_key()
    
    print()
    
    # Create env template
    create_env_template()
    
    print()
    
    # Print instructions
    print_setup_instructions()
    
    if has_key:
        print("✅ COMPOSIO_API_KEY is already configured!")
        print("   Next step: Run 'composio add twitter' to connect your account")
    else:
        print("⚠️  Please set your COMPOSIO_API_KEY to continue")

if __name__ == '__main__':
    main()
