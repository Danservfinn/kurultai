#!/bin/bash
# Multi-Agent Gemini CLI Setup Script
# Sets up separate Gemini CLI contexts for all 6 Kurultai agents
# 
# Usage: ./setup_agent_gemini.sh
# Rollback: ./setup_agent_gemini.sh --rollback

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/setup_$(date +%Y%m%d_%H%M%S).log"
BACKUP_DIR="$HOME/.gemini-backups/$(date +%Y%m%d_%H%M%S)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}ERROR: $1${NC}" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}✓ $1${NC}" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}⚠ $1${NC}" | tee -a "$LOG_FILE"
}

# Agent definitions
AGENTS=(
    "kublai:Squad Lead:orchestrates tasks and manages workflow"
    "mongke:Researcher:conducts research and analysis"
    "chagatai:Writer:creates content and documentation"
    "temujin:Developer:writes code and handles technical tasks"
    "jochi:Analyst:performs data analysis and debugging"
    "ogedei:Operations:manages infrastructure and deployment"
)

rollback() {
    log "ROLLBACK initiated..."
    
    if [ -d "$BACKUP_DIR" ]; then
        log "Restoring from backup: $BACKUP_DIR"
        
        # Restore main gemini config if backed up
        if [ -f "$BACKUP_DIR/settings.json" ]; then
            cp "$BACKUP_DIR/settings.json" ~/.gemini/
            log "Restored ~/.gemini/settings.json"
        fi
        
        # Remove agent-specific configs
        for agent_info in "${AGENTS[@]}"; do
            IFS=':' read -r agent role desc <<< "$agent_info"
            if [ -d "$HOME/.gemini-$agent" ]; then
                rm -rf "$HOME/.gemini-$agent"
                log "Removed ~/.gemini-$agent"
            fi
            if [ -f "$HOME/.openclaw/agents/$agent/.gemini.json" ]; then
                rm "$HOME/.openclaw/agents/$agent/.gemini.json"
                log "Removed $agent/.gemini.json"
            fi
        done
        
        success "Rollback completed"
        log "Backup preserved at: $BACKUP_DIR"
    else
        error "No backup found at $BACKUP_DIR"
        exit 1
    fi
}

backup_existing() {
    log "Creating backup at: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    
    # Backup main gemini config
    if [ -d "$HOME/.gemini" ]; then
        cp -r "$HOME/.gemini" "$BACKUP_DIR/"
        log "Backed up ~/.gemini"
    fi
    
    # Backup agent workspaces (just gemini configs)
    for agent_info in "${AGENTS[@]}"; do
        IFS=':' read -r agent role desc <<< "$agent_info"
        if [ -f "$HOME/.openclaw/agents/$agent/.gemini.json" ]; then
            mkdir -p "$BACKUP_DIR/agents/$agent"
            cp "$HOME/.openclaw/agents/$agent/.gemini.json" "$BACKUP_DIR/agents/$agent/"
            log "Backed up $agent/.gemini.json"
        fi
    done
    
    success "Backup created at: $BACKUP_DIR"
    log "To rollback, run: $0 --rollback"
}

setup_agent() {
    local agent=$1
    local role=$2
    local description=$3
    
    log "Setting up Gemini CLI for $agent ($role)..."
    
    # Create agent-specific gemini directory
    AGENT_GEMINI="$HOME/.gemini-$agent"
    mkdir -p "$AGENT_GEMINI"
    
    # Copy base settings
    if [ -f "$HOME/.gemini/settings.json" ]; then
        cp "$HOME/.gemini/settings.json" "$AGENT_GEMINI/"
    fi
    
    # Copy oauth credentials (share auth across agents)
    if [ -f "$HOME/.gemini/oauth_creds.json" ]; then
        cp "$HOME/.gemini/oauth_creds.json" "$AGENT_GEMINI/"
    fi
    
    if [ -f "$HOME/.gemini/google_accounts.json" ]; then
        cp "$HOME/.gemini/google_accounts.json" "$AGENT_GEMINI/"
    fi
    
    # Create agent-specific settings with role context
    cat > "$AGENT_GEMINI/settings.json" <<JSONEOF
{
  "security": {
    "auth": {
      "selectedType": "oauth-personal"
    }
  },
  "general": {
    "sessionRetention": {
      "enabled": true,
      "maxAge": "30d",
      "warningAcknowledged": true
    }
  },
  "model": {
    "name": "gemini-3.1-pro-preview"
  },
  "agent": {
    "id": "$agent",
    "role": "$role",
    "description": "$description",
    "workspace": "$HOME/.openclaw/agents/$agent"
  }
}
JSONEOF
    
    # Create .gemini.json in agent workspace
    AGENT_WORKSPACE="$HOME/.openclaw/agents/$agent"
    mkdir -p "$AGENT_WORKSPACE"
    
    cat > "$AGENT_WORKSPACE/.gemini.json" <<JSONEOF
{
  "model": {
    "name": "gemini-3.1-pro-preview"
  },
  "agent": {
    "id": "$agent",
    "role": "$role"
  },
  "workspace": "$AGENT_WORKSPACE"
}
JSONEOF
    
    # Create a wrapper script for easy access
    cat > "$AGENT_GEMINI/gemini-$agent" <<'WRAPPEREOF'
#!/bin/bash
# Gemini CLI wrapper for AGENT_NAME
export GEMINI_HOME="$HOME/.gemini-AGENT_NAME"
cd "$HOME/.openclaw/agents/AGENT_NAME"
exec gemini "$@"
WRAPPEREOF
    
    # Replace placeholder with actual agent name
    sed -i '' "s/AGENT_NAME/$agent/g" "$AGENT_GEMINI/gemini-$agent"
    chmod +x "$AGENT_GEMINI/gemini-$agent"
    
    # Create symlink in /usr/local/bin for easy access
    if [ -d "/usr/local/bin" ]; then
        sudo ln -sf "$AGENT_GEMINI/gemini-$agent" "/usr/local/bin/gemini-$agent" 2>/dev/null || \
        ln -sf "$AGENT_GEMINI/gemini-$agent" "$HOME/.local/bin/gemini-$agent" 2>/dev/null || true
    fi
    
    success "$agent configured"
    log "  Config: ~/.gemini-$agent/"
    log "  Workspace: ~/.openclaw/agents/$agent/.gemini.json"
}

test_agent() {
    local agent=$1
    
    log "Testing $agent's Gemini CLI..."
    
    export GEMINI_HOME="$HOME/.gemini-$agent"
    
    # Quick test
    if gemini -p "Say 'Gemini CLI for $agent is ready'" 2>&1 | grep -q "ready"; then
        success "$agent test passed"
        return 0
    else
        warning "$agent test may have issues (check manually)"
        return 1
    fi
}

verify_setup() {
    log "Verifying setup..."
    
    local passed=0
    local failed=0
    
    for agent_info in "${AGENTS[@]}"; do
        IFS=':' read -r agent role desc <<< "$agent_info"
        
        if [ -d "$HOME/.gemini-$agent" ] && [ -f "$HOME/.gemini-$agent/settings.json" ]; then
            ((passed++))
        else
            ((failed++))
            error "$agent configuration incomplete"
        fi
    done
    
    log "Verification: $passed passed, $failed failed"
    
    if [ $failed -eq 0 ]; then
        success "All agents configured successfully!"
        return 0
    else
        error "Some agents failed configuration"
        return 1
    fi
}

print_summary() {
    echo ""
    echo "========================================"
    echo "  MULTI-AGENT GEMINI CLI SETUP"
    echo "  Status: COMPLETE"
    echo "========================================"
    echo ""
    echo "Each agent now has their own Gemini CLI:"
    echo ""
    
    for agent_info in "${AGENTS[@]}"; do
        IFS=':' read -r agent role desc <<< "$agent_info"
        echo "  gemini-$agent → $role"
        echo "    ~/.gemini-$agent/"
        echo ""
    done
    
    echo "Usage Examples:"
    echo "  gemini-kublai -p 'Review task assignments'"
    echo "  gemini-mongke -p 'Research async patterns'"
    echo "  gemini-temujin -p 'Write API endpoint'"
    echo ""
    echo "Or with environment variable:"
    echo "  GEMINI_HOME=~/.gemini-kublai gemini -p 'Hello'"
    echo ""
    echo "Rollback (if needed):"
    echo "  $0 --rollback"
    echo "  Backup at: $BACKUP_DIR"
    echo ""
    echo "========================================"
}

# Main execution
main() {
    log "Starting Multi-Agent Gemini CLI Setup"
    log "======================================"
    
    # Check if rollback requested
    if [ "$1" == "--rollback" ]; then
        rollback
        exit 0
    fi
    
    # Check if gemini is installed
    if ! command -v gemini &> /dev/null; then
        error "Gemini CLI not found. Please install first:"
        error "  npm install -g @google/gemini-cli"
        exit 1
    fi
    
    # Check authentication
    if [ ! -f "$HOME/.gemini/oauth_creds.json" ]; then
        error "Gemini CLI not authenticated. Please run:"
        error "  gemini"
        error "And authenticate first."
        exit 1
    fi
    
    # Create backup
    backup_existing
    
    # Setup each agent
    for agent_info in "${AGENTS[@]}"; do
        IFS=':' read -r agent role desc <<< "$agent_info"
        setup_agent "$agent" "$role" "$description"
    done
    
    # Test (optional, can be slow)
    # for agent_info in "${AGENTS[@]}"; do
    #     IFS=':' read -r agent role desc <<< "$agent_info"
    #     test_agent "$agent"
    # done
    
    # Verify
    verify_setup
    
    # Print summary
    print_summary
    
    log "Setup complete! Log saved to: $LOG_FILE"
}

# Run main
main "$@"
