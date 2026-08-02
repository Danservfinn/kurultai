# Buzz ephemeral buildrooms

Kurultai can project selected Hermes Kanban tasks into private, ephemeral Buzz rooms. Buzz is the collaboration and retrieval surface; Hermes Kanban remains the canonical task ledger and authority source.

## Status vocabulary

- **Implemented:** `scripts/buzz_buildroom_controller.py` and its tests exist.
- **Configured:** a local config points to the relay, CLI, state, and secret-env paths.
- **Running:** a scheduler invokes `tick` and receives a valid result.
- **Live E2E:** a dedicated Buzz agent identity has created a room, added members, posted a kickoff, read the room back, posted a terminal receipt, and archived it.
- **Autonomous:** future eligible tasks can repeat that full lifecycle without a human copying credentials or creating channels manually.

Do not call the integration live or autonomous until the dedicated identity and live E2E receipt exist.

## Trigger policy

A task is eligible only while `ready` or `running`, after `activation_not_before`, and when either:

- its title starts with `feat`, `feature`, `bug`, `fix`, `incident`, or `security`; or
- its title/body contains `[buzz-buildroom]` or `Buzz buildroom: true`.

`Buzz buildroom: false` always opts out. The controller creates exactly one channel at most per tick, holds an OS-backed cross-process advisory lock that is released automatically on process exit, uses a full-task-ID-derived SHA-256 binding in deterministic channel names and metadata, searches for that exact bound channel before creation, and uses task-bound kickoff/closure message markers before posting. A freshly created channel must read back as private, active, and correctly bound **before** any member or task message is exported; the same proof is recomputed from the current task ID again before terminal posting or archival. It persists phase state after every successful side effect. These mechanisms recover from lost network responses or state-write crashes and prevent ordinary retry-driven duplicate channels, kickoffs, and terminal receipts.

## Templates

| Class | Visibility | Idle TTL | Prefix |
|---|---|---:|---|
| Feature | Private | 7 days | `build-` |
| Bug/fix | Private | 72 hours | `bug-` |
| Incident/security | Private | Manual closure | `incident-` |

The kickoff exports only an allowlist: validated task ID, title, assignee, reviewer, and explicit single-line `Stop condition:`, `Boundaries:`, and `Deliverables:` values. Tenant-scoped tasks are rejected outright, and every exported identity field is normalized, size-bounded, and privacy-screened before the first Buzz write. The task body, comments, sessions, customer data, private Brain paths, credentials, and secret-shaped values are never copied. A room is not closed merely because its parent implementation task reaches `done`: every declared child must also be terminal, and a `request_changes` or `reject` child verdict keeps the room active.

## Agent roster

`members` maps Hermes profile names to Buzz public keys and channel roles:

```json
{
  "members": {
    "kublai": {"pubkey": "<64 lowercase hex>", "role": "bot"},
    "temujin": {"pubkey": "<64 lowercase hex>", "role": "bot"},
    "mongke": {"pubkey": "<64 lowercase hex>", "role": "bot"}
  },
  "always_include_members": ["kublai"],
  "default_reviewer": "mongke"
}
```

Only owner-reviewed, live Buzz identities belong here. Public keys are not secrets; private keys never belong in this file. A missing profile mapping is skipped rather than replaced with another identity.

## Dedicated identity and secrets

Use a dedicated Buzz agent identity, never the human owner key. Keep only these values in the active Hermes profile’s local `.env`:

- `BUZZ_PRIVATE_KEY`
- `BUZZ_AUTH_TAG` when the relay uses owner attestation

The controller parses those two names directly and passes them through the subprocess environment. It never prints them or places them in argv.

If the dedicated identity does not exist, create it through Buzz Desktop’s owner-reviewed agent flow. This is a human cryptographic/identity gate, not something the controller fabricates.

## Install

```bash
mkdir -p ~/.hermes/profiles/kublai/config/buzz
cp config/buzz/buildrooms.example.json \
  ~/.hermes/profiles/kublai/config/buzz/buildrooms.json

# Set activation_not_before to the current Unix timestamp before enabling.
python3 scripts/buzz_buildroom_controller.py \
  --config ~/.hermes/profiles/kublai/config/buzz/buildrooms.json \
  validate-config

python3 scripts/buzz_buildroom_controller.py \
  --config ~/.hermes/profiles/kublai/config/buzz/buildrooms.json \
  status
```

A profile-local wrapper or no-agent cron may invoke:

```bash
python3 /absolute/repo/path/scripts/buzz_buildroom_controller.py \
  --config ~/.hermes/profiles/kublai/config/buzz/buildrooms.json \
  tick
```

Use a scheduler cadence of two minutes or slower. The script is deterministic and bounded; scheduler delivery should remain local/silent unless the script exits nonzero.

## Search

Search is read-only and does not ingest Buzz into Brain:

```bash
python3 scripts/buzz_buildroom_controller.py \
  --config ~/.hermes/profiles/kublai/config/buzz/buildrooms.json \
  search "Parse rate limits"
```

Results are normalized to message ID, channel, author, time, and content. Secret/private-shaped content is replaced locally with a redaction marker. Durable decisions may enter Brain only through the existing review/privacy workflow.

## Verification

```bash
python3 -m unittest -v tests/test_buzz_buildroom_controller.py
python3 -m py_compile scripts/buzz_buildroom_controller.py
python3 scripts/buzz_buildroom_controller.py --config <config> validate-config
python3 scripts/buzz_buildroom_controller.py --config <config> status
```

A live canary must use a disposable task created after `activation_not_before`, prove exactly one private channel, confirm roster membership and kickoff readback, mark the task done, confirm one terminal receipt and channel archival, and verify state phase `closed`.

## Explicit non-goals

- Buzz does not become a second task database.
- Room messages cannot mutate Kanban state or grant approval.
- The controller does not create or update agent identities.
- Whole-room history is not copied to Brain.
- Customer/private Brain data is forbidden.
- The controller does not dispatch Kanban tasks, change providers/prompts, or execute work.
