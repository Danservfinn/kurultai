# Hulagu V2

Hulagu is the dedicated, private Telegram job-search product defined by the frozen v3.4.2 authority. This tree is source-only at G1: it contains contracts, schemas, documentation, and read-only verification tools. It is not installed, running, autonomous, deployed, or pilot-validated.

## Immutable authority

<!-- HULAGU_PLAN_GATE_BEGIN -->
```json
{
  "plan_path": "/Users/kublai/brain/docs/plans/2026-07-27-kublai-hulagu-job-search-agent-implementation-plan-v3.4.2.md",
  "plan_sha256": "2c7cfd43ad2f1372cef8a076667966e9ffa72cfc97c163143e6bcaf3ed5c2c99",
  "gate_path": "/Users/kublai/brain/docs/plans/2026-07-27-hulagu-v3.4.2-research-model-call-gate.md",
  "gate_sha256": "1cadb7e749f793abbf5baa670d75a206b9723ca00ce1056bc37aeb8dafe41dd2",
  "brain_commit": "3417798b",
  "g0_record_commit": "bf1188b1",
  "receipt_path": "/Users/kublai/brain/docs/plans/reviews/2026-07-27-hulagu-v3.4.2-g-1-joint-freeze-receipt.md"
}
```
<!-- HULAGU_PLAN_GATE_END -->

The plan and binding research gate were committed together at Brain commit `3417798b` on `human-curation`. The explicit G0 owner record is at Brain commit `bf1188b1`. Any byte drift in the plan or gate voids this contract until a fresh joint exact-hash review and owner gate are recorded. The rejected v3.4.1 candidate is not authority.

## G1 boundary

Allowed here: Task 0 documentation, twelve JSON Schemas, Python toolchain metadata, static contracts, tests, and read-only doctor/verifier behavior.

Not authorized: vault writes, PostgreSQL or container startup, provider/model calls, bot configuration or messages, credentials, customer data, deployment, cron, job applications, employer contact, staging, commits, pushes, or promotion to later gates. PostgreSQL and container runtime state remain `not_evaluated` at G1.

## Commands

```bash
uv sync --frozen
uv run pytest tests/contract tests/integration/test_vault_preflight.py -vv
uv run pytest tests/integration/test_container_mount_probe.py -vv
uv run hulagu-verify-plan-gate
```

The doctor accepts only explicit absolute paths and an owner-enrolled vault UUID. It never searches `PATH`, auto-enrolls a volume, starts a service, or performs a vault write. A G1 atomic-rename result can only be evaluated from an explicit synthetic fixture; the real fsync/rename spike is separately owner-gated at G2.

## Navigation

- [Architecture](../../docs/architecture/hulagu.md)
- [Dedicated Telegram control-plane ADR](../../docs/adr/2026-07-25-hulagu-dedicated-telegram-control-plane.md)
- [Threat model](../../docs/hulagu/THREAT-MODEL.md)
