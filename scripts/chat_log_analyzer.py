#!/usr/bin/env python3
"""
Chat Log Analyzer for Agent Reflections

Extracts and summarizes chat logs from the last N hours for agent review.
Integrates with meta-reflection system.

Usage:
    python3 chat_log_analyzer.py --hours 2 --agent temujin
    python3 chat_log_analyzer.py --hours 2 --summary
"""

import argparse
import json
import os
import glob
from datetime import datetime, timedelta
from pathlib import Path

SESSIONS_DIR = "/Users/kublai/.openclaw/agents/main/sessions"
ARCHITECTURE_FILE = "/Users/kublai/.openclaw/agents/main/ARCHITECTURE.md"

def get_recent_sessions(hours=2, max_messages_per_session=100, max_sessions=10):
    """Get session files from last N hours with memory bounds."""
    cutoff = datetime.now() - timedelta(hours=hours)
    sessions = []

    # Find all session JSONL files
    session_files = glob.glob(f"{SESSIONS_DIR}/*.jsonl")

    # Sort by modification time (newest first) and limit
    session_files_with_mtime = []
    for filepath in session_files:
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            if mtime >= cutoff:
                session_files_with_mtime.append((filepath, mtime))
        except Exception:
            pass

    # Sort by mtime descending and limit
    session_files_with_mtime.sort(key=lambda x: x[1], reverse=True)
    session_files_with_mtime = session_files_with_mtime[:max_sessions]

    for filepath, mtime in session_files_with_mtime:
        sessions.append({
            'file': filepath,
            'modified': mtime,
            'messages': []
        })

    # Read messages from each session with per-session limit
    for session in sessions:
        try:
            msg_count = 0
            with open(session['file'], 'r') as f:
                for line in f:
                    if msg_count >= max_messages_per_session:
                        break
                    try:
                        msg = json.loads(line)
                        # Only include messages from last N hours
                        msg_time = datetime.fromtimestamp(msg.get('timestamp', 0) / 1000)
                        if msg_time >= cutoff:
                            session['messages'].append(msg)
                            msg_count += 1
                    except (json.JSONDecodeError, KeyError, ValueError):
                        pass
        except Exception:
            pass

    return sessions

def analyze_chat_logs(hours=2, max_messages_per_session=100, max_sessions=10):
    """Analyze chat logs and extract insights"""
    sessions = get_recent_sessions(hours, max_messages_per_session, max_sessions)
    
    analysis = {
        'period_hours': hours,
        'timestamp': datetime.now().isoformat(),
        'total_sessions': len(sessions),
        'total_messages': sum(len(s['messages']) for s in sessions),
        'sessions': [],
        'key_events': [],
        'system_interactions': [],
        'potential_issues': []
    }
    
    for session in sessions:
        session_summary = {
            'file': os.path.basename(session['file']),
            'message_count': len(session['messages']),
            'modified': session['modified'].isoformat(),
            'participants': set(),
            'topics': []
        }
        
        for msg in session['messages']:
            role = msg.get('role', 'unknown')
            content = msg.get('content', [])
            
            # Extract participant
            if role == 'user':
                session_summary['participants'].add('human')
            elif role == 'assistant':
                session_summary['participants'].add(msg.get('model', 'agent'))
            
            # Extract text content
            text = ''
            for c in content:
                if c.get('type') == 'text':
                    text += c.get('text', '')[:200]
            
            # Look for system-related keywords
            keywords = ['task', 'spawn', 'agent', 'error', 'failed', 'success', 'complete', 'queue']
            for kw in keywords:
                if kw.lower() in text.lower():
                    analysis['system_interactions'].append({
                        'keyword': kw,
                        'excerpt': text[:100],
                        'timestamp': msg.get('timestamp')
                    })
        
        session_summary['participants'] = list(session_summary['participants'])
        analysis['sessions'].append(session_summary)
    
    # Identify potential issues
    error_keywords = ['error', 'failed', 'crash', 'timeout', 'exception']
    for interaction in analysis['system_interactions']:
        for ek in error_keywords:
            if ek in interaction['excerpt'].lower():
                analysis['potential_issues'].append(interaction)
    
    return analysis

def get_architecture_context():
    """Load relevant architecture context"""
    if not os.path.exists(ARCHITECTURE_FILE):
        return "Architecture file not found"
    
    try:
        with open(ARCHITECTURE_FILE, 'r') as f:
            content = f.read()
            
        # Extract key sections relevant to task/spawning system
        sections = []
        current_section = None
        
        for line in content.split('\n'):
            if line.startswith('## ') or line.startswith('### '):
                current_section = line
            
            # Capture relevant sections
            if current_section and any(kw in current_section.lower() for kw in 
                ['task', 'spawn', 'agent', 'kurultai', 'heartbeat', 'queue']):
                sections.append(line)
        
        return '\n'.join(sections[:100])  # Limit context
    except Exception as e:
        return f"Error loading architecture: {e}"

def generate_chat_review(hours=2):
    """Generate chat log review for agent reflection"""
    analysis = analyze_chat_logs(hours)
    arch_context = get_architecture_context()
    
    review = f"""# Chat Log Review (Last {hours} Hours)

**Generated:** {analysis['timestamp']}

---

## Summary

- **Total sessions:** {analysis['total_sessions']}
- **Total messages:** {analysis['total_messages']}
- **Period:** Last {hours} hour(s)

---

## Sessions Analyzed

"""
    
    for session in analysis['sessions']:
        review += f"""
### {session['file']}
- Messages: {session['message_count']}
- Participants: {', '.join(session['participants'])}
- Modified: {session['modified'][:19]}
"""
    
    review += f"""
---

## System Interactions

**Keywords detected:** task, spawn, agent, error, failed, success, complete, queue

"""
    
    if analysis['system_interactions']:
        for i, interaction in enumerate(analysis['system_interactions'][:10], 1):
            review += f"{i}. **{interaction['keyword']}**: {interaction['excerpt'][:80]}...\n"
    else:
        review += "*No system-related interactions detected*\n"
    
    review += f"""
---

## Potential Issues

"""
    
    if analysis['potential_issues']:
        for issue in analysis['potential_issues'][:5]:
            review += f"- ⚠️ {issue['excerpt'][:80]}...\n"
    else:
        review += "*No obvious errors detected*\n"
    
    review += f"""
---

## Architecture Context

**Relevant sections from ARCHITECTURE.md:**

```
{arch_context[:1000]}
```

---

## Critical Evaluation Questions

Based on the chat logs and architecture:

### 1. System Performance Observed in Chats

- What task/spawning activities occurred?
- Were there any errors or failures visible?
- Did users report any issues?
- What worked well?

**Your observations:**
```
[Agent responds here]
```

---

### 2. Architecture Alignment

Comparing chat logs to ARCHITECTURE.md:

- Is the system behaving as designed?
- Any gaps between design and reality?
- Features working differently than intended?

**Your assessment:**
```
[Agent responds here]
```

---

### 3. Improvement Opportunities

From chat patterns, what could be better?

- Common user requests that aren't automated?
- Repeated issues that need fixing?
- Missing features users expect?

**Your proposals:**
```
[Agent responds here]
```

---

*Generated by chat_log_analyzer.py*
"""
    
    return review

def main():
    parser = argparse.ArgumentParser(description='Analyze chat logs for agent reflections')
    parser.add_argument('--hours', type=int, default=2, help='Hours to look back')
    parser.add_argument('--agent', help='Agent name (for personalized review)')
    parser.add_argument('--summary', action='store_true', help='Show summary only')
    
    args = parser.parse_args()
    
    if args.summary:
        analysis = analyze_chat_logs(args.hours)
        print(f"Chat Log Summary (Last {args.hours} Hours)")
        print(f"=" * 50)
        print(f"Total sessions: {analysis['total_sessions']}")
        print(f"Total messages: {analysis['total_messages']}")
        print(f"System interactions: {len(analysis['system_interactions'])}")
        print(f"Potential issues: {len(analysis['potential_issues'])}")
    else:
        review = generate_chat_review(args.hours)
        
        if args.agent:
            print(f"\n{'='*60}")
            print(f"CHAT LOG REVIEW FOR: {args.agent.upper()}")
            print(f"{'='*60}\n")
        
        print(review)

if __name__ == "__main__":
    main()
