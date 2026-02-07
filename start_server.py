#!/usr/bin/env python3
"""Startup script that runs migrations then starts the health server.

This script ensures Neo4j migrations are applied before the service starts.
It's designed for Railway deployment where migrations need to run against
the internal Neo4j service (bolt://neo4j.railway.internal:7687).
"""

import os
import sys
import time
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))


def run_migrations():
    """Run Neo4j migrations to target version 3."""
    print("=== Starting Neo4j Migration ===")

    # Import after adding to path
    try:
        from migrations.migration_manager import MigrationManager
        from migrations.v1_initial_schema import V1InitialSchema
        from migrations.v2_kurultai_dependencies import V2KurultaiDependencies
        from migrations.v3_capability_acquisition import V3CapabilityAcquisition

        uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD")

        if not password:
            print("ERROR: NEO4J_PASSWORD environment variable required")
            return False

        print(f"Connecting to Neo4j at {uri}...")

        # Wait for Neo4j to be ready (Railway services start in parallel)
        max_retries = 30
        for attempt in range(max_retries):
            try:
                manager = MigrationManager(uri, user, password)
                print("Neo4j connection established!")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Waiting for Neo4j... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(2)
                else:
                    print(f"Failed to connect to Neo4j: {e}")
                    return False

        try:
            # Register all migrations
            V1InitialSchema.register(manager)
            V2KurultaiDependencies.register(manager)
            V3CapabilityAcquisition.register(manager)
            print("Registered migrations: v1, v2, v3")

            current = manager.get_current_version()
            print(f"Current schema version: {current}")

            target = 3  # Latest version
            if current >= target:
                print(f"Already at version {current}. Migrations up to date.")
            else:
                print(f"Migrating from v{current} to v{target}...")
                success = manager.migrate(target_version=target)

                if success:
                    new_version = manager.get_current_version()
                    print(f"Migration complete! Now at version: {new_version}")
                else:
                    print("Migration failed!")
                    return False

        finally:
            manager.close()

    except ImportError as e:
        print(f"WARNING: Could not import migration modules: {e}")
        print("Skipping migrations - starting service anyway...")
    except Exception as e:
        print(f"ERROR during migration: {e}")
        # Don't fail startup - migrations may have already been applied
        print("Starting service anyway...")

    print("=== Migration Complete ===")
    return True


def start_health_server():
    """Start the health check server."""
    import http.server
    import socketserver
    import json
    from datetime import datetime

    PORT = int(os.environ.get("PORT", "18789"))

    class HealthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/health':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {
                    'status': 'healthy',
                    'service': 'moltbot',
                    'timestamp': datetime.now().isoformat()
                }
                self.wfile.write(json.dumps(response).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress request logs

    with socketserver.TCPServer(('', PORT), HealthHandler) as httpd:
        print(f'Agent configuration container running on port {PORT}')
        print('Health check available at /health')
        httpd.serve_forever()


if __name__ == '__main__':
    # Run migrations first
    run_migrations()

    # Then start the health server
    start_health_server()
