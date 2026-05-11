# Buildroom Lifecycle

States are artifact-derived: `candidate`, `planned`, `building`, `verifying`, `clean`, `watch`, `investigate`, or `parked`.

Every transition should be recoverable from JSON artifacts alone. Humans and future agents should not need chat history to understand why the room is in its current state.
