#!/usr/bin/env python3
"""
Create and configure Notion database for shared task tracking.

This script creates a Notion database with the proper schema for the
Kurultai task tracking system, including all required properties for
bidirectional synchronization with Neo4j.

Usage:
    python create_notion_task_database.py

Environment Variables:
    NOTION_TOKEN: Notion API integration token (required)
"""

import os
import sys
import json
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any


class NotionDatabaseCreator:
    """Creates and configures a Notion database for task tracking."""
    
    NOTION_API_BASE = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"
    
    # Database schema definition
    DATABASE_SCHEMA = {
        "title": [
            {
                "type": "text",
                "text": {"content": "Kurultai Task Tracker"}
            }
        ],
        "properties": {
            # Task name/title
            "Name": {
                "title": {}
            },
            # Task status (Kanban columns)
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
            # Priority levels
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
            # Assigned agent
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
            # Neo4j Task ID (for bidirectional sync)
            "Neo4j Task ID": {
                "rich_text": {}
            },
            # Who requested the task
            "Requester": {
                "rich_text": {}
            },
            # Source of task creation
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
            # Task type/category
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
            # Estimated duration in minutes
            "Duration": {
                "number": {
                    "format": "number"
                }
            },
            # Tags for filtering
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
            # Due date (optional)
            "Due Date": {
                "date": {}
            },
            # Task description/details
            "Description": {
                "rich_text": {}
            },
            # Completion notes
            "Completion Notes": {
                "rich_text": {}
            }
        }
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with Notion API key."""
        self.api_key = api_key or os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
        
        if not self.api_key:
            raise ValueError(
                "Notion API key required. Set NOTION_TOKEN or NOTION_API_KEY environment variable."
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": self.NOTION_VERSION
        }
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None
    ) -> Dict:
        """Make HTTP request to Notion API."""
        url = f"{self.NOTION_API_BASE}{endpoint}"
        request_body = json.dumps(data).encode("utf-8") if data else None
        
        req = urllib.request.Request(
            url,
            data=request_body,
            headers=self.headers,
            method=method
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                response_data = response.read().decode("utf-8")
                if response_data:
                    return json.loads(response_data)
                return {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"❌ API Error {e.code}: {error_body}")
            raise
        except urllib.error.URLError as e:
            print(f"❌ Network Error: {e.reason}")
            raise
    
    def search_pages(self, query: str = "") -> List[Dict]:
        """Search for pages the integration has access to."""
        data = {"query": query} if query else {}
        response = self._make_request("POST", "/search", data)
        return response.get("results", [])
    
    def create_database(
        self,
        parent_page_id: Optional[str] = None,
        database_title: str = "Kurultai Task Tracker"
    ) -> Dict:
        """
        Create the task tracking database.
        
        Args:
            parent_page_id: Notion page ID to create database under
            database_title: Title for the database
            
        Returns:
            Created database object
        """
        if not parent_page_id:
            # Try to find a suitable parent page
            pages = self.search_pages()
            if not pages:
                raise ValueError(
                    "No accessible pages found. Please provide a parent_page_id or "
                    "share a page with this integration."
                )
            parent_page_id = pages[0]["id"]
            print(f"📄 Using parent page: {pages[0].get('properties', {}).get('title', {}).get('title', [{}])[0].get('plain_text', 'Untitled')}")
        
        # Prepare database creation payload
        payload = {
            "parent": {"page_id": parent_page_id},
            **self.DATABASE_SCHEMA
        }
        payload["title"][0]["text"]["content"] = database_title
        
        print(f"📝 Creating database '{database_title}'...")
        response = self._make_request("POST", "/databases", payload)
        
        return response
    
    def create_sample_tasks(self, database_id: str) -> List[Dict]:
        """Create sample tasks to demonstrate the database structure."""
        sample_tasks = [
            {
                "name": "Review new API integration",
                "status": "To Do",
                "priority": "P1",
                "agent": "Temüjin",
                "type": "Development",
                "tags": ["code", "needs-review"],
                "duration": 60,
                "description": "Review and test the new Notion API integration for task tracking"
            },
            {
                "name": "Write documentation",
                "status": "Backlog",
                "priority": "P2",
                "agent": "Chagatai",
                "type": "Documentation",
                "tags": ["ops"],
                "duration": 120,
                "description": "Document the new task tracking workflow"
            },
            {
                "name": "Research competitor features",
                "status": "In Progress",
                "priority": "P0",
                "agent": "Möngke",
                "type": "Research",
                "tags": ["urgent", "high-value"],
                "duration": 180,
                "description": "Analyze competitor task management features"
            }
        ]
        
        created = []
        for task in sample_tasks:
            properties = {
                "Name": {"title": [{"text": {"content": task["name"]}}]},
                "Status": {"select": {"name": task["status"]}},
                "Priority": {"select": {"name": task["priority"]}},
                "Agent": {"select": {"name": task["agent"]}},
                "Type": {"select": {"name": task["type"]}},
                "Tags": {"multi_select": [{"name": tag} for tag in task["tags"]]},
                "Duration": {"number": task["duration"]},
                "Description": {"rich_text": [{"text": {"content": task["description"]}}]},
                "Created From": {"select": {"name": "Manual"}}
            }
            
            payload = {
                "parent": {"database_id": database_id},
                "properties": properties
            }
            
            try:
                response = self._make_request("POST", "/pages", payload)
                created.append(response)
                print(f"  ✅ Created sample task: {task['name']}")
            except Exception as e:
                print(f"  ⚠️ Failed to create task '{task['name']}': {e}")
        
        return created
    
    def print_database_info(self, database: Dict):
        """Print database information for the user."""
        db_id = database.get("id", "")
        url = database.get("url", "")
        
        print("\n" + "=" * 60)
        print("🎉 Notion Database Created Successfully!")
        print("=" * 60)
        print(f"\n📊 Database Name: {database.get('title', [{}])[0].get('text', {}).get('content', 'Untitled')}")
        print(f"🆔 Database ID: {db_id}")
        print(f"🔗 URL: {url}")
        print("\n📋 Database Schema:")
        print("-" * 40)
        
        properties = database.get("properties", {})
        for prop_name, prop_config in properties.items():
            prop_type = prop_config.get("type", "unknown")
            print(f"  • {prop_name}: {prop_type}")
        
        print("\n" + "=" * 60)
        print("⚙️  Configuration Instructions:")
        print("=" * 60)
        print(f"\nAdd these environment variables to your .env file:")
        print(f"\n  NOTION_TOKEN={self.api_key[:20]}...")
        print(f"  NOTION_DATABASE_ID={db_id}")
        print(f"\nOr for the full integration:")
        print(f"  NOTION_TASK_DATABASE_ID={db_id}")
        print("\n" + "=" * 60)


def main():
    """Main entry point."""
    print("🏛️  Kurultai Notion Task Database Creator")
    print("=" * 60)
    
    # Check for API key
    api_key = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
    
    if not api_key:
        print("\n❌ Error: Notion API token not found!")
        print("\nTo create a Notion integration:")
        print("1. Go to https://www.notion.so/my-integrations")
        print("2. Click 'New integration'")
        print("3. Give it a name (e.g., 'Kurultai Task Tracker')")
        print("4. Copy the 'Internal Integration Token'")
        print("5. Set it as an environment variable:")
        print("   export NOTION_TOKEN='your-token-here'")
        print("\nThen run this script again.")
        sys.exit(1)
    
    try:
        creator = NotionDatabaseCreator(api_key)
        
        # Search for available pages
        print("\n🔍 Searching for available pages...")
        pages = creator.search_pages()
        
        if not pages:
            print("\n❌ No accessible pages found!")
            print("\nTo fix this:")
            print("1. Create a page in your Notion workspace")
            print("2. Click '...' (three dots) on the page")
            print("3. Go to 'Add connections'")
            print("4. Select your integration")
            sys.exit(1)
        
        print(f"\n📄 Found {len(pages)} accessible page(s):")
        for i, page in enumerate(pages[:5], 1):
            title = page.get('properties', {}).get('title', {}).get('title', [{}])[0].get('plain_text', 'Untitled')
            print(f"   {i}. {title}")
        
        # Use first page as parent
        parent_page_id = pages[0]["id"]
        
        # Create database
        print("\n🏗️  Creating task tracking database...")
        database = creator.create_database(parent_page_id=parent_page_id)
        
        # Print database info
        creator.print_database_info(database)
        
        # Create sample tasks
        print("\n📝 Creating sample tasks...")
        db_id = database.get("id")
        creator.create_sample_tasks(db_id)
        
        print("\n✅ Setup complete!")
        print(f"\n🌐 Visit your database: {database.get('url')}")
        
        # Save configuration
        config_file = ".env.notion"
        with open(config_file, "w") as f:
            f.write(f"# Notion Task Tracker Configuration\n")
            f.write(f"NOTION_TOKEN={api_key}\n")
            f.write(f"NOTION_DATABASE_ID={db_id}\n")
            f.write(f"NOTION_TASK_DATABASE_ID={db_id}\n")
        
        print(f"\n💾 Configuration saved to: {config_file}")
        
        # Return the database ID for Neo4j update
        return db_id
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    db_id = main()
