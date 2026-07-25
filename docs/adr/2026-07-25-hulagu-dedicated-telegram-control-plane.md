# ADR: dedicated Hulagu Telegram control plane

- Date: 2026-07-25
- Status: Accepted for the approved source contract

## Context

Hulagu must receive customer CVs without allowing raw attachments or attachment paths into a model context, must own one durable Telegram offset, and must keep customer state outside operator Hermes profiles and Brain.

## Decision

Use a dedicated Hulagu service with its own owner-pinned Telegram bot identity, deterministic ingress/state machine, durable database/outbox, and no pre-parse model context. This is a customer product, not a second operator control room. Buildroom/Kanban remains the implementation and incident change-control surface.

## Rejected alternatives

### Rejected: general Hermes profile

A general Hermes profile using the standard Telegram adapter can compose attachment paths or selected text into model input before Hulagu parsing. It also exposes a broader agent/tool/identity surface and couples customer state to an operator runtime.

### Rejected: profile-hook product (`pre_gateway_dispatch`)

A synchronous `pre_gateway_dispatch` profile hook can skip or rewrite an inbound event, but it cannot safely own durable asynchronous completion, outage replay, attachment stripping, or one authoritative Telegram polling offset without remaining coupled to the general gateway lifecycle.

### Rejected: second poller using an existing Hermes bot token

Two pollers cannot safely share Telegram offset ownership. Hulagu requires a distinct bot identity/token and singleton polling proof at later gates.

## Consequences

Hulagu source has one home under `products/hulagu`. V1 performs no model calls and exposes no general shell, browser, host-filesystem, or agent toolset. A future conversational layer requires a separate approved plan after the bounded product proves its isolation contracts.
