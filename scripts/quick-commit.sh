#!/bin/bash
# Quick Commit Script for Kurultai Codebase
# Usage: ./quick-commit.sh "[category] Descriptive message"

set -e

cd /Users/kublai/.openclaw/agents/main

# Check if message provided
if [ -z "$1" ]; then
    echo "❌ Usage: $0 \"[category] Descriptive message\""
    echo ""
    echo "Categories:"
    echo "  [reflection] - Hourly/daily reflection updates"
    echo "  [docs]       - Documentation changes"
    echo "  [config]     - Configuration changes"
    echo "  [feature]    - New capabilities"
    echo "  [fix]        - Bug fixes"
    echo "  [release]    - Deployment markers"
    exit 1
fi

COMMIT_MSG="$1"

# Check for changes
if ! git status --porcelain | grep -q "."; then
    echo "✅ No uncommitted changes"
    exit 0
fi

# Show what will be committed
echo "📦 Changes to commit:"
git status --porcelain
echo ""

# Stage all changes
git add -A

# Commit
git commit -m "$COMMIT_MSG"

if [ $? -eq 0 ]; then
    echo "✅ Committed: $COMMIT_MSG"
    
    # Ask about push
    read -p "🚀 Push to GitHub? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git push origin main
        echo "✅ Pushed to GitHub"
    fi
else
    echo "❌ Commit failed"
    exit 1
fi
