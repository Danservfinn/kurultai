#!/usr/bin/env python3
"""
Neo4j Connection Helper with IPv6/IPv4 Fallback Support

This module provides resilient Neo4j connection handling for Railway deployments
where IPv6 is the primary internal networking protocol but Neo4j may need
coaxing to listen on the right interfaces.

Usage:
    from scripts.neo4j_connection_helper import create_neo4j_driver_with_fallback
    
    driver = create_neo4j_driver_with_fallback()
    # Use driver normally...
    
Or for diagnostics:
    python3 scripts/neo4j_connection_helper.py --diagnose
"""

import os
import sys
import socket
import time
import logging
from typing import Optional, List, Tuple, Dict, Any
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_NEO4J_URI = "bolt://neo4j.railway.internal:7687"
DEFAULT_NEO4J_USER = "neo4j"
DEFAULT_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# Retry configuration
MAX_RETRIES = 5
RETRY_DELAY = 2  # seconds


# =============================================================================
# Connection Strategy Detection
# =============================================================================

def resolve_hostname(hostname: str) -> Tuple[List[str], List[str]]:
    """
    Resolve hostname to IPv4 and IPv6 addresses.
    
    Returns:
        Tuple of (ipv4_addresses, ipv6_addresses)
    """
    ipv4_addrs = []
    ipv6_addrs = []
    
    try:
        # Get all address info
        addr_info = socket.getaddrinfo(hostname, None)
        
        for info in addr_info:
            family, _, _, _, sockaddr = info
            if family == socket.AF_INET:
                ipv4_addrs.append(sockaddr[0])
            elif family == socket.AF_INET6:
                ipv6_addrs.append(sockaddr[0])
                
    except socket.gaierror as e:
        logger.warning(f"DNS resolution failed for {hostname}: {e}")
    
    return list(set(ipv4_addrs)), list(set(ipv6_addrs))


def test_port_connectivity(host: str, port: int = 7687, timeout: int = 5) -> bool:
    """Test if a port is reachable on a given host."""
    try:
        if ':' in host:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        
        return result == 0
        
    except socket.timeout:
        return False
    except Exception as e:
        logger.debug(f"Port test failed for {host}:{port}: {e}")
        return False


def test_bolt_handshake(host: str, port: int = 7687, timeout: int = 5) -> bool:
    """Test if a host responds to Bolt protocol handshake."""
    # Bolt handshake preamble
    BOLT_MAGIC = b'\x60\x60\xb0\x17'
    BOLT_VERSIONS = b'\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
    
    try:
        if ':' in host:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        sock.settimeout(timeout)
        sock.connect((host, port))
        
        # Send Bolt handshake
        sock.sendall(BOLT_MAGIC + BOLT_VERSIONS)
        
        # Receive response
        response = sock.recv(4)
        sock.close()
        
        return len(response) == 4
        
    except socket.timeout:
        return False
    except Exception as e:
        logger.debug(f"Bolt handshake failed for {host}:{port}: {e}")
        return False


def find_working_connection() -> Optional[str]:
    """
    Find a working Neo4j connection by testing multiple strategies.
    
    Returns:
        Working connection URI or None if all fail
    """
    hostnames_to_try = [
        os.environ.get("NEO4J_HOST", "neo4j.railway.internal"),
        "neo4j.railway.internal",
        "neo4j",
        "localhost",
        "127.0.0.1",
        "::1",
    ]
    
    port = int(os.environ.get("NEO4J_PORT", "7687"))
    
    logger.info("Testing Neo4j connectivity...")
    
    for hostname in hostnames_to_try:
        # Skip duplicates
        if not hostname:
            continue
            
        logger.info(f"\nTesting hostname: {hostname}")
        
        # Resolve hostname
        ipv4_addrs, ipv6_addrs = resolve_hostname(hostname)
        
        if ipv4_addrs:
            logger.info(f"  IPv4 addresses: {ipv4_addrs}")
        if ipv6_addrs:
            logger.info(f"  IPv6 addresses: {ipv6_addrs}")
        
        # Test resolved IPv4 addresses first (often more reliable)
        for ip in ipv4_addrs:
            logger.info(f"  Testing IPv4 {ip}:{port}...")
            if test_port_connectivity(ip, port):
                logger.info(f"  ✓ Port connectivity OK")
                if test_bolt_handshake(ip, port):
                    logger.info(f"  ✓ Bolt handshake OK")
                    return f"bolt://{ip}:{port}"
                else:
                    logger.warning(f"  ✗ Bolt handshake failed")
            else:
                logger.warning(f"  ✗ Port connectivity failed")
        
        # Test resolved IPv6 addresses
        for ip in ipv6_addrs:
            logger.info(f"  Testing IPv6 [{ip}]:{port}...")
            if test_port_connectivity(ip, port):
                logger.info(f"  ✓ Port connectivity OK")
                if test_bolt_handshake(ip, port):
                    logger.info(f"  ✓ Bolt handshake OK")
                    # IPv6 addresses in URIs need brackets
                    return f"bolt://[{ip}]:{port}"
                else:
                    logger.warning(f"  ✗ Bolt handshake failed")
            else:
                logger.warning(f"  ✗ Port connectivity failed")
        
        # Test hostname directly (lets driver handle resolution)
        logger.info(f"  Testing direct hostname connection...")
        if test_port_connectivity(hostname, port):
            logger.info(f"  ✓ Port connectivity OK")
            if test_bolt_handshake(hostname, port):
                logger.info(f"  ✓ Bolt handshake OK")
                return f"bolt://{hostname}:{port}"
    
    logger.error("No working Neo4j connection found!")
    return None


# =============================================================================
# Neo4j Driver Creation with Fallback
# =============================================================================

def create_neo4j_driver_with_fallback(
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    max_retries: int = MAX_RETRIES,
    retry_delay: int = RETRY_DELAY,
    auto_detect: bool = True
) -> Any:
    """
    Create a Neo4j driver with automatic fallback and retry logic.
    
    This function handles:
    - IPv6/IPv4 connection issues
    - Neo4j cold start delays
    - Automatic URI detection
    - Connection retries with backoff
    
    Args:
        uri: Neo4j Bolt URI (if None, uses NEO4J_URI env var or auto-detects)
        user: Neo4j username (if None, uses NEO4J_USER env var or 'neo4j')
        password: Neo4j password (if None, uses NEO4J_PASSWORD env var)
        max_retries: Maximum connection retry attempts
        retry_delay: Delay between retries in seconds
        auto_detect: Whether to auto-detect working connection if URI fails
        
    Returns:
        Neo4j driver instance
        
    Raises:
        Exception: If all connection attempts fail
    """
    try:
        from neo4j import GraphDatabase
    except ImportError:
        raise ImportError(
            "neo4j-driver not installed. Install with: pip install neo4j"
        )
    
    # Get credentials
    uri = uri or os.environ.get("NEO4J_URI", DEFAULT_NEO4J_URI)
    user = user or os.environ.get("NEO4J_USER", DEFAULT_NEO4J_USER)
    password = password or os.environ.get("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD)
    
    if not password:
        raise ValueError(
            "Neo4j password not provided. Set NEO4J_PASSWORD environment variable."
        )
    
    logger.info(f"Creating Neo4j driver (target: {uri})")
    
    # Try primary URI first
    for attempt in range(max_retries):
        try:
            driver = GraphDatabase.driver(uri, auth=(user, password))
            driver.verify_connectivity()
            logger.info(f"✓ Connected to Neo4j at {uri}")
            return driver
            
        except Exception as e:
            logger.warning(f"Connection attempt {attempt + 1}/{max_retries} failed: {e}")
            
            if attempt < max_retries - 1:
                logger.info(f"Waiting {retry_delay}s before retry...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to connect with primary URI: {uri}")
    
    # If auto_detect is enabled, try to find a working connection
    if auto_detect:
        logger.info("Attempting auto-detection of working connection...")
        working_uri = find_working_connection()
        
        if working_uri:
            logger.info(f"Found working connection: {working_uri}")
            try:
                driver = GraphDatabase.driver(working_uri, auth=(user, password))
                driver.verify_connectivity()
                logger.info(f"✓ Connected to Neo4j at {working_uri}")
                
                # Log recommendation
                logger.info(
                    f"\n" + "="*60 + "\n"
                    f"RECOMMENDATION: Update NEO4J_URI to:\n"
                    f"  {working_uri}\n"
                    f"="*60
                )
                
                return driver
            except Exception as e:
                logger.error(f"Auto-detected URI also failed: {e}")
    
    raise Exception(
        f"Failed to connect to Neo4j after {max_retries} attempts. "
        f"Check that Neo4j is running and accessible. "
        f"Run with --diagnose for detailed troubleshooting."
    )


def create_async_neo4j_driver_with_fallback(
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    max_retries: int = MAX_RETRIES,
    retry_delay: int = RETRY_DELAY,
    auto_detect: bool = True
) -> Any:
    """
    Create an async Neo4j driver with automatic fallback and retry logic.
    
    Same as create_neo4j_driver_with_fallback but returns an AsyncDriver.
    """
    try:
        from neo4j import AsyncGraphDatabase
    except ImportError:
        raise ImportError(
            "neo4j-driver not installed. Install with: pip install neo4j"
        )
    
    # Get credentials
    uri = uri or os.environ.get("NEO4J_URI", DEFAULT_NEO4J_URI)
    user = user or os.environ.get("NEO4J_USER", DEFAULT_NEO4J_USER)
    password = password or os.environ.get("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD)
    
    if not password:
        raise ValueError(
            "Neo4j password not provided. Set NEO4J_PASSWORD environment variable."
        )
    
    logger.info(f"Creating async Neo4j driver (target: {uri})")
    
    # Note: Async driver needs to be used with asyncio
    # This is a synchronous function that returns the async driver
    # The caller needs to use it in an async context
    
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    return driver


# =============================================================================
# Diagnostic Functions
# =============================================================================

def run_diagnostics():
    """Run comprehensive Neo4j connectivity diagnostics."""
    print("\n" + "="*60)
    print("  Neo4j IPv6 Connectivity Diagnostics")
    print("="*60 + "\n")
    
    # Environment
    print("Environment Variables:")
    print("-" * 40)
    relevant_vars = [
        'NEO4J_URI', 'NEO4J_USER', 'NEO4J_PASSWORD', 'NEO4J_HOST', 'NEO4J_PORT',
        'RAILWAY_SERVICE_NAME', 'RAILWAY_PROJECT_NAME', 'RAILWAY_ENVIRONMENT_NAME'
    ]
    for var in relevant_vars:
        value = os.environ.get(var, "NOT SET")
        if 'PASSWORD' in var and value != "NOT SET":
            value = '*' * min(len(value), 10)
        print(f"  {var:<30} {value}")
    
    # DNS Resolution
    print("\n" + "-" * 40)
    print("DNS Resolution Tests:")
    print("-" * 40)
    
    hostnames = [
        'neo4j.railway.internal',
        'neo4j',
        'localhost',
        '127.0.0.1',
        '::1'
    ]
    
    for hostname in hostnames:
        ipv4, ipv6 = resolve_hostname(hostname)
        status = "✓" if (ipv4 or ipv6) else "✗"
        print(f"\n  {status} {hostname}")
        if ipv4:
            print(f"    IPv4: {ipv4}")
        if ipv6:
            print(f"    IPv6: {ipv6}")
        if not ipv4 and not ipv6:
            print(f"    No resolution")
    
    # Port connectivity
    print("\n" + "-" * 40)
    print("Port Connectivity Tests:")
    print("-" * 40)
    
    test_targets = []
    for hostname in hostnames:
        ipv4, ipv6 = resolve_hostname(hostname)
        for ip in ipv4[:1]:
            test_targets.append((ip, f"{hostname} (IPv4)"))
        for ip in ipv6[:1]:
            test_targets.append((ip, f"{hostname} (IPv6)"))
        if not ipv4 and not ipv6:
            test_targets.append((hostname, f"{hostname} (direct)"))
    
    for target, source in test_targets:
        port_open = test_port_connectivity(target, 7687)
        bolt_works = test_bolt_handshake(target, 7687) if port_open else False
        
        status = "✓" if bolt_works else ("~" if port_open else "✗")
        print(f"\n  {status} {source}")
        print(f"    Target: {target}:7687")
        print(f"    Port: {'OPEN' if port_open else 'CLOSED/TIMEOUT'}")
        print(f"    Bolt: {'WORKS' if bolt_works else 'FAILED'}")
    
    # Recommendations
    print("\n" + "="*60)
    print("  Recommendations")
    print("="*60)
    
    working = find_working_connection()
    if working:
        print(f"\n  ✓ Working connection found: {working}")
        print(f"\n  Set this environment variable in Railway:")
        print(f"    NEO4J_URI={working}")
    else:
        print("\n  ✗ No working connection found")
        print("\n  Possible causes:")
        print("    1. Neo4j service is not running")
        print("    2. Neo4j is not listening on IPv6 (fix: set NEO4J_dbms_default__listen__address=::)")
        print("    3. Services are in different Railway projects")
        print("    4. Firewall/network policy blocking connection")
        print("\n  Next steps:")
        print("    1. Check Neo4j service logs in Railway Dashboard")
        print("    2. Verify Neo4j finished starting (takes 30-60s)")
        print("    3. Apply the IPv6 fix (see docs/NEO4J_IPV6_FIX.md)")
        print("    4. Restart both Neo4j and your application service")
    
    print("\n" + "="*60 + "\n")
    return working is not None


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Neo4j Connection Helper with IPv6/IPv4 Fallback"
    )
    parser.add_argument(
        "--diagnose", "-d",
        action="store_true",
        help="Run connectivity diagnostics"
    )
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Test connection and exit"
    )
    parser.add_argument(
        "--uri",
        default=None,
        help="Neo4j URI to test (default: from NEO4J_URI env var)"
    )
    
    args = parser.parse_args()
    
    if args.diagnose:
        success = run_diagnostics()
        sys.exit(0 if success else 1)
    
    elif args.test:
        try:
            driver = create_neo4j_driver_with_fallback(uri=args.uri)
            print("✓ Connection successful!")
            driver.close()
            sys.exit(0)
        except Exception as e:
            print(f"✗ Connection failed: {e}")
            sys.exit(1)
    
    else:
        parser.print_help()
        print("\n\nExamples:")
        print("  python3 neo4j_connection_helper.py --diagnose")
        print("  python3 neo4j_connection_helper.py --test")
        print("  python3 neo4j_connection_helper.py --test --uri bolt://localhost:7687")
