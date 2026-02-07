"""Prompt injection filter for Kurultai v0.2 multi-agent orchestration.

Detects and blocks prompt injection attacks in agent inputs before they
enter the task pipeline. Covers direct instruction override, role hijacking,
prompt extraction, base64 obfuscation, homoglyph attacks, and delimiter
injection.

OWASP LLM01:2023 - Prompt Injection prevention.

Usage:
    filt = PromptInjectionFilter()
    if not filt.is_safe(user_text):
        raise ValueError("Prompt injection detected")

    safe, reason = filt.check(user_text)
    if not safe:
        audit_logger.log_security_event("prompt_injection", "high", {"reason": reason})
"""

import base64
import logging
import re
import unicodedata
from typing import List, Tuple

logger = logging.getLogger("kurultai.security.prompt_injection")

# --- Homoglyph normalization table ---
# Maps common Unicode confusables to their ASCII equivalents.
# This catches attacks that use visually similar characters to bypass
# simple string matching (e.g., Cyrillic 'a' U+0430 vs Latin 'a' U+0061).
_HOMOGLYPH_MAP: dict[str, str] = {
    "\u0430": "a",  # Cyrillic Small Letter A
    "\u0435": "e",  # Cyrillic Small Letter Ie
    "\u043e": "o",  # Cyrillic Small Letter O
    "\u0440": "p",  # Cyrillic Small Letter Er
    "\u0441": "c",  # Cyrillic Small Letter Es
    "\u0443": "y",  # Cyrillic Small Letter U
    "\u0445": "x",  # Cyrillic Small Letter Ha
    "\u0456": "i",  # Cyrillic Small Letter Byelorussian-Ukrainian I
    "\u0458": "j",  # Cyrillic Small Letter Je
    "\u04bb": "h",  # Cyrillic Small Letter Shha
    "\u0501": "d",  # Cyrillic Small Letter Komi De
    "\u051b": "q",  # Cyrillic Small Letter Qa
    "\u0222": "3",  # Latin Capital Letter Ou (looks like 3 in some fonts)
    "\uff41": "a",  # Fullwidth Latin Small Letter A
    "\uff45": "e",  # Fullwidth Latin Small Letter E
    "\uff49": "i",  # Fullwidth Latin Small Letter I
    "\uff4f": "o",  # Fullwidth Latin Small Letter O
    "\u2010": "-",  # Hyphen
    "\u2011": "-",  # Non-Breaking Hyphen
    "\u2012": "-",  # Figure Dash
    "\u2013": "-",  # En Dash
    "\u2014": "-",  # Em Dash
    "\u200b": "",   # Zero Width Space (strip entirely)
    "\u200c": "",   # Zero Width Non-Joiner
    "\u200d": "",   # Zero Width Joiner
    "\ufeff": "",   # BOM / Zero Width No-Break Space
}


class PromptInjectionFilter:
    """Detects prompt injection attacks in text input.

    All pattern matching is case-insensitive and applied after NFKC Unicode
    normalization and homoglyph replacement to defeat obfuscation.

    Categories of injection detected:
        1. Instruction override ("ignore previous instructions")
        2. Role hijacking ("you are now", "act as", "pretend to be")
        3. Prompt extraction ("system prompt", "reveal your prompt")
        4. Instruction disregard ("disregard" + "instructions")
        5. Base64-encoded injection attempts
        6. Homoglyph / Unicode confusable attacks
        7. Delimiter injection (```system, [INST], <<SYS>>, etc.)
    """

    # Each tuple: (compiled regex, human-readable category description)
    _PATTERNS: List[Tuple[re.Pattern, str]] = [
        # 1. Instruction override
        (re.compile(
            r"ignore\s+(all\s+)?(previous|prior|above|earlier|preceding)\s+"
            r"(instructions|prompts|rules|directives|context)",
            re.IGNORECASE,
        ), "instruction_override"),

        # 2. Role hijacking
        (re.compile(
            r"(you\s+are\s+now|act\s+as|pretend\s+to\s+be|"
            r"roleplay\s+as|imagine\s+you\s+are|assume\s+the\s+role\s+of|"
            r"from\s+now\s+on\s+you\s+are)",
            re.IGNORECASE,
        ), "role_hijacking"),

        # 3. Prompt extraction
        (re.compile(
            r"(system\s+prompt|reveal\s+your\s+(prompt|instructions)|"
            r"show\s+(me\s+)?your\s+(prompt|instructions|system\s+message)|"
            r"repeat\s+(your\s+)?(initial|original|system)\s+(prompt|instructions)|"
            r"what\s+are\s+your\s+(instructions|rules|directives))",
            re.IGNORECASE,
        ), "prompt_extraction"),

        # 4. Instruction disregard -- "disregard" near "instructions"
        (re.compile(
            r"disregard\s+.{0,30}(instructions|rules|guidelines|directives|prompts)",
            re.IGNORECASE,
        ), "instruction_disregard"),

        # 7. Delimiter injection
        (re.compile(
            r"(```\s*system|<\|system\|>|\[INST\]|\[/INST\]|"
            r"<<\s*SYS\s*>>|<\|im_start\|>|<\|im_end\|>|"
            r"<\|endoftext\|>|<\|assistant\|>|<\|user\|>|"
            r"### ?(system|instruction|human|assistant)\s*:)",
            re.IGNORECASE,
        ), "delimiter_injection"),
    ]

    def __init__(self) -> None:
        """Initialize the filter. No external dependencies required."""
        pass

    @staticmethod
    def _normalize(text: str) -> str:
        """Apply NFKC normalization and homoglyph replacement.

        NFKC normalization converts compatibility characters to their
        canonical equivalents (e.g., fullwidth forms to ASCII). The
        homoglyph map then catches remaining confusables.

        Args:
            text: Raw input text.

        Returns:
            Normalized text suitable for pattern matching.
        """
        # Step 1: NFKC normalization collapses fullwidth, ligatures, etc.
        normalized = unicodedata.normalize("NFKC", text)

        # Step 2: Replace known homoglyphs
        result = []
        for char in normalized:
            replacement = _HOMOGLYPH_MAP.get(char)
            if replacement is not None:
                result.append(replacement)
            else:
                result.append(char)
        return "".join(result)

    def _check_base64(self, text: str) -> Tuple[bool, str]:
        """Detect base64-encoded injection payloads.

        Scans for base64-looking tokens (20+ chars, valid alphabet) and
        attempts to decode them. Decoded content is then checked against
        all standard patterns.

        Args:
            text: Normalized input text.

        Returns:
            (is_safe, reason) tuple. is_safe is False if a decoded payload
            matches any injection pattern.
        """
        # Match potential base64 tokens -- at least 20 chars, proper alphabet
        b64_pattern = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")
        for match in b64_pattern.finditer(text):
            token = match.group()
            try:
                decoded = base64.b64decode(token, validate=True).decode("utf-8", errors="ignore")
            except Exception:
                continue

            if not decoded or len(decoded) < 8:
                continue

            # Check decoded content against all standard patterns
            for pattern, category in self._PATTERNS:
                if pattern.search(decoded):
                    return (False, f"base64_encoded_{category}: decoded payload matches '{category}'")
        return (True, "")

    def check(self, text: str) -> Tuple[bool, str]:
        """Check text for prompt injection attacks.

        Applies NFKC normalization, homoglyph replacement, pattern
        matching, and base64 payload scanning.

        Args:
            text: Input text to validate.

        Returns:
            Tuple of (is_safe, reason). is_safe is True when no injection
            is detected. reason is an empty string when safe, or a
            description of the detected injection category.
        """
        if not text or not isinstance(text, str):
            return (True, "")

        normalized = self._normalize(text)

        # Check each pattern against normalized text
        for pattern, category in self._PATTERNS:
            if pattern.search(normalized):
                logger.warning(
                    "Prompt injection detected: category=%s input_length=%d",
                    category, len(text),
                )
                return (False, category)

        # Check for base64-obfuscated payloads
        b64_safe, b64_reason = self._check_base64(normalized)
        if not b64_safe:
            logger.warning(
                "Base64 prompt injection detected: %s input_length=%d",
                b64_reason, len(text),
            )
            return (False, b64_reason)

        return (True, "")

    def is_safe(self, text: str) -> bool:
        """Quick check whether text is free of prompt injection.

        This is a convenience wrapper around check() that discards
        the reason string.

        Args:
            text: Input text to validate.

        Returns:
            True if the text is safe, False if injection is detected.
        """
        safe, _ = self.check(text)
        return safe
