#!/usr/bin/env python3
"""
Query Neo4j for Moltbook Credentials and Kublai Authentication Data

This script queries the Neo4j operational memory database for:
1. Moltbook-related credentials and configuration
2. Kublai agent authentication data
3. Any external service authentication stored in Neo4j

Usage:
    python query_moltbook_credentials.py [--uri URI] [--user USER] [--password PASSWORD]

Environment Variables:
    NEO4J_URI - Neo4j connection URI (default: bolt://localhost:7687)
    NEO4J_USER - Neo4j username (default: neo4j)
    NEO4J_PASSWORD - Neo4j password (required)
"""

import os
import sys
import argparse
import json
from typing import Dict, List, Any, Optional

# Lazy import neo4j to handle import errors gracefully
try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable, AuthError, Neo4jError
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    print("[ERROR] neo4j-driver not installed. Install with: pip install neo4j-driver")
    sys.exit(1)


class Neo4jQueryTool:
    """Tool for querying Neo4j database for Moltbook and Kublai credentials."""

    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        """
        Initialize Neo4j connection.

        Args:
            uri: Neo4j bolt URI
            username: Neo4j username
            password: Neo4j password
            database: Neo4j database name
        """
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self._driver = None

    def connect(self) -> bool:
        """Establish connection to Neo4j."""
        try:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password)
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            print(f"[SUCCESS] Connected to Neo4j at {self.uri}")
            return True
        except ServiceUnavailable as e:
            print(f"[ERROR] Neo4j service unavailable: {e}")
            return False
        except AuthError as e:
            print(f"[ERROR] Authentication failed: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] Failed to connect: {e}")
            return False

    def close(self):
        """Close Neo4j connection."""
        if self._driver:
            self._driver.close()
            print("[INFO] Neo4j connection closed")

    def run_query(self, query: str, parameters: Dict = None) -> List[Dict]:
        """
        Run a Cypher query and return results.

        Args:
            query: Cypher query string
            parameters: Query parameters

        Returns:
            List of result records as dictionaries
        """
        if not self._driver:
            print("[ERROR] Not connected to Neo4j")
            return []

        try:
            with self._driver.session(database=self.database) as session:
                result = session.run(query, parameters or {})
                records = []
                for record in result:
                    # Convert record to dictionary
                    record_dict = {}
                    for key in record.keys():
                        value = record[key]
                        # Handle Neo4j node types
                        if hasattr(value, 'items'):
                            record_dict[key] = dict(value.items())
                        else:
                            record_dict[key] = value
                    records.append(record_dict)
                return records
        except Neo4jError as e:
            print(f"[ERROR] Query failed: {e}")
            return []

    def get_database_schema(self) -> Dict:
        """Get overview of database schema (labels, relationship types)."""
        schema = {
            "labels": [],
            "relationship_types": [],
            "property_keys": []
        }

        # Get labels
        labels_query = "CALL db.labels() YIELD label RETURN label"
        labels_result = self.run_query(labels_query)
        schema["labels"] = [r["label"] for r in labels_result]

        # Get relationship types
        rels_query = "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
        rels_result = self.run_query(rels_query)
        schema["relationship_types"] = [r["relationshipType"] for r in rels_result]

        # Get property keys
        props_query = "CALL db.propertyKeys() YIELD propertyKey RETURN propertyKey"
        props_result = self.run_query(props_query)
        schema["property_keys"] = [r["propertyKey"] for r in props_result]

        return schema

    def search_moltbook(self) -> Dict[str, List[Dict]]:
        """
        Search for all Moltbook-related data in Neo4j.

        Returns:
            Dictionary with search results by category
        """
        results = {
            "agent_nodes": [],
            "operational_memory": [],
            "all_nodes_with_moltbook": [],
            "credential_nodes": [],
            "configuration_nodes": [],
            "external_services": []
        }

        print("\n" + "=" * 70)
        print("QUERY 1: Agent nodes with name containing 'kublai'")
        print("=" * 70)
        query1 = """
        MATCH (a:Agent)
        WHERE a.name CONTAINS 'kublai'
           OR a.id CONTAINS 'kublai'
           OR a.name CONTAINS 'Kublai'
        RETURN a
        """
        results["agent_nodes"] = self.run_query(query1)
        print(f"Found {len(results['agent_nodes'])} agent node(s)")
        for r in results["agent_nodes"]:
            print(f"  - {json.dumps(r, indent=4, default=str)}")

        print("\n" + "=" * 70)
        print("QUERY 2: OperationalMemory nodes containing 'moltbook'")
        print("=" * 70)
        query2 = """
        MATCH (o:OperationalMemory)
        WHERE o.context CONTAINS 'moltbook'
           OR o.context CONTAINS 'Moltbook'
           OR o.agent CONTAINS 'kublai'
        RETURN o
        """
        results["operational_memory"] = self.run_query(query2)
        print(f"Found {len(results['operational_memory'])} operational memory node(s)")
        for r in results["operational_memory"]:
            print(f"  - {json.dumps(r, indent=4, default=str)}")

        print("\n" + "=" * 70)
        print("QUERY 3: All nodes with any property containing 'moltbook'")
        print("=" * 70)
        query3 = """
        MATCH (n)
        WHERE ANY(prop IN keys(n)
              WHERE toString(n[prop]) CONTAINS 'moltbook'
                 OR toString(n[prop]) CONTAINS 'Moltbook')
        RETURN n, labels(n) as labels
        """
        results["all_nodes_with_moltbook"] = self.run_query(query3)
        print(f"Found {len(results['all_nodes_with_moltbook'])} node(s) with 'moltbook' in properties")
        for r in results["all_nodes_with_moltbook"]:
            print(f"  - Labels: {r.get('labels', 'N/A')}")
            print(f"    Data: {json.dumps(r.get('n', {}), indent=4, default=str)}")

        print("\n" + "=" * 70)
        print("QUERY 4: Credential or authentication nodes")
        print("=" * 70)
        query4 = """
        MATCH (n)
        WHERE ANY(label IN labels(n)
              WHERE label IN ['Credential', 'Auth', 'Authentication', 'Secret', 'Token', 'APIKey'])
           OR ANY(prop IN keys(n)
              WHERE prop IN ['api_key', 'token', 'secret', 'password', 'credential'])
        RETURN n, labels(n) as labels
        """
        results["credential_nodes"] = self.run_query(query4)
        print(f"Found {len(results['credential_nodes'])} credential node(s)")
        for r in results["credential_nodes"]:
            print(f"  - Labels: {r.get('labels', 'N/A')}")
            # Mask sensitive values
            node_data = r.get('n', {})
            masked_data = {}
            for k, v in node_data.items():
                if any(sensitive in k.lower() for sensitive in ['password', 'secret', 'token', 'key', 'credential']):
                    masked_data[k] = "***REDACTED***"
                else:
                    masked_data[k] = v
            print(f"    Data: {json.dumps(masked_data, indent=4, default=str)}")

        print("\n" + "=" * 70)
        print("QUERY 5: Configuration or settings nodes")
        print("=" * 70)
        query5 = """
        MATCH (n)
        WHERE ANY(label IN labels(n)
              WHERE label IN ['Configuration', 'Config', 'Settings', 'Environment'])
           OR ANY(prop IN keys(n)
              WHERE prop CONTAINS 'config' OR prop CONTAINS 'setting' OR prop CONTAINS 'env')
        RETURN n, labels(n) as labels
        """
        results["configuration_nodes"] = self.run_query(query5)
        print(f"Found {len(results['configuration_nodes'])} configuration node(s)")
        for r in results["configuration_nodes"]:
            print(f"  - Labels: {r.get('labels', 'N/A')}")
            print(f"    Data: {json.dumps(r.get('n', {}), indent=4, default=str)}")

        print("\n" + "=" * 70)
        print("QUERY 6: External service nodes")
        print("=" * 70)
        query6 = """
        MATCH (n)
        WHERE ANY(label IN labels(n)
              WHERE label IN ['ExternalService', 'Integration', 'Service', 'Provider'])
           OR ANY(prop IN keys(n)
              WHERE prop CONTAINS 'service' OR prop CONTAINS 'integration' OR prop CONTAINS 'provider')
        RETURN n, labels(n) as labels
        """
        results["external_services"] = self.run_query(query6)
        print(f"Found {len(results['external_services'])} external service node(s)")
        for r in results["external_services"]:
            print(f"  - Labels: {r.get('labels', 'N/A')}")
            print(f"    Data: {json.dumps(r.get('n', {}), indent=4, default=str)}")

        return results

    def search_kublai_auth(self) -> Dict[str, List[Dict]]:
        """
        Search for Kublai authentication and authorization data.

        Returns:
            Dictionary with search results by category
        """
        results = {
            "kublai_agents": [],
            "auth_tokens": [],
            "gateway_config": [],
            "permissions": []
        }

        print("\n" + "=" * 70)
        print("QUERY 7: Kublai agent nodes and their properties")
        print("=" * 70)
        query7 = """
        MATCH (a:Agent)
        WHERE a.name =~ '(?i).*kublai.*'
           OR a.id =~ '(?i).*kublai.*'
           OR a.role =~ '(?i).*orchestrator.*'
        RETURN a
        """
        results["kublai_agents"] = self.run_query(query7)
        print(f"Found {len(results['kublai_agents'])} Kublai agent node(s)")
        for r in results["kublai_agents"]:
            print(f"  - {json.dumps(r, indent=4, default=str)}")

        print("\n" + "=" * 70)
        print("QUERY 8: Any stored tokens or gateway configuration")
        print("=" * 70)
        query8 = """
        MATCH (n)
        WHERE ANY(prop IN keys(n)
              WHERE prop CONTAINS 'token'
                 OR prop CONTAINS 'gateway'
                 OR prop CONTAINS 'auth'
                 OR prop CONTAINS 'openclaw')
        RETURN n, labels(n) as labels
        """
        results["auth_tokens"] = self.run_query(query8)
        print(f"Found {len(results['auth_tokens'])} node(s) with auth/gateway properties")
        for r in results["auth_tokens"]:
            print(f"  - Labels: {r.get('labels', 'N/A')}")
            node_data = r.get('n', {})
            masked_data = {}
            for k, v in node_data.items():
                if any(sensitive in k.lower() for sensitive in ['token', 'password', 'secret', 'key']):
                    masked_data[k] = "***REDACTED***"
                else:
                    masked_data[k] = v
            print(f"    Data: {json.dumps(masked_data, indent=4, default=str)}")

        return results

    def get_node_counts(self) -> Dict[str, int]:
        """Get counts of all node types in the database."""
        counts = {}

        print("\n" + "=" * 70)
        print("DATABASE OVERVIEW - Node Counts by Label")
        print("=" * 70)

        # Get all labels
        labels_query = "CALL db.labels() YIELD label RETURN label"
        labels_result = self.run_query(labels_query)
        labels = [r["label"] for r in labels_result]

        for label in labels:
            count_query = f"MATCH (n:{label}) RETURN count(n) as count"
            count_result = self.run_query(count_query)
            if count_result:
                count = count_result[0].get("count", 0)
                counts[label] = count
                print(f"  {label}: {count}")

        # Total nodes
        total_query = "MATCH (n) RETURN count(n) as total"
        total_result = self.run_query(total_query)
        if total_result:
            counts["TOTAL"] = total_result[0].get("total", 0)
            print(f"  TOTAL NODES: {counts['TOTAL']}")

        return counts


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Query Neo4j for Moltbook credentials and Kublai authentication data"
    )
    parser.add_argument(
        "--uri",
        default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j connection URI (default: bolt://localhost:7687 or NEO4J_URI env var)"
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("NEO4J_USER", "neo4j"),
        help="Neo4j username (default: neo4j or NEO4J_USER env var)"
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("NEO4J_PASSWORD"),
        help="Neo4j password (default: NEO4J_PASSWORD env var)"
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("NEO4J_DATABASE", "neo4j"),
        help="Neo4j database name (default: neo4j or NEO4J_DATABASE env var)"
    )
    parser.add_argument(
        "--output",
        help="Output file to save results as JSON"
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only show database schema information"
    )

    args = parser.parse_args()

    # Validate password
    if not args.password:
        print("[ERROR] Neo4j password is required. Provide via --password or NEO4J_PASSWORD environment variable.")
        sys.exit(1)

    # Initialize tool
    tool = Neo4jQueryTool(
        uri=args.uri,
        username=args.user,
        password=args.password,
        database=args.database
    )

    # Connect to Neo4j
    if not tool.connect():
        print("\n[FAILURE] Could not connect to Neo4j. Please check:")
        print("  1. Neo4j is running and accessible at the specified URI")
        print("  2. Credentials are correct")
        print("  3. Network connectivity to the Neo4j server")
        sys.exit(1)

    try:
        # Get database overview
        node_counts = tool.get_node_counts()

        # Get schema if requested or if database is empty
        if args.schema_only or node_counts.get("TOTAL", 0) == 0:
            print("\n" + "=" * 70)
            print("DATABASE SCHEMA")
            print("=" * 70)
            schema = tool.get_database_schema()
            print(f"\nLabels: {schema['labels']}")
            print(f"\nRelationship Types: {schema['relationship_types']}")
            print(f"\nProperty Keys: {schema['property_keys'][:20]}...")  # Limit output

            if node_counts.get("TOTAL", 0) == 0:
                print("\n[WARN] Database appears to be empty (no nodes found)")

            if args.schema_only:
                return

        # Run Moltbook search
        moltbook_results = tool.search_moltbook()

        # Run Kublai auth search
        kublai_results = tool.search_kublai_auth()

        # Combine results
        all_results = {
            "database_uri": args.uri,
            "database_name": args.database,
            "node_counts": node_counts,
            "moltbook_search": moltbook_results,
            "kublai_auth_search": kublai_results
        }

        # Summary
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)

        total_moltbook = (
            len(moltbook_results["agent_nodes"]) +
            len(moltbook_results["operational_memory"]) +
            len(moltbook_results["all_nodes_with_moltbook"]) +
            len(moltbook_results["credential_nodes"]) +
            len(moltbook_results["configuration_nodes"]) +
            len(moltbook_results["external_services"])
        )

        total_kublai = (
            len(kublai_results["kublai_agents"]) +
            len(kublai_results["auth_tokens"])
        )

        print(f"\nMoltbook-related nodes found: {total_moltbook}")
        print(f"Kublai auth-related nodes found: {total_kublai}")

        if total_moltbook == 0 and total_kublai == 0:
            print("\n[RESULT] No Moltbook credentials or Kublai authentication data found in Neo4j.")
            print("This could mean:")
            print("  1. The data has not been stored in Neo4j yet")
            print("  2. The data is stored under different labels/properties")
            print("  3. The data is stored in a different database")
            print("  4. Credentials are stored in file-based memory (as per privacy guidelines)")
        else:
            print("\n[RESULT] Found relevant data. Review the detailed output above.")

        # Save to file if requested
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(all_results, f, indent=2, default=str)
            print(f"\n[INFO] Results saved to: {args.output}")

    finally:
        tool.close()


if __name__ == "__main__":
    main()
