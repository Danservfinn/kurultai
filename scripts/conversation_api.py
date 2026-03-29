#!/usr/bin/env python3
"""
Conversation API - FastAPI REST endpoints for conversation storage.

Endpoints:
  User Access:
    GET  /api/conversations/my                    - My conversations
    GET  /api/conversations/my/search             - Search my conversations
    GET  /api/conversations/my/stats              - My statistics
    POST /api/conversations/my/export             - Request export
    GET  /api/conversations/my/action-items       - My action items

  Admin Access:
    GET  /api/conversations/{phone}               - Get user conversations
    GET  /api/conversations/search                - Search all conversations
    DELETE /api/conversations/{phone}             - Delete user data

  Logging:
    POST /api/conversations/log                   - Log a conversation
    POST /api/conversations/link-event            - Link to event
    POST /api/conversations/link-task             - Link to task

  Admin Functions:
    GET  /api/admin/privacy-requests              - List privacy requests

Usage:
    uvicorn conversation_api:app --reload --port 8080
    python3 conversation_api.py --port 8080
"""

import os
import sys
import hmac
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conversation_logger import ConversationLogger
from conversation_privacy import ConversationPrivacy

# Configuration
PORT = int(os.getenv("CONVERSATION_API_PORT", "8080"))
ADMIN_TOKEN = os.getenv("CONVERSATION_API_ADMIN_TOKEN")
if not ADMIN_TOKEN:
    # Fail gracefully - admin endpoints will return 403
    print("WARNING: CONVERSATION_API_ADMIN_TOKEN not set - admin endpoints disabled")
SIGNING_KEY = os.getenv("CONVERSATION_API_SIGNING_KEY")
if not SIGNING_KEY:
    raise ValueError(
        "CONVERSATION_API_SIGNING_KEY environment variable must be set for token validation. "
        "Generate with: python3 -c 'import secrets; print(secrets.token_hex(32))'"
    )
HOST = os.getenv("CONVERSATION_API_HOST", "127.0.0.1")

# Security
security = HTTPBearer()

# FastAPI app - disable docs in production
ENABLE_DOCS = os.getenv("ENABLE_SWAGGER_DOCS", "false").lower() == "true"

app = FastAPI(
    title="Kurultai Conversation API",
    description="Private conversation storage with privacy controls",
    version="2.0.0",
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None
)

# Instances
logger = ConversationLogger()
privacy = ConversationPrivacy()


# Request/Response Models
class ConversationResponse(BaseModel):
    timestamp: str
    direction: str
    content: str
    channel: str
    topics: List[str] = []
    action_items: List[str] = []
    sentiment: Optional[Dict[str, Any]] = None


class ConversationsListResponse(BaseModel):
    ok: bool
    phone: str
    count: int
    conversations: List[ConversationResponse]
    admin_access: Optional[bool] = None


class SearchResponse(BaseModel):
    ok: bool
    query: str
    count: int
    results: List[Dict[str, Any]]


class StatsResponse(BaseModel):
    ok: bool
    phone: str
    statistics: Dict[str, Any]


class ActionItemsResponse(BaseModel):
    ok: bool
    phone: str
    pending_only: bool
    count: int
    action_items: List[Dict[str, Any]]


class ExportResponse(BaseModel):
    ok: bool
    export_date: str
    phone: str
    data: Optional[Dict[str, Any]] = None


class DeleteResponse(BaseModel):
    ok: bool
    phone_number: str
    conversations_deleted: int
    archived_deleted: int
    deleted_at: str


class LogConversationRequest(BaseModel):
    phone: str
    direction: str = "inbound"
    content: str
    channel: str = "signal"
    context: Optional[str] = None
    topics: Optional[List[str]] = None
    action_items: Optional[List[str]] = None
    sentiment: Optional[Dict[str, Any]] = None
    related_events: Optional[List[str]] = None
    related_tasks: Optional[List[str]] = None
    message_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LogResponse(BaseModel):
    ok: bool
    phone: str
    logged_at: str


class LinkEventRequest(BaseModel):
    phone: str
    conversation_date: str
    event_name: str


class LinkTaskRequest(BaseModel):
    phone: str
    conversation_date: str
    task_id: str


class LinkResponse(BaseModel):
    ok: bool
    phone: str


class HealthResponse(BaseModel):
    service: str
    version: str
    status: str
    timestamp: str


class ErrorResponse(BaseModel):
    ok: bool = False
    error: str
    detail: Optional[str] = None


# Authentication
def generate_signature(phone_number: str, key: str) -> str:
    """Generate HMAC-SHA256 signature for phone number."""
    return hmac.new(
        key.encode('utf-8') if key else b'',
        phone_number.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify Bearer token and return phone number.

    Token format: phone:signature (HMAC-SHA256)
    - phone: E.164 format phone number (e.g., +15165643945)
    - signature: HMAC-SHA256 signature using SIGNING_KEY

    Admin token (if configured): raw string match to ADMIN_TOKEN
    """
    token = credentials.credentials

    # Check for admin token (only if configured)
    if ADMIN_TOKEN and token == ADMIN_TOKEN:
        return "+15165643945"  # Admin phone

    # Token format: phone:signature
    if ":" in token:
        parts = token.split(":", 1)  # Split only on first colon
        phone_number = parts[0]
        provided_signature = parts[1]

        # Validate signature - SIGNING_KEY is now required
        expected_signature = generate_signature(phone_number, SIGNING_KEY)
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise HTTPException(
                status_code=401,
                detail="Invalid signature"
            )

        return phone_number

    raise HTTPException(status_code=401, detail="Invalid token format. Expected: phone:signature")


def verify_admin(phone_number: str) -> None:
    """Verify user is admin."""
    if not privacy.is_admin(phone_number):
        raise HTTPException(status_code=403, detail="Admin access required")


def get_phone_from_header(x_phone: Optional[str] = Header(None)) -> Optional[str]:
    """Get phone number from X-Phone header."""
    return x_phone


# CORS middleware - strict origin validation
@app.middleware("http")
async def add_cors_middleware(request, call_next):
    """Add CORS headers to all responses with strict origin validation."""
    response = await call_next(request)

    # Get allowed origins from environment - never default to wildcard
    # Reject "*" entirely for security - explicit origins only
    cors_origins_env = os.getenv("CORS_ORIGINS", "")
    allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]

    origin = request.headers.get("origin")

    # Only set CORS headers if origin is explicitly allowed
    # "*" wildcard is explicitly rejected for security
    if origin and allowed_origins and origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Phone"
        response.headers["Access-Control-Allow-Credentials"] = "true"

    return response


# Health check
@app.get("/", response_model=HealthResponse)
async def root():
    """Health check endpoint."""
    return {
        "service": "Kurultai Conversation API",
        "version": "2.0.0",
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return {
        "service": "Kurultai Conversation API",
        "version": "2.0.0",
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


# User Access Endpoints
@app.get("/api/conversations/my", response_model=ConversationsListResponse)
async def get_my_conversations(
    limit: int = Query(50, ge=1, le=100, description="Maximum conversations to return"),
    context_filter: Optional[str] = Query(None, description="Filter by context"),
    sentiment_filter: Optional[str] = Query(None, description="Filter by sentiment"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get my recent conversations."""
    # Always use authenticated phone from Bearer token - X-Phone cannot override
    phone_number = verify_token(credentials)

    # Verify self-access
    if not privacy.can_access(phone_number, phone_number):
        raise HTTPException(status_code=403, detail="Access denied")

    conversations = logger.get_recent_conversations(
        phone_number,
        limit=limit,
        context_filter=context_filter,
        sentiment_filter=sentiment_filter
    )

    privacy.audit.log("data_access", phone_number, phone_number,
                     {"type": "conversations", "limit": limit})

    return {
        "ok": True,
        "phone": phone_number,
        "count": len(conversations),
        "conversations": conversations
    }


@app.get("/api/conversations/my/search", response_model=SearchResponse)
async def search_my_conversations(
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    context_filter: Optional[str] = Query(None, description="Filter by context"),
    sentiment_filter: Optional[str] = Query(None, description="Filter by sentiment"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Search my conversations."""
    from conversation_search import ConversationSearch

    # Always use authenticated phone from Bearer token
    phone_number = verify_token(credentials)

    search = ConversationSearch()
    results = search.search_user(
        phone_number,
        q,
        context_filter=context_filter,
        sentiment_filter=sentiment_filter,
        limit=limit
    )

    return {
        "ok": True,
        "query": q,
        "count": len(results),
        "results": results
    }


@app.get("/api/conversations/my/stats", response_model=StatsResponse)
async def get_my_stats(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get my conversation statistics."""
    # Always use authenticated phone from Bearer token
    phone_number = verify_token(credentials)

    if not privacy.can_access(phone_number, phone_number):
        raise HTTPException(status_code=403, detail="Access denied")

    stats = logger.get_conversation_stats(phone_number)

    return {
        "ok": True,
        "phone": phone_number,
        "statistics": stats
    }


@app.get("/api/conversations/my/action-items", response_model=ActionItemsResponse)
async def get_my_action_items(
    pending_only: bool = Query(True, description="Only show pending items"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get my action items."""
    # Always use authenticated phone from Bearer token
    phone_number = verify_token(credentials)

    if not privacy.can_access(phone_number, phone_number):
        raise HTTPException(status_code=403, detail="Access denied")

    items = logger.get_action_items(phone_number, pending_only=pending_only)

    return {
        "ok": True,
        "phone": phone_number,
        "pending_only": pending_only,
        "count": len(items),
        "action_items": items
    }


# Admin Access Endpoints
@app.get("/api/conversations/{phone_path:path}", response_model=ConversationsListResponse)
async def get_user_conversations(
    phone_path: str,
    limit: int = Query(50, ge=1, le=100, description="Maximum conversations to return"),
    context_filter: Optional[str] = Query(None, description="Filter by context"),
    sentiment_filter: Optional[str] = Query(None, description="Filter by sentiment"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get any user's conversations (admin only)."""
    admin_phone = verify_token(credentials)

    # Normalize phone number
    phone = phone_path.lstrip("+")
    if not phone.startswith("+"):
        phone = "+" + phone

    # Check access
    if not privacy.can_access(admin_phone, phone):
        raise HTTPException(status_code=403, detail="Access denied")

    conversations = logger.get_recent_conversations(
        phone,
        limit=limit,
        context_filter=context_filter,
        sentiment_filter=sentiment_filter
    )

    privacy.audit.log("admin_access", admin_phone, phone,
                     {"type": "conversations", "limit": limit})

    return {
        "ok": True,
        "phone": phone,
        "count": len(conversations),
        "conversations": conversations,
        "admin_access": True
    }


@app.get("/api/conversations/search", response_model=SearchResponse)
async def search_all_conversations(
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results"),
    context_filter: Optional[str] = Query(None, description="Filter by context"),
    sentiment_filter: Optional[str] = Query(None, description="Filter by sentiment"),
    all_users: bool = Query(False, description="Search across all users (admin only)"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Search conversations."""
    from conversation_search import ConversationSearch

    search = ConversationSearch()
    authenticated_phone = verify_token(credentials)

    if all_users:
        # Admin search across all users
        verify_admin(authenticated_phone)

        results = search.search_all(
            q,
            context_filter=context_filter,
            sentiment_filter=sentiment_filter,
            total_limit=limit
        )
    else:
        # User search - always search authenticated user's conversations
        results = search.search_user(
            authenticated_phone,
            q,
            context_filter=context_filter,
            sentiment_filter=sentiment_filter,
            limit=limit
        )

    return {
        "ok": True,
        "query": q,
        "count": len(results),
        "results": results
    }


@app.delete("/api/conversations/{phone_path:path}", response_model=DeleteResponse)
async def delete_user_conversations(
    phone_path: str,
    confirm: bool = Query(False, description="Must be true to actually delete"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Delete user data (admin only or self)."""
    requesting_user = verify_token(credentials)

    # Normalize phone number
    phone = phone_path.lstrip("+")
    if not phone.startswith("+"):
        phone = "+" + phone

    if not privacy.can_access(requesting_user, phone):
        raise HTTPException(status_code=403, detail="Access denied")

    result = privacy.delete_user_data(phone, requesting_user, confirm=confirm)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Delete failed"))

    return result


# Logging Endpoints - All require Bearer token authentication
@app.post("/api/conversations/log", response_model=LogResponse)
async def log_conversation(
    request: LogConversationRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Log a conversation (requires authentication)."""
    # Verify token - raise 401 if invalid
    verify_token(credentials)

    success = logger.log_human_conversation(
        phone_number=request.phone,
        direction=request.direction,
        content=request.content,
        channel=request.channel,
        context=request.context,
        topics=request.topics,
        action_items=request.action_items,
        sentiment=request.sentiment,
        related_events=request.related_events,
        related_tasks=request.related_tasks,
        message_id=request.message_id,
        metadata=request.metadata
    )

    return {
        "ok": success,
        "phone": request.phone,
        "logged_at": datetime.now().isoformat()
    }


@app.post("/api/conversations/link-event", response_model=LinkResponse)
async def link_event(
    request: LinkEventRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Link conversation to event (requires authentication)."""
    # Verify token - raise 401 if invalid
    verify_token(credentials)

    success = logger.link_to_event(request.phone, request.conversation_date, request.event_name)

    return {
        "ok": success,
        "phone": request.phone
    }


@app.post("/api/conversations/link-task", response_model=LinkResponse)
async def link_task(
    request: LinkTaskRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Link conversation to task (requires authentication)."""
    # Verify token - raise 401 if invalid
    verify_token(credentials)

    success = logger.link_to_task(request.phone, request.conversation_date, request.task_id)

    return {
        "ok": success,
        "phone": request.phone
    }


@app.post("/api/conversations/export", response_model=ExportResponse)
async def export_conversations(
    request: Dict[str, Any],
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Export user data (GDPR)."""
    # Always use authenticated user from Bearer token
    requesting_user = verify_token(credentials)

    # Export either requested phone or own data
    phone = request.get("phone") or requesting_user

    data = privacy.export_user_data(phone, requesting_user)

    if data is None:
        raise HTTPException(status_code=403, detail="Unauthorized")

    return {
        "ok": True,
        "export_date": data.get("export_date"),
        "phone": phone,
        "data": data
    }


# Admin Functions
@app.get("/api/admin/privacy-requests")
async def list_privacy_requests(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """List privacy requests (admin only)."""
    admin_phone = verify_token(credentials)
    verify_admin(admin_phone)

    logs = privacy.audit.get_logs(action="export", limit=50)

    return {
        "ok": True,
        "count": len(logs),
        "requests": logs
    }


# Main
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Conversation API Server (FastAPI)")
    parser.add_argument("--port", "-p", type=int, default=PORT,
                       help="Port to listen on")
    parser.add_argument("--host", "-H", default=HOST,
                       help="Host to bind to")
    parser.add_argument("--reload", action="store_true",
                       help="Enable auto-reload")

    args = parser.parse_args()

    print(f"Starting Conversation API on {args.host}:{args.port}")
    print(f"Docs: http://{args.host}:{args.port}/docs")
    print(f"ReDoc: http://{args.host}:{args.port}/redoc")

    uvicorn.run(
        "conversation_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )
