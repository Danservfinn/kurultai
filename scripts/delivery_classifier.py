#!/usr/bin/env python3
"""
delivery_classifier.py — Detect tasks that require external message delivery.

A delivery task is one that asks an agent to send content to a human
via Signal, email, Slack, etc. When detected, the completion gate requires
a verified delivery receipt in the agent's workspace file.

Usage:
    from delivery_classifier import classify_delivery_task, DeliverySpec

    spec = classify_delivery_task(task_dict)
    if spec:
        # task requires delivery verification
        print(spec.channel, spec.recipient)
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class DeliverySpec:
    """Describes a required delivery for a task."""
    channel: str          # "signal", "email", "slack", etc.
    recipient: str        # phone number, email, channel name
    content_hint: str     # brief description of what should be sent


# Patterns that indicate a Signal delivery requirement
_SIGNAL_PATTERNS = [
    # "Send X to Y via Signal"
    r'send\b.+\bvia\s+signal',
    # "Signal DM to +1..."
    r'signal\s+(?:dm|message|text)\b',
    # "Deliver via Signal"
    r'deliver\b.+\bsignal',
    # skill_hint explicitly calls for signal delivery
    r'signal[-_]send',
]

# Patterns that extract a phone number
_PHONE_RE = re.compile(r'\+\d{7,15}')

# Section headers or labels that name the recipient
_RECIPIENT_LABEL_RE = re.compile(
    r'(?:recipient|send\s+to|deliver\s+to|phone)[^\n]*?(\+\d{7,15})',
    re.IGNORECASE,
)


def _find_recipient(text: str) -> str:
    """Extract the first phone number from text, or return empty string."""
    m = _RECIPIENT_LABEL_RE.search(text)
    if m:
        return m.group(1)
    m = _PHONE_RE.search(text)
    return m.group(0) if m else ""


def classify_delivery_task(task: dict) -> Optional[DeliverySpec]:
    """Inspect a task dict for delivery requirements.

    Args:
        task: dict with keys like title, body, skill_hint (all optional strings)

    Returns:
        DeliverySpec if the task requires delivery, or None.
    """
    title = (task.get("title") or "").lower()
    body = (task.get("body") or "").lower()
    skill_hint = (task.get("skill_hint") or "").lower()
    full_text = f"{title}\n{body}\n{skill_hint}"

    # Check for Signal delivery
    for pattern in _SIGNAL_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            recipient = _find_recipient(task.get("body") or "")
            if not recipient:
                recipient = _find_recipient(task.get("title") or "")
            return DeliverySpec(
                channel="signal",
                recipient=recipient,
                content_hint=_extract_content_hint(task),
            )

    return None


def _extract_content_hint(task: dict) -> str:
    """Return a short hint about what content should be delivered."""
    title = task.get("title") or ""
    # Strip leading "send" verbs for the hint
    hint = re.sub(r'^(?:send|deliver|message|text)\s+', '', title, flags=re.IGNORECASE).strip()
    return hint[:120] or "task deliverable"
