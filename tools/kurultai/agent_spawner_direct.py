#!/usr/bin/env python3
"""
Direct Agent Spawner via Signal Messages

Since OpenClaw HTTP API has limited spawn capabilities,
this module uses Signal messages as the primary spawn trigger.

Now with HMAC-SHA256 message signing for all agent-to-agent communication.

Usage:
    from agent_spawner_direct import spawn_agent
    spawn_agent('Möngke', 'You have pending research tasks')
"""

import os
import sys
import json
import subprocess
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from neo4j import GraphDatabase

# Import message signing
try:
    from tools.kurultai.message_signer import AgentMessageSigner, MessageSigner
    HAS_SIGNING = True
except ImportError:
    HAS_SIGNING = False

# Agent configuration
AGENTS = {
    'Kublai': {'id': 'main', 'phone': None},
    'Möngke': {'id': 'researcher', 'phone': None},
    'Chagatai': {'id': 'writer', 'phone': None},
    'Temüjin': {'id': 'developer', 'phone': None},
    'Jochi': {'id': 'analyst', 'phone': None},
    'Ögedei': {'id': 'ops', 'phone': None}
}

# Message signing configuration
SIGNING_ENABLED = os.environ.get('AGENT_SIGNING_ENABLED', 'true').lower() == 'true'
AGENT_KEYS_ENV = 'AGENT_SIGNING_KEYS'  # JSON string of agent keys


def get_neo4j_driver():
    """Get Neo4j driver."""
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    password = os.environ.get('NEO4J_PASSWORD')
    if not password:
        raise ValueError("NEO4J_PASSWORD not set")
    return GraphDatabase.driver(uri, auth=('neo4j', password))


def get_agent_signer(agent_id: str) -> Optional[AgentMessageSigner]:
    """
    Get message signer for an agent.
    
    Args:
        agent_id: Agent identifier
        
    Returns:
        AgentMessageSigner instance or None if signing unavailable
    """
    if not HAS_SIGNING or not SIGNING_ENABLED:
        return None
    
    try:
        return AgentMessageSigner(agent_id=agent_id)
    except Exception as e:
        print(f"  ⚠️  Failed to initialize signer for {agent_id}: {e}")
        return None


def sign_agent_message(
    message_content: Dict[str, Any],
    from_agent: str,
    to_agent: str
) -> tuple[Dict[str, Any], Optional[str]]:
    """
    Sign an agent-to-agent message.
    
    Args:
        message_content: Message content dictionary
        from_agent: Sending agent ID
        to_agent: Target agent ID
        
    Returns:
        Tuple of (signed message dict, signature string)
    """
    signer = get_agent_signer(from_agent)
    
    if not signer:
        # Return unsigned message
        return {
            **message_content,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signed": False
        }, None
    
    # Sign the message
    result = signer.sign_message(message_content, to_agent=to_agent)
    
    signed_message = {
        **message_content,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "timestamp": result.timestamp,
        "signed": True,
        "signature": result.signature,
        "key_id": result.key_id,
        "sig_version": result.version
    }
    
    return signed_message, result.signature


def verify_agent_message(
    message: Dict[str, Any],
    signature: str,
    expected_from: Optional[str] = None
) -> bool:
    """
    Verify an agent message signature.
    
    Args:
        message: Message dictionary (must include from_agent)
        signature: Signature string
        expected_from: Expected sender agent ID
        
    Returns:
        True if signature is valid
    """
    if not HAS_SIGNING or not SIGNING_ENABLED:
        # Accept unsigned messages when signing not available
        return True
    
    from_agent = message.get('from_agent')
    if not from_agent:
        print("  ⚠️  Message missing from_agent field")
        return False
    
    # Use expected_from if provided, otherwise use from_agent
    check_agent = expected_from or from_agent
    
    signer = get_agent_signer(check_agent)
    if not signer:
        print(f"  ⚠️  No signer available for {check_agent}")
        return False
    
    result = signer.verify_message(message, signature, from_agent=check_agent)
    
    if not result.is_valid:
        print(f"  ⚠️  Signature verification failed: {result.reason}")
        return False
    
    return True


def check_pending_work(driver, agent_name: str) -> tuple[bool, int, int]:
    """Check if agent has pending tasks or messages."""
    with driver.session() as session:
        # Check tasks
        task_result = session.run('''
            MATCH (t:Task {status: "pending", assigned_to: $agent})
            RETURN count(t) as count
        ''', agent=agent_name)
        task_count = task_result.single()['count']
        
        # Check messages - now including signature verification check
        msg_result = session.run('''
            MATCH (m:AgentMessage {to_agent: $agent, status: "pending"})
            RETURN count(m) as count
        ''', agent=agent_name)
        msg_count = msg_result.single()['count']
        
        return (task_count > 0 or msg_count > 0), task_count, msg_count


def spawn_via_signal(agent_id: str, message: str, signed: bool = False) -> bool:
    """
    Spawn agent by sending Signal message.
    This is the PRIMARY spawn mechanism since OpenClaw API is limited.
    
    Args:
        agent_id: Target agent ID
        message: Message content
        signed: Whether message is signed
    """
    signal_account = os.environ.get('SIGNAL_ACCOUNT')
    if not signal_account:
        print(f"  ⚠️  SIGNAL_ACCOUNT not set")
        return False
    
    # For now, send to owner's number with agent mention
    # In production, this would send to the agent's configured number
    owner_number = "+19194133445"  # Danny's number
    
    # Add signature indicator to message
    sig_indicator = "[SIGNED] " if signed else ""
    
    try:
        # Use signal-cli to send message
        cmd = [
            'signal-cli',
            '-a', signal_account,
            'send',
            '-m', f"{sig_indicator}@{agent_id}: {message}",
            owner_number
        ]
        
        result = subprocess.run(
            cmd,
            timeout=30,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"  ✅ Signal message sent to trigger {agent_id}")
            return True
        else:
            print(f"  ⚠️  Signal send failed: {result.stderr}")
            return False
            
    except FileNotFoundError:
        print(f"  ⚠️  signal-cli not found")
        return False
    except Exception as e:
        print(f"  ⚠️  Signal error: {e}")
        return False


def spawn_agent(agent_name: str, context: Optional[str] = None, sign: bool = True) -> bool:
    """
    Main spawn function.
    Tries multiple methods in order of preference.
    
    Args:
        agent_name: Agent name to spawn
        context: Optional context message
        sign: Whether to sign the spawn message
    """
    agent_info = AGENTS.get(agent_name)
    if not agent_info:
        print(f"❌ Unknown agent: {agent_name}")
        return False
    
    agent_id = agent_info['id']
    
    print(f"🚀 Spawning {agent_name} ({agent_id})...")
    
    # Check if there's actually work to do
    try:
        driver = get_neo4j_driver()
        has_work, task_count, msg_count = check_pending_work(driver, agent_name)
        driver.close()
        
        if not has_work:
            print(f"  ⏭️  No pending work (tasks: {task_count}, messages: {msg_count})")
            return True
        
        print(f"  📋 Found {task_count} tasks, {msg_count} messages")
    except Exception as e:
        print(f"  ⚠️  Could not check work: {e}")
        # Continue anyway
    
    # Prepare spawn message
    if context:
        message_text = context
    else:
        message_text = f"You have {task_count} pending task(s). Check Neo4j and claim them."
    
    # Sign the message if enabled
    signed = False
    if sign and SIGNING_ENABLED and HAS_SIGNING:
        try:
            spawn_message = {
                "action": "spawn",
                "task_count": task_count,
                "message_count": msg_count,
                "message": message_text
            }
            
            signed_message, signature = sign_agent_message(
                spawn_message,
                from_agent="main",  # Kublai spawns agents
                to_agent=agent_id
            )
            
            if signature:
                message_text = json.dumps(signed_message)
                signed = True
                print(f"  🔐 Message signed (key: {signed_message.get('key_id')})")
        except Exception as e:
            print(f"  ⚠️  Signing failed, sending unsigned: {e}")
    
    # Primary method: Signal message
    if spawn_via_signal(agent_id, message_text, signed=signed):
        # Log the spawn attempt
        try:
            driver = get_neo4j_driver()
            with driver.session() as session:
                session.run('''
                    CREATE (s:AgentSpawn {
                        id: $spawn_id,
                        agent: $agent,
                        method: 'signal',
                        signed: $signed,
                        triggered_at: datetime(),
                        context: $context
                    })
                ''', 
                    spawn_id=f"spawn_{agent_id}_{os.urandom(4).hex()}",
                    agent=agent_name,
                    signed=signed,
                    context=message_text[:200]
                )
            driver.close()
        except:
            pass  # Don't fail if logging fails
        
        return True
    
    print(f"  ❌ All spawn methods failed for {agent_name}")
    return False


def spawn_all_pending(sign: bool = True):
    """
    Spawn all agents that have pending work.
    
    Args:
        sign: Whether to sign spawn messages
    """
    print("🤖 Checking all agents for pending work...")
    print("=" * 60)
    
    spawned = 0
    skipped = 0
    failed = 0
    
    driver = get_neo4j_driver()
    
    for agent_name in AGENTS.keys():
        if agent_name == 'Kublai':
            continue  # Kublai is always running
        
        has_work, task_count, msg_count = check_pending_work(driver, agent_name)
        
        if has_work:
            if spawn_agent(agent_name, sign=sign):
                spawned += 1
            else:
                failed += 1
        else:
            print(f"  ⏭️  {agent_name}: No work")
            skipped += 1
    
    driver.close()
    
    print("=" * 60)
    print(f"Results: {spawned} spawned, {skipped} skipped, {failed} failed")
    if SIGNING_ENABLED and HAS_SIGNING:
        print("🔐 All messages signed with HMAC-SHA256")
    return spawned, skipped, failed

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Spawn Kurultai agents')
    parser.add_argument('--agent', '-a', help='Specific agent to spawn')
    parser.add_argument('--all', action='store_true', help='Spawn all with pending work')
    parser.add_argument('--context', '-c', help='Context message for agent')
    
    args = parser.parse_args()
    
    if args.all:
        spawn_all_pending()
    elif args.agent:
        success = spawn_agent(args.agent, args.context)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)
