#!/usr/bin/env python3
"""Fail if launchd-active runtime paths depend on the retired graph store."""
from __future__ import annotations

import ast
import os
import plistlib
import re
import sys
from pathlib import Path

HOME = Path(os.environ.get("HOME", "/Users/kublai")).expanduser()
LAUNCH_AGENTS = HOME / "Library" / "LaunchAgents"
REPO_ROOT = HOME / "kurultai" / "kublai-repo"
OPENCLAW_SCRIPTS = HOME / ".openclaw" / "agents" / "main" / "scripts"
OPENCLAW_ROOT = HOME / ".openclaw"

ACTIVE_LABEL_RE = re.compile(r"(kurultai|openclaw|hermes|brain)", re.IGNORECASE)
BLOCKED_PATTERNS = [
    re.compile(r"^\s*from\s+neo4j\b", re.IGNORECASE),
    re.compile(r"^\s*import\s+neo4j\b", re.IGNORECASE),
    re.compile(r"^\s*from\s+neo4j_task_tracker\b", re.IGNORECASE),
    re.compile(r"^\s*import\s+neo4j_task_tracker\b", re.IGNORECASE),
    re.compile(r"^\s*from\s+neo4j_v2_core\b", re.IGNORECASE),
    re.compile(r"^\s*import\s+neo4j_v2_core\b", re.IGNORECASE),
    re.compile(r"^\s*from\s+neo4j_calendar\b", re.IGNORECASE),
    re.compile(r"^\s*import\s+neo4j_calendar\b", re.IGNORECASE),
    re.compile(r"\bGraphDatabase(?:\.driver)?\b"),
    re.compile(r"\bcypher-shell\b"),
    re.compile(r"bolt://localhost:7687"),
    re.compile(r"\bNEO4J_[A-Z_]+\b"),
    re.compile(r"neo4j\.env", re.IGNORECASE),
]

RUNTIME_EXTS = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".cjs"}
SEARCH_ROOTS = [
    OPENCLAW_SCRIPTS,
    OPENCLAW_ROOT / "scripts",
    REPO_ROOT,
    REPO_ROOT / "tools",
    REPO_ROOT / "kublai",
    HOME / "Developer" / "brain-sync",
    HOME / ".hermes" / "hermes-agent",
]


def _read_plist(path: Path) -> dict:
    try:
        with path.open("rb") as f:
            return plistlib.load(f)
    except Exception:
        return {}


def _is_runtime_file(path: Path) -> bool:
    return path.exists() and path.is_file() and path.suffix in RUNTIME_EXTS


def _resolve_module(module: str, importer: Path | None = None) -> Path | None:
    parts = module.split(".")
    roots = []
    if importer is not None:
        roots.append(importer.parent)
    roots.extend(SEARCH_ROOTS)
    for root in roots:
        direct = root.joinpath(*parts).with_suffix(".py")
        package = root.joinpath(*parts, "__init__.py")
        if _is_runtime_file(direct):
            return direct.resolve()
        if _is_runtime_file(package):
            return package.resolve()
    return None


def _extract_program_files(plist_path: Path) -> set[Path]:
    data = _read_plist(plist_path)
    label = str(data.get("Label") or "")
    if not ACTIVE_LABEL_RE.search(label):
        return set()
    if label == "homebrew.mxcl.neo4j":
        return set()
    args = [str(a) for a in data.get("ProgramArguments") or []]
    workdir = Path(str(data.get("WorkingDirectory") or plist_path.parent)).expanduser()
    files: set[Path] = set()
    for idx, arg in enumerate(args):
        candidate = Path(arg).expanduser()
        if not candidate.is_absolute():
            candidate = workdir / candidate
        if _is_runtime_file(candidate):
            files.add(candidate.resolve())
        if arg == "-m" and idx + 1 < len(args):
            module_path = _resolve_module(args[idx + 1], workdir)
            if module_path:
                files.add(module_path)
    return files


_ABS_RUNTIME_RE = re.compile(r"(/Users/kublai/[^\s\"'`<>|;&]+(?:\.py|\.sh|\.bash|\.zsh|\.js|\.mjs|\.cjs))")
_REL_RUNTIME_RE = re.compile(r"(?<![-\w./])([A-Za-z0-9_.-]+(?:\.py|\.sh|\.bash|\.zsh|\.js|\.mjs|\.cjs))")


def _extract_referenced_runtime_files(path: Path, text: str) -> set[Path]:
    files: set[Path] = set()
    for match in _ABS_RUNTIME_RE.finditer(text):
        candidate = Path(match.group(1)).expanduser()
        if _is_runtime_file(candidate):
            files.add(candidate.resolve())
    # Shell wrappers commonly invoke relative scripts. Python files, by
    # contrast, often mention script names in docs/help text; only follow
    # relative names from explicit dynamic-load/invocation lines.
    if path.suffix in {".sh", ".bash", ".zsh"}:
        candidate_lines = text.splitlines()
    else:
        candidate_lines = [
            line for line in text.splitlines()
            if (
                "spec_from_file_location" in line
                or "run([" in line
                or "subprocess." in line
                or "SCRIPTS_DIR" in line
                or "Path(__file__)" in line
            )
        ]
    for line in candidate_lines:
        for match in _REL_RUNTIME_RE.finditer(line):
            candidate = path.parent / match.group(1)
            if _is_runtime_file(candidate):
                files.add(candidate.resolve())
    return files


def _extract_python_imports(path: Path, text: str) -> set[Path]:
    files: set[Path] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return files
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_path = _resolve_module(alias.name, path)
                if module_path:
                    files.add(module_path)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_path = _resolve_module(node.module, path)
            if module_path:
                files.add(module_path)
    return files


def discover_active_files() -> set[Path]:
    pending: list[Path] = []
    seen: set[Path] = set()
    for plist in LAUNCH_AGENTS.glob("*.plist"):
        pending.extend(sorted(_extract_program_files(plist)))

    while pending:
        path = pending.pop()
        if path in seen or not _is_runtime_file(path):
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        pending.extend(_extract_referenced_runtime_files(path, text) - seen)
        if path.suffix == ".py":
            pending.extend(_extract_python_imports(path, text) - seen)
    return seen


def _is_scannable_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if stripped.startswith("//"):
        return False
    return True


def scan_file(path: Path) -> list[str]:
    failures: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [f"{path}: unreadable: {exc}"]
    for lineno, line in enumerate(text.splitlines(), 1):
        if not _is_scannable_line(line):
            continue
        if any(pattern.search(line) for pattern in BLOCKED_PATTERNS):
            failures.append(f"{path}:{lineno}: {line.strip()[:180]}")
    return failures


def main() -> int:
    active_files = discover_active_files()
    failures: list[str] = []
    for path in sorted(active_files):
        failures.extend(scan_file(path))
    if failures:
        print("Active graph-store references found:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"ok: no active graph-store references ({len(active_files)} runtime files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
