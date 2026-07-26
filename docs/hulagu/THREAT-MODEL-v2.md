# Hulagu v2 threat model — autonomous authority amendment

Status: G0 autonomous authority candidate

Protected assets include tenant data, credentials, lifecycle/effect ledgers, archive bytes, exact policy/command/write-set manifests, reviews, closure envelopes, and protected refs. Credentials remain isolated by service/profile/customer and never enter logs.

G0 fails closed on missing/stale/replayed review, producer/verifier collision, base or hash drift, false predicate, unknown field/effect, forbidden surface, absent consent, expired communication permission, test mismatch, payload/evidence mutation, or protected-ref reproduction failure.

Permanent forbidden surfaces are payments, public posting, identity/SOUL changes, hard deletes, and unapproved outbound email/chat. No automatic pilot invitation exists. No runtime profile, credential, VM, customer data, Sheets effect, message, cron activation, or source-workspace mutation is authorized by this overlay.
