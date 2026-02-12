#!/bin/bash
# Railway Neo4j Networking Diagnostic Script
# Purpose: Troubleshoot IPv6 resolution but port connection timeout issues
# Usage: chmod +x railway-network-debug.sh && ./railway-network-debug.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}    Railway Neo4j Networking Diagnostic Tool${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# ============================================================
# SECTION 1: Railway Environment Variables
# ============================================================
echo -e "${YELLOW}[1/7] Collecting Railway Environment Variables...${NC}"
echo "-----------------------------------------------------------"

# Core Railway variables
echo -e "${BLUE}Core Railway Environment:${NC}"
env | grep -E "^RAILWAY_" | sort || echo "No RAILWAY_* variables found"

echo ""
echo -e "${BLUE}Service-specific variables:${NC}"
env | grep -iE "(NEO4J|BOLT|GRAPH)" | sort || echo "No Neo4j-related variables found"

echo ""
echo -e "${BLUE}Network-related variables:${NC}"
env | grep -E "(HOST|PORT|URL|ADDRESS)" | sort || echo "No network variables found"

echo ""
echo -e "${BLUE}Container network info:${NC}"
echo "Hostname: $(hostname)"
echo "IP Addresses:"
ip addr 2>/dev/null || ifconfig 2>/dev/null || echo "No ip/ifconfig available"

echo ""
echo -e "${BLUE}/etc/resolv.conf contents:${NC}"
cat /etc/resolv.conf 2>/dev/null || echo "Cannot read resolv.conf"

echo ""
echo -e "${BLUE}/etc/hosts contents:${NC}"
cat /etc/hosts 2>/dev/null || echo "Cannot read hosts file"

echo ""

# ============================================================
# SECTION 2: DNS Resolution Tests
# ============================================================
echo -e "${YELLOW}[2/7] Testing DNS Resolution...${NC}"
echo "-----------------------------------------------------------"

TARGET_HOSTS=(
    "neo4j.railway.internal"
    "neo4j"
    "neo4j-neo4j.railway.internal"
    "${RAILWAY_SERVICE_NAME:-neo4j}.railway.internal"
    "railway.internal"
)

for host in "${TARGET_HOSTS[@]}"; do
    echo -e "${BLUE}Resolving: $host${NC}"
    
    # Try different resolution methods
    echo "  nslookup:"
    nslookup "$host" 2>&1 | head -5 || echo "    nslookup failed"
    
    echo "  dig:"
    dig +short "$host" 2>&1 | head -5 || echo "    dig not available"
    
    echo "  getent hosts:"
    getent hosts "$host" 2>&1 | head -3 || echo "    getent failed"
    
    echo "  ping -c1 (timeout 5s):"
    timeout 5 ping -c1 "$host" 2>&1 | head -3 || echo "    ping timeout/failed"
    echo ""
done

echo ""

# ============================================================
# SECTION 3: IPv6 Connectivity Tests
# ============================================================
echo -e "${YELLOW}[3/7] Testing IPv6 Connectivity...${NC}"
echo "-----------------------------------------------------------"

# Check if IPv6 is enabled
echo -e "${BLUE}IPv6 Kernel Support:${NC}"
cat /proc/sys/net/ipv6/conf/all/disable_ipv6 2>/dev/null && echo "IPv6 disabled in kernel" || echo "IPv6 appears enabled"

echo ""
echo -e "${BLUE}IPv6 Addresses on interfaces:${NC}"
ip -6 addr 2>/dev/null || echo "No IPv6 addresses or ip command unavailable"

echo ""
echo -e "${BLUE}IPv6 Route table:${NC}"
ip -6 route 2>/dev/null || echo "No IPv6 routes or ip command unavailable"

echo ""
echo -e "${BLUE}Testing IPv6 connectivity to localhost:${NC}"
timeout 3 bash -c 'echo > /dev/tcp/::1/7687' 2>&1 && echo "IPv6 localhost port 7687: OPEN" || echo "IPv6 localhost port 7687: CLOSED/TIMEOUT"

echo ""

# ============================================================
# SECTION 4: Port Connectivity Tests
# ============================================================
echo -e "${YELLOW}[4/7] Testing Port Connectivity...${NC}"
echo "-----------------------------------------------------------"

# Get the resolved IP for neo4j.railway.internal
NEO4J_IP=$(getent hosts neo4j.railway.internal 2>/dev/null | awk '{print $1}' | head -1)

if [ -n "$NEO4J_IP" ]; then
    echo -e "${BLUE}Resolved neo4j.railway.internal to: $NEO4J_IP${NC}"
    
    # Test common Neo4j ports
    NEO4J_PORTS=(7474 7687 7473 6362)
    
    for port in "${NEO4J_PORTS[@]}"; do
        echo ""
        echo -e "${BLUE}Testing port $port on $NEO4J_IP:${NC}"
        
        # Test with timeout using bash
        echo -n "  Bash /dev/tcp test: "
        if timeout 5 bash -c "echo > /dev/tcp/$NEO4J_IP/$port" 2>/dev/null; then
            echo -e "${GREEN}OPEN${NC}"
        else
            echo -e "${RED}TIMEOUT/CLOSED${NC}"
        fi
        
        # Test with netcat if available
        if command -v nc &> /dev/null; then
            echo -n "  netcat test: "
            if timeout 5 nc -zv "$NEO4J_IP" "$port" 2>&1 | grep -q succeeded; then
                echo -e "${GREEN}OPEN${NC}"
            else
                echo -e "${RED}TIMEOUT/CLOSED${NC}"
            fi
        fi
        
        # Test with curl for HTTP ports
        if [ "$port" = "7474" ] || [ "$port" = "7473" ]; then
            echo -n "  curl test: "
            if timeout 5 curl -s "http://$NEO4J_IP:$port" > /dev/null 2>&1; then
                echo -e "${GREEN}HTTP RESPONDS${NC}"
            else
                echo -e "${RED}NO HTTP RESPONSE${NC}"
            fi
        fi
    done
else
    echo -e "${RED}Could not resolve neo4j.railway.internal${NC}"
fi

echo ""

# ============================================================
# SECTION 5: Alternative Connection Methods
# ============================================================
echo -e "${YELLOW}[5/7] Testing Alternative Connection Methods...${NC}"
echo "-----------------------------------------------------------"

# Try connecting via Railway's internal URL pattern
echo -e "${BLUE}Alternative hostnames to try:${NC}"
ALT_HOSTS=(
    "neo4j.railway.app"
    "${RAILWAY_SERVICE_NAME:-neo4j}.railway.app"
    "neo4j"
    "neo4j-service"
    "neo4j-svc"
    "localhost"
    "127.0.0.1"
    "::1"
    "0.0.0.0"
)

for host in "${ALT_HOSTS[@]}"; do
    echo ""
    echo -e "${BLUE}Testing $host:7687${NC}"
    
    # Get IP
    ALT_IP=$(getent hosts "$host" 2>/dev/null | awk '{print $1}' | head -1)
    if [ -n "$ALT_IP" ]; then
        echo "  Resolves to: $ALT_IP"
        echo -n "  Port 7687: "
        if timeout 3 bash -c "echo > /dev/tcp/$ALT_IP/7687" 2>/dev/null; then
            echo -e "${GREEN}OPEN${NC}"
        else
            echo -e "${RED}TIMEOUT/CLOSED${NC}"
        fi
    else
        echo "  Does not resolve"
    fi
done

echo ""

# ============================================================
# SECTION 6: Network Stack Inspection
# ============================================================
echo -e "${YELLOW}[6/7] Network Stack Inspection...${NC}"
echo "-----------------------------------------------------------"

echo -e "${BLUE}Network namespaces:${NC}"
ls -la /proc/self/ns/ 2>/dev/null || echo "Cannot access network namespaces"

echo ""
echo -e "${BLUE}Active connections:${NC}"
netstat -tlnp 2>/dev/null || ss -tlnp 2>/dev/null || echo "No netstat/ss available"

echo ""
echo -e "${BLUE}IPTables rules (if available):${NC}"
iptables -L 2>/dev/null | head -20 || echo "Cannot check iptables"

echo ""
echo -e "${BLUE}Kernel network parameters:${NC}"
sysctl net.ipv6 2>/dev/null | head -10 || echo "Cannot check sysctl"

echo ""
echo -e "${BLUE}Container network interfaces:${NC}"
cat /proc/net/dev 2>/dev/null || echo "Cannot read /proc/net/dev"

echo ""

# ============================================================
# SECTION 7: Railway-Specific Checks
# ============================================================
echo -e "${YELLOW}[7/7] Railway-Specific Diagnostics...${NC}"
echo "-----------------------------------------------------------"

# Check if we have Railway's internal metadata
echo -e "${BLUE}Railway metadata (if available):${NC}"
curl -s "http://metadata.google.internal/computeMetadata/v1/instance/" -H "Metadata-Flavor: Google" 2>/dev/null | head -10 || echo "Google metadata not available (expected on Railway)"

echo ""
echo -e "${BLUE}Railway-specific environment analysis:${NC}"
echo "RAILWAY_SERVICE_NAME: ${RAILWAY_SERVICE_NAME:-NOT SET}"
echo "RAILWAY_PROJECT_NAME: ${RAILWAY_PROJECT_NAME:-NOT SET}"
echo "RAILWAY_ENVIRONMENT_NAME: ${RAILWAY_ENVIRONMENT_NAME:-NOT SET}"
echo "RAILWAY_SERVICE_ID: ${RAILWAY_SERVICE_ID:-NOT SET}"

# Check for Railway's internal networking docs pattern
echo ""
echo -e "${BLUE}Suggested Railway connection strings:${NC}"
echo "  Bolt: bolt://neo4j:7687 (if in same compose/network)"
echo "  Bolt: bolt://neo4j.railway.internal:7687 (via internal DNS)"
echo "  HTTP: http://neo4j.railway.internal:7474"

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Diagnostic Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "Summary recommendations:"
echo "  1. If DNS resolves but connection times out, check if Neo4j is listening on IPv6"
echo "  2. Try connecting via IPv4 if available (check NEO4J_dbms_default__listen__address)"
echo "  3. Verify Neo4j is configured to accept connections on 0.0.0.0 or specific interfaces"
echo "  4. Check Railway service logs for Neo4j startup errors"
echo ""
