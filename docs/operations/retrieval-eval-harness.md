# Native Brain retrieval-eval harness

Implemented from Brain plan `${BRAIN_ROOT}/docs/plans/2026-05-10-native-brain-retrieval-eval-capture-replay.md`.

## Safety boundary

- Dev/local only.
- Production capture is disabled by default and not wired to service traffic.
- Public fixtures may be committed only after scrub/validation.
- Hard-private fixtures must be written under `~/.kublai/retrieval-eval/private/` and are not committed.
- Fixtures store `rel_path`, `body_hash`, rank, and coarse `score_bucket`; they do not store raw body text, snippets, frontmatter, full scores, API keys, tokens, passwords, secrets, or Authorization/Bearer strings.

## Commands

```bash
PYTHONPATH=/path/to/kurultai python -m kublai.retrieval_eval status
PYTHONPATH=/path/to/kurultai python -m kublai.retrieval_eval source-policy \
  --brain-root "$BRAIN_ROOT" \
  --report-json /tmp/brain-source-policy-report.json
PYTHONPATH=/path/to/kurultai python -m kublai.retrieval_eval validate \
  --fixtures tests/fixtures/retrieval_eval/public-smoke.ndjson
PYTHONPATH=/path/to/kurultai python -m kublai.retrieval_eval replay \
  --fixtures tests/fixtures/retrieval_eval/public-smoke.ndjson \
  --brain-root "$BRAIN_ROOT" \
  --privacy-scope public \
  --k 10 \
  --report-json /tmp/retrieval-eval-report.json \
  --explain-json /tmp/retrieval-eval-explain.json
```

## Current public smoke fixture

`tests/fixtures/retrieval_eval/public-smoke.ndjson` covers four public recall cases:

- GBrain v0.36 / skillpack disposition recall.
- x402 / Parse Agents payment policy recall.
- Ogedei bridge `capture_all` silent acknowledgement safety recall.
- Parse Agents x402 + Stripe dual payment rail recall.

`tests/fixtures/retrieval_eval/source-policy.ndjson` covers two scrubbed public replay cases with `source_policy` tier metadata for source-aware retrieval regressions.

Current local replay receipt on 2026-05-22 after source-policy enforcement:

- case count: 4
- mean Jaccard@k: 0.5683275058275058
- top-1 stability: 1.0
- source policy summary: `{"tier_1": 40}`
- failures: none

## Verification

The source policy implementation lives in `kublai/retrieval_eval.py` and the source-map/page convention is documented in `docs/operations/brain-source-policy.md`.

```bash
python -m pytest tests -q
python -m py_compile kublai/retrieval_eval.py kublai/__init__.py tests/test_retrieval_eval.py
git diff --check
```
