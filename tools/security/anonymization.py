"""
Anonymization Engine for Privacy-Preserving Neo4j Storage.

Provides multi-layer PII detection and anonymization:
- Layer 1: Regex-based pattern matching (fast, deterministic)
- Layer 2: LLM-based review (comprehensive, slower)
- Layer 3: Tokenization for reversible anonymization

OWASP References:
- A02:2021-Cryptographic Failures (data protection)
- A05:2021-Security Misconfiguration (data exposure)
"""

import re
import hashlib
import hmac
import os
import logging
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class PIIEntity:
    """Detected PII entity with location and replacement info."""
    entity_type: str
    start: int
    end: int
    value: str
    replacement: str
    confidence: float = 1.0


class AnonymizationEngine:
    """
    Multi-layer PII detection and anonymization engine.

    Uses regex patterns for fast detection and optional LLM review
    for complex cases. Supports both irreversible anonymization
    and reversible tokenization.

    Example:
        engine = AnonymizationEngine(salt=os.getenv("ANONYMIZATION_SALT"))

        # Detect PII
        entities = engine.detect_pii("Contact john@example.com or 555-123-4567")

        # Anonymize
        anonymized, token_map = engine.anonymize(
            "My friend Sarah's startup",
            reversible=True
        )
        # Result: "My friend <TOKEN:PERSON:abc123> startup"

        # Restore (if reversible)
        original = engine.deanonymize(anonymized, token_map)
    """

    # Regex patterns for common PII
    # These patterns are designed to minimize false positives while
    # catching the most common PII formats
    PII_PATTERNS = {
        "email": {
            "pattern": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "sensitivity": "high"
        },
        "phone_us": {
            "pattern": r'\b(\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b',
            "sensitivity": "high"
        },
        "phone_international": {
            "pattern": r'\+\d{1,3}[-.\s]?\(?[0-9]{1,4}\)?[-.\s]?[0-9]{1,4}[-.\s]?[0-9]{1,9}',
            "sensitivity": "high"
        },
        "ssn": {
            "pattern": r'\b\d{3}-\d{2}-\d{4}\b',
            "sensitivity": "critical"
        },
        "ssn_no_dashes": {
            "pattern": r'\b\d{9}\b',
            "sensitivity": "high"
        },
        "credit_card": {
            "pattern": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
            "sensitivity": "critical"
        },
        "api_key_openai": {
            "pattern": r'\bsk-[a-zA-Z0-9]{48}\b',
            "sensitivity": "critical"
        },
        "api_key_generic": {
            "pattern": r'\b(sk-|pk-|Bearer\s|api[_-]?key[:\s])[a-zA-Z0-9_-]{20,}\b',
            "sensitivity": "critical"
        },
        "url_with_auth": {
            "pattern": r'https?://[^:]+:[^@]+@[^\s]+',
            "sensitivity": "high"
        },
        "ip_address": {
            "pattern": r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
            "sensitivity": "medium"
        },
        "crypto_address_btc": {
            "pattern": r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b',
            "sensitivity": "medium"
        },
        "crypto_address_eth": {
            "pattern": r'\b0x[a-fA-F0-9]{40}\b',
            "sensitivity": "medium"
        },
    }

    # Patterns for detecting names in context
    NAME_CONTEXT_PATTERNS = [
        # "My friend/colleague/contact [Name]"
        (r'My\s+(?:friend|colleague|contact|mentor|advisor)\s+(\w+)', "relationship_name"),
        # "[Name]'s startup/company/project"
        (r"(\w+)'s\s+(?:startup|company|project|business)", "possessive_name"),
        # "from [Name]" at end of sentence
        (r'from\s+(\w+)\s*[.!?]$', "source_name"),
    ]

    def __init__(self, salt: Optional[str] = None):
        """
        Initialize anonymization engine.

        Args:
            salt: Salt for consistent hashing. Should be from environment
                  variable and consistent across application restarts.
        """
        self.salt = salt or os.getenv("ANONYMIZATION_SALT")
        if not self.salt:
            logger.warning(
                "No anonymization salt provided. Using default salt "
                "which is insecure for production."
            )
            self.salt = "default-salt-change-in-production"

        # Token map for reversible tokenization
        self._token_map: Dict[str, str] = {}

    def detect_pii(self, text: str, include_contextual: bool = True) -> List[PIIEntity]:
        """
        Detect PII entities in text using regex patterns.

        Args:
            text: Input text to analyze
            include_contextual: Whether to include contextual name detection

        Returns:
            List of detected PII entities sorted by position
        """
        entities = []

        # Pattern-based detection
        for entity_type, config in self.PII_PATTERNS.items():
            pattern = config["pattern"]
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Validate match (e.g., check IP address is valid)
                if self._validate_match(entity_type, match.group()):
                    entities.append(PIIEntity(
                        entity_type=entity_type,
                        start=match.start(),
                        end=match.end(),
                        value=match.group(),
                        replacement=self._generate_replacement(
                            entity_type,
                            match.group(),
                            config["sensitivity"]
                        ),
                        confidence=1.0
                    ))

        # Contextual name detection
        if include_contextual:
            for pattern, context_type in self.NAME_CONTEXT_PATTERNS:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    name = match.group(1)
                    # Filter out common words that might match
                    if self._is_likely_name(name):
                        entities.append(PIIEntity(
                            entity_type=context_type,
                            start=match.start(1),
                            end=match.end(1),
                            value=name,
                            replacement=self._generate_replacement(
                                "person_name",
                                name,
                                "high"
                            ),
                            confidence=0.8
                        ))

        # Sort by position (reverse) for replacement
        entities.sort(key=lambda e: e.start, reverse=True)

        # Remove overlapping entities (keep longer match)
        entities = self._remove_overlapping(entities)

        return entities

    def _validate_match(self, entity_type: str, value: str) -> bool:
        """Validate that a regex match is actually valid PII."""
        if entity_type == "ip_address":
            # Validate IP address octets
            parts = value.split(".")
            if len(parts) != 4:
                return False
            for part in parts:
                if not part.isdigit() or not 0 <= int(part) <= 255:
                    return False
            # Skip common private/reserved IPs in documentation
            if value.startswith("127.") or value.startswith("192.168."):
                return False
        return True

    def _is_likely_name(self, word: str) -> bool:
        """Check if a word is likely to be a name (not a common word)."""
        common_words = {
            "the", "and", "for", "are", "but", "not", "you", "all",
            "can", "had", "her", "was", "one", "our", "out", "day",
            "get", "has", "him", "his", "how", "its", "may", "new",
            "now", "old", "see", "two", "who", "boy", "did", "she",
            "use", "her", "way", "many", "oil", "sit", "set", "run",
            "eat", "far", "sea", "eye", "ago", "off", "too", "any",
            "say", "man", "try", "ask", "end", "why", "let", "put",
            "say", "she", "try", "way", "own", "say", "too", "old",
            "tell", "very", "when", "much", "would", "there", "their",
            "what", "said", "each", "which", "will", "about", "could",
            "other", "after", "first", "never", "these", "think",
            "where", "being", "every", "great", "might", "shall",
            "still", "those", "while", "this", "that", "with", "have",
            "from", "they", "know", "want", "been", "good", "come",
            "make", "well", "were", "said", "time", "than", "them",
            "into", "just", "like", "over", "also", "back", "only",
            "work", "life", "even", "more", "here", "look", "down",
            "most", "long", "last", "find", "give", "does", "made",
            "part", "such", "take", "year", "call", "come", "came",
            "went", "seen", "done", "going", "getting", "friend",
            "contact", "colleague", "startup", "company", "business",
        }
        return (
            word.lower() not in common_words and
            len(word) > 1 and
            word[0].isupper() and
            word.isalpha()
        )

    def _remove_overlapping(self, entities: List[PIIEntity]) -> List[PIIEntity]:
        """Remove overlapping entities, keeping longer matches."""
        if not entities:
            return entities

        # Sort by start position
        sorted_entities = sorted(entities, key=lambda e: e.start)
        result = [sorted_entities[0]]

        for entity in sorted_entities[1:]:
            last = result[-1]
            # Check for overlap
            if entity.start < last.end:
                # Overlapping - keep the longer one
                if (entity.end - entity.start) > (last.end - last.start):
                    result[-1] = entity
            else:
                result.append(entity)

        return result

    def _generate_replacement(
        self,
        entity_type: str,
        value: str,
        sensitivity: str
    ) -> str:
        """
        Generate consistent replacement for entity.

        Uses HMAC with salt to ensure:
        1. Same value always gets same replacement (consistency)
        2. Replacement cannot be reversed without salt
        3. Different entity types get different replacements
        """
        # Create hash for consistent replacement
        hash_input = f"{self.salt}:{entity_type}:{value.lower()}"
        hash_val = hmac.new(
            self.salt.encode(),
            hash_input.encode(),
            hashlib.sha256
        ).hexdigest()[:8]

        # Format based on sensitivity
        if sensitivity == "critical":
            return f"[REDACTED_{entity_type.upper()}_{hash_val}]"
        else:
            return f"[{entity_type.upper()}_{hash_val}]"

    def anonymize(
        self,
        text: str,
        reversible: bool = False,
        include_contextual: bool = True
    ) -> Tuple[str, Dict[str, str]]:
        """
        Anonymize text by replacing PII.

        Args:
            text: Input text
            reversible: If True, store token mapping for de-anonymization
            include_contextual: Whether to include contextual detection

        Returns:
            Tuple of (anonymized_text, token_map)
        """
        entities = self.detect_pii(text, include_contextual)
        anonymized = text
        token_map = {}

        for entity in entities:
            if reversible:
                # Generate reversible token
                token = self._generate_token(entity.entity_type)
                token_map[token] = entity.value
                replacement = token
            else:
                replacement = entity.replacement

            anonymized = (
                anonymized[:entity.start] +
                replacement +
                anonymized[entity.end:]
            )

        return anonymized, token_map

    def _generate_token(self, entity_type: str) -> str:
        """Generate unique reversible token."""
        token_id = hashlib.sha256(
            f"{datetime.utcnow().isoformat()}:{entity_type}".encode()
        ).hexdigest()[:8]
        return f"<TOKEN:{entity_type.upper()}:{token_id}>"

    def deanonymize(self, text: str, token_map: Dict[str, str]) -> str:
        """Restore original values from token map."""
        result = text
        for token, original in token_map.items():
            result = result.replace(token, original)
        return result

    def batch_anonymize(
        self,
        texts: List[str],
        reversible: bool = False
    ) -> List[Tuple[str, Dict[str, str]]]:
        """
        Anonymize multiple texts efficiently.

        Args:
            texts: List of texts to anonymize
            reversible: Whether to enable de-anonymization

        Returns:
            List of (anonymized_text, token_map) tuples
        """
        return [
            self.anonymize(text, reversible)
            for text in texts
        ]

    def get_statistics(self, text: str) -> Dict[str, Any]:
        """
        Get anonymization statistics for text.

        Returns:
            Dict with entity counts, types, and risk assessment
        """
        entities = self.detect_pii(text)

        type_counts = {}
        for entity in entities:
            type_counts[entity.entity_type] = type_counts.get(entity.entity_type, 0) + 1

        # Risk assessment
        critical_types = {"ssn", "credit_card", "api_key_openai", "api_key_generic"}
        has_critical = any(e.entity_type in critical_types for e in entities)

        risk_level = "low"
        if has_critical:
            risk_level = "critical"
        elif len(entities) > 5:
            risk_level = "high"
        elif len(entities) > 0:
            risk_level = "medium"

        return {
            "total_entities": len(entities),
            "type_counts": type_counts,
            "risk_level": risk_level,
            "has_critical": has_critical,
            "entities": [
                {"type": e.entity_type, "replacement": e.replacement}
                for e in entities
            ]
        }


class LLMPrivacyReviewer:
    """
    LLM-based privacy review for complex cases.

    Used as secondary check after regex-based detection for:
    - Complex contextual PII
    - Ambiguous cases
    - Business-specific sensitive information
    """

    REVIEW_PROMPT_TEMPLATE = """Analyze the following text for any personally identifiable information (PII) or sensitive personal data that should not be stored in a shared database.

Categories to flag:
1. Personal names (especially of friends, family, colleagues)
2. Specific company names (unless public/known)
3. Locations that could identify someone
4. Health information
5. Financial details beyond general concepts
6. Any information that could be used to identify a specific individual

Text to analyze:
{text}

Respond in this exact format:
CONTAINS_PII: [yes/no]
SENSITIVE_ENTITIES:
- Type: [category], Value: [text], Suggested replacement: [replacement]
RISK_LEVEL: [low/medium/high/critical]
REASONING: [brief explanation]
"""

    def __init__(self, llm_client=None):
        """
        Initialize LLM privacy reviewer.

        Args:
            llm_client: LLM client with async complete() method
        """
        self.llm_client = llm_client

    async def review(self, text: str) -> Dict[str, Any]:
        """
        Review text for PII using LLM.

        Args:
            text: Text to review

        Returns:
            Dict with 'contains_pii', 'entities', 'risk_level', 'reasoning'
        """
        if not self.llm_client:
            # Fallback: assume safe if no LLM available
            return {
                "contains_pii": False,
                "entities": [],
                "risk_level": "unknown",
                "reasoning": "No LLM available for review"
            }

        prompt = self.REVIEW_PROMPT_TEMPLATE.format(text=text[:2000])  # Limit length

        try:
            response = await self.llm_client.complete(prompt)
            return self._parse_review_response(response)
        except Exception as e:
            logger.error(f"LLM review failed: {e}")
            return {
                "contains_pii": None,  # Unknown due to error
                "entities": [],
                "risk_level": "unknown",
                "reasoning": f"Review failed: {e}"
            }

    def _parse_review_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM review response."""
        lines = response.strip().split('\n')
        result = {
            "contains_pii": False,
            "entities": [],
            "risk_level": "low",
            "reasoning": ""
        }

        in_entities = False
        reasoning_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("CONTAINS_PII:"):
                value = line.split(":", 1)[1].strip().lower()
                result["contains_pii"] = value in ("yes", "true", "1")
                in_entities = False

            elif line.startswith("SENSITIVE_ENTITIES:"):
                in_entities = True

            elif line.startswith("RISK_LEVEL:"):
                result["risk_level"] = line.split(":", 1)[1].strip().lower()
                in_entities = False

            elif line.startswith("REASONING:"):
                in_entities = False
                reasoning_lines.append(line.split(":", 1)[1].strip())

            elif in_entities and line.startswith("-"):
                entity = self._parse_entity_line(line)
                if entity:
                    result["entities"].append(entity)

            elif reasoning_lines:
                reasoning_lines.append(line)

        result["reasoning"] = " ".join(reasoning_lines)
        return result

    def _parse_entity_line(self, line: str) -> Optional[Dict[str, str]]:
        """Parse entity line from LLM response."""
        try:
            # Remove leading dash
            line = line.lstrip("- ").strip()

            entity = {}
            parts = line.split(", ")

            for part in parts:
                if ":" in part:
                    key, value = part.split(":", 1)
                    entity[key.strip().lower()] = value.strip()

            return entity if entity else None
        except Exception as e:
            logger.warning(f"Failed to parse entity line: {line}, error: {e}")
            return None

    async def review_batch(
        self,
        texts: List[str],
        max_concurrent: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Review multiple texts with concurrency control.

        Args:
            texts: List of texts to review
            max_concurrent: Maximum concurrent reviews

        Returns:
            List of review results
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def review_with_limit(text: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.review(text)

        return await asyncio.gather(*[
            review_with_limit(text)
            for text in texts
        ])
