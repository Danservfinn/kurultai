#!/usr/bin/env python3
"""
Tool Manager for Kurultai - Phase 4 S3 Statelessness

Manages AI-generated tools with S3/R2 storage backend.
Integrates with CapabilityRegistry for metadata and authorization.
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Import S3 storage
try:
    from tools.kurultai.storage.s3_storage import get_storage, ToolStorage
    HAS_S3 = True
except ImportError:
    HAS_S3 = False
    logging.warning("S3 storage not available")

logger = logging.getLogger("kurultai.tools")


class ToolManager:
    """
    Manages AI-generated tools with S3-compatible storage.
    
    Phase 4: Stateless tool storage - tools survive container restarts.
    """
    
    def __init__(self, neo4j_driver=None):
        self.driver = neo4j_driver
        self.storage = get_storage() if HAS_S3 else None
        
    def create_tool(
        self,
        tool_id: str,
        name: str,
        description: str,
        code: str,
        agent: str,
        version: str = "1.0.0",
        risk_level: str = "MEDIUM",
        dependencies: List[str] = None
    ) -> Dict[str, Any]:
        """
        Create and store a new AI-generated tool.
        
        Args:
            tool_id: Unique identifier (e.g., "temujin-api-client-v1")
            name: Human-readable name
            description: What the tool does
            code: Python code as string
            agent: Which agent created it
            version: Semantic version
            risk_level: LOW, MEDIUM, HIGH
            dependencies: List of required packages
        
        Returns:
            Tool metadata with S3 URI
        """
        # Calculate code hash
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
        
        # Prepare metadata
        metadata = {
            "tool_id": tool_id,
            "name": name,
            "description": description,
            "agent": agent,
            "version": version,
            "risk_level": risk_level,
            "code_hash": code_hash,
            "dependencies": dependencies or [],
            "created_at": datetime.utcnow().isoformat(),
            "status": "active"
        }
        
        # Upload to S3 (or local fallback)
        if self.storage and self.storage.is_available():
            s3_uri = self.storage.upload_tool(tool_id, code, metadata)
            metadata["storage_uri"] = s3_uri
            metadata["storage_backend"] = "s3"
        else:
            # Local fallback
            local_uri = self._save_local(tool_id, code, metadata)
            metadata["storage_uri"] = local_uri
            metadata["storage_backend"] = "local"
        
        # Register in Neo4j
        if self.driver:
            self._register_in_neo4j(metadata)
        
        logger.info(f"✅ Created tool {tool_id} at {metadata['storage_uri']}")
        return metadata
    
    def get_tool(self, tool_id: str) -> Optional[str]:
        """
        Retrieve tool code by ID.
        
        Args:
            tool_id: Tool identifier
        
        Returns:
            Python code as string, or None if not found
        """
        # First check Neo4j for URI
        uri = self._get_tool_uri(tool_id)
        if not uri:
            logger.warning(f"Tool {tool_id} not found in registry")
            return None
        
        # Download from storage
        if uri.startswith('s3://') and self.storage:
            return self.storage.download_tool(uri)
        elif uri.startswith('file://'):
            return self._load_local(uri)
        else:
            # Legacy: local path
            return Path(uri).read_text() if Path(uri).exists() else None
    
    def execute_tool(self, tool_id: str, **kwargs) -> Any:
        """
        Download and execute a tool dynamically.
        
        Phase 4: Tools are fetched from S3 and executed in memory.
        No local disk writes required.
        
        Args:
            tool_id: Tool to execute
            **kwargs: Arguments to pass to the tool
        
        Returns:
            Tool execution result
        """
        import importlib.util
        import sys
        from io import StringIO
        
        # Get tool code
        code = self.get_tool(tool_id)
        if not code:
            raise ValueError(f"Tool {tool_id} not found")
        
        # Create module dynamically (no disk write)
        module_name = f"kurultai_generated_{tool_id.replace('-', '_')}"
        spec = importlib.util.spec_from_loader(module_name, loader=None)
        module = importlib.util.module_from_spec(spec)
        
        # Execute in isolated namespace
        namespace = {
            '__name__': module_name,
            '__file__': f'{tool_id}.py',
        }
        
        try:
            exec(code, namespace)
        except Exception as e:
            logger.error(f"❌ Tool {tool_id} execution failed: {e}")
            raise
        
        # Find and call main function
        if 'main' in namespace:
            return namespace['main'](**kwargs)
        elif 'run' in namespace:
            return namespace['run'](**kwargs)
        else:
            # Return the namespace for manual access
            return namespace
    
    def list_tools(self, agent: Optional[str] = None) -> List[Dict]:
        """List all tools, optionally filtered by agent."""
        if self.storage:
            return self.storage.list_tools(agent)
        else:
            return self._list_local(agent)
    
    def delete_tool(self, tool_id: str) -> bool:
        """Delete a tool from storage and registry."""
        # TODO: Implement S3 deletion
        logger.warning(f"Tool deletion not yet implemented for {tool_id}")
        return False
    
    # Private methods
    def _register_in_neo4j(self, metadata: Dict):
        """Register tool metadata in Neo4j."""
        if not self.driver:
            return
        
        query = """
        MERGE (t:LearnedCapability {tool_id: $tool_id})
        SET t.name = $name,
            t.description = $description,
            t.agent = $agent,
            t.version = $version,
            t.risk_level = $risk_level,
            t.code_hash = $code_hash,
            t.storage_uri = $storage_uri,
            t.storage_backend = $storage_backend,
            t.created_at = datetime($created_at),
            t.status = 'active'
        RETURN t.tool_id as id
        """
        
        with self.driver.session() as session:
            session.run(query, **metadata)
    
    def _get_tool_uri(self, tool_id: str) -> Optional[str]:
        """Get storage URI from Neo4j."""
        if not self.driver:
            return None
        
        query = """
        MATCH (t:LearnedCapability {tool_id: $tool_id})
        RETURN t.storage_uri as uri
        """
        
        with self.driver.session() as session:
            result = session.run(query, tool_id=tool_id)
            record = result.single()
            return record["uri"] if record else None
    
    def _save_local(self, tool_id: str, code: str, metadata: Dict) -> str:
        """Fallback local storage."""
        base_path = Path("tools/kurultai/generated")
        base_path.mkdir(parents=True, exist_ok=True)
        
        tool_dir = base_path / tool_id
        tool_dir.mkdir(exist_ok=True)
        
        (tool_dir / "tool.py").write_text(code)
        (tool_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
        
        return f"file://{tool_dir}/tool.py"
    
    def _load_local(self, uri: str) -> str:
        """Load from local fallback."""
        path = uri.replace('file://', '')
        return Path(path).read_text()
    
    def _list_local(self, agent: Optional[str] = None) -> List[Dict]:
        """List local tools."""
        base_path = Path("tools/kurultai/generated")
        if not base_path.exists():
            return []
        
        tools = []
        for meta_file in base_path.glob("*/metadata.json"):
            try:
                metadata = json.loads(meta_file.read_text())
                if agent is None or metadata.get('agent') == agent:
                    tools.append(metadata)
            except Exception:
                pass
        return tools


# Singleton
_tool_manager: Optional[ToolManager] = None

def get_tool_manager(neo4j_driver=None) -> ToolManager:
    """Get or create tool manager instance."""
    global _tool_manager
    if _tool_manager is None:
        _tool_manager = ToolManager(neo4j_driver)
    return _tool_manager


if __name__ == "__main__":
    # Test tool manager
    print("Testing Tool Manager...")
    
    # Create test tool
    tm = get_tool_manager()
    
    test_code = '''
def main(name="World"):
    """A simple test tool."""
    return f"Hello, {name}!"
'''
    
    metadata = tm.create_tool(
        tool_id="test-hello-v1",
        name="Hello World",
        description="A simple greeting tool",
        code=test_code,
        agent="temujin",
        version="1.0.0",
        risk_level="LOW"
    )
    
    print(f"Created: {metadata}")
    
    # Execute it
    result = tm.execute_tool("test-hello-v1", name="Kurultai")
    print(f"Result: {result}")
