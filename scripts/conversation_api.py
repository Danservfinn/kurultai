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
    uvicorn conversation_api_fastapi:app --reload --port 8080
    python3 conversation_api_fastapi.py --port 8080
"""

import os
import sys
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
ADMIN_TOKEN = os.getenv("CONVERSATION_API_ADMIN_TOKEN", "dev-admin-token")
HOST = os.getenv("CONVERSATION_API_HOST", "127.0.0.1")

# Security
security = HTTPBearer()

# FastAPI app
app = FastAPI(
    title="Kurultai Conversation API",
    description="Private conversation storage with privacy controls",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
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
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify Bearer token and return phone number."""
    token = credentials.credentials

    # Check for admin token
    if token == ADMIN_TOKEN:
        return "+15165643945"  # Admin phone

    # Token format: phone:signature (simplified for now)
    # In production, decode JWT token
    if ":" in token:
        phone_number = token.split(":")[0]
        return phone_number

    raise HTTPException(status_code=401, detail="Invalid token")


def verify_admin(phone_number: str) -> None:
    """Verify user is admin."""
    if not privacy.is_admin(phone_number):
        raise HTTPException(status_code=403, detail="Admin access required")


def get_phone_from_header(x_phone: Optional[str] = Header(None)) -> Optional[str]:
    """Get phone number from X-Phone header."""
    return x_phone


# CORS middleware will be configured via middleware
@app.middleware("http")
async def add_cors_middleware(request, call_next):
    """Add CORS headers to all responses."""
    response = await call_next(request)

    # Get origin from environment
    allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")

    origin = request.headers.get("origin")
    if origin in allowed_origins or "*" in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin if origin in allowed_origins else "*"

    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Phone"

    return response


@app.options("/{path:path}")
async def options_handler():
    """Handle CORS preflight requests."""
    return {"ok": True}


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
    x_phone: Optional[str] = Header(None, description="User's phone number"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get my recent conversations."""
    phone_number = x_phone or verify_token(credentials)

    if not phone_number:
        raise HTTPException(status_code=400, detail="X-Phone header required")

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
    x_phone: Optional[str] = Header(None, description="User's phone number"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Search my conversations."""
    from conversation_search import ConversationSearch

    phone_number = x_phone or verify_token(credentials)

    if not phone_number:
        raise HTTPException(status_code=400, detail="X-Phone header required")

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
    x_phone: Optional[str] = Header(None, description="User's phone number"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get my conversation statistics."""
    phone_number = x_phone or verify_token(credentials)

    if not phone_number:
        raise HTTPException(status_code=400, detail="X-Phone header required")

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
    x_phone: Optional[str] = Header(None, description="User's phone number"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get my action items."""
    phone_number = x_phone or verify_token(credentials)

    if not phone_number:
        raise HTTPException(status_code=400, detail="X-Phone header required")

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
    x_phone: Optional[str] = Header(None, description="User's phone number"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Search conversations."""
    from conversation_search import ConversationSearch

    search = ConversationSearch()
    phone_number = x_phone or verify_token(credentials)

    if all_users:
        # Admin search across all users
        admin_phone = verify_token(credentials)
        verify_admin(admin_phone)

        results = search.search_all(
            q,
            context_filter=context_filter,
            sentiment_filter=sentiment_filter,
            total_limit=limit
        )
    elif phone_number:
        # User search
        results = search.search_user(
            phone_number,
            q,
            context_filter=context_filter,
            sentiment_filter=sentiment_filter,
            limit=limit
        )
    else:
        raise HTTPException(status_code=400, detail="X-Phone header required or use all_users=true with admin access")

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


# Logging Endpoints
@app.post("/api/conversations/log", response_model=LogResponse)
async def log_conversation(request: LogConversationRequest):
    """Log a conversation."""
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
async def link_event(request: LinkEventRequest):
    """Link conversation to event."""
    success = logger.link_to_event(request.phone, request.conversation_date, request.event_name)

    return {
        "ok": success,
        "phone": request.phone
    }


@app.post("/api/conversations/link-task", response_model=LinkResponse)
async def link_task(request: LinkTaskRequest):
    """Link conversation to task."""
    success = logger.link_to_task(request.phone, request.conversation_date, request.task_id)

    return {
        "ok": success,
        "phone": request.phone
    }


@app.post("/api/conversations/export", response_model=ExportResponse)
async def export_conversations(
    request: Dict[str, Any],
    x_phone: Optional[str] = Header(None, description="User's phone number"),
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Export user data (GDPR)."""
    phone = request.get("phone") or x_phone or verify_token(credentials)

    if not phone:
        raise HTTPException(status_code=400, detail="phone required")

    requesting_user = x_phone or verify_token(credentials) or phone

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
        "conversation_api_fastapi:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )
