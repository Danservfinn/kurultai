#!/usr/bin/env python3
"""
Antigravity API Routes for Kurultai FastAPI

Exposes Antigravity functionality via REST API:
- POST /api/antigravity/open - Open file in Antigravity
- POST /api/antigravity/edit - Edit file
- POST /api/antigravity/execute - Execute command
- POST /api/antigravity/generate - Generate code
- GET /api/antigravity/status - Get status
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from tools.kurultai.antigravity_bridge import get_antigravity_bridge

router = APIRouter(prefix="/api/antigravity", tags=["antigravity"])


# Request/Response models
class OpenFileRequest(BaseModel):
    filepath: str
    line: Optional[int] = None
    column: Optional[int] = None


class EditRequest(BaseModel):
    filepath: str
    edits: List[Dict[str, str]]  # [{"old": "...", "new": "..."}]


class ExecuteRequest(BaseModel):
    command: str


class GenerateRequest(BaseModel):
    prompt: str
    context_file: Optional[str] = None


class ProjectRequest(BaseModel):
    project_name: str
    template: str = "basic"  # basic, python, web


@router.get("/status")
async def get_status():
    """Get Antigravity bridge status."""
    bridge = get_antigravity_bridge()
    return bridge.get_status()


@router.post("/open")
async def open_file(request: OpenFileRequest):
    """Open a file in Antigravity."""
    bridge = get_antigravity_bridge()
    
    if not bridge.is_available():
        raise HTTPException(status_code=503, detail="Antigravity not available")
    
    success = bridge.open_file(request.filepath, request.line, request.column)
    
    if success:
        return {
            "status": "success",
            "action": "opened",
            "file": request.filepath,
            "line": request.line,
            "column": request.column
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to open file")


@router.post("/edit")
async def edit_file(request: EditRequest):
    """Apply edits to a file."""
    bridge = get_antigravity_bridge()
    
    success = bridge.edit_file(request.filepath, request.edits)
    
    if success:
        return {
            "status": "success",
            "action": "edited",
            "file": request.filepath,
            "edits_count": len(request.edits)
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to edit file")


@router.post("/execute")
async def execute_command(request: ExecuteRequest):
    """Execute a shell command."""
    bridge = get_antigravity_bridge()
    
    result = bridge.execute_command(request.command)
    
    return {
        "status": "success" if result.get("success") else "error",
        "command": request.command,
        "result": result
    }


@router.post("/generate")
async def generate_code(request: GenerateRequest):
    """Generate code using Antigravity AI."""
    bridge = get_antigravity_bridge()
    
    if not bridge.is_available():
        raise HTTPException(status_code=503, detail="Antigravity not available")
    
    code = bridge.generate_code(request.prompt, request.context_file)
    
    return {
        "status": "success",
        "prompt": request.prompt,
        "generated_code": code
    }


@router.post("/project/create")
async def create_project(request: ProjectRequest):
    """Create a new project."""
    bridge = get_antigravity_bridge()
    
    project_path = bridge.create_project(request.project_name, request.template)
    
    return {
        "status": "success",
        "action": "project_created",
        "project_name": request.project_name,
        "template": request.template,
        "path": project_path
    }


@router.post("/workspace/add")
async def add_to_workspace(folder_path: str):
    """Add folder to Antigravity workspace."""
    bridge = get_antigravity_bridge()
    
    if not bridge.is_available():
        raise HTTPException(status_code=503, detail="Antigravity not available")
    
    success = bridge.add_workspace_folder(folder_path)
    
    if success:
        return {
            "status": "success",
            "action": "added_to_workspace",
            "folder": folder_path
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to add folder")
