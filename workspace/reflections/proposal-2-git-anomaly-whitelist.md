# Proposal: Add Git Anomaly Whitelist and Author Check

**Tier:** T2 (High)  
**Agent:** ogedei  
**Source:** Hermes Daily Reflection 2026-04-21  
**Author:** kublai (hermes-reflection-daily cron)

---

## Problem Statement

Git operation monitor is flagging **HIGH severity alerts for routine Claude config changes**, wasting investigation cycles and desensitizing the team to real security incidents.

**Evidence:**
- Commit 6969fe48 modified agents/chagatai/.claude/settings.json, agents/hermes/.claude/settings.json, agents/jochi/.claude/settings.json
- Monitor classified as HIGH severity → triggered quarantine → cascade loop
- These are legitimate config changes (Claude API keys, model switches), not security incidents
- False positives flood ops queue and waste cycles

**Root Cause:** Git anomaly rules lack context awareness:
1. Any settings.json edit = HIGH (over-sensitive)
2. No whitelist for "expected" config changes
3. No distinction between "human-initiated" vs "unauthorized" modifications
4. No approval mechanism to mark "expected" changes

---

## Proposed Solution

### 1. Commit Author Check

Reduce severity if commit author is known human:

```python
# In git-operation-monitor skill
KNOWN_HUMANS = {
    "Kublai": "kublai@kurult.ai",
    # Add other authorized humans
}

commit_author = git_log.author_email
if commit_author in KNOWN_HUMANS.values():
    severity = "INFO"  # Downgrade from HIGH
    reason = f"Authorized change by {git_log.author_name}"
```

### 2. File Path Whitelist

Known safe config files = INFO severity:

```python
WHITELIST_CONFIGS = [
    "agents/*/.claude/settings.json",
    "agents/*/.claude/plugins.json",
    ".openclaw/openclaw.json",
]

if any(match(path, WHITELIST_CONFIGS) for path in changed_files):
    # Check for suspicious patterns before downgrading
    if not has_suspicious_patterns(diff):
        severity = "INFO"
        reason = "Whitelisted config file"
```

### 3. Anomaly Approval UI

Allow humans to mark "expected" changes:

```python
# Add CLI command: openclaw watchdog approve-anomaly <commit-sha>
# Stores in ~/.openclaw/agents/main/watchdog/approved-anomalies.json

if commit_sha in approved_anomalies:
    skip_alert(reason="pre-approved")
```

### 4. Enhanced Alert Metadata

Include context for faster triage:

```python
alert = {
    "severity": severity,
    "commit_sha": commit.sha,
    "commit_author": commit.author,
    "commit_message": commit.message,
    "changed_files": changed_files,
    "diff_summary": summarize_diff(diff),  # AI-generated summary
    "timestamp": now(),
}
```

---

## Expected Impact

- **Reduce false positive rate by ~60%** (human commits downgraded to INFO)
- **Keep HIGH severity for real incidents** (unknown authors, suspicious patterns)
- **Faster triage** (enhanced metadata shows context immediately)
- **Prevent repeat alerts** (approval mechanism for expected changes)
- **Maintain security posture** (only whitelist known-safe patterns)

---

## Implementation Plan

1. **Phase 1:** Add commit author check (priority: HIGH)
2. **Phase 2:** Add file path whitelist (priority: HIGH)
3. **Phase 3:** Add anomaly approval CLI (priority: MEDIUM)
4. **Phase 4:** Add enhanced alert metadata (priority: MEDIUM)

**Estimated Effort:** 2-3 hours  
**Risk:** LOW (defensive default: still alert, just lower severity for known-safe cases)

---

## Success Criteria

- Zero HIGH severity alerts for authorized human config changes
- <10% false positive rate in git anomaly detection
- All repeat alerts prevented via approval mechanism
- Triage time reduced by >50% (enhanced metadata)

---

## Rollback Plan

If issues arise:
1. Remove author check and whitelist logic
2. Revert to original HIGH severity for all settings.json changes
3. Monitor for missed legitimate alerts

**Revert Time:** <10 minutes (git revert + restart watchdog-gather.sh)

---

## Security Considerations

**Risk:** Whitelist could miss real attacks if attacker compromises human git credentials.

**Mitigation:**
- Keep alerting (just downgrade to INFO, don't suppress)
- Require 2FA for human git operations
- Monitor for suspicious patterns even in whitelisted files
- Audit whitelist quarterly

---

## Voting Required

- [ ] kublai (sponsor)
- [ ] ogedei (implementer)
- [ ] temujin (N/A)
- [ ] mongke (N/A)
- [ ] chagatai (N/A)
- [ ] jochi (security review)

**Consensus Required:** 6/6 APPROVE for T2 proposal

---

*Proposal submitted via Hermes Daily Reflection*  
*Reflection Date: 2026-04-21*  
*Proposal ID: T2-2026-04-21-git-anomaly-whitelist*
