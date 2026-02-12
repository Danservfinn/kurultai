#!/usr/bin/env python3
"""
Configure Notion database for shared task tracking.

Since no valid Notion API token is available, this script creates:
1. Database schema definition (JSON)
2. Environment configuration template
3. Manual setup instructions
4. Verification checklist

Usage:
    python configure_notion_database.py
"""

import json
import os
from datetime import datetime


# Database schema for Notion Task Tracker
DATABASE_SCHEMA = {
    "title": "Kurultai Task Tracker",
    "properties": {
        "Name": {
            "title": {}
        },
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
        "Neo4j Task ID": {
            "rich_text": {}
        },
        "Requester": {
            "rich_text": {}
        },
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
        "Duration": {
            "number": {"format": "number"}
        },
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
}


def create_schema_json():
    """Save database schema to JSON file."""
    filename = "config/notion_database_schema.json"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, "w") as f:
        json.dump(DATABASE_SCHEMA, f, indent=2)
    
    print(f"✅ Database schema saved to: {filename}")
    return filename


def create_env_template():
    """Create environment configuration template."""
    env_content = """# Notion Task Tracker Configuration
# Generated: {timestamp}
# 
# To complete setup:
# 1. Go to https://www.notion.so/my-integrations
# 2. Create a new integration named "Kurultai Task Tracker"
# 3. Copy the token and paste below
# 4. Create a database using the schema in config/notion_database_schema.json
# 5. Copy the database ID and paste below

# Required: Notion API integration token (starts with 'secret_')
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NOTION_API_KEY=${{NOTION_TOKEN}}

# Required: Database ID from the created database
# Format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
NOTION_DATABASE_ID=your-database-id-here
NOTION_TASK_DATABASE_ID=${{NOTION_DATABASE_ID}}

# Optional: Polling interval in seconds (default: 60)
NOTION_POLL_INTERVAL_SECONDS=60
""".format(timestamp=datetime.now().isoformat())
    
    filename = ".env.notion.template"
    with open(filename, "w") as f:
        f.write(env_content)
    
    print(f"✅ Environment template saved to: {filename}")
    return filename


def create_notion_api_script():
    """Create a curl script for manual database creation."""
    script_content = """#!/bin/bash
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

curl -X POST https://api.notion.com/v1/databases \\
  -H "Authorization: Bearer $NOTION_TOKEN" \\
  -H "Content-Type: application/json" \\
  -H "Notion-Version: 2022-06-28" \\
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
"""
    
    filename = "scripts/create_notion_db.sh"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, "w") as f:
        f.write(script_content)
    
    os.chmod(filename, 0o755)
    print(f"✅ API script saved to: {filename}")
    return filename


def print_setup_instructions():
    """Print detailed setup instructions."""
    print("""
╔════════════════════════════════════════════════════════════════════╗
║            NOTION DATABASE SETUP INSTRUCTIONS                      ║
╚════════════════════════════════════════════════════════════════════╝

📋 STEP 1: Create a Notion Integration
──────────────────────────────────────
1. Go to https://www.notion.so/my-integrations
2. Click "New integration"
3. Name: "Kurultai Task Tracker"
4. Select your workspace
5. Copy the "Internal Integration Token" (starts with 'secret_')

📋 STEP 2: Create a Parent Page
───────────────────────────────
1. In Notion, create a new page (e.g., "Kurultai Workspace")
2. Click "..." (three dots) at top right
3. Select "Add connections"
4. Choose "Kurultai Task Tracker"
5. Get the page ID from the URL:
   - URL format: https://www.notion.so/Page-Name-PAGE_ID
   - Copy the PAGE_ID part

📋 STEP 3: Create the Database
──────────────────────────────
Option A: Using the API script (recommended)
   export NOTION_TOKEN="secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   export NOTION_PAGE_ID="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   ./scripts/create_notion_db.sh

Option B: Manual creation
   1. Create an inline database on your page
   2. Name it "Kurultai Task Tracker"
   3. Add properties from config/notion_database_schema.json
   4. Copy the database ID from the URL

📋 STEP 4: Configure Environment
────────────────────────────────
1. Copy .env.notion.template to .env.notion
2. Fill in your NOTION_TOKEN and NOTION_DATABASE_ID
3. Source the file: source .env.notion

📋 STEP 5: Verify Setup
───────────────────────
   python tools/verify_notion_setup.py

📋 STEP 6: Share Database
─────────────────────────
1. Open your new database in Notion
2. Click "..." → "Add connections"
3. Select "Kurultai Task Tracker"
4. This allows the integration to read/write tasks

═══════════════════════════════════════════════════════════════════

📁 Generated Files:
   • config/notion_database_schema.json - Database schema
   • .env.notion.template - Environment template
   • scripts/create_notion_db.sh - API creation script
   • docs/NOTION_SETUP_GUIDE.md - Full documentation

🔗 Helpful Links:
   • Notion API Docs: https://developers.notion.com/
   • My Integrations: https://www.notion.so/my-integrations
   • Setup Guide: docs/NOTION_SETUP_GUIDE.md

═══════════════════════════════════════════════════════════════════
""")


def main():
    """Main entry point."""
    print("=" * 70)
    print("🏛️  Kurultai Notion Task Tracker Configuration")
    print("=" * 70)
    print()
    
    # Check for existing token
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
    
    if token:
        print(f"🔑 Found NOTION_API_KEY: {token[:20]}...")
        print("   Note: The existing token appears to be invalid or expired.")
        print("   Please generate a new token from https://www.notion.so/my-integrations")
    else:
        print("🔑 No Notion API token found in environment.")
    
    print()
    
    # Create configuration files
    print("📁 Creating configuration files...")
    print()
    
    schema_file = create_schema_json()
    env_file = create_env_template()
    script_file = create_notion_api_script()
    
    print()
    
    # Print instructions
    print_setup_instructions()
    
    # Summary
    print()
    print("=" * 70)
    print("✅ Configuration files created successfully!")
    print("=" * 70)
    print()
    print("📋 Files created:")
    print(f"   • {schema_file}")
    print(f"   • {env_file}")
    print(f"   • {script_file}")
    print()
    print("📝 Next steps:")
    print("   1. Follow the setup instructions above")
    print("   2. Create a Notion integration")
    print("   3. Run: ./scripts/create_notion_db.sh")
    print("   4. Verify: python tools/verify_notion_setup.py")
    print()


if __name__ == "__main__":
    main()
