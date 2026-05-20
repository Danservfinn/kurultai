# Native Brain retrieval-eval harness

Implemented from Brain plan `/Users/kublai/brain/docs/plans/2026-05-10-native-brain-retrieval-eval-capture-replay.md`.

## Safety boundary

- Dev/local only.
- Production capture is disabled by default and not wired to service traffic.
- Public fixtures may be committed only after scrub/validation.
- Hard-private fixtures must be written under `~/.kublai/retrieval-eval/private/` and are not committed.
- Fixtures store `rel_path`, `body_hash`, rank, and coarse `score_bucket`; they do not store raw body text, snippets, frontmatter, full scores, API keys, tokens, passwords, secrets, or Authorization/Bearer strings.

## Commands

```bash
PYTHONPATH=/Users/kublai/kurultai/kurultai-repo python -m kublai.retrieval_eval status
PYTHONPATH=/Users/kublai/kurultai/kurultai-repo python -m kublai.retrieval_eval validate \
  --fixtures tests/fixtures/retrieval_eval/public-smoke.ndjson
PYTHONPATH=/Users/kublai/kurultai/kurultai-repo python -m kublai.retrieval_eval replay \
  --fixtures tests/fixtures/retrieval_eval/public-smoke.ndjson \
  --brain-root /Users/kublai/brain \
  --privacy-scope public \
  --k 10 \
  --report-json /tmp/retrieval-eval-report.json
```

## Current public smoke fixture

`tests/fixtures/retrieval_eval/public-smoke.ndjson` covers four public recall cases:

- GBrain v0.36 / skillpack disposition recall.
- x402 / Parse Agents payment policy recall.
- Ogedei bridge `capture_all` silent acknowledgement safety recall.
- Parse Agents x402 + Stripe dual payment rail recall.

Current local replay receipt on 2026-05-20:

- case count: 4
- mean Jaccard@k: 1.0
- top-1 stability: 1.0
- failures: none

## Verification

```bash
/Users/kublai/.hermes/hermes-agent/venv/bin/python -m pytest tests -q
/Users/kublai/.hermes/hermes-agent/venv/bin/python -m py_compile kublai/retrieval_eval.py kublai/__init__.py tests/test_retrieval_eval.py
git diff --check
```
