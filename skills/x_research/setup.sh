#!/bin/bash
# Setup script for x-research skill

echo "🔧 Setting up x-research skill..."

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

echo "✅ Python 3 found"

# Check for Composio API key
if [ -z "$COMPOSIO_API_KEY" ]; then
    echo "⚠️  Warning: COMPOSIO_API_KEY not set"
    echo "   Get your API key at: https://composio.ai"
    echo "   Then set it with: export COMPOSIO_API_KEY=your_key"
else
    echo "✅ Composio API key configured"
fi

# Create __pycache__ directory
mkdir -p skills/x_research/__pycache__

echo ""
echo "🧪 Running tests..."
python3 skills/x_research/test_skill.py --mock

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ x-research skill setup complete!"
    echo ""
    echo "Usage:"
    echo "  from skills.x_research import XResearchClient"
    echo "  client = XResearchClient()"
    echo "  tweets = client.search_tweets('#AI', max_results=50)"
    echo ""
else
    echo ""
    echo "❌ Setup failed - tests did not pass"
    exit 1
fi
