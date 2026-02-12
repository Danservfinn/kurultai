#!/bin/bash
# Notion Database Creation Script
# Run this after setting NOTION_TOKEN and NOTION_PAGE_ID

set -e

if [ -z "$NOTION_TOKEN" ]; then
    echo "❌ NOTION_TOKEN not set"
    echo "   Get your token from: https://www.notion.so/my-integrations"
    exit 1
fi

if [ -z "$NOTION_PAGE_ID" ]; then
    echo "❌ NOTION_PAGE_ID not set"
    echo "   Find your page ID in the Notion URL"
    exit 1
fi

echo "🏗️  Creating Notion database..."

curl -X POST https://api.notion.com/v1/databases \
  -H "Authorization: Bearer $NOTION_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Notion-Version: 2022-06-28" \
  -d '{
    "parent": {"page_id": "'"$NOTION_PAGE_ID"'"},
    "title": [{"type": "text", "text": {"content": "Kurultai Task Tracker"}}],
    "properties": {
      "Name": {"title": {}},
      "Status": {
        "select": {
          "options": [
            {"name": "Backlog", "color": "gray"},
            {"name": "Pending Review", "color": "yellow"},
            {"name": "To Do", "color": "blue"},
            {"name": "In Progress", "color": "orange"},
            {"name": "Review", "color": "purple"},
            {"name": "Done", "color": "green"},
            {"name": "Blocked", "color": "red"}
          ]
        }
      },
      "Priority": {
        "select": {
          "options": [
            {"name": "P0", "color": "red"},
            {"name": "P1", "color": "orange"},
            {"name": "P2", "color": "yellow"},
            {"name": "P3", "color": "gray"}
          ]
        }
      },
      "Agent": {
        "select": {
          "options": [
            {"name": "Kublai", "color": "blue"},
            {"name": "Möngke", "color": "green"},
            {"name": "Chagatai", "color": "yellow"},
            {"name": "Temüjin", "color": "orange"},
            {"name": "Jochi", "color": "purple"},
            {"name": "Ögedei", "color": "pink"},
            {"name": "any", "color": "gray"}
          ]
        }
      },
      "Neo4j Task ID": {"rich_text": {}},
      "Requester": {"rich_text": {}},
      "Created From": {
        "select": {
          "options": [
            {"name": "Notion", "color": "blue"},
            {"name": "Discord", "color": "purple"},
            {"name": "Signal", "color": "green"},
            {"name": "Telegram", "color": "yellow"},
            {"name": "GitHub", "color": "gray"},
            {"name": "Cron", "color": "orange"},
            {"name": "Manual", "color": "pink"}
          ]
        }
      },
      "Type": {
        "select": {
          "options": [
            {"name": "Research", "color": "blue"},
            {"name": "Analysis", "color": "green"},
            {"name": "Development", "color": "orange"},
            {"name": "Writing", "color": "yellow"},
            {"name": "Operations", "color": "pink"},
            {"name": "Strategy", "color": "purple"},
            {"name": "Bug Fix", "color": "red"},
            {"name": "Feature", "color": "blue"},
            {"name": "Documentation", "color": "gray"}
          ]
        }
      },
      "Duration": {"number": {"format": "number"}},
      "Tags": {
        "multi_select": {
          "options": [
            {"name": "urgent", "color": "red"},
            {"name": "blocked", "color": "gray"},
            {"name": "needs-review", "color": "yellow"},
            {"name": "high-value", "color": "green"},
            {"name": "quick-win", "color": "blue"},
            {"name": "ops", "color": "pink"},
            {"name": "code", "color": "orange"},
            {"name": "strategy", "color": "purple"}
          ]
        }
      },
      "Due Date": {"date": {}},
      "Description": {"rich_text": {}},
      "Completion Notes": {"rich_text": {}}
    }
  }'

echo ""
echo "✅ Database creation request sent!"
echo "   Check the response above for the database ID."
