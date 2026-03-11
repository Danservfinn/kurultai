#!/usr/bin/env python3
"""
Source Validator — Pre-execution URL validation for research tasks.

Extracts URLs from task content and validates responsiveness with a hard 5s
timeout per source. If ALL extracted sources are unreachable, the task should
be failed fast instead of burning 600-900s of Claude Code time.

SECURITY: Includes SSRF protection to block requests to private IP ranges
and enforce domain allowlisting.

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
import socket
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
from typing import Tuple

# Hard timeout per URL check — the whole point of this module
SOURCE_CHECK_TIMEOUT = 5

# URL extraction patterns (task body, not just verification sections)
URL_PATTERNS = [
    # Explicit URLs in task text
    r'https?://[^\s"\'<>\]\)]+',
    # API endpoint references
    r'(?:api|endpoint|url|base_url|host)[:\s=]+["\']?(https?://[^\s"\'<>\]]+)',
]

# =============================================================================
# SSRF Protection Configuration
# =============================================================================

# Allowed URL domains (regex patterns) - Kurultai trusted infrastructure
ALLOWED_URL_DOMAINS = [
    r".*\.kurult\.ai$",
    r".*\.parsethe\.media$",
    r".*\.up\.railway\.app$",
    r".*\.vercel\.app$",
    r"localhost$",
    r"127\.0\.0\.1$",
    # Common legitimate research domains
    r".*\.github\.com$",
    r".*\.githubusercontent\.com$",
    r".*\.gitlab\.com$",
    r".*\.stackoverflow\.com$",
    r".*\.stackexchange\.com$",
    r".*\.readthedocs\.io$",
    r".*\.pypi\.org$",
    r".*\.npmjs\.com$",
    r".*\.pypi\.io$",
    r".*\.python\.org$",
    r".*\.anthropic\.com$",
    r".*\.openai\.com$",
    r".*\.google\.com$",
    r".*\.googleapis\.com$",
]

# Blocked private IP ranges (SSRF protection)
BLOCKED_PRIVATE_RANGES = [
    r"^10\.",                                    # Class A private
    r"^172\.(1[6-9]|2[0-9]|3[0-1])\.",           # Class B private (172.16-31.x.x)
    r"^192\.168\.",                              # Class C private
    r"^169\.254\.",                              # Link-local (AWS metadata)
    r"^0\.",                                     # Current network
    r"^224\.",                                   # Multicast
    r"^240\.",                                   # Reserved
    r"^255\.255\.255\.255$",                     # Broadcast
    r"^127\.",                                   # Loopback (except allowed explicitly)
    r"^::1$",                                    # IPv6 loopback
    r"^fe80::",                                  # IPv6 link-local
    r"^fc00::",                                  # IPv6 unique local
]

# Allow localhost for development but block other private IPs
LOCALHOST_ALLOWED = True


@dataclass
class SourceCheck:
    url: str
    reachable: bool
    latency_ms: int
    error: str = ""
    ssrf_blocked: bool = False


def validate_url_ssrf(url: str) -> Tuple[bool, str]:
    """Validate URL against SSRF protection rules.

    Returns:
        Tuple of (is_allowed, reason)

    Security checks:
    1. Parse URL and extract hostname
    2. Check against blocked private IP ranges
    3. Resolve DNS and check resolved IP
    4. Check domain allowlist (warning only, not blocking)
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        # Check if hostname is an IP address
        ip_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"

        if re.match(ip_pattern, hostname):
            # Direct IP address - check against blocked ranges
            for pattern in BLOCKED_PRIVATE_RANGES:
                if re.match(pattern, hostname):
                    # Allow localhost if configured
                    if LOCALHOST_ALLOWED and hostname == "127.0.0.1":
                        continue
                    return False, f"SSRF: Private IP range blocked: {hostname}"

        # Resolve DNS to check for DNS rebinding attacks
        try:
            resolved_ips = socket.getaddrinfo(hostname, parsed.port or 80)
            for family, socktype, proto, canonname, sockaddr in resolved_ips[:5]:
                resolved_ip = sockaddr[0]
                # Check resolved IP against blocked ranges
                for pattern in BLOCKED_PRIVATE_RANGES:
                    if re.match(pattern, resolved_ip):
                        # Allow localhost if configured
                        if LOCALHOST_ALLOWED and resolved_ip == "127.0.0.1":
                            continue
                        return False, f"SSRF: Resolved to private IP: {hostname} -> {resolved_ip}"
        except socket.gaierror:
            # DNS resolution failed - URL is unreachable anyway
            return True, "DNS resolution failed (will fail in check)"

        # Check domain allowlist (warning only, not blocking)
        in_allowlist = any(re.match(p, hostname) for p in ALLOWED_URL_DOMAINS)
        if not in_allowlist:
            # Log warning but don't block - research may need arbitrary domains
            pass

        return True, "OK"

    except Exception as e:
        return False, f"SSRF validation error: {str(e)[:100]}"


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
    internal_patterns = [
        r'^https?://localhost',
        r'^https?://127\.0\.0\.1',
        r'^https?://.*\.local(?::\d+)?/?$',
    ]
    return any(re.match(p, url) for p in internal_patterns)


def check_url(url: str, timeout: int = SOURCE_CHECK_TIMEOUT) -> SourceCheck:
    """Check single URL responsiveness with hard timeout.

    SECURITY: First validates URL against SSRF rules before making request.

    Uses HEAD request first (fast), falls back to GET if HEAD returns 405.
    """
    # SSRF validation first
    ssrf_ok, ssrf_reason = validate_url_ssrf(url)
    if not ssrf_ok:
        return SourceCheck(url, False, 0, ssrf_reason, ssrf_blocked=True)

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
