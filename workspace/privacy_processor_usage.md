# Privacy Request Processor - Quick Reference

## Location
`/Users/kublai/.openclaw/agents/main/scripts/privacy_request_processor.py`

## Overview
Background process to handle GDPR-style privacy requests (export and deletion) with SLA monitoring and automated processing.

## Commands

### Process All Pending Requests
```bash
cd /Users/kublai/.openclaw/agents/main/scripts
python3 privacy_request_processor.py --process
```

### Monitor SLA Compliance
```bash
cd /Users/kublai/.openclaw/agents/main/scripts
python3 privacy_request_processor.py --monitor
```

### Process Specific Request
```bash
cd /Users/kublai/.openclaw/agents/main/scripts
python3 privacy_request_processor.py --request pr-001-export
```

### Show Help
```bash
cd /Users/kublai/.openclaw/agents/main/scripts
python3 privacy_request_processor.py --help
```

## Request File Format

### Export Request
```json
{
  "request_id": "pr-001-export",
  "phone_number": "+15550199",
  "type": "export",
  "status": "pending",
  "created_at": "2026-03-08T10:00:00",
  "created_by": "user"
}
```

### Deletion Request
```json
{
  "request_id": "pr-002-delete",
  "phone_number": "+15550199",
  "type": "delete",
  "status": "pending",
  "created_at": "2026-03-08T10:00:00",
  "created_by": "user"
}
```

## Processing Flow

### Export Request
1. Load request from `privacy_requests/` directory
2. Verify access permissions
3. Gather all user data:
   - Profile information
   - Conversation history
   - Archived conversations
   - Statistics
4. Create export JSON file with secure permissions (600)
5. Update request status to "completed"
6. TODO: Deliver to user (email/Signal)

### Deletion Request
1. Load request from `privacy_requests/` directory
2. Verify access permissions
3. Delete all user data:
   - Profile file
   - Conversation index
   - Archived conversations
   - Cross-references
4. Update request status to "completed"
5. TODO: Notify user of completion

### SLA Monitoring
1. Scan all pending requests
2. Check if request is older than 24 hours
3. Calculate hours overdue
4. Report breaches for escalation

## File Locations

### Request Files
`~/.openclaw/agents/main/privacy_requests/pr-*.json`

### Export Files
`~/.openclaw/agents/main/privacy_requests/pr-*-export.json` (permissions: 600)

### Audit Log
`~/.openclaw/logs/privacy_audit.log`

## SLA Policy

- **Standard SLA:** 24 hours from request creation
- **Breach Detection:** Automated via `--monitor` flag
- **Escalation:** TODO - Integrate with alert system

## Integration

### Crontab Example
```bash
# Process privacy requests every hour
0 * * * * cd /Users/kublai/.openclaw/agents/main/scripts && python3 privacy_request_processor.py --process >> /var/log/privacy_processor.log 2>&1

# Check SLA compliance every 6 hours
0 */6 * * * cd /Users/kublai/.openclaw/agents/main/scripts && python3 privacy_request_processor.py --monitor
```

### Python API
```python
from privacy_request_processor import PrivacyRequestProcessor

processor = PrivacyRequestProcessor()

# Process specific request
result = processor.process_export_request("pr-001-export")

# Process all pending
results = processor.process_all_pending()

# Check SLA
breaches = processor.monitor_sla()
```

## Security Features

- ✅ Export files created with 600 permissions (owner read/write only)
- ✅ Audit logging for all operations
- ✅ Access control checks before processing
- ✅ Confirmation required for deletions
- ✅ Request tracking for compliance

## Dependencies

- `conversation_privacy.py` - Privacy controls and audit logging
- `conversation_logger.py` - Data access and export
- `human_profile_memory.py` - Profile management

## Error Handling

- Missing request file: Returns `{"success": false, "error": "Request not found"}`
- Access denied: Logged to audit log, returns error
- Export failure: Returns `{"success": false, "error": "Export failed"}`
- Deletion failure: Returns `{"success": false, "error": "Deletion failed"}`

## Status Codes

- `pending` - Request awaiting processing
- `completed` - Request successfully processed
- `failed` - Request processing failed (check error field)

## Compliance Notes

- Meets GDPR-style requirements for data export and deletion
- 24-hour SLA for request processing
- Full audit trail maintained
- Permanent deletion with confirmation
- Export includes all user data

## Troubleshooting

### Module not found
```bash
cd /Users/kublai/.openclaw/agents/main/scripts
python3 privacy_request_processor.py [command]
```

### Permission denied on export
Check file permissions:
```bash
ls -la ~/.openclaw/agents/main/privacy_requests/
```

### Check audit log
```bash
tail -f ~/.openclaw/logs/privacy_audit.log
```

## Related Documentation

- Full test results: `/Users/kublai/.openclaw/agents/main/workspace/privacy_processor_test_results.md`
- Privacy API: `/Users/kublai/.openclaw/agents/main/scripts/conversation_privacy.py`
- Logger API: `/Users/kublai/.openclaw/agents/main/scripts/conversation_logger.py`
