#!/bin/bash
# Neo4j IPv6 Wrapper Script
# 
# This script wraps Neo4j startup to ensure it listens on both IPv4 and IPv6.
# Use this if you cannot modify the Railway dashboard variables directly.
#
# Usage: Add to your Dockerfile or as a pre-start command:
#   CMD ["./scripts/neo4j-ipv6-wrapper.sh", "original", "command"]

set -e

echo "[neo4j-ipv6-wrapper] Starting with IPv6 compatibility..."

# =============================================================================
# Option 1: Environment Variable Injection (preferred)
# =============================================================================

# Set the critical environment variable if not already set
if [ -z "$NEO4J_dbms_default__listen__address" ]; then
    export NEO4J_dbms_default__listen__address="::"
    echo "[neo4j-ipv6-wrapper] Set NEO4J_dbms_default__listen__address=::"
else
    echo "[neo4j-ipv6-wrapper] NEO4J_dbms_default__listen__address already set: $NEO4J_dbms_default__listen__address"
fi

# Also set specific connector addresses for redundancy
export NEO4J_dbms_connector_bolt_listen__address="::"
export NEO4J_dbms_connector_http_listen__address="::"
export NEO4J_dbms_connector_https_listen__address="::"

echo "[neo4j-ipv6-wrapper] Bolt connector: $NEO4J_dbms_connector_bolt_listen__address"
echo "[neo4j-ipv6-wrapper] HTTP connector: $NEO4J_dbms_connector_http_listen__address"

# =============================================================================
# Option 2: Runtime Configuration File Modification (fallback)
# =============================================================================

# Function to update neo4j.conf if we have write access
update_neo4j_conf() {
    local CONF_FILE="$1"
    
    if [ -f "$CONF_FILE" ] && [ -w "$CONF_FILE" ]; then
        echo "[neo4j-ipv6-wrapper] Updating $CONF_FILE..."
        
        # Backup original
        cp "$CONF_FILE" "$CONF_FILE.backup.$(date +%s)" 2>/dev/null || true
        
        # Update or add listen address configuration
        if grep -q "^dbms.default_listen_address" "$CONF_FILE"; then
            # Replace existing setting
            sed -i 's/^dbms.default_listen_address=.*/dbms.default_listen_address=::/' "$CONF_FILE"
        else
            # Add new setting
            echo "dbms.default_listen_address=::" >> "$CONF_FILE"
        fi
        
        # Also update connector-specific settings
        for connector in bolt http https; do
            setting="dbms.connector.${connector}.listen_address"
            if grep -q "^$setting" "$CONF_FILE"; then
                sed -i "s/^$setting=.*/$setting=::$connector_port/" "$CONF_FILE"
            fi
        done
        
        echo "[neo4j-ipv6-wrapper] Updated $CONF_FILE"
    fi
}

# Try common config file locations
update_neo4j_conf "/var/lib/neo4j/conf/neo4j.conf"
update_neo4j_conf "/etc/neo4j/neo4j.conf"
update_neo4j_conf "/usr/share/neo4j/conf/neo4j.conf"

# =============================================================================
# Option 3: /etc/hosts Workaround (last resort)
# =============================================================================

# If we need to force IPv4 resolution, we can add entries to /etc/hosts
# This is commented out by default as it's usually not needed with the above fixes
# 
# if [ -w "/etc/hosts" ]; then
#     echo "127.0.0.1 neo4j neo4j.railway.internal" >> /etc/hosts
#     echo "[neo4j-ipv6-wrapper] Added /etc/hosts entries"
# fi

# =============================================================================
# Execute Original Command
# =============================================================================

echo "[neo4j-ipv6-wrapper] Environment prepared, executing command: $@"
echo "[neo4j-ipv6-wrapper] ================================================="

# If no arguments provided, start Neo4j directly
if [ $# -eq 0 ]; then
    echo "[neo4j-ipv6-wrapper] No command specified, starting Neo4j..."
    
    # Try different Neo4j start methods
    if command -v neo4j &> /dev/null; then
        exec neo4j console
    elif [ -f "/var/lib/neo4j/bin/neo4j" ]; then
        exec /var/lib/neo4j/bin/neo4j console
    elif [ -f "/usr/bin/neo4j" ]; then
        exec /usr/bin/neo4j console
    else
        echo "[neo4j-ipv6-wrapper] ERROR: Could not find Neo4j start command"
        exit 1
    fi
else
    # Execute the provided command
    exec "$@"
fi
