"""
Example: Privacy-Preserving Task Creation with Neo4j Security.

This example demonstrates how to use the security module to:
1. Anonymize PII before Neo4j storage
2. Enforce sender isolation
3. Prevent Cypher injection
4. Apply field-level encryption for sensitive data

Usage:
    python -m tools.security.example_usage
"""

import os
import asyncio
from datetime import datetime
from typing import Dict, Any

# Import security components
from tools.security import (
    AnonymizationEngine,
    TokenizationService,
    FieldEncryption,
    HybridPrivacyProcessor,
    LLMPrivacyReviewer,
    Neo4jSecurityManager,
    SenderIsolationEnforcer,
    SecureQueryBuilder,
    CypherInjectionPrevention,
    PrivacyBlockedError,
    apply_privacy_boundary,
)


async def create_privacy_preserving_task(
    description: str,
    task_type: str,
    delegated_by: str,
    assigned_to: str,
    sender_hash: str,
    neo4j_client,
    privacy_processor: HybridPrivacyProcessor,
    security_manager: Neo4jSecurityManager
) -> str:
    """
    Create a task with full privacy protection.

    This function demonstrates the complete privacy pipeline:
    1. Check agent permissions
    2. Process description through privacy pipeline
    3. Enforce sender isolation
    4. Use secure query building
    5. Audit log the operation
    """
    import uuid

    # Step 1: Check agent permissions
    if not security_manager.check_agent_permission(
        delegated_by, "write", "Task"
    ):
        raise PermissionError(
            f"Agent {delegated_by} does not have permission to create tasks"
        )

    # Step 2: Process description through privacy pipeline
    task_data = {
        "description": description,
        "type": task_type,
    }

    try:
        processed_data, metadata = await privacy_processor.process_for_neo4j(
            task_data,
            "task_metadata"
        )
    except PrivacyBlockedError as e:
        print(f"Task blocked by privacy rules: {e}")
        # Store in Kublai's file-based memory instead
        return await store_in_kublai_memory(task_data, sender_hash)

    # Step 3: Create task with secure query building
    task_id = str(uuid.uuid4())

    builder = SecureQueryBuilder()
    query, params = (builder
        .create("(t:Task {",
            id=task_id,
            description=processed_data["description"],
            type=processed_data["type"],
            delegated_by=delegated_by,
            assigned_to=assigned_to,
            sender_hash=sender_hash,
            status="pending",
            created_at=datetime.utcnow().isoformat(),
            privacy_classification=metadata["original_classification"]
        )
        .set("t.pii_detected = $pii_count", pii_count=len(metadata.get("pii_detected", [])))
        .return_("t.id as task_id")
        .build()
    )

    # Step 4: Enforce sender isolation
    enforcer = SenderIsolationEnforcer(security_manager)
    safe_query, safe_params = enforcer.enforce_isolation(
        query, params, delegated_by, sender_hash
    )

    # Step 5: Validate query for injection
    validation = CypherInjectionPrevention.validate_query(safe_query)
    if not validation.is_valid:
        raise ValueError(f"Query validation failed: {validation.errors}")

    # Execute query
    result = await neo4j_client.run(safe_query, safe_params)

    # Step 6: Log audit record
    print(f"Created task {task_id} with privacy protection:")
    print(f"  - Classification: {metadata['original_classification']}")
    print(f"  - PII detected: {len(metadata.get('pii_detected', []))}")
    print(f"  - Processing steps: {metadata.get('processing_steps', [])}")

    return task_id


async def store_in_kublai_memory(data: Dict[str, Any], sender_hash: str) -> str:
    """
    Store data in Kublai's file-based memory when it can't go to Neo4j.

    This is the fallback for PRIVATE classification data.
    """
    # Implementation would write to Kublai's MEMORY.md or similar
    print(f"Storing in Kublai's file memory for sender {sender_hash}")
    return "file-based-id"


async def example_privacy_pipeline():
    """Demonstrate the complete privacy pipeline."""

    print("=" * 60)
    print("Privacy-Preserving Neo4j Storage Example")
    print("=" * 60)

    # Initialize components
    print("\n1. Initializing security components...")

    # Anonymization engine with salt from env
    anonymizer = AnonymizationEngine(
        salt=os.getenv("ANONYMIZATION_SALT", "example-salt")
    )

    # Tokenization service (without vault for demo)
    tokenizer = TokenizationService(vault_client=None, ttl_days=90)

    # Field encryption (would use real key in production)
    try:
        encryption = FieldEncryption(
            master_key="example-key-for-demo-only"
        )
    except ValueError:
        print("   (Using placeholder encryption for demo)")
        encryption = None

    # Privacy processor combining all techniques
    privacy_processor = HybridPrivacyProcessor(
        anonymizer=anonymizer,
        tokenizer=tokenizer,
        encryption=encryption
    )

    # Security manager
    security_manager = Neo4jSecurityManager(
        uri="bolt+s://localhost:7687",
        username="neo4j",
        password="password",
        encryption_key="example-key"
    )

    print("   Components initialized.")

    # Example 1: Task with PII
    print("\n2. Processing task with PII...")

    description_with_pii = (
        "My friend Sarah has a startup idea. Contact her at sarah@example.com "
        "or call 555-123-4567 to discuss. Her company Acme Corp is in stealth mode."
    )

    print(f"   Original: {description_with_pii}")

    # Detect PII
    entities = anonymizer.detect_pii(description_with_pii)
    print(f"\n   Detected PII entities:")
    for entity in entities:
        print(f"     - {entity.entity_type}: {entity.value[:20]}... -> {entity.replacement}")

    # Anonymize
    anonymized, token_map = anonymizer.anonymize(description_with_pii)
    print(f"\n   Anonymized: {anonymized}")

    # Example 2: Privacy boundary enforcement
    print("\n3. Applying privacy boundary...")

    task_data = {
        "description": description_with_pii,
        "type": "research"
    }

    try:
        processed, metadata = await privacy_processor.process_for_neo4j(
            task_data,
            "task_metadata"
        )
        print(f"   Processed description: {processed['description']}")
        print(f"   Classification: {metadata['original_classification']}")
        print(f"   Processing steps: {metadata['processing_steps']}")
    except PrivacyBlockedError as e:
        print(f"   Blocked: {e}")

    # Example 3: Secure query building
    print("\n4. Building secure Cypher query...")

    builder = SecureQueryBuilder()
    query, params = (builder
        .match("(t:Task)")
        .where("t.status = $status", status="pending")
        .and_where("t.sender_hash = $sender_hash", sender_hash="abc123")
        .return_("t.id, t.description")
        .limit(10)
        .build()
    )

    print(f"   Query:\n{query}")
    print(f"   Parameters: {params}")

    # Validate query
    validation = CypherInjectionPrevention.validate_query(query)
    print(f"   Validation: {'PASS' if validation.is_valid else 'FAIL'}")

    # Example 4: Sender isolation
    print("\n5. Enforcing sender isolation...")

    enforcer = SenderIsolationEnforcer(security_manager)

    # This query would be modified for regular agents
    unsafe_query = "MATCH (t:Task) WHERE t.status = 'pending' RETURN t"

    # For researcher (requires isolation)
    try:
        safe_query, safe_params = enforcer.enforce_isolation(
            unsafe_query, {}, "researcher", "user123"
        )
        print(f"   Researcher query modified: {safe_query[:60]}...")
    except ValueError as e:
        print(f"   Error: {e}")

    # For main agent (no isolation required)
    safe_query, safe_params = enforcer.enforce_isolation(
        unsafe_query, {}, "main", None
    )
    print(f"   Main agent query unchanged: {safe_query[:60]}...")

    # Example 5: What should NEVER go to Neo4j
    print("\n6. Data that should NEVER go to Neo4j:")

    prohibited_examples = [
        ("My SSN is 123-45-6789", "SSN"),
        ("Use API key sk-abc123xyz789", "API key"),
        ("My friend John Smith lives at 123 Main St", "Personal info"),
        ("Credit card: 4111-1111-1111-1111", "Credit card"),
    ]

    for text, category in prohibited_examples:
        entities = anonymizer.detect_pii(text)
        critical = [e for e in entities
                   if e.entity_type in ("ssn", "api_key_openai", "credit_card")]

        if critical:
            print(f"   BLOCKED ({category}): {text[:40]}...")
            for e in critical:
                print(f"     -> Detected: {e.entity_type}")

    print("\n" + "=" * 60)
    print("Example complete.")
    print("=" * 60)


# Mock Neo4j client for demo
class MockNeo4jClient:
    async def run(self, query: str, params: Dict[str, Any]):
        print(f"   [Mock] Executing: {query[:50]}...")
        return [{"task_id": "mock-id"}]


if __name__ == "__main__":
    # Run the example
    asyncio.run(example_privacy_pipeline())
