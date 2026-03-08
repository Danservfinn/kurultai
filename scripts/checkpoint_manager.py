#!/usr/bin/env python3
"""
Checkpoint Manager - Save and resume agent execution state.

Provides crash recovery for the Kurultai multi-agent system by:
- Auto-saving checkpoints every 5 minutes during execution
- Sanitizing secrets before saving
- Allowing resume from last checkpoint after crash
- Auto-expiring checkpoints after 24 hours
- Enforcing 1MB size limit per checkpoint

Usage:
    python3 checkpoint-manager.py --save <task_id> <agent> <state_file>
    python3 checkpoint-manager.py --load <task_id>
    python3 checkpoint-manager.py --clear <task_id>
    python3 checkpoint-manager.py --cleanup
    python3 checkpoint-manager.py --list
"""

import argparse
import json
import os
import re
import sys
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

# Kurultai paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kurultai_paths import LOGS_DIR

# Configuration
CHECKPOINT_DIR = LOGS_DIR / "checkpoints"
CHECKPOINT_INDEX = CHECKPOINT_DIR / "index.json"
MAX_CHECKPOINT_SIZE = 1_000_000  # 1MB
CHECKPOINT_EXPIRY_HOURS = 24
AUTO_SAVE_INTERVAL = 300  # 5 minutes

# Secret patterns to sanitize
SANITIZE_PATTERNS = [
    # API keys
    (r'ANTHROPIC_API_KEY[=:]\s*["\']?[\w-]+["\']?', 'ANTHROPIC_API_KEY=***'),
    (r'ANTHROPIC_AUTH_TOKEN[=:]\s*["\']?[\w-]+["\']?', 'ANTHROPIC_AUTH_TOKEN=***'),
    (r'OPENAI_API_KEY[=:]\s*["\']?[\w-]+["\']?', 'OPENAI_API_KEY=***'),
    (r'GOOGLE_API_KEY[=:]\s*["\']?[\w-]+["\']?', 'GOOGLE_API_KEY=***'),
    (r'API_KEY[=:]\s*["\']?[\w-]{20,}["\']?', 'API_KEY=***'),
    # Tokens
    (r'token[=:]\s*["\']?[\w-]{20,}["\']?', 'token=***'),
    (r'access_token[=:]\s*["\']?[\w-]+["\']?', 'access_token=***'),
    (r'auth_token[=:]\s*["\']?[\w-]+["\']?', 'auth_token=***'),
    # Passwords
    (r'password[=:]\s*["\']?[^\s"\']{8,}["\']?', 'password=***'),
    (r'passwd[=:]\s*["\']?[^\s"\']{8,}["\']?', 'passwd=***'),
    # Secrets
    (r'secret[=:]\s*["\']?[\w-]{16,}["\']?', 'secret=***'),
    (r'client_secret[=:]\s*["\']?[\w-]+["\']?', 'client_secret=***'),
    # Connection strings
    (r'postgresql://[^:]+:[^@]+@', 'postgresql://user:***@'),
    (r'redis://[^:]+:[^@]+@', 'redis://user:***@'),
    (r'mongodb://[^:]+:[^@]+@', 'mongodb://user:***@'),
    # AWS
    (r'AWS_ACCESS_KEY_ID[=:]\s*["\']?[\w]+["\']?', 'AWS_ACCESS_KEY_ID=***'),
    (r'AWS_SECRET_ACCESS_KEY[=:]\s*["\']?[\w]+["\']?', 'AWS_SECRET_ACCESS_KEY=***'),
]

SANITIZE_REGEX = [(re.compile(p, re.IGNORECASE), r) for p, r in SANITIZE_PATTERNS]


@dataclass
class Checkpoint:
    """Represents an execution checkpoint."""
    id: str
    task_id: str
    agent: str
    created_at: str
    expires_at: str
    stage: str
    state: Dict[str, Any]
    size_bytes: int
    checksum: str

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


class CheckpointManager:
    """Manages execution checkpoints for crash recovery."""

    def __init__(self, checkpoint_dir: Path = None):
        self.checkpoint_dir = checkpoint_dir or CHECKPOINT_DIR
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _generate_id(self, task_id: str) -> str:
        """Generate a unique checkpoint ID."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"ckpt-{task_id[:8]}-{timestamp}"

    def _sanitize(self, content: str) -> str:
        """Remove secrets from content."""
        for pattern_obj, replacement in SANITIZE_REGEX:
            content = pattern_obj.sub(replacement, content)
        return content

    def _get_checkpoint_path(self, checkpoint_id: str) -> Path:
        """Get the file path for a checkpoint."""
        return self.checkpoint_dir / f"{checkpoint_id}.json"

    def _load_index(self) -> Dict[str, dict]:
        """Load the checkpoint index."""
        if CHECKPOINT_INDEX.exists():
            try:
                with open(CHECKPOINT_INDEX, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_index(self, index: Dict[str, dict]):
        """Save the checkpoint index."""
        with open(CHECKPOINT_INDEX, "w") as f:
            json.dump(index, f, indent=2)

    def _calculate_checksum(self, content: str) -> str:
        """Calculate SHA256 checksum of content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def save_checkpoint(
        self,
        task_id: str,
        agent: str,
        state: Dict[str, Any],
        stage: str = "execution"
    ) -> Optional[str]:
        """Save a checkpoint with secret sanitization.

        Args:
            task_id: The task being executed
            agent: The agent executing the task
            state: The execution state to save
            stage: Current execution stage

        Returns:
            Checkpoint ID if successful, None if failed
        """
        try:
            # Sanitize state content
            state_json = json.dumps(state, default=str)
            sanitized_json = self._sanitize(state_json)
            sanitized_state = json.loads(sanitized_json)

            # Check size limit
            if len(sanitized_json) > MAX_CHECKPOINT_SIZE:
                # Truncate large output fields
                if "output_so_far" in sanitized_state:
                    max_output = MAX_CHECKPOINT_SIZE // 2
                    if len(sanitized_state["output_so_far"]) > max_output:
                        sanitized_state["output_so_far"] = sanitized_state["output_so_far"][-max_output:]
                        sanitized_state["output_truncated"] = True

            # Re-encode after potential truncation
            final_json = json.dumps(sanitized_state, default=str)

            # Create checkpoint
            checkpoint_id = self._generate_id(task_id)
            now = datetime.now()
            expires = now + timedelta(hours=CHECKPOINT_EXPIRY_HOURS)

            checkpoint = Checkpoint(
                id=checkpoint_id,
                task_id=task_id,
                agent=agent,
                created_at=now.isoformat(),
                expires_at=expires.isoformat(),
                stage=stage,
                state=sanitized_state,
                size_bytes=len(final_json),
                checksum=self._calculate_checksum(final_json)
            )

            # Save checkpoint file
            checkpoint_path = self._get_checkpoint_path(checkpoint_id)
            with open(checkpoint_path, "w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2)

            # Update index
            index = self._load_index()
            index[task_id] = {
                "checkpoint_id": checkpoint_id,
                "agent": agent,
                "created_at": checkpoint.created_at,
                "expires_at": checkpoint.expires_at,
                "stage": stage,
                "size_bytes": checkpoint.size_bytes
            }
            self._save_index(index)

            return checkpoint_id

        except Exception as e:
            print(f"ERROR saving checkpoint: {e}")
            return None

    def load_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        """Load the most recent checkpoint for a task.

        Args:
            task_id: The task to resume

        Returns:
            Checkpoint if found and valid, None otherwise
        """
        try:
            index = self._load_index()

            if task_id not in index:
                return None

            checkpoint_info = index[task_id]
            checkpoint_id = checkpoint_info["checkpoint_id"]

            # Check expiry
            expires_at = datetime.fromisoformat(checkpoint_info["expires_at"])
            if datetime.now() > expires_at:
                # Checkpoint expired, remove it
                self.clear_checkpoint(task_id)
                return None

            # Load checkpoint file
            checkpoint_path = self._get_checkpoint_path(checkpoint_id)
            if not checkpoint_path.exists():
                # Index out of sync, clean up
                del index[task_id]
                self._save_index(index)
                return None

            with open(checkpoint_path, "r") as f:
                data = json.load(f)

            # Verify checksum
            state_json = json.dumps(data["state"], default=str)
            expected_checksum = self._calculate_checksum(state_json)
            if data.get("checksum") != expected_checksum:
                print(f"WARNING: Checkpoint checksum mismatch for {task_id}")
                # Still return it but warn

            return Checkpoint.from_dict(data)

        except Exception as e:
            print(f"ERROR loading checkpoint: {e}")
            return None

    def clear_checkpoint(self, task_id: str) -> bool:
        """Clear a checkpoint for a task.

        Args:
            task_id: The task whose checkpoint to clear

        Returns:
            True if checkpoint was cleared, False otherwise
        """
        try:
            index = self._load_index()

            if task_id not in index:
                return False

            checkpoint_id = index[task_id]["checkpoint_id"]
            checkpoint_path = self._get_checkpoint_path(checkpoint_id)

            # Remove file
            if checkpoint_path.exists():
                checkpoint_path.unlink()

            # Update index
            del index[task_id]
            self._save_index(index)

            return True

        except Exception as e:
            print(f"ERROR clearing checkpoint: {e}")
            return False

    def list_checkpoints(self) -> List[dict]:
        """List all checkpoints."""
        index = self._load_index()
        checkpoints = []

        for task_id, info in index.items():
            checkpoints.append({
                "task_id": task_id,
                "checkpoint_id": info["checkpoint_id"],
                "agent": info["agent"],
                "created_at": info["created_at"],
                "expires_at": info["expires_at"],
                "stage": info["stage"],
                "size_bytes": info["size_bytes"],
                "expired": datetime.now() > datetime.fromisoformat(info["expires_at"])
            })

        return sorted(checkpoints, key=lambda x: x["created_at"], reverse=True)

    def cleanup_expired(self) -> int:
        """Remove expired checkpoints.

        Returns:
            Number of checkpoints removed
        """
        removed = 0
        index = self._load_index()
        now = datetime.now()

        to_remove = []
        for task_id, info in index.items():
            expires_at = datetime.fromisoformat(info["expires_at"])
            if now > expires_at:
                to_remove.append(task_id)

        for task_id in to_remove:
            if self.clear_checkpoint(task_id):
                removed += 1

        return removed

    def get_resume_context(self, task_id: str) -> Optional[str]:
        """Get a formatted resume context for a task.

        Args:
            task_id: The task to resume

        Returns:
            Formatted resume context string, or None if no checkpoint
        """
        checkpoint = self.load_checkpoint(task_id)
        if not checkpoint:
            return None

        context = f"""
## CHECKPOINT RESUME

**Recovering from checkpoint:** {checkpoint.id}
**Created:** {checkpoint.created_at}
**Stage:** {checkpoint.stage}

### Previous State
```
{checkpoint.state.get('output_so_far', 'No output recorded')[-2000:]}
```

**Resume Instructions:**
- Continue from where execution left off
- Do not repeat work already done
- Report progress to squad chat if connected
"""
        return context.strip()


def main():
    parser = argparse.ArgumentParser(description="Checkpoint Manager")
    parser.add_argument("--save", nargs=3, metavar=("TASK_ID", "AGENT", "STATE_FILE"),
                       help="Save a checkpoint from state file")
    parser.add_argument("--load", metavar="TASK_ID", help="Load checkpoint for task")
    parser.add_argument("--clear", metavar="TASK_ID", help="Clear checkpoint for task")
    parser.add_argument("--cleanup", action="store_true", help="Remove expired checkpoints")
    parser.add_argument("--list", action="store_true", help="List all checkpoints")
    parser.add_argument("--context", metavar="TASK_ID", help="Get resume context for task")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    manager = CheckpointManager()

    if args.save:
        task_id, agent, state_file = args.save
        try:
            with open(state_file, "r") as f:
                state = json.load(f)
        except Exception as e:
            print(f"Error loading state file: {e}")
            sys.exit(1)

        checkpoint_id = manager.save_checkpoint(task_id, agent, state)
        if checkpoint_id:
            print(f"Saved checkpoint: {checkpoint_id}")
        else:
            print("Failed to save checkpoint")
            sys.exit(1)

    elif args.load:
        checkpoint = manager.load_checkpoint(args.load)
        if checkpoint:
            if args.json:
                print(json.dumps(checkpoint.to_dict(), indent=2))
            else:
                print(f"Checkpoint: {checkpoint.id}")
                print(f"Task: {checkpoint.task_id}")
                print(f"Agent: {checkpoint.agent}")
                print(f"Stage: {checkpoint.stage}")
                print(f"Created: {checkpoint.created_at}")
                print(f"Expires: {checkpoint.expires_at}")
                print(f"Size: {checkpoint.size_bytes} bytes")
                print(f"\nState:")
                print(json.dumps(checkpoint.state, indent=2, default=str)[:1000])
        else:
            print("No checkpoint found")
            sys.exit(1)

    elif args.clear:
        if manager.clear_checkpoint(args.clear):
            print(f"Cleared checkpoint for {args.clear}")
        else:
            print(f"No checkpoint to clear for {args.clear}")

    elif args.cleanup:
        removed = manager.cleanup_expired()
        print(f"Removed {removed} expired checkpoints")

    elif args.list:
        checkpoints = manager.list_checkpoints()
        if args.json:
            print(json.dumps(checkpoints, indent=2))
        else:
            if not checkpoints:
                print("No checkpoints")
            else:
                for cp in checkpoints:
                    status = "EXPIRED" if cp["expired"] else "active"
                    print(f"{cp['task_id'][:8]}: {cp['stage']} ({cp['agent']}) [{status}]")

    elif args.context:
        context = manager.get_resume_context(args.context)
        if context:
            print(context)
        else:
            print("No checkpoint found")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
