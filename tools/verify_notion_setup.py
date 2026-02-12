#!/usr/bin/env python3
"""
Verify Notion Task Tracker configuration and test connectivity.

Usage:
    python verify_notion_setup.py
"""

import os
import sys
import json
import urllib.request
import urllib.error


def check_env_vars():
    """Check for required environment variables."""
    print("🔍 Checking environment variables...")
    
    token = os.getenv("NOTION_TOKEN") or os.getenv("NOTION_API_KEY")
    db_id = os.getenv("NOTION_DATABASE_ID") or os.getenv("NOTION_TASK_DATABASE_ID")
    
    issues = []
    
    if not token:
        issues.append("❌ NOTION_TOKEN or NOTION_API_KEY not set")
    else:
        print(f"  ✅ NOTION_TOKEN: {token[:20]}...")
    
    if not db_id:
        issues.append("❌ NOTION_DATABASE_ID or NOTION_TASK_DATABASE_ID not set")
    else:
        print(f"  ✅ NOTION_DATABASE_ID: {db_id}")
    
    return token, db_id, issues


def test_notion_api(token: str) -> bool:
    """Test Notion API connectivity."""
    print("\n🌐 Testing Notion API connectivity...")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28"
    }
    
    req = urllib.request.Request(
        "https://api.notion.com/v1/users/me",
        headers=headers,
        method="GET"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            print(f"  ✅ API connection successful")
            print(f"     Integration name: {data.get('name', 'Unknown')}")
            print(f"     Workspace: {data.get('workspace_name', 'Unknown')}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"  ❌ API Error: {e.code} - {error_body}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def test_database_access(token: str, db_id: str) -> bool:
    """Test database access."""
    print(f"\n📊 Testing database access...")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    # Try to query the database
    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        headers=headers,
        data=json.dumps({}).encode("utf-8"),
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            results = data.get("results", [])
            print(f"  ✅ Database access successful")
            print(f"     Tasks in database: {len(results)}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        error_data = json.loads(error_body)
        
        if e.code == 404:
            print(f"  ❌ Database not found (404)")
            print(f"     Check that NOTION_DATABASE_ID is correct")
        elif e.code == 403:
            print(f"  ❌ Access denied (403)")
            print(f"     Make sure the integration is added to the database:")
            print(f"     1. Open the database in Notion")
            print(f"     2. Click '...' → 'Add connections'")
            print(f"     3. Select your integration")
        else:
            print(f"  ❌ API Error: {e.code} - {error_data.get('message', 'Unknown error')}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def get_database_schema(token: str, db_id: str) -> dict:
    """Get and display database schema."""
    print(f"\n📋 Checking database schema...")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28"
    }
    
    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{db_id}",
        headers=headers,
        method="GET"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            properties = data.get("properties", {})
            
            print(f"  ✅ Schema retrieved")
            print(f"\n  Properties:")
            
            required_props = ["Name", "Status", "Priority", "Agent", "Neo4j Task ID"]
            found_props = []
            
            for prop_name, prop_config in properties.items():
                prop_type = prop_config.get("type", "unknown")
                print(f"    • {prop_name}: {prop_type}")
                if prop_name in required_props:
                    found_props.append(prop_name)
            
            missing = set(required_props) - set(found_props)
            if missing:
                print(f"\n  ⚠️  Missing recommended properties: {', '.join(missing)}")
            else:
                print(f"\n  ✅ All recommended properties present")
            
            return data
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return {}


def main():
    """Main entry point."""
    print("=" * 60)
    print("🔧 Notion Task Tracker Verification")
    print("=" * 60)
    
    # Check environment variables
    token, db_id, issues = check_env_vars()
    
    if issues:
        print("\n" + "=" * 60)
        print("❌ Configuration Issues Found")
        print("=" * 60)
        for issue in issues:
            print(f"  {issue}")
        
        print("\n📖 Setup Instructions:")
        print("  1. Read: docs/NOTION_SETUP_GUIDE.md")
        print("  2. Create a Notion integration at https://www.notion.so/my-integrations")
        print("  3. Set NOTION_TOKEN environment variable")
        print("  4. Run: python tools/create_notion_task_database.py")
        print("  5. Add the database ID to your .env file")
        
        sys.exit(1)
    
    # Test API connectivity
    if not test_notion_api(token):
        print("\n❌ Failed to connect to Notion API")
        print("   Check your NOTION_TOKEN is valid")
        sys.exit(1)
    
    # Test database access
    if db_id:
        if not test_database_access(token, db_id):
            print("\n❌ Failed to access database")
            print("   Check that:")
            print("   1. NOTION_DATABASE_ID is correct")
            print("   2. The integration has access to the database")
            sys.exit(1)
        
        # Get schema
        get_database_schema(token, db_id)
    
    print("\n" + "=" * 60)
    print("✅ Notion Task Tracker is configured correctly!")
    print("=" * 60)
    
    print("\n📋 Next Steps:")
    print("  1. Create tasks in your Notion database")
    print("  2. They will automatically sync to Neo4j")
    print("  3. Agents will pick up and execute tasks")
    
    print("\n🔧 For manual testing:")
    print("  python tools/create_notion_task_database.py")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
