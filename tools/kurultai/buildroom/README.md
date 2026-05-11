# Kurultai Buildroom

Buildroom is the public-safe contract surface for the Auto-think -> Auto-build chain. It stores typed JSON artifacts that show why an idea exists, who approved it, what Coder was allowed to build, what changed, what QA verified, and what the operator should know.

Canonical repo mirror: `tools/kurultai/buildroom/`. The long-term brain location can mirror these same docs/schemas/fixtures when the brain-side task runs.

## Quick start

```bash
cd tools/kurultai/buildroom
python scripts/validate_room.py rooms/demo-room
python scripts/build_operator_summary.py rooms/demo-room
python scripts/kanban_adapter.py task-packet rooms/demo-room /tmp/buildroom-task-packet.json
python scripts/kanban_adapter.py receipt rooms/demo-room /tmp/kanban-completion.json
python scripts/qa_trust.py qa-packet rooms/demo-room /tmp/buildroom-qa-task-packet.json
python scripts/qa_trust.py delta rooms/demo-room
python scripts/qa_trust.py trust rooms/demo-room
python scripts/export_sanitized_bundle.py rooms/demo-room /tmp/kurultai-buildroom-export
```

## Directory map

- `docs/` — lifecycle, architecture, operator model, safety, retention notes.
- `schemas/` — JSON Schemas for every lifecycle artifact.
- `rooms/demo-room/` — complete demo fixture covering every artifact stage.
- `scripts/` — stdlib-friendly validation, room creation, operator summary, Kanban adapter, QA/trust, sanitized export.

## Safety boundary

Buildroom bundles are designed to be public-safe after sanitization, but source rooms can contain internal references. Do not place secrets, tokens, raw private logs, or private absolute paths in artifacts unless the sanitizer has a specific redaction rule and the source is never exported directly.
