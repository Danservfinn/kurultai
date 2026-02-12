#!/usr/bin/env python3
"""
Emergency Neo4j Workaround Script

Usage:
    python emergency_neo4j_workaround.py [command] [options]

Commands:
    status      - Check Neo4j and fallback status
    force-fallback - Force fallback mode (disable Neo4j attempts)
    sync        - Manually sync fallback data to Neo4j
    export      - Export fallback data to JSON
    import      - Import JSON data to Neo4j when available
    clear-queue - Clear stuck sync queue items
    test        - Test Neo4j connectivity
    repair      - Attempt to repair connection issues

Examples:
    python emergency_neo4j_workaround.py status
    python emergency_neo4j_workaround.py sync --dry-run
    python emergency_neo4j_workaround.py export --output backup.json
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools' / 'kurultai'))

from tools.kurultai.neo4j_agent_memory import Neo4jAgentMemory, get_memory_status
from tools.kurultai.resilient_neo4j import FallbackStorage, get_resilient_connection


def cmd_status(args):
    """Check Neo4j and fallback status."""
    print("=" * 60)
    print("NEO4J CONNECTION STATUS")
    print("=" * 60)
    
    # Get memory status
    status = get_memory_status()
    
    print(f"\n📊 Connection State:")
    conn = status.get('connection', {})
    print(f"   State: {conn.get('state', 'unknown')}")
    print(f"   URI: {conn.get('uri', 'N/A')}")
    print(f"   Fallback Mode: {conn.get('fallback_mode', False)}")
    print(f"   Fallback Enabled: {conn.get('fallback_enabled', False)}")
    
    print(f"\n📈 Connection Statistics:")
    stats = conn.get('stats', {})
    print(f"   Total Attempts: {stats.get('total_attempts', 0)}")
    print(f"   Successful: {stats.get('successful_connections', 0)}")
    print(f"   Failed: {stats.get('failed_connections', 0)}")
    print(f"   Retry Attempts: {stats.get('retry_attempts', 0)}")
    print(f"   Circuit Opens: {stats.get('circuit_opens', 0)}")
    print(f"   Avg Response: {stats.get('average_response_ms', 0)}ms")
    
    if stats.get('last_success'):
        print(f"   Last Success: {stats['last_success']}")
    if stats.get('last_failure'):
        print(f"   Last Failure: {stats['last_failure']}")
    
    print(f"\n💾 Fallback Storage Statistics:")
    fb_stats = status.get('fallback_stats', {})
    if fb_stats:
        print(f"   Total Memories: {fb_stats.get('total_memories', 0)}")
        print(f"   Unsynced Memories: {fb_stats.get('unsynced_memories', 0)}")
        print(f"   Total Tasks: {fb_stats.get('total_tasks', 0)}")
        print(f"   Pending Sync: {fb_stats.get('pending_sync', 0)}")
    else:
        print("   No fallback data available")
    
    # Test direct connection
    print(f"\n🔌 Direct Connection Test:")
    try:
        conn = get_resilient_connection()
        if conn.is_healthy():
            print("   ✅ Neo4j is reachable and healthy")
        elif conn.is_fallback_mode():
            print("   ⚠️  Neo4j unavailable - running in fallback mode")
        else:
            print("   ⚠️  Neo4j degraded - connection issues detected")
        conn.close()
    except Exception as e:
        print(f"   ❌ Connection test failed: {e}")
    
    print("\n" + "=" * 60)


def cmd_force_fallback(args):
    """Force fallback mode by creating a flag file."""
    flag_file = Path("/data/workspace/souls/main/memory/.force_fallback")
    
    if args.disable:
        if flag_file.exists():
            flag_file.unlink()
            print("✅ Fallback mode forced OFF - Neo4j will be attempted")
        else:
            print("ℹ️  Fallback mode was not forced")
    else:
        flag_file.touch()
        print("✅ Fallback mode forced ON - Neo4j will be skipped")
        print("   Remove with: --disable flag")


def cmd_sync(args):
    """Manually sync fallback data to Neo4j."""
    print("🔄 Syncing fallback data to Neo4j...")
    
    memory = Neo4jAgentMemory()
    
    if memory._is_fallback_mode():
        print("❌ Cannot sync - Neo4j is still unavailable")
        print("   Run 'status' command to check connection")
        return 1
    
    if args.dry_run:
        # Just show what would be synced
        fb = FallbackStorage()
        pending = fb.get_pending_sync_items(limit=1000)
        print(f"\n📋 Would sync {len(pending)} items:")
        for item in pending[:10]:
            print(f"   - {item['table_name']}.{item['record_id']} ({item['operation']})")
        if len(pending) > 10:
            print(f"   ... and {len(pending) - 10} more")
    else:
        result = memory.sync_fallback_to_neo4j()
        print(f"\n✅ Sync complete:")
        print(f"   Synced: {result.get('synced', 0)}")
        if 'error' in result:
            print(f"   Error: {result['error']}")
    
    memory.close()
    return 0


def cmd_export(args):
    """Export fallback data to JSON."""
    print(f"📤 Exporting fallback data to {args.output}...")
    
    fb = FallbackStorage()
    
    # Get all data
    data = {
        'exported_at': datetime.utcnow().isoformat(),
        'memories': [],
        'tasks': [],
        'sync_queue': []
    }
    
    # Export memories
    conn = fb._get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM agent_memories')
    for row in cursor.fetchall():
        data['memories'].append(fb._row_to_dict(row))
    
    cursor.execute('SELECT * FROM tasks')
    for row in cursor.fetchall():
        data['tasks'].append(fb._row_to_dict(row))
    
    cursor.execute('SELECT * FROM sync_queue WHERE retry_count < 5')
    for row in cursor.fetchall():
        data['sync_queue'].append(fb._row_to_dict(row))
    
    # Write to file
    with open(args.output, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Exported:")
    print(f"   Memories: {len(data['memories'])}")
    print(f"   Tasks: {len(data['tasks'])}")
    print(f"   Sync Queue Items: {len(data['sync_queue'])}")
    print(f"\n   Saved to: {args.output}")
    
    return 0


def cmd_import(args):
    """Import JSON data to Neo4j."""
    print(f"📥 Importing data from {args.input}...")
    
    if not os.path.exists(args.input):
        print(f"❌ File not found: {args.input}")
        return 1
    
    with open(args.input, 'r') as f:
        data = json.load(f)
    
    memory = Neo4jAgentMemory()
    
    if memory._is_fallback_mode():
        print("❌ Cannot import - Neo4j is unavailable")
        return 1
    
    imported = {'memories': 0, 'tasks': 0}
    
    # Import memories
    for mem in data.get('memories', []):
        try:
            entry = AgentMemoryEntry(
                id=mem['id'],
                agent_name=mem['agent_name'],
                memory_type=mem['memory_type'],
                content=mem['content'],
                source_task_id=mem.get('source_task_id'),
                related_agents=mem.get('related_agents', []),
                tags=mem.get('tags', []),
                importance=mem.get('importance', 0.5),
                created_at=mem.get('created_at', datetime.utcnow().isoformat())
            )
            if memory.add_memory(entry):
                imported['memories'] += 1
        except Exception as e:
            if args.verbose:
                print(f"   ⚠️  Failed to import memory {mem.get('id')}: {e}")
    
    memory.close()
    
    print(f"✅ Import complete:")
    print(f"   Memories: {imported['memories']}/{len(data.get('memories', []))}")
    
    return 0


def cmd_clear_queue(args):
    """Clear stuck sync queue items."""
    print("🧹 Clearing sync queue...")
    
    fb = FallbackStorage()
    conn = fb._get_connection()
    cursor = conn.cursor()
    
    # Get count before
    cursor.execute('SELECT COUNT(*) FROM sync_queue')
    before = cursor.fetchone()[0]
    
    if args.all:
        cursor.execute('DELETE FROM sync_queue')
    else:
        # Clear items with many retries
        cursor.execute('DELETE FROM sync_queue WHERE retry_count >= ?', (args.threshold,))
    
    conn.commit()
    
    cursor.execute('SELECT COUNT(*) FROM sync_queue')
    after = cursor.fetchone()[0]
    
    print(f"✅ Cleared {before - after} items from sync queue")
    print(f"   Remaining: {after}")
    
    return 0


def cmd_test(args):
    """Test Neo4j connectivity."""
    print("🧪 Testing Neo4j connectivity...")
    
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    password = os.environ.get('NEO4J_PASSWORD')
    
    print(f"\n📍 Target: {uri}")
    
    # Test 1: DNS resolution
    print("\n1️⃣  DNS Resolution:")
    try:
        import socket
        host = uri.split('//')[1].split(':')[0] if '//' in uri else uri.split(':')[0]
        ip = socket.gethostbyname(host)
        print(f"   ✅ {host} resolves to {ip}")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Test 2: Port connectivity
    print("\n2️⃣  Port Connectivity:")
    try:
        import socket
        host = uri.split('//')[1].split(':')[0] if '//' in uri else uri.split(':')[0]
        port = int(uri.split(':')[-1].split('/')[0]) if ':' in uri else 7687
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"   ✅ Port {port} is open")
        else:
            print(f"   ❌ Port {port} is closed (error {result})")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Test 3: Bolt connection
    print("\n3️⃣  Bolt Protocol:")
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(uri, auth=("neo4j", password))
        driver.verify_connectivity()
        print("   ✅ Bolt connection successful")
        
        # Test query
        with driver.session() as session:
            result = session.run("RETURN 1 as test")
            value = result.single()["test"]
            if value == 1:
                print("   ✅ Query execution successful")
        
        driver.close()
    except ImportError:
        print("   ⚠️  neo4j package not installed")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Test 4: Resilient connection
    print("\n4️⃣  Resilient Connection:")
    try:
        conn = get_resilient_connection()
        status = conn.get_status()
        print(f"   State: {status['state']}")
        print(f"   Fallback Mode: {status['fallback_mode']}")
        conn.close()
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    print("\n" + "=" * 60)
    return 0


def cmd_repair(args):
    """Attempt to repair connection issues."""
    print("🔧 Attempting to repair Neo4j connection...")
    
    # Step 1: Reset circuit breaker
    print("\n1️⃣  Resetting circuit breaker...")
    try:
        conn = get_resilient_connection()
        with conn._state_lock:
            conn._state = ConnectionState.UNAVAILABLE
            conn._failure_count = 0
            conn._circuit_opened_at = None
        print("   ✅ Circuit breaker reset")
        conn.close()
    except Exception as e:
        print(f"   ⚠️  Could not reset circuit: {e}")
    
    # Step 2: Clear connection pool
    print("\n2️⃣  Clearing connection state...")
    try:
        conn = get_resilient_connection()
        if conn._driver:
            try:
                conn._driver.close()
            except:
                pass
            conn._driver = None
        print("   ✅ Connection pool cleared")
        conn.close()
    except Exception as e:
        print(f"   ⚠️  Could not clear pool: {e}")
    
    # Step 3: Test connection
    print("\n3️⃣  Testing connection...")
    try:
        conn = get_resilient_connection()
        if conn._try_connect():
            print("   ✅ Connection restored!")
            
            # Sync any pending data
            print("\n4️⃣  Syncing pending data...")
            memory = Neo4jAgentMemory()
            result = memory.sync_fallback_to_neo4j()
            print(f"   Synced {result.get('synced', 0)} items")
            memory.close()
        else:
            print("   ❌ Connection still failing")
            print("\n   Troubleshooting tips:")
            print("   - Check Neo4j server is running")
            print("   - Verify network connectivity")
            print("   - Check authentication credentials")
            print("   - Review Neo4j server logs")
        conn.close()
    except Exception as e:
        print(f"   ❌ Connection test failed: {e}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Emergency Neo4j Workaround Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status
  %(prog)s sync --dry-run
  %(prog)s export --output backup.json
  %(prog)s test
  %(prog)s repair
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Status command
    subparsers.add_parser('status', help='Check Neo4j and fallback status')
    
    # Force fallback command
    force_parser = subparsers.add_parser('force-fallback', help='Force fallback mode')
    force_parser.add_argument('--disable', action='store_true', help='Disable forced fallback')
    
    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Sync fallback data to Neo4j')
    sync_parser.add_argument('--dry-run', action='store_true', help='Show what would be synced')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export fallback data to JSON')
    export_parser.add_argument('--output', '-o', default='fallback_export.json',
                              help='Output file (default: fallback_export.json)')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import JSON data to Neo4j')
    import_parser.add_argument('--input', '-i', required=True, help='Input JSON file')
    import_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    # Clear queue command
    clear_parser = subparsers.add_parser('clear-queue', help='Clear stuck sync queue items')
    clear_parser.add_argument('--threshold', '-t', type=int, default=10,
                             help='Clear items with retry count >= threshold')
    clear_parser.add_argument('--all', action='store_true', help='Clear all queue items')
    
    # Test command
    subparsers.add_parser('test', help='Test Neo4j connectivity')
    
    # Repair command
    subparsers.add_parser('repair', help='Attempt to repair connection issues')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Run command
    commands = {
        'status': cmd_status,
        'force-fallback': cmd_force_fallback,
        'sync': cmd_sync,
        'export': cmd_export,
        'import': cmd_import,
        'clear-queue': cmd_clear_queue,
        'test': cmd_test,
        'repair': cmd_repair,
    }
    
    try:
        return commands[args.command](args) or 0
    except Exception as e:
        print(f"❌ Command failed: {e}")
        import traceback
        if args.verbose:
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
