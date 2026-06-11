# Brain retrieval source policy

This repo has a local/dev implementation of the Brain retrieval source policy in `kublai.retrieval_eval`. It is a safety wrapper for evaluation replay and diagnostics; it is not wired into live brain-service production traffic.

## Tiers

| Tier | Source type | Default behavior | Examples |
|---|---|---|---|
| 1 | canonical | include and boost | `home.md`, `hot.md`, `log.md`, `entities/`, `projects/`, `infrastructure/`, `concepts/`, `runbooks/`, `status/`, `analyses/`, `docs/research/`, `docs/plans/` |
| 2 | explicit | include as fallback/down-ranked | `operations/reports/`, `operations/tasks/`, `operations/verification/`, `operations/telemetry/`, `operations/runs/`, `content/`, `receipts/`, `synthesis/`, `proposals/` |
| 3 | forensic | exclude by default; opt in with forensic modes | `raw/`, `captures/`, `graphify-out/` |
| 3 | excluded | exclude by default; only explicit forensic/excluded modes | `operations/backups/`, `_archive/`, `archive/`, `.qmd/`, `.git/`, `node_modules/`, `__pycache__/` |
| 4 | hard_private | hard excluded from public search | `hard-private/` and any path containing `/hard-private/` |

## Page convention

Retrieval-facing knowledge should be folded into Tier 1 pages when it becomes durable. Tier 2 is acceptable for receipts, run reports, verification records, proposals, and current operational evidence. Tier 3 is for raw captures, generated graph reports, backups, archives, and other high-noise evidence that should not answer normal operator queries unless forensic mode is explicitly requested. Tier 4 is private and must never appear in public fixtures or public replay output.

## Dev commands

```bash
PYTHONPATH=/path/to/kurultai-repo python -m kublai.retrieval_eval source-policy \
  --brain-root /path/to/brain \
  --report-json /tmp/brain-source-policy-report.json

PYTHONPATH=/path/to/kurultai-repo python -m kublai.retrieval_eval replay \
  --fixtures tests/fixtures/retrieval_eval/public-smoke.ndjson \
  --brain-root /path/to/brain \
  --privacy-scope public \
  --k 10 \
  --report-json /tmp/retrieval-eval-report.json \
  --explain-json /tmp/retrieval-eval-explain.json
```

Replay reports include `source_policy_summary`. The explain receipt is intentionally compact and scrubbed: schema version, case count, failure count, policy enforcement boolean, and tier counts only.

## Safety properties

- Public scope skips hard-private paths before scoring.
- Normal replay excludes raw captures, graphify output, backups, archives, and generated/dependency folders.
- Forensic modes (`retrieval_mode="forensic"` or `filters={"source_policy": "include-forensic"}`) are explicit and local/dev only.
- Scrubbed fixtures still do not persist raw body text, snippets, frontmatter, secrets, or exact scores.
