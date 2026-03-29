#!/usr/bin/env python3
"""
delivery_verifier.py — Parse and verify delivery receipts from agent workspace files.

Agents are expected to include a ## Signal Delivery section in their workspace
task file after sending a message. This module reads that section and verifies
the delivery was successful WITHOUT re-sending anything.

Expected receipt format in workspace file:

    ## Signal Delivery
    - recipient: +19193375833
    - exit_code: 0
    - timestamp: 1742700000000
    - raw_response: {"jsonrpc":"2.0","result":{"timestamp":1742700000000,"results":[{"type":"SUCCESS","address":{"number":"+19193375833"}}]},"id":1}

Usage:
    from delivery_verifier import verify_delivery, parse_receipt_block
"""

import json
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class DeliveryReceipt:
    recipient: str
    exit_code: int
    timestamp: Optional[int]
    raw_response: Optional[dict]
    success: bool


def parse_receipt_block(file_content: str) -> Optional[DeliveryReceipt]:
    """Extract and parse a ## Signal Delivery section from a workspace file.

    Returns DeliveryReceipt or None if no section found.
    """
    # Find the section
    match = re.search(
        r'##\s*Signal\s+Delivery\b(.+?)(?=\n##|\Z)',
        file_content,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None

    section = match.group(1)

    # Extract fields
    recipient = _extract_field(section, "recipient") or ""
    exit_code_str = _extract_field(section, "exit_code")
    timestamp_str = _extract_field(section, "timestamp")
    raw_str = _extract_field(section, "raw_response")

    try:
        exit_code = int(exit_code_str) if exit_code_str is not None else -1
    except (ValueError, TypeError):
        exit_code = -1

    try:
        timestamp = int(timestamp_str) if timestamp_str else None
    except (ValueError, TypeError):
        timestamp = None

    raw_response = None
    if raw_str:
        # May be on the same line or a following code block
        raw_str = raw_str.strip().lstrip('`').rstrip('`').strip()
        try:
            raw_response = json.loads(raw_str)
        except (json.JSONDecodeError, ValueError):
            # Try to find a JSON object anywhere in the section
            json_match = re.search(r'\{.+\}', section, re.DOTALL)
            if json_match:
                try:
                    raw_response = json.loads(json_match.group(0))
                except (json.JSONDecodeError, ValueError):
                    pass

    success = _determine_success(exit_code, raw_response)

    return DeliveryReceipt(
        recipient=recipient,
        exit_code=exit_code,
        timestamp=timestamp,
        raw_response=raw_response,
        success=success,
    )


def _extract_field(text: str, field: str) -> Optional[str]:
    """Extract a field value from lines like '- field: value' or 'field: value'."""
    pattern = rf'[-*]?\s*{re.escape(field)}\s*:\s*(.+?)(?:\n|$)'
    m = re.search(pattern, text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _determine_success(exit_code: int, raw_response: Optional[dict]) -> bool:
    """Return True if delivery was successful based on exit_code and raw_response."""
    if exit_code != 0:
        return False
    if raw_response is None:
        # exit_code: 0 is sufficient if no raw_response was recorded
        return True
    # Validate the JSON-RPC result structure from signal-cli daemon
    result = raw_response.get("result", {})
    if isinstance(result, dict):
        results_list = result.get("results", [])
        if results_list and isinstance(results_list, list):
            delivery_type = results_list[0].get("type", "")
            return delivery_type == "SUCCESS"
    return True  # exit_code 0 with unrecognized response structure — trust the exit code


def verify_delivery(file_content: str, expected_recipient: str = "") -> tuple[bool, str]:
    """Parse workspace file and verify a successful delivery receipt.

    Args:
        file_content: Full content of the agent's workspace task file.
        expected_recipient: Phone/address to match (optional; skipped if empty).

    Returns:
        (passed, reason) tuple.
        passed=True means delivery was verified.
        passed=False means delivery was not confirmed — reason explains why.
    """
    receipt = parse_receipt_block(file_content)

    if receipt is None:
        return False, "no ## Signal Delivery section found in workspace file"

    if not receipt.success:
        return False, f"delivery exit_code={receipt.exit_code}, raw={receipt.raw_response}"

    if expected_recipient and receipt.recipient:
        # Normalize: strip spaces, compare last N digits for safety
        norm_expected = re.sub(r'\s+', '', expected_recipient)
        norm_actual = re.sub(r'\s+', '', receipt.recipient)
        if norm_expected != norm_actual:
            return False, f"recipient mismatch: expected {expected_recipient}, got {receipt.recipient}"

    return True, f"delivery confirmed to {receipt.recipient} at ts={receipt.timestamp}"
