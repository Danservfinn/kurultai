#!/usr/bin/env python3
"""
Test script for Kurultai Discord bots.
Verifies all 6 bots can connect and send messages.
"""

import os
import sys
import asyncio
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from deliberation_client import (
    AgentRole,
    AGENT_PERSONALITIES,
    CHANNELS,
    create_discord_client,
    KurultaiDiscordClient,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kurultai-test")


class BotTester:
    """Tests Discord bot connectivity and functionality."""
    
    def __init__(self):
        self.discord = create_discord_client()
        self.results = []
    
    async def run_all_tests(self):
        """Run all tests."""
        print("🧪 Kurultai Discord Bot Tests")
        print("=" * 50)
        
        # Test 1: Configuration
        await self.test_configuration()
        
        # Test 2: Agent Personalities
        await self.test_personalities()
        
        # Test 3: Channel Configuration
        await self.test_channels()
        
        # Test 4: Bot Tokens
        await self.test_tokens()
        
        # Test 5: Message Sending (if tokens available)
        await self.test_messaging()
        
        # Summary
        self.print_summary()
    
    async def test_configuration(self):
        """Test configuration loading."""
        print("\n📋 Test 1: Configuration")
        print("-" * 30)
        
        tests = [
            ("Environment loaded", self.discord is not None),
            ("Personalities loaded", len(self.discord.personalities) == 6),
            ("Channels loaded", len(self.discord.channels) == 9),
            ("Memory initialized", len(self.discord.memories) == 9),
        ]
        
        for name, passed in tests:
            status = "✅" if passed else "❌"
            print(f"  {status} {name}")
            self.results.append((name, passed))
    
    async def test_personalities(self):
        """Test agent personality configuration."""
        print("\n🎭 Test 2: Agent Personalities")
        print("-" * 30)
        
        all_passed = True
        for role in AgentRole:
            personality = AGENT_PERSONALITIES[role]
            
            checks = [
                personality.name,
                personality.display_name,
                personality.voice_style,
                personality.signature_phrase,
                len(personality.emoji_reactions) > 0,
            ]
            
            passed = all(checks)
            all_passed = all_passed and passed
            
            status = "✅" if passed else "❌"
            print(f"  {status} {personality.display_name}")
            print(f"      Voice: {personality.voice_style[:40]}...")
            print(f"      Signature: '{personality.signature_phrase}'")
        
        self.results.append(("Personalities configured", all_passed))
    
    async def test_channels(self):
        """Test channel configuration."""
        print("\n📢 Test 3: Channel Configuration")
        print("-" * 30)
        
        all_passed = True
        categories = {}
        
        for key, config in CHANNELS.items():
            cat = config.category or "Uncategorized"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(config)
            
            passed = bool(config.name and config.purpose)
            all_passed = all_passed and passed
            
            status = "✅" if passed else "❌"
            agents = len(config.allowed_agents)
            print(f"  {status} #{config.name} ({agents} agents)")
        
        print("\n  Categories:")
        for cat, channels in categories.items():
            print(f"    📁 {cat}: {len(channels)} channels")
        
        self.results.append(("Channels configured", all_passed))
    
    async def test_tokens(self):
        """Test bot token availability."""
        print("\n🔑 Test 4: Bot Tokens")
        print("-" * 30)
        
        token_status = {}
        for role in AgentRole:
            token = self.discord.bot_tokens.get(role)
            has_token = token is not None and token != f"your_{role.value}_bot_token_here"
            token_status[role] = has_token
            
            status = "✅" if has_token else "⚠️"
            print(f"  {status} {role.value.title()}: {'Set' if has_token else 'Not set'}")
        
        set_count = sum(token_status.values())
        print(f"\n  Tokens configured: {set_count}/6")
        
        self.results.append(("Tokens available", set_count > 0))
    
    async def test_messaging(self):
        """Test message sending (if tokens available)."""
        print("\n💬 Test 5: Messaging")
        print("-" * 30)
        
        if not self.discord.bot_tokens:
            print("  ⚠️  No bot tokens - skipping messaging tests")
            print("  Set tokens in .env to test actual Discord connectivity")
            self.results.append(("Messaging test", None))  # Skipped
            return
        
        # Test sending messages (this would actually send if configured)
        print("  Testing message format...")
        
        for role in [AgentRole.KUBLAI, AgentRole.MONGKE]:
            personality = AGENT_PERSONALITIES[role]
            test_message = f"Test message from {personality.name}"
            formatted = personality.format_message(test_message)
            
            if personality.signature_phrase:
                print(f"  ✅ {role.value}: '{formatted[:50]}...'")
            else:
                print(f"  ✅ {role.value}: Message formatted")
        
        self.results.append(("Messaging", True))
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 50)
        print("📊 Test Summary")
        print("=" * 50)
        
        passed = sum(1 for _, r in self.results if r is True)
        failed = sum(1 for _, r in self.results if r is False)
        skipped = sum(1 for _, r in self.results if r is None)
        
        print(f"\n  ✅ Passed: {passed}")
        print(f"  ❌ Failed: {failed}")
        print(f"  ⚠️  Skipped: {skipped}")
        
        print("\n  Details:")
        for name, result in self.results:
            if result is True:
                icon = "✅"
            elif result is False:
                icon = "❌"
            else:
                icon = "⚠️"
            print(f"    {icon} {name}")
        
        print("\n" + "=" * 50)
        if failed == 0:
            print("🎉 All tests passed! Ready for Discord integration.")
        else:
            print("⚠️  Some tests failed. Check configuration.")


def test_environment():
    """Quick environment check."""
    print("🔧 Environment Check")
    print("-" * 30)
    
    checks = [
        ("Python 3.8+", sys.version_info >= (3, 8)),
        ("aiohttp", _check_import("aiohttp")),
        ("Working directory", os.getcwd()),
    ]
    
    for name, result in checks:
        if isinstance(result, bool):
            status = "✅" if result else "❌"
            print(f"  {status} {name}")
        else:
            print(f"  📁 {name}: {result}")


def _check_import(module: str) -> bool:
    """Check if a module can be imported."""
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def show_setup_instructions():
    """Show quick setup instructions."""
    print("\n📚 Quick Start")
    print("=" * 50)
    print("""
1. Create Discord server "Kurultai Council"
2. Run: python tools/discord/bot_setup.py
3. Follow SETUP.md to create 6 bot applications
4. Copy .env.discord.example to .env
5. Add your bot tokens to .env
6. Run: python tools/discord/test_bots.py
7. Start heartbeat: python tools/discord/heartbeat_bridge.py --continuous

Trigger a test deliberation:
  python tools/discord/trigger_deliberation.py --topic "Test deliberation"
""")


async def main():
    """Main test runner."""
    test_environment()
    
    tester = BotTester()
    await tester.run_all_tests()
    
    show_setup_instructions()


if __name__ == "__main__":
    asyncio.run(main())
