#!/usr/bin/env python3
"""
Railway Neo4j IPv6 Connection Troubleshooter
Diagnoses the specific issue: DNS resolves to IPv6 but port connection times out
"""

import socket
import sys
import os
import subprocess
import json
from urllib.parse import urlparse

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_info(label, value):
    print(f"  {label:<30} {value}")

def print_error(msg):
    print(f"  ❌ {msg}")

def print_success(msg):
    print(f"  ✅ {msg}")

def print_warning(msg):
    print(f"  ⚠️  {msg}")

def get_railway_env():
    """Collect all Railway-related environment variables"""
    railway_vars = {}
    for key, value in os.environ.items():
        if key.startswith('RAILWAY_') or 'NEO4J' in key or 'BOLT' in key:
            railway_vars[key] = value
    return railway_vars

def test_dns_resolution(hostname):
    """Test DNS resolution with detailed output"""
    print(f"\n  Testing resolution for: {hostname}")
    
    try:
        # Get all address info
        addr_info = socket.getaddrinfo(hostname, None)
        
        ipv4_addrs = []
        ipv6_addrs = []
        
        for info in addr_info:
            family, socktype, proto, canonname, sockaddr = info
            if family == socket.AF_INET:
                ipv4_addrs.append(sockaddr[0])
            elif family == socket.AF_INET6:
                ipv6_addrs.append(sockaddr[0])
        
        if ipv4_addrs:
            print_success(f"IPv4: {', '.join(set(ipv4_addrs))}")
        else:
            print_warning("No IPv4 addresses found")
            
        if ipv6_addrs:
            print_success(f"IPv6: {', '.join(set(ipv6_addrs))}")
        else:
            print_warning("No IPv6 addresses found")
            
        return ipv4_addrs, ipv6_addrs
        
    except socket.gaierror as e:
        print_error(f"DNS resolution failed: {e}")
        return [], []

def test_port_connectivity(host, port, timeout=5):
    """Test if a port is reachable on a given host"""
    print(f"\n  Testing {host}:{port}")
    
    try:
        # Create socket with appropriate family
        if ':' in host:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print_success(f"Port {port} is OPEN")
            return True
        else:
            print_error(f"Port {port} is CLOSED/REFUSED (error: {result})")
            return False
            
    except socket.timeout:
        print_error(f"Connection TIMEOUT after {timeout}s")
        return False
    except Exception as e:
        print_error(f"Connection failed: {e}")
        return False

def test_bolt_handshake(host, port=7687, timeout=5):
    """Test if a host responds to Bolt protocol handshake"""
    print(f"\n  Testing Bolt handshake on {host}:{port}")
    
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
        
        if len(response) == 4:
            print_success(f"Bolt handshake successful! Server version: {response.hex()}")
            return True
        else:
            print_warning(f"Unexpected response length: {len(response)}")
            return False
            
    except socket.timeout:
        print_error("Bolt handshake TIMEOUT")
        return False
    except Exception as e:
        print_error(f"Bolt handshake failed: {e}")
        return False

def check_neo4j_config():
    """Check if we can find Neo4j configuration"""
    print_section("Neo4j Configuration Analysis")
    
    config_paths = [
        '/var/lib/neo4j/conf/neo4j.conf',
        '/etc/neo4j/neo4j.conf',
        '/usr/share/neo4j/conf/neo4j.conf',
        'neo4j.conf',
    ]
    
    for path in config_paths:
        if os.path.exists(path):
            print_success(f"Found config: {path}")
            try:
                with open(path, 'r') as f:
                    content = f.read()
                    
                # Check listen addresses
                for line in content.split('\n'):
                    if 'listen_address' in line and not line.strip().startswith('#'):
                        print_info("Config", line.strip())
                        
                    if 'dbms.default_listen_address' in line:
                        if '127.0.0.1' in line or 'localhost' in line:
                            print_error(f"Neo4j only listening on localhost: {line.strip()}")
                            print("  → This prevents external connections!")
                            
            except Exception as e:
                print_error(f"Cannot read config: {e}")
            return
    
    print_warning("No Neo4j config file found in standard locations")

def suggest_workarounds(ipv4_addrs, ipv6_addrs, diagnosis):
    """Suggest workarounds based on diagnosis"""
    print_section("RECOMMENDED WORKAROUNDS")
    
    print("\n  🔧 IMMEDIATE FIXES:")
    print("  " + "-"*56)
    
    if not ipv4_addrs and ipv6_addrs:
        print("\n  1. IPv6-ONLY ENVIRONMENT DETECTED")
        print("     → Ensure Neo4j is configured to listen on IPv6:")
        print("       dbms.default_listen_address=::")
        print("       Or set environment variable:")
        print("       NEO4J_dbms_default__listen__address=::")
        
    if diagnosis.get('dns_works') and not diagnosis.get('port_works'):
        print("\n  2. DNS WORKS BUT PORT UNREACHABLE")
        print("     → Neo4j may not be accepting external connections")
        print("     → Check Neo4j is running: ps aux | grep neo4j")
        print("     → Check Neo4j logs for startup errors")
        print("     → Verify Neo4j is listening on 0.0.0.0 or ::")
        
    print("\n  🔧 ENVIRONMENT VARIABLE WORKAROUNDS:")
    print("  " + "-"*56)
    
    # Neo4j connection strings
    print("\n  For your application, try these connection strings:")
    
    if ipv4_addrs:
        for ip in ipv4_addrs[:1]:
            print(f"    bolt://{ip}:7687")
    if ipv6_addrs:
        for ip in ipv6_addrs[:1]:
            print(f"    bolt://[{ip}]:7687")
    
    print("\n  Railway-specific variables to set:")
    print("    NEO4J_URI=bolt://neo4j.railway.internal:7687")
    print("    NEO4J_AUTH=neo4j/password")
    
    if not diagnosis.get('port_works'):
        print("\n  ⚠️  If Neo4j isn't accepting connections:")
        print("    Check Railway Dashboard → Neo4j service → Logs")
        print("    Ensure Neo4j finished startup (can take 30-60s)")
        print("    Restart both services if needed")

def main():
    print("\n" + "="*60)
    print("  Railway Neo4j IPv6 Troubleshooter")
    print("="*60)
    
    diagnosis = {
        'dns_works': False,
        'port_works': False,
        'bolt_works': False
    }
    
    # Section 1: Environment
    print_section("Railway Environment Variables")
    env_vars = get_railway_env()
    if env_vars:
        for key, value in env_vars.items():
            # Mask sensitive values
            if 'PASSWORD' in key or 'AUTH' in key or 'SECRET' in key:
                value = '*' * min(len(value), 10)
            print_info(key, value)
    else:
        print_warning("No Railway/Neo4j environment variables found")
    
    # Section 2: DNS Resolution
    print_section("DNS Resolution Tests")
    
    test_hosts = [
        'neo4j.railway.internal',
        os.environ.get('RAILWAY_SERVICE_NAME', 'neo4j') + '.railway.internal',
        'neo4j',
        'localhost',
    ]
    
    all_ipv4 = []
    all_ipv6 = []
    
    for host in test_hosts:
        ipv4, ipv6 = test_dns_resolution(host)
        all_ipv4.extend(ipv4)
        all_ipv6.extend(ipv6)
        if ipv4 or ipv6:
            diagnosis['dns_works'] = True
    
    all_ipv4 = list(set(all_ipv4))
    all_ipv6 = list(set(all_ipv6))
    
    # Section 3: Port Connectivity
    print_section("Port Connectivity Tests")
    
    # Test with resolved IPs
    test_targets = []
    
    # Add resolved IPs
    for ip in all_ipv4[:2]:
        test_targets.append((ip, 'IPv4 resolved'))
    for ip in all_ipv6[:2]:
        test_targets.append((ip, 'IPv6 resolved'))
    
    # Add hostnames for direct testing
    test_targets.extend([
        ('neo4j.railway.internal', 'hostname'),
        ('127.0.0.1', 'localhost IPv4'),
    ])
    
    for target, source in test_targets:
        if test_port_connectivity(target, 7687):
            diagnosis['port_works'] = True
            # Test Bolt handshake on working connections
            if test_bolt_handshake(target, 7687):
                diagnosis['bolt_works'] = True
    
    # Section 4: Config Analysis
    check_neo4j_config()
    
    # Section 5: Summary
    print_section("DIAGNOSIS SUMMARY")
    
    print_info("DNS Resolution", "✅ WORKS" if diagnosis['dns_works'] else "❌ FAILS")
    print_info("Port Connectivity", "✅ WORKS" if diagnosis['port_works'] else "❌ FAILS")
    print_info("Bolt Protocol", "✅ WORKS" if diagnosis['bolt_works'] else "❌ FAILS")
    
    print("\n" + "-"*60)
    
    if diagnosis['dns_works'] and not diagnosis['port_works']:
        print("\n  🔴 ROOT CAUSE IDENTIFIED:")
        print("     DNS resolves correctly, but Neo4j is not accepting connections.")
        print("     This is likely a Neo4j configuration issue, not a networking issue.")
        
    elif not diagnosis['dns_works']:
        print("\n  🔴 ROOT CAUSE IDENTIFIED:")
        print("     DNS resolution is failing.")
        print("     Check Railway service names and internal networking setup.")
        
    elif diagnosis['bolt_works']:
        print("\n  🟢 CONNECTION IS WORKING!")
        print("     Use the working connection string from above.")
    
    # Section 6: Workarounds
    suggest_workarounds(all_ipv4, all_ipv6, diagnosis)
    
    print("\n" + "="*60)
    print("  Troubleshooting complete!")
    print("="*60 + "\n")
    
    # Return exit code based on diagnosis
    if diagnosis['bolt_works']:
        return 0
    elif diagnosis['port_works']:
        return 1
    else:
        return 2

if __name__ == '__main__':
    sys.exit(main())
