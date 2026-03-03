#!/usr/bin/env python3
"""
Kublai Feedback Review System

Kublai reviews agent feedback and decides what to implement.
Creates tasks for approved proposals.

Usage:
    python3 kublai_review_feedback.py --list              # List pending feedback
    python3 kublai_review_feedback.py --review <id>       # Review specific feedback
    python3 kublai_review_feedback.py --approve <id> --assign temujin --task "Implement X"
    python3 kublai_review_feedback.py --reject <id> --reason "Not now"
"""

import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from neo4j_task_tracker import get_tracker

def list_pending():
    """List all pending feedback for Kublai"""
    tracker = get_tracker()
    
    with tracker.driver.session() as session:
        result = session.run("""
            MATCH (f:AgentFeedback {status: 'pending_review'})
            RETURN f ORDER BY 
                CASE f.priority 
                    WHEN 'CRITICAL' THEN 1 
                    WHEN 'HIGH' THEN 2 
                    WHEN 'MEDIUM' THEN 3 
                    ELSE 4 
                END,
                f.submitted DESC
        """)
        feedback = [dict(r['f']) for r in result]
    
    tracker.close()
    
    print(f"\n{'='*70}")
    print(f"PENDING FEEDBACK FOR KUBLAI ({len(feedback)} items)")
    print(f"{'='*70}\n")
    
    for i, f in enumerate(feedback, 1):
        priority = f.get('priority', 'MEDIUM')
        agent = f.get('agent', 'unknown')
        submitted = f.get('submitted', 'unknown')
        feedback_text = f.get('feedback', '')[:100]
        
        # Priority emoji
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(priority, "⚪")
        
        print(f"{i}. {emoji} [{priority}] {agent}")
        print(f"   Submitted: {str(submitted)[:19] if submitted else 'N/A'}")
        print(f"   Preview: {feedback_text}...")
        print(f"   ID: {f.get('id', 'N/A')}")
        print()
    
    return feedback

def review_feedback(feedback_id):
    """Review specific feedback"""
    tracker = get_tracker()
    
    with tracker.driver.session() as session:
        result = session.run("""
            MATCH (f:AgentFeedback {id: $id})
            RETURN f
        """, id=feedback_id)
        record = result.single()
    
    tracker.close()
    
    if not record:
        print(f"Feedback {feedback_id} not found")
        return None
    
    f = dict(record['f'])
    
    print(f"\n{'='*70}")
    print(f"FEEDBACK REVIEW: {f.get('id')}")
    print(f"{'='*70}\n")
    
    print(f"Agent: {f.get('agent')}")
    print(f"Priority: {f.get('priority')}")
    print(f"Submitted: {str(f.get('submitted', ''))[:19]}")
    print(f"\nFeedback:\n{f.get('feedback', 'N/A')}\n")
    print(f"Proposals:\n{f.get('proposals', '[]')}\n")
    
    return f

def approve_feedback(feedback_id, assign_agent, task_desc, priority="normal"):
    """Approve feedback and create task"""
    tracker = get_tracker()
    
    # Create task for the assigned agent
    label = f"{assign_agent}-{int(datetime.now().timestamp())}"
    
    with tracker.driver.session() as session:
        # Create task node
        session.run("""
            MATCH (a:Agent {name: $agent})
            CREATE (t:Task {
                label: $label,
                agent: $agent,
                task: $task,
                priority: $priority,
                source: 'kublai_approved_feedback',
                feedback_id: $feedback_id,
                status: 'ready',
                created: datetime(),
                retry_count: 0,
                max_retries: 3
            })
            CREATE (a)-[:EXECUTED]->(t)
        """,
        agent=assign_agent,
        label=label,
        task=task_desc,
        priority=priority,
        feedback_id=feedback_id
        )
        
        # Update feedback status
        session.run("""
            MATCH (f:AgentFeedback {id: $id})
            SET f.status = 'approved',
                f.approved_by = 'kublai',
                f.approved_at = datetime(),
                f.task_label = $label
        """, id=feedback_id, label=label)
    
    tracker.close()
    
    print(f"✓ Feedback approved!")
    print(f"  Task created: {label}")
    print(f"  Assigned to: {assign_agent}")
    print(f"  Task: {task_desc[:60]}...")
    
    # Also write to spawn queue for immediate processing
    from chat_to_task import queue_spawn
    
    # Minimal classification for manual task
    classification = {
        "agent": assign_agent,
        "model": "qwen3.5-plus" if assign_agent != "jochi" else "MiniMax-M2.5"
    }
    
    queue_spawn(
        classification=classification,
        message=task_desc,
        priority=priority,
        mode="run",
        continuous=False
    )
    
    print(f"  → Added to spawn queue for immediate execution")

def reject_feedback(feedback_id, reason):
    """Reject feedback"""
    tracker = get_tracker()
    
    with tracker.driver.session() as session:
        session.run("""
            MATCH (f:AgentFeedback {id: $id})
            SET f.status = 'rejected',
                f.rejected_by = 'kublai',
                f.rejected_at = datetime(),
                f.rejection_reason = $reason
        """, id=feedback_id, reason=reason)
    
    tracker.close()
    
    print(f"✓ Feedback rejected")
    print(f"  Reason: {reason}")

def kublai_summary():
    """Get summary for Kublai's review session"""
    tracker = get_tracker()
    
    with tracker.driver.session() as session:
        # Count feedback by status
        result = session.run("""
            MATCH (f:AgentFeedback)
            RETURN 
                f.status AS status,
                count(f) AS count
        """)
        status_counts = {r['status']: r['count'] for r in result}
        
        # Count by priority
        result = session.run("""
            MATCH (f:AgentFeedback {status: 'pending_review'})
            RETURN 
                f.priority AS priority,
                count(f) AS count
        """)
        priority_counts = {r['priority']: r['count'] for r in result}
        
        # Recent approved
        result = session.run("""
            MATCH (f:AgentFeedback {status: 'approved'})
            RETURN f ORDER BY f.approved_at DESC LIMIT 5
        """)
        recent_approved = [dict(r['f']) for r in result]
    
    tracker.close()
    
    print(f"\n{'='*70}")
    print(f"KUBLAI FEEDBACK REVIEW SUMMARY")
    print(f"{'='*70}\n")
    
    print(f"Feedback Status:")
    print(f"  Pending:   {status_counts.get('pending_review', 0)}")
    print(f"  Approved:  {status_counts.get('approved', 0)}")
    print(f"  Rejected:  {status_counts.get('rejected', 0)}")
    print()
    
    print(f"Pending by Priority:")
    for p in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
        count = priority_counts.get(p, 0)
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}.get(p, "⚪")
        print(f"  {emoji} {p}: {count}")
    print()
    
    if recent_approved:
        print(f"Recently Approved ({len(recent_approved)}):")
        for f in recent_approved:
            print(f"  - {f.get('agent')}: {f.get('task_label', 'N/A')}")
    print()

def main():
    parser = argparse.ArgumentParser(description='Kublai feedback review system')
    parser.add_argument('--list', action='store_true', help='List pending feedback')
    parser.add_argument('--summary', action='store_true', help='Show review summary')
    parser.add_argument('--review', metavar='ID', help='Review specific feedback')
    parser.add_argument('--approve', metavar='ID', help='Approve feedback')
    parser.add_argument('--assign', help='Agent to assign task to (with --approve)')
    parser.add_argument('--task', help='Task description (with --approve)')
    parser.add_argument('--priority', default='normal', help='Task priority (with --approve)')
    parser.add_argument('--reject', metavar='ID', help='Reject feedback')
    parser.add_argument('--reason', help='Rejection reason (with --reject)')
    
    args = parser.parse_args()
    
    if args.summary:
        kublai_summary()
    elif args.list:
        list_pending()
    elif args.review:
        review_feedback(args.review)
    elif args.approve:
        if not args.assign or not args.task:
            print("Error: --approve requires --assign and --task")
            sys.exit(1)
        approve_feedback(args.approve, args.assign, args.task, args.priority)
    elif args.reject:
        if not args.reason:
            print("Error: --reject requires --reason")
            sys.exit(1)
        reject_feedback(args.reject, args.reason)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
