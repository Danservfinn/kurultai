#!/usr/bin/env python3
"""
Kurultai FastAPI - Unified Python Backend (Phase 3 v4.0)
Replaces Express.js server with FastAPI
"""

import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import json

from neo4j import GraphDatabase

app = FastAPI(
    title="Kurultai API",
    description="Unified backend for Kurultai agent orchestration",
    version="4.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Neo4j connection
def get_db():
    driver = GraphDatabase.driver(
        os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
        auth=(
            os.getenv('NEO4J_USER', 'neo4j'),
            os.getenv('NEO4J_PASSWORD', 'myStrongPassword123')
        )
    )
    return driver

# Import and register antigravity routes
try:
    from tools.kurultai.api.routes import antigravity as antigravity_routes
    app.include_router(antigravity_routes.router)
    print("✅ Antigravity routes registered")
except Exception as e:
    print(f"⚠️  Antigravity routes not loaded: {e}")

# Health check
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "kurultai-fastapi",
        "version": "4.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

# Architecture routes
@app.get("/api/architecture/overview")
async def architecture_overview():
    """Get all architecture sections."""
    driver = get_db()
    with driver.session() as session:
        result = session.run('''
            MATCH (s:ArchitectureSection)
            RETURN s.title as title, s.order as order, 
                   s.updated_at as updated_at
            ORDER BY s.order
        ''')
        sections = [
            {
                "title": r["title"],
                "order": r["order"],
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None
            }
            for r in result
        ]
    driver.close()
    return {"sections": sections, "count": len(sections)}

@app.get("/api/architecture/search")
async def architecture_search(q: str = Query(..., description="Search term")):
    """Search architecture sections."""
    driver = get_db()
    with driver.session() as session:
        result = session.run('''
            MATCH (s:ArchitectureSection)
            WHERE s.title CONTAINS $term OR s.content CONTAINS $term
            RETURN s.title as title, s.content as content
            LIMIT 10
        ''', term=q)
        matches = [
            {"title": r["title"], "preview": r["content"][:200] + "..."}
            for r in result
        ]
    driver.close()
    return {"query": q, "matches": matches}

@app.get("/api/architecture/section/{title}")
async def get_section(title: str):
    """Get specific architecture section."""
    driver = get_db()
    with driver.session() as session:
        result = session.run('''
            MATCH (s:ArchitectureSection {title: $title})
            RETURN s.title as title, s.content as content, 
                   s.updated_at as updated_at
        ''', title=title)
        record = result.single()
    driver.close()
    
    if not record:
        raise HTTPException(status_code=404, detail="Section not found")
    
    return {
        "title": record["title"],
        "content": record["content"],
        "updated_at": record["updated_at"].isoformat() if record["updated_at"] else None
    }

# Proposals/Workflow routes
@app.get("/api/proposals")
async def list_proposals(status: Optional[str] = None):
    """List architecture proposals."""
    driver = get_db()
    query = "MATCH (p:ArchitectureProposal)"
    if status:
        query += " WHERE p.status = $status"
    query += " RETURN p ORDER BY p.created_at DESC"
    
    with driver.session() as session:
        result = session.run(query, status=status)
        proposals = [
            {
                "id": r["p"]["id"],
                "title": r["p"]["title"],
                "status": r["p"]["status"],
                "created_at": r["p"]["created_at"].isoformat() if r["p"]["created_at"] else None
            }
            for r in result
        ]
    driver.close()
    return {"proposals": proposals}

@app.post("/api/workflow/process")
async def process_workflow():
    """Trigger workflow processing."""
    return {
        "message": "Workflow processing triggered",
        "timestamp": datetime.utcnow().isoformat(),
        "status": "queued"
    }

@app.get("/api/workflow/status/{proposal_id}")
async def workflow_status(proposal_id: str):
    """Check proposal workflow status."""
    driver = get_db()
    with driver.session() as session:
        result = session.run('''
            MATCH (p:ArchitectureProposal {id: $id})
            RETURN p.status as status, p.implementation_status as impl_status
        ''', id=proposal_id)
        record = result.single()
    driver.close()
    
    if not record:
        raise HTTPException(status_code=404, detail="Proposal not found")
    
    return {
        "proposal_id": proposal_id,
        "status": record["status"],
        "implementation_status": record["impl_status"]
    }

# Agent status
@app.get("/api/agents")
async def list_agents():
    """List all agents and their status."""
    driver = get_db()
    with driver.session() as session:
        result = session.run('''
            MATCH (a:Agent)
            RETURN a.name as name, a.id as id, a.status as status,
                   a.last_heartbeat as last_heartbeat
            ORDER BY a.name
        ''')
        agents = [
            {
                "name": r["name"],
                "id": r["id"],
                "status": r["status"],
                "last_heartbeat": r["last_heartbeat"].isoformat() if r["last_heartbeat"] else None
            }
            for r in result
        ]
    driver.close()
    return {"agents": agents}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
