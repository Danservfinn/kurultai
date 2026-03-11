#!/usr/bin/env python3
"""
Dashboard Utilities - Shared dashboard rendering utilities.

Consolidates dashboard rendering functions from:
- agent-dashboard.py
- health_dashboard.py
- gate-metrics.py
- pipeline_health.py

Usage:
    from dashboard_utils import print_header, print_table, run_watch_mode

    print_header("Agent Status", "System Overview")
    print_table(["Agent", "Status", "Queue"], rows)
    run_watch_mode(render_function, interval=5)
"""

import os
import time
from datetime import datetime
from typing import Callable, List, Any, Optional, Dict


def clear_screen():
    """Clear terminal screen (cross-platform)."""
    os.system('clear' if os.name != 'nt' else 'cls')


def print_header(title: str, subtitle: Optional[str] = None, width: int = 60):
    """Print a formatted dashboard header.

    Args:
        title: Main title
        subtitle: Optional subtitle
        width: Header width in characters
    """
    print(f"\n{'=' * width}")
    print(f"  {title}")
    if subtitle:
        print(f"  {subtitle}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * width}\n")


def print_section(title: str, width: int = 60):
    """Print a section header.

    Args:
        title: Section title
        width: Width of separator line
    """
    print(f"\n--- {title} ---\n")


def print_table(
    headers: List[str],
    rows: List[List[Any]],
    widths: Optional[List[int]] = None,
    align: Optional[List[str]] = None
):
    """Print a formatted table.

    Args:
        headers: Column headers
        rows: Table rows (list of lists)
        widths: Optional column widths (auto-calculated if None)
        align: Optional alignment per column ('left', 'right', 'center')
    """
    if not rows:
        print("  (no data)")
        return

    # Calculate column widths
    if widths is None:
        widths = [
            max(
                len(str(headers[i])),
                max(len(str(row[i])) if i < len(row) else 0 for row in rows)
            )
            for i in range(len(headers))
        ]

    # Default alignment
    if align is None:
        align = ['left'] * len(headers)

    # Build format string
    fmt_parts = []
    for i, (w, a) in enumerate(zip(widths, align)):
        if a == 'right':
            fmt_parts.append(f"{{:>{w}}}")
        elif a == 'center':
            fmt_parts.append(f"{{:^{w}}}")
        else:
            fmt_parts.append(f"{{:<{w}}}")
    row_fmt = "  ".join(fmt_parts)

    # Print header
    print(row_fmt.format(*headers))

    # Print separator
    separator = "-" * sum(widths) + "  " * (len(widths) - 1)
    print(separator)

    # Print rows
    for row in rows:
        # Pad row if needed
        padded_row = list(row) + [''] * (len(headers) - len(row))
        print(row_fmt.format(*padded_row[:len(headers)]))


def print_bar(
    value: int,
    max_value: int,
    width: int = 20,
    filled: str = '█',
    empty: str = '░'
) -> str:
    """Create a text progress bar.

    Args:
        value: Current value
        max_value: Maximum value
        width: Bar width in characters
        filled: Character for filled portion
        empty: Character for empty portion

    Returns:
        Bar string
    """
    if max_value <= 0:
        return empty * width

    filled_width = int((value / max_value) * width)
    return filled * filled_width + empty * (width - filled_width)


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted string (e.g., "2h 15m", "45s")
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"


def format_number(num: int) -> str:
    """Format large numbers with K/M suffixes.

    Args:
        num: Number to format

    Returns:
        Formatted string (e.g., "1.2K", "3.5M")
    """
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return str(num)


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp for display.

    Args:
        ts: ISO format timestamp

    Returns:
        Human-readable timestamp
    """
    try:
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return ts


def truncate_text(text: str, max_len: int = 50, suffix: str = "...") -> str:
    """Truncate text to max length with suffix.

    Args:
        text: Text to truncate
        max_len: Maximum length
        suffix: Suffix to add when truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix


def colorize(text: str, color: str) -> str:
    """Add ANSI color codes to text.

    Args:
        text: Text to colorize
        color: Color name ('red', 'green', 'yellow', 'blue', 'reset')

    Returns:
        Colorized text (or original if color not supported)
    """
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m',
        'reset': '\033[0m'
    }

    if color not in colors:
        return text
    return f"{colors[color]}{text}{colors['reset']}"


def run_watch_mode(
    render_func: Callable[[], None],
    interval_seconds: int = 5,
    show_controls: bool = True
):
    """Run a render function in watch mode.

    Refreshes display at regular intervals until Ctrl+C.

    Args:
        render_func: Function to call for each refresh
        interval_seconds: Refresh interval in seconds
        show_controls: Whether to show control instructions
    """
    if show_controls:
        print("Watch mode - Press Ctrl+C to exit\n")

    try:
        while True:
            clear_screen()
            render_func()
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\n\nExiting watch mode.")


def print_metric_card(
    title: str,
    value: Any,
    delta: Optional[str] = None,
    status: Optional[str] = None,
    width: int = 20
):
    """Print a metric card with title, value, and optional delta.

    Args:
        title: Card title
        value: Main value
        delta: Optional change indicator (e.g., "+5%", "-2")
        status: Optional status ('up', 'down', 'neutral')
        width: Card width
    """
    border = "┌" + "─" * (width - 2) + "┐"
    bottom = "└" + "─" * (width - 2) + "┘"

    print(border)
    print(f"│ {title:<{width-4}} │")
    print(f"│ {str(value):^{width-4}} │")

    if delta:
        indicator = ''
        if status == 'up':
            indicator = '↑'
        elif status == 'down':
            indicator = '↓'
        delta_text = f"{indicator} {delta}"
        print(f"│ {delta_text:^{width-4}} │")

    print(bottom)


def print_status_line(
    label: str,
    value: Any,
    status: Optional[str] = None,
    width: int = 30
):
    """Print a labeled status line with optional indicator.

    Args:
        label: Label text
        value: Value to display
        status: Optional status ('ok', 'warn', 'error')
        width: Label width
    """
    indicator = ''
    if status == 'ok':
        indicator = '✓'
    elif status == 'warn':
        indicator = '⚠'
    elif status == 'error':
        indicator = '✗'

    print(f"{label:<{width}} {value} {indicator}")


def print_tree(
    items: List[Dict[str, Any]],
    name_key: str = 'name',
    children_key: str = 'children',
    indent: int = 0
):
    """Print a tree structure.

    Args:
        items: List of item dicts
        name_key: Key for item name
        children_key: Key for children list
        indent: Current indentation level
    """
    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        prefix = "  " * indent
        connector = "└─ " if is_last else "├─ "

        name = item.get(name_key, 'unnamed')
        print(f"{prefix}{connector}{name}")

        children = item.get(children_key, [])
        if children:
            print_tree(children, name_key, children_key, indent + 1)


class Dashboard:
    """Base class for dashboards with common functionality."""

    def __init__(self, title: str, refresh_interval: int = 5):
        """Initialize dashboard.

        Args:
            title: Dashboard title
            refresh_interval: Refresh interval in seconds
        """
        self.title = title
        self.refresh_interval = refresh_interval

    def render(self):
        """Render dashboard content. Override in subclass."""
        raise NotImplementedError

    def run(self, watch: bool = True):
        """Run the dashboard.

        Args:
            watch: If True, run in watch mode; if False, render once
        """
        if watch:
            run_watch_mode(self.render, self.refresh_interval)
        else:
            clear_screen()
            self.render()

    def print_header(self, subtitle: Optional[str] = None):
        """Print dashboard header."""
        print_header(self.title, subtitle)

    def print_section(self, title: str):
        """Print section header."""
        print_section(title)
