# Conversation Privacy Policy

**Version:** 1.0
**Last Updated:** 2026-03-08
**System:** OpenClaw Conversation Management System

## Overview

This privacy policy governs the collection, storage, access, and management of conversation data within the OpenClaw system. The system is designed with privacy-first principles, ensuring user data sovereignty, transparency, and security.

### Core Privacy Principles

1. **Transparency**: Users know what data is collected and how it's used
2. **Access**: Users can view their own data at any time
3. **Rectification**: Users can correct inaccurate data
4. **Erasure**: Users can request deletion of their data
5. **Portability**: Users can export their data in a structured format

---

## 1. Data Classification

### 1.1 Personal Identifiable Information (PII)

| Data Type | Description | Sensitivity Level | Storage Location |
|-----------|-------------|-------------------|------------------|
| Phone Number | User's contact identifier (e.g., +1234567890) | **HIGH** | Conversation filenames and metadata |
| User Name | Display name from conversations | **MEDIUM** | Conversation content |

### 1.2 Conversation Content

| Data Type | Description | Sensitivity Level | Storage Location |
|-----------|-------------|-------------------|------------------|
| Messages | User-sent messages | **HIGH** | Main conversation files |
| Responses | System or agent responses | **MEDIUM** | Main conversation files |
| Attachments | File references or embedded content | **MEDIUM** | Conversation metadata |

### 1.3 Metadata

| Data Type | Description | Sensitivity Level | Storage Location |
|-----------|-------------|-------------------|------------------|
| Timestamps | Message creation times | **LOW** | All conversation records |
| Channels | Source channels (e.g., SMS, WhatsApp) | **MEDIUM** | Conversation metadata |
| Topics | Derived conversation topics | **LOW** | Analysis files |
| Message Counts | Aggregate statistics | **LOW** | Analytics |

### 1.4 Derived Data

| Data Type | Description | Sensitivity Level | Storage Location |
|-----------|-------------|-------------------|------------------|
| Sentiment Analysis | Emotional tone classification | **MEDIUM** | Analysis outputs |
| Action Items | Extracted tasks or commitments | **MEDIUM** | Task management system |
| Summaries | Generated conversation summaries | **MEDIUM** | Archive files |

---

## 2. Access Control Matrix

### 2.1 Permission Levels

| Role | Own Data | Others' Data | Admin Functions | Audit Access |
|------|----------|--------------|-----------------|--------------|
| **User** | ✅ Read/Write | ❌ No access | ❌ No access | ❌ No access |
| **Admin** | ✅ Read/Write | ✅ Read/Write* | ✅ Full access | ✅ Read-only |
| **System** | ✅ Automated processing | ❌ No access | ❌ No access | ✅ Write-only |

*Admin access to other users' data requires explicit reason and is logged.

### 2.2 Access Control Implementation

#### File-Level Permissions
```bash
# Conversation files: User-readable only
-rw------- 1 user group 12345 Mar  8 10:00 +1234567890.json

# Directory permissions: User-executable only
drwx------ 2 user group 4096 Mar  8 10:00 conversations/
```

#### Application-Level Checks
```python
# Phone number validation before access
def can_access_conversation(user_phone: str, conversation_phone: str) -> bool:
    # Normalize phone numbers
    normalized_user = normalize_phone(user_phone)
    normalized_conv = normalize_phone(conversation_phone)

    # Direct match
    if normalized_user == normalized_conv:
        return True

    # Admin check with logging
    if is_admin(user_phone):
        log_admin_access(user_phone, conversation_phone, "direct_access")
        return True

    # Permission denied
    log_access_denied(user_phone, conversation_phone)
    return False
```

### 2.3 Admin Whitelist

**Location:** `~/.openclaw/config/privacy_admins.json`

```json
{
  "version": "1.0",
  "last_updated": "2026-03-08T10:00:00Z",
  "admins": [
    {
      "phone_number": "+1234567890",
      "name": "System Administrator",
      "role": "super_admin",
      "granted_at": "2026-01-01T00:00:00Z",
      "granted_by": "system",
      "access_scope": "all"
    }
  ]
}
```

**Admin Access Requirements:**
- Must be whitelisted in `privacy_admins.json`
- Must provide explicit reason for accessing user data
- All access attempts are logged
- Regular audit reviews conducted monthly

---

## 3. Retention Policy

### 3.1 Data Lifecycle

```
Active Conversations (50 most recent)
    ↓
Monthly Archive (after 50 messages)
    ↓
Long-term Storage (max 12 months)
    ↓
Deletion (unless user requests extension)
```

### 3.2 Retention Periods

| Data Type | Active | Archive | Maximum | Deletion |
|-----------|--------|---------|---------|----------|
| Conversations | 50 recent | Monthly | 12 months | After 12 months* |
| Metadata | Active | Monthly | 12 months | After 12 months |
| Audit Logs | Continuous | - | 1 year | After 1 year |
| Admin Records | Continuous | - | 3 years | After 3 years |
| Derived Data | Active | Monthly | 12 months | After 12 months |

*Users can request earlier deletion or extended retention.

### 3.3 Archive Structure

```
~/.openclaw/data/conversations/
├── active/
│   ├── +1234567890.json          # Most recent 50 messages
│   └── +9876543210.json
├── archive/
│   ├── 2026-01/
│   │   ├── +1234567890.json
│   │   └── monthly_summary.json
│   ├── 2026-02/
│   └── 2026-03/
└── deleted/
    └── marked_for_deletion/
```

### 3.4 Automated Cleanup

```bash
# Monthly archive job (runs on 1st of each month)
0 0 1 * * /usr/local/bin/archive-conversations.sh

# Quarterly cleanup job (removes data > 12 months)
0 2 1 */3 * /usr/local/bin/cleanup-old-conversations.sh

# Annual audit log cleanup
0 3 1 1 * /usr/local/bin/cleanup-audit-logs.sh
```

---

## 4. Privacy Request Workflow

### 4.1 Request Types

| Request Type | Description | SLA | Confirmation Required |
|--------------|-------------|-----|----------------------|
| **Export** | Full data package in JSON/CSV | 24 hours | No |
| **View** | Read-only access via web interface | Immediate | No |
| **Delete** | Permanent removal of all data | 7 days | **Yes** (explicit) |
| **Rectify** | Correct inaccurate information | 48 hours | No |
| **Restrict** | Limit processing to storage only | 48 hours | No |

### 4.2 Export Request Flow

```
1. User submits export request
   ↓
2. System validates user identity (phone verification)
   ↓
3. Request logged in privacy request tracker
   ↓
4. Data package assembled (conversations + metadata + derived data)
   ↓
5. Package encrypted and uploaded to secure location
   ↓
6. Download link sent to user (expires in 48 hours)
   ↓
7. Access logged in audit trail
```

**Export Package Structure:**
```
export_+1234567890_20260308.tar.gz
├── conversations/
│   ├── active.json
│   └── archive_2025-01_to_2026-03.json
├── metadata/
│   ├── message_stats.json
│   └── topic_analysis.json
├── derived/
│   ├── sentiment_analysis.json
│   └── action_items.json
└── README.txt (data dictionary)
```

### 4.3 Deletion Request Flow

```
1. User submits deletion request
   ↓
2. System sends confirmation code (SMS)
   ↓
3. User must reply with confirmation code
   ↓
4. Second confirmation: "Are you sure? Type DELETE to confirm"
   ↓
5. User must type "DELETE"
   ↓
6. Deletion process initiated (7-day grace period starts)
   ↓
7. Data moved to "marked_for_deletion" directory
   ↓
8. Final deletion after 7-day grace period
   ↓
9. Deletion certificate sent to user
```

**Deletion Certificate:**
```json
{
  "certificate_id": "del_20260308_1234567890",
  "user_phone": "+1234567890",
  "deletion_timestamp": "2026-03-15T10:00:00Z",
  "data_types_deleted": [
    "conversations",
    "metadata",
    "derived_data",
    "archive_records"
  ],
  "retention_backup": "none",
  "confirmation_code": "ABC123XYZ",
  "processed_by": "system"
}
```

### 4.4 Request Tracking

**Location:** `~/.openclaw/data/privacy_requests/`

```json
{
  "request_id": "req_20260308_export_1234567890",
  "request_type": "export",
  "user_phone": "+1234567890",
  "status": "processing",
  "submitted_at": "2026-03-08T10:00:00Z",
  "sla_deadline": "2026-03-09T10:00:00Z",
  "assigned_to": "system",
  "progress": [
    {
      "step": "validation",
      "status": "completed",
      "timestamp": "2026-03-08T10:01:00Z"
    },
    {
      "step": "data_assembly",
      "status": "in_progress",
      "timestamp": "2026-03-08T10:05:00Z"
    }
  ],
  "completion_estimate": "2026-03-08T12:00:00Z"
}
```

### 4.5 SLA Monitoring & Escalation

```python
# Automated SLA monitoring
def check_sla_compliance():
    requests = get_all_pending_requests()
    for request in requests:
        if datetime.now() > request['sla_deadline']:
            # Escalate
            escalate_violation(request)
            notify_admin(request)
            log_sla_breach(request)

# Escalation levels
ESCALATION_LEVELS = {
    "warning": 4,   # 4 hours before deadline
    "critical": 2,  # 2 hours before deadline
    "breached": 0   # After deadline
}
```

---

## 5. Audit Logging

### 5.1 Audit Log Structure

**Location:** `~/.openclaw/logs/privacy_audit.log`

```log
2026-03-08T10:00:00Z | ACCESS | user:+1234567890 | conversation:+1234567890 | action:read | result:success | ip:192.168.1.1
2026-03-08T10:01:00Z | ACCESS | user:+1234567890 | conversation:+1234567890 | action:write | result:success | ip:192.168.1.1
2026-03-08T10:02:00Z | ADMIN_ACCESS | admin:+9876543210 | target:+1234567890 | reason:user_support_request | result:success | ip:192.168.1.2
2026-03-08T10:03:00Z | ACCESS_DENIED | user:+1111111111 | conversation:+1234567890 | action:read | result:denied | reason:permission_violation | ip:192.168.1.3
2026-03-08T10:04:00Z | PRIVACY_REQUEST | user:+1234567890 | request_type:export | status:submitted | request_id:req_20260308_export_1234567890
2026-03-08T10:05:00Z | DELETION_REQUEST | user:+1234567890 | confirmation:sent | confirmation_code:ABC123 | grace_period:7_days
```

### 5.2 Log Entry Format

| Field | Description | Example |
|-------|-------------|---------|
| Timestamp | ISO 8601 UTC | `2026-03-08T10:00:00Z` |
| Event Type | ACCESS, ADMIN_ACCESS, ACCESS_DENIED, PRIVACY_REQUEST, DELETION_REQUEST | `ACCESS` |
| Actor | User phone or admin phone | `user:+1234567890` |
| Target | Conversation or affected resource | `conversation:+1234567890` |
| Action | Performed action | `read`, `write`, `delete` |
| Result | success, denied, partial | `success` |
| Reason | For admin access or denials | `user_support_request` |
| IP Address | Source IP | `192.168.1.1` |

### 5.3 Security Event Logging

```python
# Security events are logged separately
def log_security_event(event_type, details):
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "severity": details.get("severity", "medium"),
        "details": details,
        "investigation_required": True
    }
    append_to("~/.openclaw/logs/security_events.log", event)

# Example security events
security_events = [
    "multiple_failed_access_attempts",
    "admin_access_without_reason",
    "unusual_data_export_pattern",
    "permission_escalation_attempt",
    "data_exfiltration_risk"
]
```

### 5.4 Audit Log Retention

| Log Type | Retention Period | Archive Location |
|----------|------------------|------------------|
| Access Logs | 1 year | `~/.openclaw/logs/archive/access/` |
| Admin Access Logs | 3 years | `~/.openclaw/logs/archive/admin/` |
| Security Events | 5 years | `~/.openclaw/logs/archive/security/` |
| Privacy Requests | 3 years | `~/.openclaw/logs/archive/requests/` |
| SLA Breaches | 3 years | `~/.openclaw/logs/archive/sla/` |

---

## 6. Data Sovereignty

### 6.1 User Rights

#### Right to Access
Users can view their own conversations at any time through:
- Web interface (read-only)
- Export request (full data package)
- API access (authenticated)

**API Endpoint:**
```http
GET /api/conversations/me
Authorization: Bearer <jwt_token>
Phone: +1234567890
```

#### Right to Export
Users can request a complete export of their data in:
- JSON format (machine-readable)
- CSV format (spreadsheet-compatible)
- PDF format (human-readable)

**Example Export Request:**
```bash
curl -X POST https://api.openclaw.com/privacy/export \
  -H "Authorization: Bearer <token>" \
  -H "Phone: +1234567890" \
  -d '{"format": "json"}'
```

#### Right to Deletion
Users can request permanent deletion of:
- All conversations
- Specific conversation ranges
- Metadata only
- Derived data only

**Example Deletion Request:**
```bash
curl -X POST https://api.openclaw.com/privacy/delete \
  -H "Authorization: Bearer <token>" \
  -H "Phone: +1234567890" \
  -d '{
    "scope": "all",
    "confirmation": "DELETE",
    "confirmation_code": "ABC123XYZ"
  }'
```

#### Right to Rectification
Users can correct inaccurate information:
```bash
curl -X PATCH https://api.openclaw.com/conversations/<id> \
  -H "Authorization: Bearer <token>" \
  -d '{
    "correction": "Fix typo in message",
    "original_text": "Helo world",
    "corrected_text": "Hello world"
  }'
```

### 6.2 Data Ownership Statement

```
The OpenClaw system acknowledges that:
1. Users retain full ownership of their conversation data
2. Users have the right to access, export, or delete their data at any time
3. The system acts as a custodian, not an owner, of user data
4. No data is sold, licensed, or shared with third parties
5. Data is used only for the purpose of providing conversation services
```

---

## 7. Security Measures

### 7.1 File System Security

```bash
# Conversation files: User read/write only
chmod 600 ~/.openclaw/data/conversations/*.json

# Conversation directories: User execute only
chmod 700 ~/.openclaw/data/conversations/

# Admin config: Admin read/write only
chmod 600 ~/.openclaw/config/privacy_admins.json

# Audit logs: Append-only
chmod 644 ~/.openclaw/logs/privacy_audit.log
chattr +a ~/.openclaw/logs/privacy_audit.log  # Linux append-only
```

### 7.2 Application-Level Security

```python
# Phone number normalization and validation
def normalize_phone(phone: str) -> str:
    # Remove all non-numeric characters
    cleaned = re.sub(r'[^\d+]', '', phone)

    # Validate format
    if not re.match(r'^\+\d{10,15}$', cleaned):
        raise ValueError("Invalid phone number format")

    return cleaned

# Access control check
def check_access(user_phone: str, conversation_phone: str) -> bool:
    normalized_user = normalize_phone(user_phone)
    normalized_conv = normalize_phone(conversation_phone)

    if normalized_user != normalized_conv:
        if not is_admin(user_phone):
            log_access_denied(user_phone, conversation_phone)
            return False

    return True

# Rate limiting for export requests
@rate_limit(max_requests=3, period=86400)  # 3 per day
def request_export(user_phone: str):
    # Export logic
    pass
```

### 7.3 Admin Verification

```python
# Admin verification with audit logging
def verify_admin_access(admin_phone: str, target_phone: str, reason: str) -> bool:
    # Check whitelist
    admins = load_json("~/.openclaw/config/privacy_admins.json")
    admin = next((a for a in admins["admins"] if a["phone_number"] == admin_phone), None)

    if not admin:
        log_security_event("unauthorized_admin_attempt", {
            "admin_phone": admin_phone,
            "target": target_phone
        })
        return False

    # Verify reason provided
    if not reason or len(reason) < 10:
        log_security_event("admin_access_without_reason", {
            "admin_phone": admin_phone,
            "target": target_phone
        })
        return False

    # Log approved access
    log_admin_access(admin_phone, target_phone, reason)
    return True
```

### 7.4 Encryption

| Data State | Encryption Method | Key Management |
|------------|------------------|----------------|
| At Rest | AES-256 (file system) | OS-managed |
| In Transit | TLS 1.3 | Certificate-based |
| Export Package | AES-256 (ZIP encryption) | User-provided password |
| Audit Logs | No encryption (append-only) | N/A |

---

## 8. API Endpoints

### 8.1 Privacy Management APIs

#### Export Request
```http
POST /api/privacy/export
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "phone_number": "+1234567890",
  "format": "json",  // json, csv, pdf
  "include_metadata": true,
  "include_derived": true
}

Response:
{
  "request_id": "req_20260308_export_1234567890",
  "status": "processing",
  "estimated_completion": "2026-03-08T12:00:00Z",
  "sla_deadline": "2026-03-09T10:00:00Z"
}
```

#### Check Export Status
```http
GET /api/privacy/export/{request_id}
Authorization: Bearer <jwt_token>

Response:
{
  "request_id": "req_20260308_export_1234567890",
  "status": "completed",
  "download_url": "https://storage.openclaw.com/exports/export_1234567890.tar.gz",
  "expires_at": "2026-03-10T10:00:00Z",
  "file_size_bytes": 12345678
}
```

#### Deletion Request
```http
POST /api/privacy/delete
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "phone_number": "+1234567890",
  "scope": "all",  // all, range, metadata_only
  "confirmation": "DELETE",
  "confirmation_code": "ABC123XYZ"
}

Response:
{
  "request_id": "req_20260308_delete_1234567890",
  "status": "confirmation_pending",
  "grace_period_ends": "2026-03-15T10:00:00Z",
  "certificate_id": "del_20260308_1234567890"
}
```

#### View Own Data
```http
GET /api/conversations/me
Authorization: Bearer <jwt_token>
Phone: +1234567890

Response:
{
  "conversations": [
    {
      "id": "+1234567890",
      "message_count": 50,
      "first_message": "2026-01-01T00:00:00Z",
      "last_message": "2026-03-08T10:00:00Z",
      "topics": ["support", "technical"]
    }
  ],
  "metadata": {
    "total_messages": 50,
    "archive_months": 3
  }
}
```

### 8.2 Admin APIs

#### Admin Access to User Data
```http
GET /api/admin/conversations/{user_phone}
Authorization: Bearer <admin_jwt_token>
X-Admin-Reason: User requested support via ticket #12345

Response:
{
  "user_phone": "+1234567890",
  "conversations": [...],
  "access_logged": true,
  "audit_id": "audit_20260308_1234567890"
}
```

#### Add Admin to Whitelist
```http
POST /api/admin/whitelist
Authorization: Bearer <super_admin_jwt_token>
Content-Type: application/json

{
  "phone_number": "+9876543210",
  "name": "Jane Administrator",
  "role": "admin",
  "access_scope": "all"
}

Response:
{
  "status": "added",
  "admin_phone": "+9876543210",
  "added_at": "2026-03-08T10:00:00Z",
  "added_by": "super_admin"
}
```

---

## 9. Examples and Scenarios

### 9.1 Example 1: User Requests Data Export

**Scenario:** User wants to export all their conversation data.

**Steps:**
1. User logs in to web interface
2. Navigates to "Privacy" → "Export Data"
3. Selects format: "JSON"
4. Clicks "Request Export"
5. System sends confirmation: "Export request received. You'll receive a download link within 24 hours."
6. System processes export (assembles data, encrypts, uploads)
7. User receives email: "Your data export is ready. Download link: [URL] (expires in 48 hours)"
8. User downloads and extracts archive

**Audit Trail:**
```log
2026-03-08T10:00:00Z | PRIVACY_REQUEST | user:+1234567890 | request_type:export | status:submitted | request_id:req_20260308_export_1234567890
2026-03-08T12:00:00Z | PRIVACY_REQUEST | user:+1234567890 | request_type:export | status:completed | request_id:req_20260308_export_1234567890 | download_url:https://storage.openclaw.com/exports/export_1234567890.tar.gz
```

### 9.2 Example 2: Admin Accesses User Data for Support

**Scenario:** User reports missing messages, admin investigates.

**Steps:**
1. User submits support ticket: "Messages from Feb 15 are missing"
2. Admin receives ticket, opens investigation
3. Admin calls API: `GET /api/admin/conversations/+1234567890` with header `X-Admin-Reason: Investigating missing messages - ticket #456`
4. System verifies admin is whitelisted
5. System validates reason is provided
6. System logs admin access
7. System returns conversation data
8. Admin identifies issue (archive not loaded)
9. Admin fixes issue
10. User notified: "Your messages have been restored"

**Audit Trail:**
```log
2026-03-08T10:00:00Z | ADMIN_ACCESS | admin:+9876543210 | target:+1234567890 | reason:Investigating missing messages - ticket #456 | result:success | ip:192.168.1.2
2026-03-08T10:05:00Z | ADMIN_ACTION | admin:+9876543210 | target:+1234567890 | action:restore_archive | result:success
```

### 9.3 Example 3: User Requests Deletion

**Scenario:** User wants to permanently delete all their data.

**Steps:**
1. User logs in to web interface
2. Navigates to "Privacy" → "Delete Data"
3. Reads warning: "This will permanently delete all your data. This action cannot be undone."
4. Clicks "Request Deletion"
5. System sends SMS: "Confirm deletion request. Reply with code: ABC123XYZ"
6. User replies: "ABC123XYZ"
7. System sends second confirmation: "Are you sure? Type DELETE to confirm."
8. User replies: "DELETE"
9. System starts 7-day grace period
10. User receives email: "Deletion scheduled for March 15, 2026. You can cancel by replying CANCEL before then."
11. After 7 days, data permanently deleted
12. User receives deletion certificate

**Audit Trail:**
```log
2026-03-08T10:00:00Z | DELETION_REQUEST | user:+1234567890 | confirmation:sent | confirmation_code:ABC123 | grace_period:7_days
2026-03-08T10:02:00Z | DELETION_REQUEST | user:+1234567890 | confirmation:received | confirmation_code:ABC123 | second_confirmation:sent
2026-03-08T10:03:00Z | DELETION_REQUEST | user:+1234567890 | confirmation:final_received | status:scheduled | deletion_date:2026-03-15T10:00:00Z
2026-03-15T10:00:00Z | DELETION_COMPLETE | user:+1234567890 | certificate_id:del_20260308_1234567890 | data_types_deleted:conversations,metadata,derived_data,archive_records
```

### 9.4 Example 4: Access Denied - Permission Violation

**Scenario:** User tries to access another user's conversations.

**Steps:**
1. User A attempts to access: `/api/conversations/+9876543210`
2. System normalizes phone numbers
3. System checks: User A is +1234567890, target is +9876543210
4. System checks: User A is not admin
5. System denies access
6. System logs security event
7. User receives error: "Access denied. You can only view your own conversations."
8. Security team notified of suspicious activity

**Audit Trail:**
```log
2026-03-08T10:00:00Z | ACCESS_DENIED | user:+1234567890 | conversation:+9876543210 | action:read | result:denied | reason:permission_violation | ip:192.168.1.3
2026-03-08T10:00:01Z | SECURITY_EVENT | event_type:unauthorized_access_attempt | severity:high | user:+1234567890 | target:+9876543210 | ip:192.168.1.3 | investigation_required:true
```

---

## 10. Compliance and Certifications

### 10.1 Regulatory Compliance

| Regulation | Status | Notes |
|------------|--------|-------|
| **GDPR** | Compliant | Full support for data subject rights (access, portability, erasure) |
| **CCPA** | Compliant | Right to delete, right to know, right to opt-out |
| **POPIA** | Compliant | Data protection principles, subject rights |
| **PDPA** | Compliant | Consent, access, correction, withdrawal |

### 10.2 Security Best Practices

- **ISO 27001**: Information security management
- **NIST CSF**: Cybersecurity framework alignment
- **OWASP**: Secure coding practices
- **SOC 2**: Security, availability, processing integrity (planned)

---

## 11. Contact and Support

### 11.1 Privacy-Related Inquiries

**Email:** privacy@openclaw.com
**Response Time:** 48 hours
**Escalation:** privacy-escalation@openclaw.com (if no response in 72 hours)

### 11.2 Data Breach Notification

**In the event of a data breach:**
1. Affected users notified within 72 hours
2. Clear description of what data was affected
3. Steps taken to mitigate the breach
4. Steps users should take to protect themselves
5. Contact information for more information

**Breaches logged in:** `~/.openclaw/logs/security_breaches.log`

---

## 12. Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-03-08 | Initial privacy policy release |

---

## Appendix A: File Structure

```
~/.openclaw/
├── data/
│   ├── conversations/
│   │   ├── active/
│   │   │   ├── +1234567890.json (600 permissions)
│   │   │   └── +9876543210.json (600 permissions)
│   │   ├── archive/
│   │   │   ├── 2026-01/
│   │   │   ├── 2026-02/
│   │   │   └── 2026-03/
│   │   └── deleted/
│   │       └── marked_for_deletion/
│   ├── privacy_requests/
│   │   ├── req_20260308_export_1234567890.json
│   │   └── req_20260308_delete_9876543210.json
│   └── exports/
│       └── export_+1234567890_20260308.tar.gz
├── config/
│   └── privacy_admins.json (600 permissions)
└── logs/
    ├── privacy_audit.log
    ├── security_events.log
    └── archive/
        ├── access/
        ├── admin/
        ├── security/
        ├── requests/
        └── sla/
```

---

## Appendix B: Data Dictionary

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `phone_number` | string | User's phone number in E.164 format | `+1234567890` |
| `conversation_id` | string | Unique conversation identifier | `+1234567890` |
| `message_id` | string | Unique message identifier | `msg_20260308_123456` |
| `timestamp` | datetime | ISO 8601 UTC timestamp | `2026-03-08T10:00:00Z` |
| `sentiment` | string | Sentiment classification | `positive`, `neutral`, `negative` |
| `topic` | string array | Derived conversation topics | `["support", "technical"]` |
| `action_item` | object | Extracted task or commitment | `{"text": "Call user back", "due": "2026-03-09"}` |

---

**This privacy policy is effective as of March 8, 2026, and will be reviewed annually.**
