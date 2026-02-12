#!/usr/bin/env python3
"""
Composio Twitter Integration Verification

This script verifies that:
1. Composio API key is configured
2. Twitter connection is established
3. Basic Twitter operations work

Usage:
    python3 verify_composio_twitter.py
"""

import os
import sys

def check_environment():
    """Check environment setup."""
    print("🔍 Checking environment...")
    
    api_key = os.environ.get('COMPOSIO_API_KEY')
    if not api_key:
        print("   ❌ COMPOSIO_API_KEY not set")
        print("      Set it with: export COMPOSIO_API_KEY=your_key")
        return False
    
    # Mask the key for display
    masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    print(f"   ✅ COMPOSIO_API_KEY is set ({masked_key})")
    return True

def check_composio_installation():
    """Check if Composio is installed."""
    print("\n📦 Checking Composio installation...")
    
    try:
        import composio
        print(f"   ✅ composio-core installed (version: {composio.__version__})")
        return True
    except ImportError:
        print("   ❌ composio-core not installed")
        print("      Install with: pip install composio-core")
        return False
    except AttributeError:
        print("   ✅ composio-core installed (version unknown)")
        return True

def check_twitter_connection():
    """Check Twitter/X connection status."""
    print("\n🐦 Checking Twitter/X connection...")
    
    try:
        from composio import ComposioToolSet, App
        
        toolset = ComposioToolSet()
        
        # Check if Twitter is connected
        try:
            # Get connected accounts
            connections = toolset.get_connected_accounts()
            twitter_connected = any(
                conn.app_name.lower() in ['twitter', 'x'] 
                for conn in connections
            )
            
            if twitter_connected:
                print("   ✅ Twitter/X account is connected")
                return True
            else:
                print("   ⚠️  Twitter/X account not connected")
                print("      Connect with: composio add twitter")
                return False
                
        except Exception as e:
            print(f"   ⚠️  Could not verify connection: {e}")
            print("      Try running: composio add twitter")
            return False
            
    except Exception as e:
        print(f"   ❌ Error checking connection: {e}")
        return False

def test_twitter_tools():
    """Test Twitter tools availability."""
    print("\n🛠️  Checking Twitter tools...")
    
    try:
        from composio import ComposioToolSet, App
        
        toolset = ComposioToolSet()
        
        # Try to get Twitter tools
        try:
            tools = toolset.get_tools(apps=[App.TWITTER])
            print(f"   ✅ Found {len(tools)} Twitter tools")
            
            # List available actions
            actions = [tool.__name__ if hasattr(tool, '__name__') else str(tool) for tool in tools[:5]]
            for action in actions:
                print(f"      • {action}")
            
            if len(tools) > 5:
                print(f"      ... and {len(tools) - 5} more")
                
            return True
            
        except Exception as e:
            print(f"   ⚠️  Could not list tools: {e}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    """Main verification function."""
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║         COMPOSIO TWITTER INTEGRATION VERIFICATION                            ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print()
    
    results = {
        'environment': check_environment(),
        'installation': check_composio_installation(),
        'connection': check_twitter_connection(),
        'tools': test_twitter_tools()
    }
    
    print("\n" + "="*80)
    print("VERIFICATION SUMMARY")
    print("="*80)
    
    passed = sum(results.values())
    total = len(results)
    
    for check, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {check:20s} {status}")
    
    print("="*80)
    
    if passed == total:
        print("\n🎉 All checks passed! Twitter integration is ready to use.")
        print("\nExample usage:")
        print("  from composio import ComposioToolSet, App")
        print("  toolset = ComposioToolSet()")
        print("  tools = toolset.get_tools(apps=[App.TWITTER])")
        return 0
    else:
        print(f"\n⚠️  {total - passed} of {total} checks failed.")
        print("   Please complete the setup steps above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
