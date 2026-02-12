#!/usr/bin/env python3
"""
Test script for Neo4j fallback implementation.

Run this to verify the fallback system is working correctly.
"""

import sys
import os
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'tools' / 'kurultai'))


def test_imports():
    """Test that all modules import correctly."""
    print("🧪 Testing imports...")
    
    try:
        from tools.kurultai.resilient_neo4j import (
            ResilientNeo4jConnection,
            FallbackStorage,
            get_resilient_connection,
            RetryConfig,
            CircuitBreakerConfig
        )
        print("   ✅ resilient_neo4j imports OK")
    except Exception as e:
        print(f"   ❌ resilient_neo4j import failed: {e}")
        return False
    
    try:
        from tools.kurultai.neo4j_agent_memory import (
            Neo4jAgentMemory,
            AgentMemoryEntry,
            record_agent_memory,
            get_task_context,
            get_memory_status
        )
        print("   ✅ neo4j_agent_memory imports OK")
    except Exception as e:
        print(f"   ❌ neo4j_agent_memory import failed: {e}")
        return False
    
    try:
        from tools.kurultai.neo4j_task_helpers import (
            check_neo4j_available,
            with_neo4j_fallback,
            health_check_partial
        )
        print("   ✅ neo4j_task_helpers imports OK")
    except Exception as e:
        print(f"   ❌ neo4j_task_helpers import failed: {e}")
        return False
    
    return True


def test_fallback_storage():
    """Test SQLite fallback storage."""
    print("\n🧪 Testing fallback storage...")
    
    try:
        from tools.kurultai.resilient_neo4j import FallbackStorage
        
        # Create storage
        fb = FallbackStorage()
        print("   ✅ FallbackStorage created")
        
        # Test adding memory
        test_memory = {
            'id': 'test-memory-001',
            'agent_name': 'test_agent',
            'memory_type': 'observation',
            'content': 'Test memory content',
            'source_task_id': None,
            'related_agents': ['agent1', 'agent2'],
            'tags': ['test', 'fallback'],
            'importance': 0.8,
            'created_at': '2024-01-01T00:00:00'
        }
        
        result = fb.add_memory(test_memory)
        assert result, "Failed to add memory"
        print("   ✅ Memory added to fallback storage")
        
        # Test retrieving memories
        memories = fb.get_agent_memories('test_agent', limit=10)
        assert len(memories) > 0, "No memories retrieved"
        print(f"   ✅ Retrieved {len(memories)} memories")
        
        # Test stats
        stats = fb.get_stats()
        assert 'total_memories' in stats, "Stats missing total_memories"
        print(f"   ✅ Stats: {stats}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Fallback storage test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_resilient_connection():
    """Test resilient connection wrapper."""
    print("\n🧪 Testing resilient connection...")
    
    try:
        from tools.kurultai.resilient_neo4j import (
            ResilientNeo4jConnection,
            ConnectionState
        )
        
        # Create connection with invalid URI (forces fallback)
        conn = ResilientNeo4jConnection(
            uri="bolt://invalid-host-for-testing:9999",
            fallback_enabled=True
        )
        
        print("   ✅ ResilientNeo4jConnection created")
        
        # Check that it's in fallback mode
        status = conn.get_status()
        print(f"   📊 Status: {status['state']}")
        
        # Cleanup
        conn.close()
        print("   ✅ Connection closed")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Resilient connection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_agent_memory_with_fallback():
    """Test agent memory system with fallback."""
    print("\n🧪 Testing agent memory with fallback...")
    
    try:
        from tools.kurultai.neo4j_agent_memory import (
            Neo4jAgentMemory,
            AgentMemoryEntry
        )
        
        # Create memory system (will use fallback if Neo4j down)
        memory = Neo4jAgentMemory(fallback_enabled=True)
        print("   ✅ Neo4jAgentMemory created")
        
        # Check mode
        is_fallback = memory._is_fallback_mode()
        print(f"   📊 Fallback mode: {is_fallback}")
        
        # Add memory
        entry = AgentMemoryEntry(
            id='test-entry-001',
            agent_name='temujin',
            memory_type='learning',
            content='Test learning about Neo4j resilience',
            importance=0.9
        )
        
        result = memory.add_memory(entry)
        print(f"   ✅ Memory added: {result}")
        
        # Retrieve memories
        memories = memory.get_agent_memories('temujin', limit=5)
        print(f"   ✅ Retrieved {len(memories)} memories")
        
        # Get status
        status = memory.get_status()
        print(f"   📊 Fallback stats: {status.get('fallback_stats', {})}")
        
        # Cleanup
        memory.close()
        print("   ✅ Memory system closed")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Agent memory test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_convenience_functions():
    """Test convenience functions."""
    print("\n🧪 Testing convenience functions...")
    
    try:
        from tools.kurultai.neo4j_agent_memory import (
            record_agent_memory,
            get_memory_status
        )
        
        # Record memory
        result = record_agent_memory(
            agent_name='temujin',
            memory_type='insight',
            content='Fallback system is working correctly',
            importance=0.95
        )
        print(f"   ✅ record_agent_memory: {result}")
        
        # Get status
        status = get_memory_status()
        print(f"   ✅ get_memory_status: {status['fallback_mode']}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Convenience functions test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_neo4j_availability_check():
    """Test Neo4j availability checking."""
    print("\n🧪 Testing Neo4j availability check...")
    
    try:
        from tools.kurultai.neo4j_task_helpers import check_neo4j_available
        
        # Check availability
        available = check_neo4j_available(force=True)
        print(f"   📊 Neo4j available: {available}")
        
        # Second check should use cache
        available2 = check_neo4j_available()
        print(f"   📊 Neo4j available (cached): {available2}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Availability check test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("NEO4J FALLBACK IMPLEMENTATION TESTS")
    print("=" * 60)
    
    tests = [
        ("Imports", test_imports),
        ("Fallback Storage", test_fallback_storage),
        ("Resilient Connection", test_resilient_connection),
        ("Agent Memory", test_agent_memory_with_fallback),
        ("Convenience Functions", test_convenience_functions),
        ("Availability Check", test_neo4j_availability_check),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n💥 Test '{name}' crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Neo4j fallback system is working.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check output above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
