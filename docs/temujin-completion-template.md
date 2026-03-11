# Temujin Task Completion Template

**Purpose**: Ensure task completions pass the completion gate audit on first try.

**Usage**: Copy this format into your task output before marking `.done.md`

---

## Resolution

<Brief 1-2 sentence summary of what was accomplished>

### What Was Done
- <Specific action 1>
- <Specific action 2>
- <Specific action 3>

### Files Changed
- `<path/to/file1>` - <brief description of change>
- `<path/to/file2>` - <brief description of change>

### Verification
- [x] <How you verified it works>
- [x] <Tests run and passed>
- [x] <Manual testing checklist>

---

**Notes:**
- The `## Resolution` heading is REQUIRED — the gate checks for this exact pattern
- Minimum 3 headings total (Resolution + at least 2 subsections)
- "What Was Done", "Files Changed", and "Verification" are recommended subsections
- Be specific: list actual files, actual tests, actual verification steps
- If no tests were written, explain why (e.g., "N/A - configuration change only")

**Common failures to avoid:**
- Don't use different heading text like "## Summary" or "## Result" — must be "## Resolution"
- Don't omit the Files Changed section — gate audits flag this
- Don't skip Verification — gate audits flag "Tests not written"

**Example (minimal but complete):**

## Resolution

Fixed the authentication timeout bug by increasing the session timeout from 15 to 30 minutes.

### What Was Done
- Modified `src/middleware/session.ts` to increase `SESSION_TIMEOUT` constant
- Updated unit tests to reflect new timeout value

### Files Changed
- `src/middleware/session.ts` - Changed SESSION_TIMEOUT from 900 to 1800
- `src/__tests__/session.test.ts` - Updated test expectations

### Verification
- [x] Ran unit tests: all passed
- [x] Manually tested login session — now expires after 30 minutes as expected
- [x] No breaking changes to existing functionality
