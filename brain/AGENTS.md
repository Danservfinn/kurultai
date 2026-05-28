# Brain Wiki Schema

This is a local knowledge base maintained by LLM agents and curated by the operator.

## Rules

- Markdown pages use YAML frontmatter.
- Use wikilinks (`[[page-name]]`) for internal references.
- Dates use ISO 8601 (`YYYY-MM-DD`).
- Keep private, secret, customer, and person-specific material in local-only private tiers.
- Public exports contain schema, templates, and synthesized non-sensitive patterns only.

## Required frontmatter

```yaml
---
type: entity | project | infrastructure | concept | analysis
status: active | maintenance | stalled | archived | exploratory
updated: 2026-01-01
created: 2026-01-01
sources: 0
tags: []
---
```

## Post-write validation

- Frontmatter exists and matches directory type.
- `created` is preserved on updates.
- `updated` is current.
- Page has meaningful wikilinks.
- Page is listed in `index.md` when intended for the public/local catalog.
