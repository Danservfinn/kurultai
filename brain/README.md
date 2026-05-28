# Brain/wiki replication contract

This directory contains the public schema and runbooks for a Brain-style wiki. It does not contain the live Brain.

## Public schema

```text
brain/
├── AGENTS.md
├── index.md
├── log.md
├── home.md
├── entities/
├── projects/
├── infrastructure/
├── concepts/
├── analyses/
├── docs/plans/
└── raw/assets/
```

## Private/local-only state

- raw source captures that contain private data;
- `hard-private/` people, attachments, conversations, receipts;
- local vector/BM25 indexes and service caches;
- session transcripts and messaging exports.

Use `scripts/bootstrap.sh` to create the skeleton and `brain/templates/page.md` for new pages.
