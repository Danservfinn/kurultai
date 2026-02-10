#!/usr/bin/env python3
"""
Delete Empty Notion Databases

Deletes the 4 empty databases identified in the Kurultai review:
- 📈 Metrics & Reports
- 🤝 Vendors & Partners  
- 📅 Compliance & Deadlines
- 💰 Financial Transactions

Usage:
    python delete_empty_notion_databases.py [--dry-run]
"""

import os
import sys
import httpx
import argparse

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Databases to delete (confirmed empty with 0 items each)
DATABASES_TO_DELETE = [
    "📈 Metrics & Reports",
    "🤝 Vendors & Partners",
    "📅 Compliance & Deadlines", 
    "💰 Financial Transactions"
]


def get_notion_client(api_token: str):
    """Create HTTP client with Notion headers."""
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }
    return httpx.Client(headers=headers, timeout=30.0)


def search_databases(client: httpx.Client) -> dict:
    """Search for all databases."""
    response = client.post(
        f"{NOTION_API_BASE}/search",
        json={
            "filter": {"value": "database", "property": "object"},
            "page_size": 100
        }
    )
    
    if response.status_code != 200:
        raise RuntimeError(f"Failed to search databases: {response.status_code} - {response.text}")
    
    return response.json()


def query_database_items(client: httpx.Client, database_id: str) -> int:
    """Query database to count items."""
    response = client.post(
        f"{NOTION_API_BASE}/databases/{database_id}/query",
        json={"page_size": 1}  # Just need to know if any exist
    )
    
    if response.status_code != 200:
        return -1  # Error counting
    
    data = response.json()
    return len(data.get('results', []))


def archive_database(client: httpx.Client, database_id: str) -> bool:
    """Archive (delete) a database by ID."""
    # Notion doesn't allow true deletion via API, but we can archive
    response = client.patch(
        f"{NOTION_API_BASE}/databases/{database_id}",
        json={
            "archived": True
        }
    )
    
    return response.status_code == 200


def main():
    parser = argparse.ArgumentParser(description='Delete empty Notion databases')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be deleted without making changes')
    parser.add_argument('--token', type=str,
                       help='Notion API token (or use NOTION_API_KEY env var)')
    parser.add_argument('--confirm-empty', action='store_true',
                       help='Verify databases are empty before deleting')
    
    args = parser.parse_args()
    
    # Get API token
    api_token = args.token or os.environ.get('NOTION_API_KEY')
    if not api_token:
        print("❌ Error: Notion API token required. Set NOTION_API_KEY or use --token")
        sys.exit(1)
    
    print("\n🗑️  Notion Database Cleanup")
    print("=" * 50)
    
    try:
        with get_notion_client(api_token) as client:
            # Search for all databases
            print("\n📋 Searching for databases...")
            search_result = search_databases(client)
            databases = search_result.get('results', [])
            
            # Map database names to IDs
            db_map = {}
            for db in databases:
                title_parts = db.get('title', [])
                if title_parts:
                    title = title_parts[0].get('text', {}).get('content', '')
                    db_map[title] = {
                        'id': db['id'],
                        'archived': db.get('archived', False)
                    }
            
            print(f"Found {len(db_map)} databases")
            
            # Process each target database
            deleted_count = 0
            skipped_count = 0
            error_count = 0
            
            for db_name in DATABASES_TO_DELETE:
                print(f"\n📁 {db_name}")
                
                if db_name not in db_map:
                    print("   ⚠️  Database not found (may already be deleted)")
                    skipped_count += 1
                    continue
                
                db_info = db_map[db_name]
                db_id = db_info['id']
                
                if db_info['archived']:
                    print("   ✅ Already archived")
                    deleted_count += 1
                    continue
                
                # Verify empty if requested
                if args.confirm_empty:
                    item_count = query_database_items(client, db_id)
                    if item_count > 0:
                        print(f"   ⚠️  Database has {item_count} items - skipping (not empty)")
                        skipped_count += 1
                        continue
                    else:
                        print(f"   ✓ Confirmed empty ({item_count} items)")
                
                if args.dry_run:
                    print(f"   [DRY RUN] Would archive database {db_id}")
                    deleted_count += 1
                else:
                    # Archive the database
                    if archive_database(client, db_id):
                        print(f"   ✅ Archived successfully")
                        deleted_count += 1
                    else:
                        print(f"   ❌ Failed to archive")
                        error_count += 1
            
            # Summary
            print("\n" + "=" * 50)
            print("Summary:")
            print(f"  Databases processed: {len(DATABASES_TO_DELETE)}")
            print(f"  Archived: {deleted_count}")
            print(f"  Skipped: {skipped_count}")
            print(f"  Errors: {error_count}")
            
            if args.dry_run:
                print("\n[DRY RUN] No changes made. Run without --dry-run to archive.")
            
            print()
            
            if error_count > 0:
                sys.exit(1)
                
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
