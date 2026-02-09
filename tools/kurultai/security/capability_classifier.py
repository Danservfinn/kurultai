#!/usr/bin/env python3
"""
Security Layer 3: Capability Classification System

Hybrid approach: Rule-based + Semantic + LLM fallback
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class ClassificationResult:
    capability_type: str
    risk_level: RiskLevel
    confidence: float
    method: str  # 'rule', 'semantic', 'llm'
    reasoning: str


class CapabilityClassifier:
    """
    Classify capabilities using three-tier approach:
    1. Rule-based (fast path, >0.85 confidence)
    2. Semantic similarity (via Neo4j vector index)
    3. LLM fallback (ambiguous cases)
    """
    
    # Risk patterns for rule-based classification
    CRITICAL_PATTERNS = [
        r'exec\s*\(',
        r'eval\s*\(',
        r'__import__\s*\(',
        r'subprocess\.call\s*\(',
        r'os\.system\s*\(',
        r'shell\s*=\s*True',
        r'dangerous',
        r'unsafe',
    ]
    
    HIGH_PATTERNS = [
        r'requests\.(get|post|put|delete)',
        r'urllib\.request',
        r'socket\.(socket|connect)',
        r'open\s*\([^)]*,\s*['"'"'w]',
        r'file.*write',
        r'delete.*permanent',
    ]
    
    MEDIUM_PATTERNS = [
        r'query.*database',
        r'read.*file',
        r'parse.*(json|xml|yaml)',
        r'format.*string',
        r'template',
    ]
    
    def __init__(self, neo4j_driver=None):
        self.driver = neo4j_driver
        self.min_rule_confidence = 0.85
    
    def classify(self, request_text: str) -> ClassificationResult:
        """
        Main classification entry point.
        Tries rule-based first, then semantic, then LLM.
        """
        # Tier 1: Rule-based (fast path)
        rule_result = self._rule_based_classify(request_text)
        if rule_result.confidence >= self.min_rule_confidence:
            return rule_result
        
        # Tier 2: Semantic similarity (if Neo4j available)
        if self.driver:
            semantic_result = self._semantic_classify(request_text)
            if semantic_result.confidence >= self.min_rule_confidence:
                return semantic_result
        
        # Tier 3: LLM fallback
        return self._llm_classify(request_text)
    
    def _rule_based_classify(self, text: str) -> ClassificationResult:
        """
        Fast rule-based classification using regex patterns.
        """
        text_lower = text.lower()
        
        # Check critical patterns
        for pattern in self.CRITICAL_PATTERNS:
            if re.search(pattern, text_lower):
                return ClassificationResult(
                    capability_type="code_execution",
                    risk_level=RiskLevel.CRITICAL,
                    confidence=0.95,
                    method="rule",
                    reasoning=f"Matched critical pattern: {pattern}"
                )
        
        # Check high-risk patterns
        for pattern in self.HIGH_PATTERNS:
            if re.search(pattern, text_lower):
                return ClassificationResult(
                    capability_type="network_io" if "request" in text_lower or "socket" in text_lower else "file_io",
                    risk_level=RiskLevel.HIGH,
                    confidence=0.90,
                    method="rule",
                    reasoning=f"Matched high-risk pattern: {pattern}"
                )
        
        # Check medium patterns
        for pattern in self.MEDIUM_PATTERNS:
            if re.search(pattern, text_lower):
                return ClassificationResult(
                    capability_type="data_processing",
                    risk_level=RiskLevel.MEDIUM,
                    confidence=0.88,
                    method="rule",
                    reasoning=f"Matched medium pattern: {pattern}"
                )
        
        # No pattern match - low confidence
        return ClassificationResult(
            capability_type="unknown",
            risk_level=RiskLevel.LOW,
            confidence=0.40,
            method="rule",
            reasoning="No matching patterns found"
        )
    
    def _semantic_classify(self, text: str) -> ClassificationResult:
        """
        Semantic similarity using Neo4j vector index.
        Finds similar existing capabilities.
        """
        if not self.driver:
            return ClassificationResult(
                capability_type="unknown",
                risk_level=RiskLevel.LOW,
                confidence=0.0,
                method="semantic",
                reasoning="Neo4j driver not available"
            )
        
        # Query for similar capabilities using vector similarity
        # This would use Neo4j's vector index in production
        # For now, return placeholder
        
        return ClassificationResult(
            capability_type="unknown",
            risk_level=RiskLevel.LOW,
            confidence=0.30,
            method="semantic",
            reasoning="Semantic search not yet implemented (requires vector index)"
        )
    
    def _llm_classify(self, text: str) -> ClassificationResult:
        """
        LLM fallback for ambiguous cases.
        Returns conservative classification.
        """
        # In production, this would call an LLM API
        # For now, return conservative medium risk
        
        return ClassificationResult(
            capability_type="unknown",
            risk_level=RiskLevel.MEDIUM,
            confidence=0.70,
            method="llm",
            reasoning="LLM classification - ambiguous request, defaulting to medium risk"
        )
    
    def check_existing_capability(self, name: str) -> Optional[Dict]:
        """
        Check if a capability with this name already exists.
        """
        if not self.driver:
            return None
        
        from neo4j import GraphDatabase
        
        with self.driver.session() as session:
            result = session.run("""
                MATCH (lc:LearnedCapability {name: $name})
                RETURN lc.id as id,
                       lc.risk_level as risk,
                       lc.agent as agent
            """, name=name)
            
            record = result.single()
            if record:
                return {
                    'id': record['id'],
                    'risk_level': record['risk'],
                    'agent': record['agent']
                }
            return None


if __name__ == '__main__':
    # Test classification
    classifier = CapabilityClassifier()
    
    test_requests = [
        "Learn how to send HTTP requests to APIs",
        "Create a capability that executes shell commands",
        "Build a file reader that parses JSON",
        "Help me format this data into a template",
        "Write code that uses eval() to parse expressions",
    ]
    
    for request in test_requests:
        result = classifier.classify(request)
        print(f"\nRequest: {request}")
        print(f"  Type: {result.capability_type}")
        print(f"  Risk: {result.risk_level.value}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Method: {result.method}")
