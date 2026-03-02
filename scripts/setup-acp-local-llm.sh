#!/bin/bash
# ACP + Local LLM Setup Script
# Run this when local LLM is available

echo "=== SETTING UP ACP WITH LOCAL LLM ==="

# 1. Install ACP plugin
echo "Installing ACP plugin..."
openclaw plugins install @openclaw/acpx
openclaw config set plugins.entries.acpx.enabled true

# 2. Configure local LLM backend
echo "Configuring local LLM backend..."
openclaw config set acp.backend "local-llm"
openclaw config set acp.defaultAgent "local-codex"
openclaw config set acp.allowedAgents '["local-codex", "local-claude", "local-gemini"]'

# 3. Install Superpowers
echo "Installing Superpowers plugin..."
openclaw plugins install obra/superpowers

# 4. Configure Temüjin to use Superpowers
echo "Configuring Temüjin with Superpowers..."
openclaw config set agents.list[3].skills '["superpowers", "acp"]'

# 5. Verify setup
echo "Verifying setup..."
/acp doctor

echo ""
echo "✅ ACP + Local LLM setup complete!"
echo ""
echo "Next steps:"
echo "  1. Test ACP session: /acp spawn local-codex --mode persistent"
echo "  2. Generate content packages"
echo "  3. Process articles through Parse"
