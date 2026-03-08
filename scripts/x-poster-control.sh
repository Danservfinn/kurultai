#!/usr/bin/env bash
#
# OpenClaw X/Twitter Poster Control Script
# Control automated posting for OpenClaw updates
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
X_POSTER="$SCRIPT_DIR/x_poster.py"
PAUSE_FLAG="$HOME/.openclaw/data/x_posting_paused"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Show usage
show_usage() {
    cat << EOF
OpenClaw X/Twitter Poster Control

Usage: $(basename "$0") <command>

Commands:
    status          Show posting system status
    pause           Pause all automated posting
    resume          Resume automated posting
    post-status     Post daily status update immediately
    post-public     Post "building in public" update
    post-weekly     Force post weekly review (any day)
    list-pending    List posts awaiting approval
    approve <id>    Approve a draft post
    dry-run         Show what would be posted (no actual post)
    help            Show this message

Examples:
    $(basename "$0") status
    $(basename "$0") pause
    $(basename "$0") post-status
    $(basename "$0") approve abc123def456

EOF
}

# Check if script exists
check_script() {
    if [[ ! -f "$X_POSTER" ]]; then
        error "x-poster.py not found at $X_POSTER"
        exit 1
    fi
}

# Status command
cmd_status() {
    check_script

    info "OpenClaw X Posting System Status"
    echo ""

    # Check pause status
    if [[ -f "$PAUSE_FLAG" ]]; then
        warn "Posting is PAUSED"
    else
        info "Posting is ACTIVE"
    fi
    echo ""

    # Run x-poster status
    python3 "$X_POSTER" status --json 2>/dev/null | python3 -m json.tool 2>/dev/null || \
        python3 "$X_POSTER" status
}

# Pause command
cmd_pause() {
    touch "$PAUSE_FLAG"
    info "OpenClaw X posting PAUSED"
    info "Use '$(basename "$0") resume' to enable posting again"
}

# Resume command
cmd_resume() {
    if [[ -f "$PAUSE_FLAG" ]]; then
        rm "$PAUSE_FLAG"
        info "OpenClaw X posting RESUMED"
    else
        info "Posting is already active"
    fi
}

# Post status command
cmd_post_status() {
    check_script

    if [[ -f "$PAUSE_FLAG" ]]; then
        error "Posting is paused. Use 'resume' first."
        exit 1
    fi

    info "Posting daily status update..."
    python3 "$X_POSTER" post_status
}

# Post build public command
cmd_post_public() {
    check_script

    if [[ -f "$PAUSE_FLAG" ]]; then
        error "Posting is paused. Use 'resume' first."
        exit 1
    fi

    info "Posting 'building in public' update..."
    python3 "$X_POSTER" post_build_public
}

# Post weekly command
cmd_post_weekly() {
    check_script

    if [[ -f "$PAUSE_FLAG" ]]; then
        error "Posting is paused. Use 'resume' first."
        exit 1
    fi

    info "Posting weekly review..."
    python3 "$X_POSTER" post_weekly
}

# List pending command
cmd_list_pending() {
    check_script

    info "Posts awaiting approval:"
    echo ""

    pending=$(python3 "$X_POSTER" list_pending --json 2>/dev/null)

    if echo "$pending" | python3 -c "import sys, json; data=json.load(sys.stdin); sys.exit(0 if len(data)>0 else 1)" 2>/dev/null; then
        echo "$pending" | python3 -m json.tool 2>/dev/null || echo "$pending"
    else
        info "No pending posts"
    fi
}

# Approve command
cmd_approve() {
    check_script

    if [[ -z "$1" ]]; then
        error "Post ID required"
        echo "Usage: $(basename "$0") approve <post-id>"
        exit 1
    fi

    info "Approving post: $1"
    python3 "$X_POSTER" approve --post-id "$1"
}

# Dry run command
cmd_dry_run() {
    check_script

    info "DRY RUN - Showing what would be posted:"
    echo ""
    info "--- Daily Status ---"
    python3 "$X_POSTER" post_status --dry-run
    echo ""
    info "--- Build Public ---"
    python3 "$X_POSTER" post_build_public --dry-run
}

# Main
case "${1:-}" in
    status)
        cmd_status
        ;;
    pause)
        cmd_pause
        ;;
    resume)
        cmd_resume
        ;;
    post-status)
        cmd_post_status
        ;;
    post-public)
        cmd_post_public
        ;;
    post-weekly)
        cmd_post_weekly
        ;;
    list-pending)
        cmd_list_pending
        ;;
    approve)
        cmd_approve "$2"
        ;;
    dry-run)
        cmd_dry_run
        ;;
    help|--help|-h|"")
        show_usage
        ;;
    *)
        error "Unknown command: $1"
        echo ""
        show_usage
        exit 1
        ;;
esac
