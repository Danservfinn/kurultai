#!/usr/bin/env python3
"""
Ögedei Workspace Redesign Tool

Audits and cleans up Notion workspace by:
- Identifying unused databases
- Organizing untitled pages
- Creating clean hierarchy for Kurultai operations
"""

import os
import sys
import json
from typing import Dict, List

sys.path.insert(0, os.path.dirname(__file__))


class WorkspaceRedesigner:
    """Redesigns Notion workspace for optimal Kurultai operations."""
    
    def __init__(self):
        self.api_key = os.environ.get('NOTION_TOKEN') or os.environ.get('NOTION_API_KEY')
        self.base_url = "https://api.notion.com/v1"
        
    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Make authenticated request to Notion API."""
        import urllib.request
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode() if data else None,
            headers=headers,
            method=method
        )
        
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    
    def scan_workspace(self) -> Dict:
        """Scan workspace and identify cleanup targets."""
        print("🔍 Scanning Notion workspace...\n")
        
        # Get all databases
        db_result = self._make_request("POST", "/search", {
            "filter": {"value": "database", "property": "object"}
        })
        databases = db_result.get('results', [])
        
        # Analyze each database
        db_analysis = []
        for db in databases:
            title = db.get('title', [{}])[0].get('text', {}).get('content', 'Untitled')
            db_id = db['id']
            
            # Query item count
            try:
                items = self._make_request("POST", f"/databases/{db_id}/query", {"page_size": 100})
                item_count = len(items.get('results', []))
            except:
                item_count = 0
            
            db_analysis.append({
                'id': db_id,
                'title': title,
                'item_count': item_count,
                'recommendation': 'KEEP' if item_count > 0 else 'CONSIDER_DELETE'
            })
        
        # Get untitled pages
        page_result = self._make_request("POST", "/search", {
            "filter": {"value": "page", "property": "object"}
        })
        pages = page_result.get('results', [])
        
        untitled_pages = []
        for page in pages:
            props = page.get('properties', {})
            title_parts = props.get('title', {}).get('title', [])
            title = title_parts[0].get('text', {}).get('content', 'Untitled') if title_parts else 'Untitled'
            
            if title == 'Untitled' or not title_parts:
                untitled_pages.append({
                    'id': page['id'],
                    'title': title,
                    'created_time': page.get('created_time', 'unknown')
                })
        
        return {
            'databases': db_analysis,
            'untitled_pages': untitled_pages,
            'total_databases': len(databases),
            'total_pages': len(pages)
        }
    
    def create_workspace_structure(self):
        """Create clean workspace structure."""
        print("\n🏗️ Creating workspace structure...\n")
        
        # Create main Kurultai page
        try:
            result = self._make_request("POST", "/pages", {
                "parent": {"page_id": os.environ.get('NOTION_ROOT_PAGE', '')} if os.environ.get('NOTION_ROOT_PAGE') else {"database_id": os.environ.get('NOTION_TASK_DATABASE_ID')},
                "properties": {
                    "title": {
                        "title": [{"text": {"content": "🌙 Kurultai HQ"}}]
                    }
                },
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": "Central command for Kurultai operations. All systems, tasks, and intelligence converge here."}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": "📊 Systems"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": "Tasks & Action Items - Active work tracking"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": "Research Findings - Möngke's intelligence reports"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": "Agent Status - Live agent monitoring"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": "🤖 Agents"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": "Kublai - Router & orchestration"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": "Möngke - Research & intelligence"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": "Jochi - Analysis & testing"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": "Chagatai - Writing & documentation"}}]
                        }
                    },
                    {
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": [{"type": "text", "text": {"content": "Ögedei - Operations & monitoring"}}]
                        }
                    }
                ]
            })
            print("✅ Created: Kurultai HQ page")
            return result['id']
        except Exception as e:
            print(f"⚠️ Could not create main page: {e}")
            return None
    
    def redesign_workspace(self):
        """Execute full workspace redesign."""
        print("=" * 60)
        print("ÖGEDEI WORKSPACE REDESIGN")
        print("=" * 60)
        
        # Scan workspace
        analysis = self.scan_workspace()
        
        print(f"\n📊 WORKSPACE AUDIT:")
        print(f"   Total databases: {analysis['total_databases']}")
        print(f"   Total pages: {analysis['total_pages']}")
        print(f"   Untitled pages: {len(analysis['untitled_pages'])}")
        
        print(f"\n📋 DATABASE ANALYSIS:")
        empty_dbs = []
        for db in analysis['databases']:
            status = "✅ KEEP" if db['item_count'] > 0 else "🗑️ EMPTY"
            print(f"   {status} - {db['title']} ({db['item_count']} items)")
            if db['item_count'] == 0:
                empty_dbs.append(db)
        
        print(f"\n🗑️ RECOMMENDED FOR DELETION:")
        for db in empty_dbs:
            print(f"   • {db['title']}")
        
        print(f"\n📝 UNTITLED PAGES (first 10):")
        for page in analysis['untitled_pages'][:10]:
            print(f"   • {page['id'][:8]}... (created: {page['created_time'][:10]})")
        if len(analysis['untitled_pages']) > 10:
            print(f"   ... and {len(analysis['untitled_pages']) - 10} more")
        
        # Create structure
        hq_id = self.create_workspace_structure()
        
        print("\n" + "=" * 60)
        print("✅ WORKSPACE REDESIGN COMPLETE")
        print("=" * 60)
        print(f"\n📌 NEXT STEPS:")
        print(f"   1. Review empty databases: {len(empty_dbs)} found")
        print(f"   2. Clean up untitled pages: {len(analysis['untitled_pages'])} found")
        print(f"   3. Move active content to Kurultai HQ")
        
        return {
            'empty_databases': empty_dbs,
            'untitled_pages': analysis['untitled_pages'],
            'hq_page_id': hq_id
        }


if __name__ == '__main__':
    designer = WorkspaceRedesigner()
    designer.redesign_workspace()
