#!/bin/bash
# Test script for FastAPI conversation_api server

cd /Users/kublai/.openclaw/agents/main/scripts

# Kill any existing servers
pkill -f "uvicorn conversation_api" 2>/dev/null || true
sleep 2

# Start the server
echo "Starting FastAPI server on port 8080..."
uvicorn conversation_api:app --host 127.0.0.1 --port 8080 2>&1 &
SERVER_PID=$!
sleep 3

echo "Server PID: $SERVER_PID"
echo ""

# Test endpoints
echo "=== Testing FastAPI Server ==="
echo ""

echo "1. Health Check:"
curl -s http://127.0.0.1:8080/health | python3 -m json.tool
echo ""

echo "2. Root Endpoint:"
curl -s http://127.0.0.1:8080/ | python3 -m json.tool
echo ""

echo "3. API Documentation (Swagger UI):"
curl -s -o /dev/null -w "   Status: %{http_code}\n" http://127.0.0.1:8080/docs
echo ""

echo "4. ReDoc Documentation:"
curl -s -o /dev/null -w "   Status: %{http_code}\n" http://127.0.0.1:8080/redoc
echo ""

echo "5. OpenAPI Schema:"
curl -s http://127.0.0.1:8080/openapi.json | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"   OpenAPI Version: {data.get('openapi')}\")
print(f\"   Title: {data.get('info', {}).get('title')}\")
print(f\"   Version: {data.get('info', {}).get('version')}\")
print(f\"   Endpoints: {len(data.get('paths', []))}\")
"
echo ""

echo "6. Test API Endpoint (should require auth):"
curl -s http://127.0.0.1:8080/api/conversations/my
echo ""

echo "7. CORS Preflight:"
curl -s -X OPTIONS -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" http://127.0.0.1:8080/api/conversations/my
echo ""

# Cleanup
echo "Cleaning up..."
kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true

echo ""
echo "=== Test Complete ==="
