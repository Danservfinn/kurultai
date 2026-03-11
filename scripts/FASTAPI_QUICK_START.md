# FastAPI Conversation API - Quick Start Guide

## Server Information
- **Framework:** FastAPI 0.135.1
- **ASGI Server:** Uvicorn 0.41.0
- **OpenAPI Version:** 3.1.0
- **Default Port:** 8080
- **Default Host:** 127.0.0.1

## Start the Server

### Development (with auto-reload)
```bash
cd /Users/kublai/.openclaw/agents/main/scripts
uvicorn conversation_api:app --host 127.0.0.1 --port 8080 --reload
```

### Production
```bash
cd /Users/kublai/.openclaw/agents/main/scripts
uvicorn conversation_api:app --host 0.0.0.0 --port 8080 --workers 4
```

### Using Python script
```bash
python3 conversation_api.py --port 8080 --reload
```

## Documentation URLs
Once the server is running:
- **Swagger UI:** http://127.0.0.1:8080/docs
- **ReDoc:** http://127.0.0.1:8080/redoc
- **OpenAPI Schema:** http://127.0.0.1:8080/openapi.json

## Authentication

### Bearer Token (Recommended)
```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://127.0.0.1:8080/api/conversations/my
```

### X-Phone Header (Simple)
```bash
curl -H "X-Phone: +1234567890" \
  http://127.0.0.1:8080/api/conversations/my
```

### Admin Token
```bash
export CONVERSATION_API_ADMIN_TOKEN="your-admin-token"
curl -H "Authorization: Bearer your-admin-token" \
  http://127.0.0.1:8080/api/conversations/+1234567890
```

## Example API Calls

### Get My Conversations
```bash
curl -H "X-Phone: +1234567890" \
  http://127.0.0.1:8080/api/conversations/my?limit=10
```

### Search My Conversations
```bash
curl -H "X-Phone: +1234567890" \
  "http://127.0.0.1:8080/api/conversations/my/search?q=authentication"
```

### Get My Statistics
```bash
curl -H "X-Phone: +1234567890" \
  http://127.0.0.1:8080/api/conversations/my/stats
```

### Get My Action Items
```bash
curl -H "X-Phone: +1234567890" \
  http://127.0.0.1:8080/api/conversations/my/action-items?pending_only=true
```

### Log a Conversation
```bash
curl -X POST http://127.0.0.1:8080/api/conversations/log \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+1234567890",
    "direction": "inbound",
    "content": "Hello world",
    "channel": "signal",
    "topics": ["greeting"],
    "action_items": ["Respond to hello"]
  }'
```

### Admin: Get User Conversations
```bash
curl -H "Authorization: Bearer your-admin-token" \
  http://127.0.0.1:8080/api/conversations/+1234567890?limit=50
```

### Admin: Search All Conversations
```bash
curl -H "Authorization: Bearer your-admin-token" \
  "http://127.0.0.1:8080/api/conversations/search?q=authentication&all_users=true"
```

### Export User Data
```bash
curl -X POST http://127.0.0.1:8080/api/conversations/export \
  -H "Content-Type: application/json" \
  -H "X-Phone: +1234567890" \
  -d '{"phone": "+1234567890"}'
```

### Delete User Data
```bash
curl -X DELETE http://127.0.0.1:8080/api/conversations/+1234567890?confirm=true \
  -H "Authorization: Bearer your-admin-token"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONVERSATION_API_PORT` | 8080 | Port to listen on |
| `CONVERSATION_API_HOST` | 127.0.0.1 | Host to bind to |
| `CONVERSATION_API_ADMIN_TOKEN` | dev-admin-token | Admin authentication token |
| `CORS_ORIGINS` | * | Comma-separated list of allowed origins |

## Response Format

All responses follow this structure:

### Success Response
```json
{
  "ok": true,
  "data": { ... }
}
```

### Error Response
```json
{
  "ok": false,
  "error": "Error message",
  "detail": "Detailed error information"
}
```

## HTTP Status Codes

- `200 OK` - Successful request
- `401 Unauthorized` - Missing or invalid authentication
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation error

## Testing

### Run Test Script
```bash
cd /Users/kublai/.openclaw/agents/main/scripts
./test_fastapi_server.sh
```

### Manual Health Check
```bash
curl http://127.0.0.1:8080/health
```

## Migration from http.server

### Key Changes
1. **Authentication:** Now requires Bearer token or X-Phone header
2. **Error Handling:** HTTP status codes instead of 200 with error field
3. **Validation:** Automatic request validation with Pydantic
4. **Documentation:** Auto-generated at /docs

### Backward Compatibility
- All endpoints preserved at same paths
- Same functionality maintained
- Enhanced type safety and validation

## Troubleshooting

### Port Already in Use
```bash
# Kill existing server
pkill -f "uvicorn conversation_api"

# Use different port
uvicorn conversation_api:app --port 8081
```

### Import Errors
```bash
# Check dependencies
pip3 list | grep -E "(fastapi|uvicorn|pydantic)"

# Reinstall if needed
pip3 install --break-system-packages fastapi uvicorn pydantic
```

### CORS Issues
```bash
# Set allowed origins
export CORS_ORIGINS="http://localhost:3000,https://yourdomain.com"
uvicorn conversation_api:app --reload
```

## Performance Tips

1. **Use multiple workers in production:**
   ```bash
   uvicorn conversation_api:app --workers 4
   ```

2. **Enable auto-reload only in development:**
   ```bash
   # Development
   uvicorn conversation_api:app --reload

   # Production
   uvicorn conversation_api:app --workers 4
   ```

3. **Use gunicorn with uvicorn workers for production:**
   ```bash
   pip3 install gunicorn
   gunicorn conversation_api:app --workers 4 --worker-class uvicorn.workers.UvicornWorker
   ```

## Files Reference

- **Main API:** `/Users/kublai/.openclaw/agents/main/scripts/conversation_api.py`
- **Backup:** `/Users/kublai/.openclaw/agents/main/scripts/conversation_api.http.server.bak`
- **Test Script:** `/Users/kublai/.openclaw/agents/main/scripts/test_fastapi_server.sh`
- **Completion Report:** `/Users/kublai/.openclaw/agents/main/scripts/TASK_3.1_COMPLETION_REPORT.md`
