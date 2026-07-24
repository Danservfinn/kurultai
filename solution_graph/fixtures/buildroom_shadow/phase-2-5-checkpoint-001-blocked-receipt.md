# Phase 2.5 ShadowEvaluationCorpus/v1 checkpoint blocked receipt

Status: blocked — do not publish as a reviewed 10-case checkpoint.

Artifact choice: truthful blocked receipt. The reviewed 10-case ShadowEvaluationCorpus/v1 checkpoint is not available in the repository state validated for this receipt.

Validated source
- Corpus path: `solution_graph/fixtures/buildroom_shadow/shadow-corpus.json`
- Corpus schema: `ShadowEvaluationCorpus/v1`
- Corpus id: `shadow-corpus:solution-graph-phase-2-5/bootstrap`
- Case target for the later evaluation soak: 25-50 reviewed shadow cases
- Checkpoint target for this gate: 10 strict genuine non-demo completed Buildroom cases with independent review

Counts
- Total corpus rows: 1
- Independently reviewed corpus rows: 0
- Strict genuine non-demo completed Buildroom candidate rows: 0
- Independently reviewed strict rows counted toward the 10-case checkpoint: 0
- Strict candidate shortfall to 10: 10
- Independently reviewed checkpoint shortfall to 10: 10
- Post-build verification agreement counts: agree=0, disagree=0, not_yet_reviewed=1, unknown=0
- Acceptance counts: accepted=0, overridden=0, rejected=0, unknown_or_not_yet_reviewed=1
- 25-reviewed soak gate: `insufficient_reviewed_cases`
- First-10 checkpoint gate: `blocked_pending_genuine_reviewed_cases`

Why blocked
- The validated corpus is the byte-identical origin/main bootstrap fixture, containing only the public research-digest bootstrap row. It is not a strict genuine non-demo completed Buildroom case and does not satisfy the first-10 checkpoint.
- The row conservatively retains `acceptance=not_yet_reviewed`, `override=unknown`, `proof_debt=unknown`, and `post_build_verification_agreement=not_yet_reviewed`. It does not count as independently reviewed or successful.
- No private/raw Buildroom payloads, operator-identifying data, runtime/service/cron changes, dispatch enablement, execution authority, or artifact invocation are required or included by this receipt.

Next safe intake trigger
- Resume checkpoint assembly after at least ten public-safe, strict genuine non-demo completed Buildroom cases are available.
- Each intake case must include the five required reference types: operator summary, implementation receipt, verification delta, trust report, and retention review.
- All ten cases must have independent, non-contradictory reviewed outcomes recorded before any row can count toward the reviewed checkpoint.
- Exclude raw/private payloads, duplicate cases, demo cases, extrapolated outcomes, unreviewed assumptions, and any case whose acceptance/proof-debt/post-build-verification state is contradictory.

Authority boundary
- Authority: none
- Dispatch allowed: false
- Requires operator approval: true
- Artifact invocation count: 0
- Runtime/service/cron configuration modified: false
- Publication/push: not allowed by this receipt; requires a separate operator gate
