# Buildroom Architecture

Buildroom is a filesystem-backed contract chain, not a scheduler. Native Hermes Kanban, profiles, cron, receipts, and brain-service remain the runtime organs.

Flow: research input -> idea contract -> intent review -> main review -> product/build plans -> implementation receipt -> verification report/delta -> trust report -> retention review -> operator summary.

Public-safe contract files reference private runtime data by IDs, hashes, or sanitized paths. Private adapters may read live Kanban/receipt/brain state, but they should not copy private logs into export bundles.
