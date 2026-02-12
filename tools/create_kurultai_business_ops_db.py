#!/usr/bin/env python3
"""
Check and create Kurultai Business Operations database in Notion.
"""
import os
import json
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any

NOTION_API_KEY = os.getenv("NOTION_API_KEY") or os.getenv("NOTION_TOKEN")
NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": NOTION_VERSION
}

def make_request(method: str, endpoint: str, data: Optional[Dict] = None) -> Dict:
    """Make HTTP request to Notion API."""
    url = f"{NOTION_API_BASE}{endpoint}"
    request_body = json.dumps(data).encode("utf-8") if data else None
    
    req = urllib.request.Request(
        url,
        data=request_body,
        headers=headers,
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

def search_databases(query: str = "") -> List[Dict]:
    """Search for databases."""
    data = {"query": query, "filter": {"value": "database", "property": "object"}}
    response = make_request("POST", "/search", data)
    return response.get("results", [])

def get_database(database_id: str) -> Dict:
    """Get database details."""
    return make_request("GET", f"/databases/{database_id}")

def create_database(parent_page_id: str, title: str = "Kurultai Business Operations") -> Dict:
    """Create the Kurultai Business Operations database."""
    payload = {
        "parent": {"page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": {
            "Name": {"title": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "Todo", "color": "blue"},
                        {"name": "In Progress", "color": "yellow"},
                        {"name": "Blocked", "color": "red"},
                        {"name": "Done", "color": "green"},
                        {"name": "Archived", "color": "gray"}
                    ]
                }
            },
            "Assignee": {
                "select": {
                    "options": [
                        {"name": "Kublai", "color": "blue"},
                        {"name": "Möngke", "color": "green"},
                        {"name": "Chagatai", "color": "yellow"},
                        {"name": "Temüjin", "color": "orange"},
                        {"name": "Jochi", "color": "purple"},
                        {"name": "Ögedei", "color": "pink"},
                        {"name": "Danny", "color": "brown"}
                    ]
                }
            },
            "Priority": {
                "select": {
                    "options": [
                        {"name": "High", "color": "red"},
                        {"name": "Medium", "color": "yellow"},
                        {"name": "Low", "color": "gray"}
                    ]
                }
            },
            "Source": {
                "select": {
                    "options": [
                        {"name": "Discord", "color": "purple"},
                        {"name": "Heartbeat", "color": "pink"},
                        {"name": "Agent", "color": "blue"},
                        {"name": "Cron", "color": "orange"}
                    ]
                }
            },
            "Created": {"date": {}},
            "Completed": {"date": {}},
            "Neo4j ID": {"rich_text": {}}
        }
    }
    
    print(f"📝 Creating database '{title}'...")
    response = make_request("POST", "/databases", payload)
    return response

def main():
    print("🏛️  Kurultai Business Operations - Notion Database Setup")
    print("=" * 60)
    
    # Step 1: Check if database exists
    print("\n🔍 Searching for existing 'Kurultai Business Operations' database...")
    databases = search_databases("Kurultai Business Operations")
    
    existing_db = None
    for db in databases:
        db_title = db.get("title", [{}])[0].get("text", {}).get("content", "")
        if db_title == "Kurultai Business Operations":
            existing_db = db
            break
    
    if existing_db:
        print(f"✅ Database already exists!")
        print(f"   ID: {existing_db['id']}")
        print(f"   URL: {existing_db.get('url', 'N/A')}")
        return existing_db['id']
    
    print("❌ Database not found. Creating new database...")
    
    # Step 2: Find a parent page
    print("\n🔍 Searching for parent pages...")
    pages = make_request("POST", "/search", {"filter": {"value": "page", "property": "object"}})
    pages = pages.get("results", [])
    
    if not pages:
        print("❌ No accessible pages found!")
        return None
    
    # Use first available page
    parent_page_id = pages[0]["id"]
    parent_title = pages[0].get('properties', {}).get('title', {}).get('title', [{}])[0].get('plain_text', 'Untitled')
    print(f"📄 Using parent page: {parent_title}")
    
    # Step 3: Create the database
    database = create_database(parent_page_id)
    
    print(f"\n✅ Database created successfully!")
    print(f"   ID: {database['id']}")
    print(f"   URL: {database.get('url', 'N/A')}")
    print(f"\n📋 Schema configured:")
    print("   • Name (title)")
    print("   • Status (Todo/In Progress/Blocked/Done/Archived)")
    print("   • Assignee (Kublai, Möngke, Chagatai, Temüjin, Jochi, Ögedei, Danny)")
    print("   • Priority (High/Medium/Low)")
    print("   • Source (Discord/Heartbeat/Agent/Cron)")
    print("   • Created (date)")
    print("   • Completed (date)")
    print("   • Neo4j ID (rich_text)")
    
    return database['id']

if __name__ == "__main__":
    db_id = main()
    if db_id:
        print(f"\n💾 Database ID: {db_id}")
        # Output for shell
        print(f"\nEXPORT_NOTION_DB_ID={db_id}")
    else:
        exit(1)
