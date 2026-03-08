#!/usr/bin/env python3
"""
Prompt Cache - File-based caching for optimized prompts.

Provides caching to avoid re-optimizing similar tasks.
Cache stores task hash → optimized prompt with TTL support.
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
import threading

# Default cache directory
DEFAULT_CACHE_DIR = os.path.expanduser("~/.openclaw/cache/prompts")
DEFAULT_TTL_SECONDS = 3600  # 1 hour
MAX_CACHE_SIZE = 500  # Max entries before pruning


@dataclass
class CacheEntry:
    """A cached prompt optimization result."""
    task_hash: str
    agent_type: str
    original_task: str
    optimized_prompt: str
    metadata: Dict[str, Any]
    created_at: float
    expires_at: float
    hit_count: int = 0


class PromptCache:
    """File-based cache for prompt optimizations."""

    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _hash_task(self, task: str, agent_type: str, context: Optional[Dict] = None) -> str:
        """Generate a hash key for task + agent + context."""
        content = f"{agent_type}:{task}"
        if context:
            # Sort context keys for consistent hashing
            content += ":" + json.dumps(context, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _cache_path(self, task_hash: str) -> Path:
        """Get the cache file path for a hash."""
        return self.cache_dir / f"{task_hash}.json"

    def get(self, task: str, agent_type: str, context: Optional[Dict] = None) -> Optional[CacheEntry]:
        """
        Retrieve a cached optimization if it exists and is not expired.

        Returns None if not found or expired.
        """
        task_hash = self._hash_task(task, agent_type, context)
        cache_file = self._cache_path(task_hash)

        with self._lock:
            if not cache_file.exists():
                return None

            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)

                entry = CacheEntry(**data)

                # Check expiration
                if time.time() > entry.expires_at:
                    cache_file.unlink()
                    return None

                # Update hit count
                entry.hit_count += 1
                with open(cache_file, 'w') as f:
                    json.dump(asdict(entry), f, indent=2)

                return entry

            except (json.JSONDecodeError, KeyError, TypeError):
                # Corrupted cache entry, remove it
                cache_file.unlink(missing_ok=True)
                return None

    def set(
        self,
        task: str,
        agent_type: str,
        optimized_prompt: str,
        metadata: Dict[str, Any],
        context: Optional[Dict] = None,
        ttl_seconds: Optional[int] = None
    ) -> CacheEntry:
        """
        Store an optimized prompt in the cache.

        Returns the created cache entry.
        """
        task_hash = self._hash_task(task, agent_type, context)
        ttl = ttl_seconds or self.ttl_seconds
        now = time.time()

        entry = CacheEntry(
            task_hash=task_hash,
            agent_type=agent_type,
            original_task=task[:500],  # Truncate for storage
            optimized_prompt=optimized_prompt,
            metadata=metadata,
            created_at=now,
            expires_at=now + ttl,
            hit_count=0
        )

        with self._lock:
            cache_file = self._cache_path(task_hash)
            with open(cache_file, 'w') as f:
                json.dump(asdict(entry), f, indent=2)

            # Prune if needed
            self._prune_if_needed()

        return entry

    def _prune_if_needed(self):
        """Prune old entries if cache exceeds max size."""
        entries = list(self.cache_dir.glob("*.json"))
        if len(entries) <= MAX_CACHE_SIZE:
            return

        # Sort by created_at (oldest first)
        entry_data = []
        for entry_file in entries:
            try:
                with open(entry_file, 'r') as f:
                    data = json.load(f)
                entry_data.append((entry_file, data.get('created_at', 0)))
            except (json.JSONDecodeError, KeyError):
                entry_file.unlink(missing_ok=True)

        entry_data.sort(key=lambda x: x[1])

        # Remove oldest entries to get under limit
        to_remove = len(entries) - MAX_CACHE_SIZE + 50  # Remove extra for buffer
        for entry_file, _ in entry_data[:to_remove]:
            entry_file.unlink(missing_ok=True)

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            for entry_file in self.cache_dir.glob("*.json"):
                entry_file.unlink(missing_ok=True)

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        entries = list(self.cache_dir.glob("*.json"))
        now = time.time()

        total_hits = 0
        expired = 0
        active = 0

        for entry_file in entries:
            try:
                with open(entry_file, 'r') as f:
                    data = json.load(f)
                total_hits += data.get('hit_count', 0)
                if data.get('expires_at', 0) < now:
                    expired += 1
                else:
                    active += 1
            except (json.JSONDecodeError, KeyError):
                pass

        return {
            "total_entries": len(entries),
            "active_entries": active,
            "expired_entries": expired,
            "total_hits": total_hits,
            "cache_dir": str(self.cache_dir)
        }


# Global cache instance
_cache_instance: Optional[PromptCache] = None


def get_cache() -> PromptCache:
    """Get the global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = PromptCache()
    return _cache_instance


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prompt cache management")
    parser.add_argument("--stats", action="store_true", help="Show cache statistics")
    parser.add_argument("--clear", action="store_true", help="Clear all cached entries")
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS, help="TTL in seconds")

    args = parser.parse_args()

    cache = PromptCache(ttl_seconds=args.ttl)

    if args.stats:
        print(json.dumps(cache.stats(), indent=2))
    elif args.clear:
        cache.clear()
        print("Cache cleared")
    else:
        parser.print_help()
