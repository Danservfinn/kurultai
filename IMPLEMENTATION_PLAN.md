# Implementation Plan

This plan outlines the steps necessary to implement the remaining architectural components of the Kurultai system, now that the "Authentication & SSO Layer" and "Steppe Visualization Dashboard" have been deprecated.

## Phase 1: Neo4j Operational Memory

1.  **Install Neo4j**:
    -   Deploy Neo4j 5 Community locally via Docker, or provision a remote AuraDB instance.
    -   Example Docker command: `docker run -d --name neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/<STRONG_PASSWORD> neo4j:5-community`
2.  **Configure Environment Variables**:
    -   Update the `.env` file (or system environment variables) with `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`.
3.  **Run Migrations**:
    -   Execute the Neo4j schema migrations to create the required node types (`Agent`, `Task`, `LearnedCapability`, etc.) and constraints.
    -   Command: `python /tmp/kublai-repo/migrations/run_migrations.py --target-version 3` (or the equivalent migration script).

## Phase 2: Python Tools & Capability Access

1.  **Install Dependencies**:
    -   Install the required Python packages from the repository.
    -   Command: `pip install -r /tmp/kublai-repo/requirements.txt`
2.  **Deploy Agent Skills**:
    -   Integrate the Python toolset (`tools/kurultai/*`) into the agents' workspaces or global OpenClaw skills directory.
    -   Ensure the execution sandboxes (e.g., `subprocess` with resource limits) have the correct permissions to run `sandbox_executor.py` and AST analysis (`tree-sitter`).
3.  **Validate Execution**:
    -   Run the unit and security test suites to verify tools work without Neo4j connectivity errors.
    -   Command: `python -m pytest /tmp/kublai-repo/tests/`

## Phase 3: The Unified Heartbeat Engine

1.  **Configure Heartbeat Daemon**:
    -   Set up the unified heartbeat daemon (`tools/kurultai/heartbeat_master.py`) to run continuously or as a cron job every 5 minutes.
    -   Command for continuous daemon mode: `python /tmp/kublai-repo/tools/kurultai/heartbeat_master.py --daemon`
2.  **Test Agent Task Execution**:
    -   Verify the heartbeat cycle executes correctly by checking the Neo4j `HeartbeatCycle` and `TaskResult` nodes.
    -   Ensure Ögedei's `health_check` and Jochi's `memory_curation_rapid` run successfully within the token budgets.
3.  **Setup Failover Monitoring**:
    -   Confirm that Ögedei correctly monitors the `Agent.infra_heartbeat` and activates failover if the heartbeat is missed for 120 seconds.