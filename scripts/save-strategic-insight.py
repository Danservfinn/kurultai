#!/usr/bin/env python3
"""
Save Strategic Insight to Neo4j

Stores strategic decisions, opportunities, and insights in Neo4j for long-term memory.

Usage:
    python3 save-strategic-insight.py --type opportunity --name "Kurultai Monetization" --data '{"model": "Open Core", "arr_y1": 180000}'
    python3 save-strategic-insight.py --type decision --name "Parse + Kurultai Parallel" --data '{"rationale": "Both are viable"}'
    python3 save-strategic-insight.py --type insight --name "Multi-Agent is Moat" --data '{"source": "OpenClaw analysis"}'
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_task_tracker import get_driver


def save_insight(insight_type, name, data, source="manual", tags=None):
    """Save a strategic insight to Neo4j."""
    driver = get_driver()
    
    insight_id = f"{insight_type.lower()}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    timestamp = datetime.now().isoformat()
    
    with driver.session() as session:
        # Create or update the insight
        result = session.run("""
            MERGE (i:StrategicInsight {id: $id})
            SET i.type = $type,
                i.name = $name,
                i.data = $data,
                i.source = $source,
                i.tags = $tags,
                i.created = $timestamp,
                i.updated = $timestamp,
                i.status = 'active'
            RETURN i.id as id, i.name as name
        """, 
        id=insight_id,
        type=insight_type,
        name=name,
        data=json.dumps(data),
        source=source,
        tags=tags or [],
        timestamp=timestamp
        )
        
        record = result.single()
        print(f"✅ Saved: {record['name']} (ID: {record['id']})")
    
    driver.close()
    return insight_id


def save_opportunity(name, data):
    """Save a business opportunity."""
    return save_insight("opportunity", name, data, source="ecosystem-analysis")


def save_decision(name, data):
    """Save a strategic decision."""
    return save_insight("decision", name, data, source="strategic-planning")


def save_insight_entry(name, data):
    """Save a general insight."""
    return save_insight("insight", name, data, source="analysis")


def link_to_goal(insight_id, goal_name):
    """Link an insight to a goal."""
    driver = get_driver()
    
    with driver.session() as session:
        session.run("""
            MATCH (i:StrategicInsight {id: $id})
            MATCH (g:Goal {name: $goal})
            MERGE (i)-[:SUPPORTS]->(g)
        """, id=insight_id, goal=goal_name)
    
    driver.close()
    print(f"  → Linked to goal: {goal_name}")


def list_insights(insight_type=None, limit=10):
    """List recent strategic insights."""
    driver = get_driver()
    
    with driver.session() as session:
        if insight_type:
            result = session.run("""
                MATCH (i:StrategicInsight {type: $type})
                RETURN i ORDER BY i.created DESC LIMIT $limit
            """, type=insight_type, limit=limit)
        else:
            result = session.run("""
                MATCH (i:StrategicInsight)
                RETURN i ORDER BY i.created DESC LIMIT $limit
            """, limit=limit)
        
        insights = [dict(r['i']) for r in result]
        
        print(f"\n{'='*60}")
        print(f"Strategic Insights ({len(insights)} found)")
        print(f"{'='*60}")
        
        for i in insights:
            print(f"\n[{i.get('type', '?').upper()}] {i.get('name', 'Unknown')}")
            print(f"  ID: {i.get('id', '?')}")
            print(f"  Source: {i.get('source', '?')}")
            print(f"  Created: {i.get('created', '?')}")
            print(f"  Data: {i.get('data', '{}')[:100]}...")
    
    driver.close()
    return insights


def main():
    parser = argparse.ArgumentParser(description="Save strategic insights to Neo4j")
    parser.add_argument("--type", choices=["opportunity", "decision", "insight"])
    parser.add_argument("--name", help="Name of the insight")
    parser.add_argument("--data", help="JSON data for the insight")
    parser.add_argument("--source", default="manual", help="Source of the insight")
    parser.add_argument("--tags", help="Comma-separated tags")
    parser.add_argument("--link-goal", help="Link to a goal")
    parser.add_argument("--list", action="store_true", help="List recent insights")
    parser.add_argument("--filter-type", help="Filter by type when listing")
    
    args = parser.parse_args()
    
    if args.list:
        list_insights(args.filter_type)
        return
    
    # Parse data JSON
    try:
        data = json.loads(args.data)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON data: {e}")
        sys.exit(1)
    
    # Parse tags
    tags = args.tags.split(",") if args.tags else []
    
    # Save insight
    insight_id = save_insight(args.type, args.name, data, args.source, tags)
    
    # Link to goal if specified
    if args.link_goal:
        link_to_goal(insight_id, args.link_goal)
    
    print(f"\n✅ Insight saved to Neo4j")


if __name__ == "__main__":
    main()
