# ADR: dedicated Telegram control plane for Hulagu

- Date: 2026-07-25
- Status: accepted as a source contract; runtime not implemented at G1
- Authority: Hulagu v3.4.2 plan §2.3

## Context

Hulagu receives private CV documents and must prove Parse-before-context, durable replay, single-poller ownership, tenant isolation, bounded worker authority, and customer-data exclusion from Hermes/Brain. The inspected general Hermes Telegram path can cache attachments and compose attachment paths or selected text into model input before product parsing.

## Decision

Use a dedicated Hulagu Telegram application service with its own owner-pinned bot identity. The service owns one long-polling offset, deterministic state transitions, durable dedupe/outbox, bounded adapters, and no pre-parse model context. Kublai and existing Hermes/Brain/Kanban remain the operator change-control plane, not the customer runtime.

Hulagu Tasks 0–10 must not import, patch, wrap, or depend on Hermes `MessageEvent`, `media_urls`, `BasePlatformAdapter.send`, `send_document`, plugin hooks, gateway paths, or attachment-cache behavior.

## Rejected alternatives

1. General Hermes profile with the standard Telegram adapter: rejected because attachment paths and selected text can reach model context before product parsing, while a general agent expands tool and identity authority.
2. Synchronous `pre_gateway_dispatch` profile/plugin hook as the whole product: rejected because skip/rewrite cannot provide independent durable asynchronous delivery, outage recovery, or background completion semantics without coupling customer state to the general gateway lifecycle.
3. A second Telegram poller sharing a Hermes bot token: rejected because long polling needs one authoritative offset owner and shared polling creates loss, duplication, and identity ambiguity.
4. A second general agent with terminal/file tools: rejected because customer work needs a deterministic product state machine and least privilege, not broad agent authority.

## Consequences

The chosen design requires a separate bot identity, standalone poller, native product persistence, durable outbox, dedicated app/runner/deletion roles, and independent rollout gates. It prevents reuse of the Hermes attachment path as implementation evidence. A future Hermes conversational layer is out of scope and requires a separate threat model and approval after G6.
