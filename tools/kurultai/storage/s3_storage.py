#!/usr/bin/env python3
"""
S3-Compatible Storage Client for Kurultai
Supports Cloudflare R2, AWS S3, or any S3-compatible service

Phase 4 v4.0: Stateless tool storage
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    logging.warning("boto3 not installed, S3 storage disabled")

logger = logging.getLogger("kurultai.storage")


@dataclass
class StorageConfig:
    """Configuration for S3-compatible storage."""
    endpoint_url: str
    access_key_id: str
    secret_access_key: str
    bucket_name: str
    region: str = "auto"  # R2 uses 'auto', S3 uses specific regions
    
    @classmethod
    def from_env(cls) -> Optional['StorageConfig']:
        """Load config from environment variables."""
        endpoint = os.getenv('S3_ENDPOINT_URL') or os.getenv('R2_ENDPOINT_URL')
        key_id = os.getenv('S3_ACCESS_KEY_ID') or os.getenv('R2_ACCESS_KEY_ID')
        secret = os.getenv('S3_SECRET_ACCESS_KEY') or os.getenv('R2_SECRET_ACCESS_KEY')
        bucket = os.getenv('S3_BUCKET_NAME') or os.getenv('R2_BUCKET_NAME')
        
        if not all([endpoint, key_id, secret, bucket]):
            logger.warning("S3/R2 credentials not fully configured")
            return None
        
        return cls(
            endpoint_url=endpoint,
            access_key_id=key_id,
            secret_access_key=secret,
            bucket_name=bucket,
            region=os.getenv('S3_REGION', 'auto')
        )


class ToolStorage:
    """Storage backend for AI-generated tools."""
    
    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig.from_env()
        self._client = None
        self._local_fallback = True  # Fallback to local disk if S3 fails
        
        if self.config and HAS_BOTO3:
            self._init_client()
    
    def _init_client(self):
        """Initialize S3 client."""
        try:
            self._client = boto3.client(
                's3',
                endpoint_url=self.config.endpoint_url,
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
                region_name=self.config.region,
                config=Config(
                    retries={'max_attempts': 3},
                    connect_timeout=5,
                    read_timeout=30
                )
            )
            # Test connection
            self._client.head_bucket(Bucket=self.config.bucket_name)
            logger.info(f"✅ S3 storage connected: {self.config.bucket_name}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to S3: {e}")
            self._client = None
    
    def is_available(self) -> bool:
        """Check if S3 storage is available."""
        return self._client is not None
    
    def upload_tool(self, tool_id: str, code: str, metadata: Dict[str, Any]) -> str:
        """
        Upload a tool to S3 storage.
        
        Args:
            tool_id: Unique tool identifier
            code: Python code as string
            metadata: Tool metadata (agent, version, description, etc.)
        
        Returns:
            s3_uri: S3 URI for the stored tool
        """
        if not self.is_available():
            if self._local_fallback:
                return self._upload_local(tool_id, code, metadata)
            raise RuntimeError("S3 storage not available and local fallback disabled")
        
        try:
            # Upload code
            code_key = f"tools/{tool_id}/tool.py"
            self._client.put_object(
                Bucket=self.config.bucket_name,
                Key=code_key,
                Body=code.encode('utf-8'),
                ContentType='text/x-python',
                Metadata={
                    'tool-id': tool_id,
                    'agent': metadata.get('agent', 'unknown'),
                    'version': metadata.get('version', '1.0.0'),
                    'created-at': metadata.get('created_at', ''),
                    'risk-level': metadata.get('risk_level', 'MEDIUM')
                }
            )
            
            # Upload metadata as JSON
            meta_key = f"tools/{tool_id}/metadata.json"
            self._client.put_object(
                Bucket=self.config.bucket_name,
                Key=meta_key,
                Body=json.dumps(metadata, indent=2).encode('utf-8'),
                ContentType='application/json'
            )
            
            s3_uri = f"s3://{self.config.bucket_name}/{code_key}"
            logger.info(f"✅ Uploaded {tool_id} to {s3_uri}")
            return s3_uri
            
        except ClientError as e:
            logger.error(f"❌ S3 upload failed for {tool_id}: {e}")
            if self._local_fallback:
                logger.warning("Falling back to local storage")
                return self._upload_local(tool_id, code, metadata)
            raise
    
    def download_tool(self, s3_uri: str) -> str:
        """
        Download tool code from S3.
        
        Args:
            s3_uri: S3 URI (s3://bucket/tools/tool-id/tool.py)
        
        Returns:
            code: Python code as string
        """
        if s3_uri.startswith('file://'):
            # Local file fallback
            return self._download_local(s3_uri)
        
        if not self.is_available():
            raise RuntimeError("S3 storage not available")
        
        try:
            # Parse S3 URI
            # s3://bucket-name/tools/tool-id/tool.py
            parts = s3_uri.replace('s3://', '').split('/', 1)
            bucket = parts[0]
            key = parts[1]
            
            response = self._client.get_object(Bucket=bucket, Key=key)
            code = response['Body'].read().decode('utf-8')
            logger.debug(f"✅ Downloaded {s3_uri}")
            return code
            
        except ClientError as e:
            logger.error(f"❌ S3 download failed for {s3_uri}: {e}")
            raise
    
    def list_tools(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all stored tools."""
        if not self.is_available():
            return self._list_local(agent)
        
        try:
            prefix = f"tools/"
            if agent:
                prefix = f"tools/{agent}-"
            
            response = self._client.list_objects_v2(
                Bucket=self.config.bucket_name,
                Prefix=prefix
            )
            
            tools = []
            for obj in response.get('Contents', []):
                if obj['Key'].endswith('metadata.json'):
                    try:
                        resp = self._client.get_object(
                            Bucket=self.config.bucket_name,
                            Key=obj['Key']
                        )
                        metadata = json.loads(resp['Body'].read().decode('utf-8'))
                        tools.append(metadata)
                    except Exception as e:
                        logger.warning(f"Failed to load metadata: {e}")
            
            return tools
            
        except ClientError as e:
            logger.error(f"❌ Failed to list tools: {e}")
            return self._list_local(agent)
    
    # Local fallback methods
    def _upload_local(self, tool_id: str, code: str, metadata: Dict) -> str:
        """Fallback to local filesystem."""
        base_path = Path("tools/kurultai/generated")
        base_path.mkdir(parents=True, exist_ok=True)
        
        tool_dir = base_path / tool_id
        tool_dir.mkdir(exist_ok=True)
        
        # Save code
        code_path = tool_dir / "tool.py"
        code_path.write_text(code)
        
        # Save metadata
        meta_path = tool_dir / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2))
        
        local_uri = f"file://{tool_dir}/tool.py"
        logger.info(f"💾 Saved locally: {local_uri}")
        return local_uri
    
    def _download_local(self, uri: str) -> str:
        """Download from local filesystem."""
        path = uri.replace('file://', '')
        return Path(path).read_text()
    
    def _list_local(self, agent: Optional[str] = None) -> List[Dict]:
        """List locally stored tools."""
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


# Singleton instance
_storage_instance: Optional[ToolStorage] = None

def get_storage() -> ToolStorage:
    """Get or create storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = ToolStorage()
    return _storage_instance


if __name__ == "__main__":
    # Test connection
    storage = get_storage()
    if storage.is_available():
        print("✅ S3 storage connected")
        tools = storage.list_tools()
        print(f"Found {len(tools)} tools")
    else:
        print("⚠️ S3 storage not configured, using local fallback")
        print("Set environment variables:")
        print("  R2_ENDPOINT_URL=https://xxx.r2.cloudflarestorage.com")
        print("  R2_ACCESS_KEY_ID=your-key")
        print("  R2_SECRET_ACCESS_KEY=your-secret")
        print("  R2_BUCKET_NAME=kurultai-tools")
