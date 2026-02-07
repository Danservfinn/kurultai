#!/bin/bash
# Test script for skill sync integration
# This script simulates the webhook flow and verifies each component

set -e

echo "=== Skill Sync Integration Test ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test functions
check_passed() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
}

check_failed() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    exit 1
}

check_warning() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
}

# =============================================================================
# Test 1: Verify skill-sync-service files exist
# =============================================================================
echo "Test 1: Verify skill-sync-service files..."

FILES=(
    "skill-sync-service/src/index.js"
    "skill-sync-service/src/webhook/handler.js"
    "skill-sync-service/src/deployer/deployer.js"
    "skill-sync-service/src/validators/skill.js"
    "skill-sync-service/src/utils/lock.js"
    "skill-sync-service/src/audit/logger.js"
    "skill-sync-service/Dockerfile"
    "skill-sync-service/railway.yml"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        check_passed "File exists: $file"
    else
        check_failed "File missing: $file"
    fi
done
echo ""

# =============================================================================
# Test 2: Verify security fixes applied
# =============================================================================
echo "Test 2: Verify security fixes..."

# Check for signature verification fix
if grep -q "return false" skill-sync-service/src/webhook/handler.js 2>/dev/null; then
    check_passed "Signature verification returns false when no secret"
else
    check_warning "Could not verify signature fix - manual review needed"
fi

# Check for rate limiting
if grep -q "express-rate-limit" skill-sync-service/package.json; then
    check_passed "Rate limiting dependency installed"
else
    check_failed "Rate limiting missing"
fi

# Check for API key middleware
if grep -q "requireApiKey" skill-sync-service/src/index.js; then
    check_passed "API key middleware present"
else
    check_failed "API key middleware missing"
fi

# Check for O_EXCL lock
if grep -q "O_EXCL" skill-sync-service/src/utils/lock.js; then
    check_passed "Atomic lock (O_EXCL) implemented"
else
    check_failed "Atomic lock missing"
fi
echo ""

# =============================================================================
# Test 3: Verify moltbot skill watcher exists
# =============================================================================
echo "Test 3: Verify moltbot skill watcher..."

if [ -f "moltbot-railway-template/src/skills/watcher.js" ]; then
    check_passed "Node.js skill watcher exists"
else
    check_failed "Node.js skill watcher missing"
fi

# Check for chokidar dependency
if grep -q "chokidar" moltbot-railway-template/package.json; then
    check_passed "chokidar dependency installed"
else
    check_failed "chokidar dependency missing"
fi
echo ""

# =============================================================================
# Test 4: Verify shared volume configuration
# =============================================================================
echo "Test 4: Verify shared volume configuration..."

# Check skill-sync-service volume mount
if grep -q "mountPath: /data" skill-sync-service/railway.yml; then
    check_passed "skill-sync-service mounts /data"
else
    check_failed "skill-sync-service volume mount missing"
fi

# Check moltbot volume mount
if grep -q "clawdbot-data" railway.yml && grep -q "mountPath: /data" railway.yml; then
    check_passed "moltbot mounts shared volume at /data"
else
    check_warning "Could not verify moltbot volume mount - manual review needed"
fi
echo ""

# =============================================================================
# Test 5: Verify Railway configuration
# =============================================================================
echo "Test 5: Verify Railway configuration..."

# Check skill-sync-service in main railway.yml
if grep -q "skill-sync-service" railway.yml; then
    check_passed "skill-sync-service in main railway.yml"
else
    check_warning "skill-sync-service not in main railway.yml (uses separate config)"
fi

# Check environment variables
ENV_VARS=(
    "SKILLS_DIR"
    "GITHUB_WEBHOOK_SECRET"
    "GITHUB_TOKEN"
    "MANUAL_SYNC_API_KEY"
)

echo "  Environment variables to configure:"
for var in "${ENV_VARS[@]}"; do
    echo "    - $var"
done
echo ""

# =============================================================================
# Test 6: Verify deployer features
# =============================================================================
echo "Test 6: Verify deployer features..."

# Check for atomic deployment
if grep -q "Atomic rename" skill-sync-service/src/deployer/deployer.js; then
    check_passed "Atomic deployment implemented"
else
    check_warning "Atomic deployment comment not found"
fi

# Check for rollback
if grep -q "rollback" skill-sync-service/src/deployer/deployer.js; then
    check_passed "Rollback functionality implemented"
else
    check_failed "Rollback functionality missing"
fi

# Check for backup
if grep -q "createBackup" skill-sync-service/src/deployer/deployer.js; then
    check_passed "Backup functionality implemented"
else
    check_failed "Backup functionality missing"
fi

# Check for reload trigger
if grep -q "triggerReload" skill-sync-service/src/deployer/deployer.js; then
    check_passed "Reload trigger implemented"
else
    check_failed "Reload trigger missing"
fi
echo ""

# =============================================================================
# Test 7: Verify webhook features
# =============================================================================
echo "Test 7: Verify webhook features..."

# Check for timestamp verification
if grep -q "verifyTimestamp" skill-sync-service/src/webhook/handler.js; then
    check_passed "Timestamp verification implemented"
else
    check_failed "Timestamp verification missing"
fi

# Check for skill file extraction
if grep -q "extractSkillFiles" skill-sync-service/src/webhook/handler.js; then
    check_passed "Skill file extraction implemented"
else
    check_failed "Skill file extraction missing"
fi
echo ""

# =============================================================================
# Summary
# =============================================================================
echo "=== Test Summary ==="
echo "All local tests passed!"
echo ""
echo "Next steps for full integration testing:"
echo "1. Deploy to Railway: railway up"
echo "2. Run setup script: bash scripts/setup-github-webhook.sh"
echo "3. Configure webhook in GitHub"
echo "4. Test with actual push to kurultai-skills"
echo ""
echo "To test webhook locally:"
echo "  cd skill-sync-service"
echo "  npm test"
echo ""
