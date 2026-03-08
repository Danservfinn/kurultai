# Chagatai Routing Guide

## Purpose
This document clarifies domain boundaries for the Writer agent (chagatai) to reduce misroutes and task rejections under Rule C16.

## Rule C16: Domain Boundary Enforcement
> WHEN chagatai receives task AND task_type NOT IN (blog, documentation, changelog, marketing, social_media, article, guide, README, draft) THEN reject task, route to appropriate agent.

## Chagatai's Domain: Primary Output is PROSE

Tasks routed to chagatai MUST have **writing/content creation** as their PRIMARY output.

### ACCEPTED Task Types (with examples)

| Task Type | Example Tasks | Primary Output |
|-----------|---------------|----------------|
| **blog** | "Write a blog post about feature X", "Draft blog announcement" | Published blog article |
| **documentation** | "Document the API endpoints", "Update README with new config" | Technical documentation |
| **changelog** | "Generate changelog for v1.5", "Write release notes" | Release notes/changelog |
| **marketing** | "Write marketing copy for landing page", "Create product announcement" | Marketing materials |
| **social_media** | "Draft Twitter thread about launch", "Write LinkedIn post" | Social content |
| **article** | "Write technical article about architecture", "Create guide for users" | Published article |
| **guide** | "Write user guide for onboarding", "Create tutorial for feature X" | Tutorial/guide |
| **README** | "Update README with installation steps", "Create README for new repo" | README file |
| **draft** | "Draft proposal for feature Y", "Write initial outline for docs" | Draft content |

### REJECTED Task Types (route elsewhere)

| Task Type | Example | Route To | Why |
|-----------|---------|----------|-----|
| code implementation | "Implement user auth" | temujin | Primary output is code |
| bug fixing | "Fix login bug" | temujin | Primary output is code |
| security review | "Review for vulnerabilities" | jochi | Analysis, not prose |
| market research | "Research competitors" | mongke | Research, not content |
| ops tasks | "Restart the server" | ogedei | Operations |
| testing | "Write tests for feature X" | jochi | Code/analysis |
| design/planning | "Design architecture for X" | temujin | Technical design |

## Routing Decision Tree

```
Is the PRIMARY OUTPUT prose/content?
├─ Yes → Is it for publication/documentation?
│  ├─ Yes → chagatai (Writer)
│  └─ No → Check other domains
└─ No → Not chagatai (route by primary output type)
```

## Keyword Ambiguity Resolution

Some keywords overlap with other agents. Use PRIMARY OUTPUT test:

| Keyword | chagatai context | Other agent context |
|---------|-----------------|-------------------|
| "create" | create content/blog/guide | create feature/code → temujin |
| "update" | update docs/README | update code/config → temujin/ogedei |
| "write" | write documentation/post | write code → temujin |
| "explain" | explain in docs/guide | explain via code → temujin |
| "draft" | draft content | draft not applicable elsewhere |

## Common Misroutes and Corrections

| Misroute | Correct Route | Reason |
|----------|---------------|--------|
| "Create user authentication system" | temujin | Primary output is code, not prose |
| "Write tests for payment flow" | jochi | Tests = analysis, not content |
| "Research competitor pricing" | mongke | Research, not content creation |
| "Update deployment config" | ogedei | Ops configuration |
| "Fix broken email template" | temujin | Code fix, even though output is HTML |
| "Design new API endpoints" | temujin | Technical design/architecture |

## Special Cases

### "Research and write" tasks
- "Research topic and write blog post" → chagatai (output is content)
- "Research competitors for feature" → mongke (output is research findings)

### "Update documentation" tasks
- "Update docs to reflect new feature" → chagatai (doc sync)
- "Update code to match documentation" → temujin (code change)

### "Create presentation" tasks
- "Create slide deck content" → chagatai (prose)
- "Implement presentation feature" → temujin (code)

## When in Doubt: Primary Output Test

Ask: **What is the PRIMARY deliverable?**

- Deliverable is prose/content → chagatai
- Deliverable is code → temujin
- Deliverable is findings/data → mongke
- Deliverable is analysis/report → jochi
- Deliverable is system health → ogedei

## Version History
- 2026-03-08: Initial version to address Rule C16 rejections and routing ambiguity
