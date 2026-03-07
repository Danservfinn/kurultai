#!/usr/bin/env python3
"""
Source Validator — Pre-execution URL validation for research tasks.

Extracts URLs from task content and validates responsiveness with a hard 5s
timeout per source. If ALL extracted sources are unreachable, the task should
be failed fast instead of burning 600-900s of Claude Code time.

This closes the operationalization gap for mongke's behavioral rule:
  WHEN research task assigned THEN validate source responsiveness <5s BEFORE query

Usage:
    from source_validator import validate_task_sources
    result = validate_task_sources(task_content)
    if result["block"]:
        # fail the task immediately
    # else proceed with execution

CLI:
    python3 source_validator.py "task content or file path"
"""

import re
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict

# Hard timeout per URL check — the whole point of this module
SOURCE_CHECK_TIMEOUT = 5

# URL extraction patterns (task body, not just verification sections)
URL_PATTERNS = [
    # Explicit URLs in task text
    r'https?://[^\s"\'<>\]\)]+',
    # API endpoint references
    r'(?:api|endpoint|url|base_url|host)[:\s=]+["\']?(https?://[^\s"\'<>\]]+)',
]

# Known-internal URLs that don't need validation (always reachable)
INTERNAL_SKIP = [
    r'^https?://localhost',
    r'^https?://127\.0\.0\.1',
    r'^https?://.*\.local(?::\d+)?/?$',
]


@dataclass
class SourceCheck:
    url: str
    reachable: bool
    latency_ms: int
    error: str = ""


def extract_urls(task_content: str) -> list[str]:
    """Extract unique URLs from task content."""
    urls = []
    for pattern in URL_PATTERNS:
        for match in re.finditer(pattern, task_content):
            url = match.group(0).rstrip('.,;:)\'">')
            # Normalize trailing slashes for dedup
            if url not in urls:
                urls.append(url)
    return urls


def _is_internal(url: str) -> bool:
    """Check if URL is internal/localhost (skip validation)."""
    return any(re.match(p, url) for p in INTERNAL_SKIP)


def check_url(url: str, timeout: int = SOURCE_CHECK_TIMEOUT) -> SourceCheck:
    """Check single URL responsiveness with hard timeout.

    Uses HEAD request first (fast), falls back to GET if HEAD returns 405.
    """
    start = time.time()
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Kurultai-SourceValidator/1.0")
        resp = urllib.request.urlopen(req, timeout=timeout)
        elapsed = int((time.time() - start) * 1000)
        code = resp.getcode()
        if code and 200 <= code < 400:
            return SourceCheck(url, True, elapsed)
        return SourceCheck(url, False, elapsed, f"HTTP {code}")
    except urllib.error.HTTPError as e:
        elapsed = int((time.time() - start) * 1000)
        if e.code == 405:
            # HEAD not allowed, try GET
            try:
                req2 = urllib.request.Request(url, method="GET")
                req2.add_header("User-Agent", "Kurultai-SourceValidator/1.0")
                resp2 = urllib.request.urlopen(req2, timeout=timeout)
                elapsed = int((time.time() - start) * 1000)
                code2 = resp2.getcode()
                if code2 and 200 <= code2 < 400:
                    return SourceCheck(url, True, elapsed)
                return SourceCheck(url, False, elapsed, f"HTTP {code2}")
            except Exception as e2:
                elapsed = int((time.time() - start) * 1000)
                return SourceCheck(url, False, elapsed, str(e2)[:100])
        # 4xx/5xx but server responded — source exists
        if 400 <= e.code < 500:
            return SourceCheck(url, True, elapsed, f"HTTP {e.code} (server responded)")
        return SourceCheck(url, False, elapsed, f"HTTP {e.code}")
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return SourceCheck(url, False, elapsed, f"{type(e).__name__}: {str(e)[:80]}")


def validate_task_sources(task_content: str) -> dict:
    """Validate all URLs in task content.

    Returns:
        {
            "urls_found": int,
            "urls_checked": int,
            "urls_reachable": int,
            "urls_failed": int,
            "block": bool,          # True if task should be failed fast
            "reason": str,          # Human-readable reason
            "checks": [SourceCheck],
            "elapsed_ms": int,
        }

    Block logic:
        - No URLs found: don't block (task may not need web sources)
        - Some URLs reachable: don't block
        - ALL URLs unreachable: BLOCK — fail fast
    """
    start = time.time()
    urls = extract_urls(task_content)

    # Filter out internal URLs
    external_urls = [u for u in urls if not _is_internal(u)]

    if not external_urls:
        return {
            "urls_found": len(urls),
            "urls_checked": 0,
            "urls_reachable": 0,
            "urls_failed": 0,
            "block": False,
            "reason": "no external URLs to validate",
            "checks": [],
            "elapsed_ms": 0,
        }

    # Check each URL (cap at 5 to stay under total time budget)
    checks = []
    for url in external_urls[:5]:
        checks.append(check_url(url))

    reachable = sum(1 for c in checks if c.reachable)
    failed = sum(1 for c in checks if not c.reachable)
    elapsed = int((time.time() - start) * 1000)

    block = reachable == 0 and failed > 0
    if block:
        failed_details = "; ".join(f"{c.url}: {c.error}" for c in checks if not c.reachable)
        reason = f"ALL {failed} source(s) unreachable: {failed_details[:200]}"
    else:
        reason = f"{reachable}/{len(checks)} sources reachable"

    return {
        "urls_found": len(urls),
        "urls_checked": len(checks),
        "urls_reachable": reachable,
        "urls_failed": failed,
        "block": block,
        "reason": reason,
        "checks": [asdict(c) for c in checks],
        "elapsed_ms": elapsed,
    }


def main():
    """CLI entry point for testing."""
    import os
    if len(sys.argv) < 2:
        print("Usage: python3 source_validator.py <task_content_or_file>")
        sys.exit(1)

    arg = sys.argv[1]
    if os.path.isfile(arg):
        with open(arg) as f:
            content = f.read()
    else:
        content = arg

    result = validate_task_sources(content)

    print(f"URLs found: {result['urls_found']}")
    print(f"URLs checked: {result['urls_checked']}")
    print(f"Reachable: {result['urls_reachable']}")
    print(f"Failed: {result['urls_failed']}")
    print(f"Block: {result['block']}")
    print(f"Reason: {result['reason']}")
    print(f"Elapsed: {result['elapsed_ms']}ms")

    for check in result["checks"]:
        icon = "+" if check["reachable"] else "-"
        print(f"  [{icon}] {check['url']} ({check['latency_ms']}ms) {check.get('error', '')}")

    sys.exit(1 if result["block"] else 0)


if __name__ == "__main__":
    main()
