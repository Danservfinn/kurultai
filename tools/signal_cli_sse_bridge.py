#!/usr/bin/env python3
"""
Signal-CLI SSE Bridge with Full Media Support

OpenClaw expects signal-cli to expose an SSE endpoint for receiving messages,
but signal-cli 0.13.24 only provides JSON-RPC over HTTP.

This bridge:
1. Starts signal-cli daemon in HTTP mode (JSON-RPC)
2. Exposes an SSE endpoint that OpenClaw can connect to
3. Polls signal-cli for new messages and forwards them as SSE events
4. Forwards send requests from OpenClaw to signal-cli
5. Handles media attachments via base64 encoding/decoding

Usage:
    python3 signal_cli_sse_bridge.py

Environment:
    SIGNAL_ACCOUNT - Signal account number (e.g., +15165643945)
    SIGNAL_CLI_PATH - Path to signal-cli binary (default: /usr/local/bin/signal-cli)
    BRIDGE_HOST - Host to bind SSE server (default: 127.0.0.1)
    BRIDGE_PORT - Port for SSE server (default: 8080)
    SIGNAL_HTTP_PORT - Port for signal-cli HTTP JSON-RPC (default: 8081)
"""

import os
import sys
import json
import time
import asyncio
import subprocess
import signal
import base64
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any, AsyncGenerator, List
from pathlib import Path

# Try to import aiohttp for SSE server
try:
    import aiohttp
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    print("❌ aiohttp not installed. Install with: pip install aiohttp")
    sys.exit(1)

# Configuration
SIGNAL_ACCOUNT = os.getenv("SIGNAL_ACCOUNT", "+15165643945")
SIGNAL_CLI_PATH = os.getenv("SIGNAL_CLI_PATH", "/usr/local/bin/signal-cli")
BRIDGE_HOST = os.getenv("BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8080"))
SIGNAL_HTTP_PORT = int(os.getenv("SIGNAL_HTTP_PORT", "8081"))

# Global state
signal_cli_process: Optional[subprocess.Popen] = None
last_message_timestamp: Optional[int] = None
message_queue: asyncio.Queue = asyncio.Queue()
active_sse_connections: set = set()
MAX_SSE_CONNECTIONS = 5  # Limit concurrent connections


class SignalCLIBridge:
    """Bridge between signal-cli JSON-RPC and SSE with media support."""
    
    def __init__(self):
        self.signal_url = f"http://127.0.0.1:{SIGNAL_HTTP_PORT}/api/v1/rpc"
        self.running = False
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def start_signal_cli(self):
        """Start signal-cli daemon in HTTP mode."""
        global signal_cli_process
        
        cmd = [
            SIGNAL_CLI_PATH,
            "-a", SIGNAL_ACCOUNT,
            "daemon",
            "--http", f"127.0.0.1:{SIGNAL_HTTP_PORT}",
            "--receive-mode", "manual",  # Changed from on-start to manual
        ]
        
        print(f"🚀 Starting signal-cli daemon on port {SIGNAL_HTTP_PORT}...")
        print(f"   Command: {' '.join(cmd)}")
        
        signal_cli_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for daemon to be ready
        await asyncio.sleep(3)
        
        # Check if process is running
        if signal_cli_process.poll() is not None:
            stdout, stderr = signal_cli_process.communicate()
            print(f"❌ signal-cli failed to start:")
            print(f"   stdout: {stdout}")
            print(f"   stderr: {stderr}")
            return False
            
        print(f"✅ signal-cli daemon started (PID: {signal_cli_process.pid})")
        return True
        
    async def stop_signal_cli(self):
        """Stop signal-cli daemon."""
        global signal_cli_process
        
        if signal_cli_process:
            print(f"🛑 Stopping signal-cli (PID: {signal_cli_process.pid})...")
            signal_cli_process.terminate()
            try:
                signal_cli_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                signal_cli_process.kill()
            signal_cli_process = None
            
    async def jsonrpc_call(self, method: str, params: Optional[Dict] = None) -> Dict:
        """Make a JSON-RPC call to signal-cli."""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params or {}
        }
        
        try:
            async with self.session.post(
                self.signal_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    raise RuntimeError(f"JSON-RPC error {resp.status}: {text}")
        except Exception as e:
            print(f"❌ JSON-RPC call failed: {e}")
            raise
            
    async def fetch_attachment(self, attachment_id: str) -> Optional[bytes]:
        """Fetch attachment from signal-cli as base64 and decode."""
        try:
            result = await self.jsonrpc_call("getAttachment", {
                "account": SIGNAL_ACCOUNT,
                "attachment": attachment_id
            })
            
            if result and "result" in result:
                # Decode base64 attachment data
                return base64.b64decode(result["result"])
            return None
        except Exception as e:
            print(f"⚠️ Failed to fetch attachment {attachment_id}: {e}")
            return None
            
    async def download_attachments(self, message: Dict) -> List[Dict]:
        """Download all attachments for a message and add data."""
        envelope = message.get("envelope", {})
        sync_message = envelope.get("syncMessage", {})
        data_message = sync_message.get("dataMessage", {}) or envelope.get("dataMessage", {})
        
        attachments = data_message.get("attachments", [])
        downloaded = []
        
        for att in attachments:
            att_id = att.get("id")
            if att_id:
                print(f"📥 Downloading attachment {att_id}...")
                data = await self.fetch_attachment(att_id)
                if data:
                    # Add base64 data to attachment
                    att["data"] = base64.b64encode(data).decode('utf-8')
                    att["size"] = len(data)
                    downloaded.append(att)
                    print(f"✅ Downloaded {len(data)} bytes")
                else:
                    att["data"] = None
                    downloaded.append(att)
                    
        return downloaded
            
    async def send_message(self, recipient: str, message: str, 
                          attachments: List[Dict] = None) -> Dict:
        """Send a message via signal-cli with optional media attachments."""
        params = {
            "account": SIGNAL_ACCOUNT,
            "recipient": recipient,
            "message": message
        }
        
        temp_files = []
        try:
            if attachments:
                # Process attachments - either file paths or base64 data
                attachment_paths = []
                for att in attachments:
                    if isinstance(att, str):
                        # File path
                        attachment_paths.append(att)
                    elif isinstance(att, dict):
                        # Base64 data - write to temp file
                        if "data" in att and "filename" in att:
                            temp_dir = tempfile.gettempdir()
                            temp_path = os.path.join(temp_dir, att["filename"])
                            with open(temp_path, "wb") as f:
                                f.write(base64.b64decode(att["data"]))
                            attachment_paths.append(temp_path)
                            temp_files.append(temp_path)
                            print(f"📝 Wrote attachment to {temp_path}")
                            
                if attachment_paths:
                    params["attachments"] = attachment_paths
                
            return await self.jsonrpc_call("send", params)
            
        finally:
            # Cleanup temp files
            for temp_file in temp_files:
                try:
                    os.remove(temp_file)
                except:
                    pass
        
    async def poll_messages(self):
        """Poll signal-cli for new messages and queue them for SSE."""
        global last_message_timestamp
        
        while self.running:
            try:
                # Call receive to get messages (no account param in daemon mode)
                result = await self.jsonrpc_call("receive", {
                    "timeout": 1
                })
                
                if result and "result" in result:
                    messages = result["result"]
                    if messages:
                        for msg in messages:
                            # Download attachments if present
                            envelope = msg.get("envelope", {})
                            sync_message = envelope.get("syncMessage", {})
                            data_message = sync_message.get("dataMessage", {}) or envelope.get("dataMessage", {})
                            
                            if data_message.get("attachments"):
                                print(f"📎 Message has {len(data_message['attachments'])} attachments, downloading...")
                                msg["downloaded_attachments"] = await self.download_attachments(msg)
                            
                            # Add to queue for SSE consumers
                            await message_queue.put(msg)
                            timestamp = envelope.get("timestamp", "unknown")
                            print(f"📨 RECEIVED: {timestamp}")
                            
            except Exception as e:
                # Receive timeout is expected - this means no new messages
                if "timeout" in str(e).lower() or "empty" in str(e).lower():
                    pass  # Normal - no messages waiting
                else:
                    print(f"⚠️ Poll error: {e}")
                    
            await asyncio.sleep(0.5)  # Poll every 500ms for faster response
            
    async def sse_handler(self, request: web.Request) -> web.StreamResponse:
        """Handle SSE connection from OpenClaw with connection limiting."""
        global active_sse_connections
        
        # Check connection limit
        if len(active_sse_connections) >= MAX_SSE_CONNECTIONS:
            print(f"⚠️ Max SSE connections ({MAX_SSE_CONNECTIONS}) reached, rejecting new connection")
            return web.Response(status=503, text="Server busy - max connections reached")
        
        client_id = f"{request.remote}:{id(asyncio.current_task())}"
        active_sse_connections.add(client_id)
        print(f"🔌 SSE connection #{len(active_sse_connections)} from {request.remote} (total: {len(active_sse_connections)})")
        
        response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
            }
        )
        
        try:
            await response.prepare(request)
            
            # Send initial connection event
            await response.write(b'event: connected\ndata: {"status": "connected"}\n\n')
            
            while self.running:
                # Wait for messages from queue with shorter timeout for responsiveness
                try:
                    msg = await asyncio.wait_for(message_queue.get(), timeout=2.0)
                    
                    # Format as SSE event
                    event_data = json.dumps(msg)
                    sse_event = f"event: message\ndata: {event_data}\n\n"
                    await response.write(sse_event.encode())
                    
                except asyncio.TimeoutError:
                    # Send keepalive every 2 seconds
                    try:
                        await response.write(b':keepalive\n\n')
                    except Exception:
                        # Client disconnected
                        break
                except Exception as e:
                    # Connection broken
                    print(f"⚠️ SSE write error for {client_id}: {e}")
                    break
                    
        except Exception as e:
            print(f"⚠️ SSE handler error for {client_id}: {e}")
        finally:
            active_sse_connections.discard(client_id)
            print(f"🔌 SSE connection closed: {client_id} (remaining: {len(active_sse_connections)})")
            
        return response
        
    async def health_handler(self, request: web.Request) -> web.Response:
        """Health check endpoint with connection stats."""
        return web.json_response({
            "status": "healthy",
            "signal_cli_running": signal_cli_process is not None and signal_cli_process.poll() is None,
            "account": SIGNAL_ACCOUNT,
            "sse_connections": len(active_sse_connections),
            "max_connections": MAX_SSE_CONNECTIONS,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    async def send_handler(self, request: web.Request) -> web.Response:
        """Handle send requests from OpenClaw with media support."""
        try:
            data = await request.json()
            recipient = data.get("recipient")
            message = data.get("message")
            attachments = data.get("attachments", [])
            
            if not recipient:
                return web.json_response(
                    {"error": "Missing recipient"},
                    status=400
                )
                
            result = await self.send_message(recipient, message, attachments)
            return web.json_response(result)
            
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
            
    async def run(self):
        """Run the bridge."""
        self.running = True
        
        # Start signal-cli
        if not await self.start_signal_cli():
            print("❌ Failed to start signal-cli")
            return
            
        # Create HTTP session
        self.session = aiohttp.ClientSession()
        
        # Start polling task
        poll_task = asyncio.create_task(self.poll_messages())
        
        # Create web server
        app = web.Application()
        app.router.add_get('/events', self.sse_handler)  # SSE endpoint
        app.router.add_get('/health', self.health_handler)  # Health check
        app.router.add_post('/send', self.send_handler)  # Send message
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, BRIDGE_HOST, BRIDGE_PORT)
        await site.start()
        
        print(f"✅ SSE Bridge running on http://{BRIDGE_HOST}:{BRIDGE_PORT}")
        print(f"   SSE endpoint: http://{BRIDGE_HOST}:{BRIDGE_PORT}/events")
        print(f"   Health check: http://{BRIDGE_HOST}:{BRIDGE_PORT}/health")
        print(f"   Send message: http://{BRIDGE_HOST}:{BRIDGE_PORT}/send")
        print()
        print("📝 OpenClaw configuration:")
        print(f'   {{ channels: {{ signal: {{ httpUrl: "http://{BRIDGE_HOST}:{BRIDGE_PORT}", autoStart: false }} }} }}')
        
        # Keep running until interrupted
        try:
            while self.running:
                await asyncio.sleep(1)
                
                # Check if signal-cli is still running
                if signal_cli_process and signal_cli_process.poll() is not None:
                    print("⚠️ signal-cli died, restarting...")
                    await self.start_signal_cli()
                    
        except asyncio.CancelledError:
            pass
        finally:
            # Cleanup
            self.running = False
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass
                
            await runner.cleanup()
            await self.session.close()
            await self.stop_signal_cli()
            

def main():
    """Main entry point."""
    print("=" * 60)
    print("Signal-CLI SSE Bridge with Media Support")
    print("=" * 60)
    print()
    print(f"Configuration:")
    print(f"  Signal Account: {SIGNAL_ACCOUNT}")
    print(f"  signal-cli: {SIGNAL_CLI_PATH}")
    print(f"  Bridge: {BRIDGE_HOST}:{BRIDGE_PORT}")
    print(f"  signal-cli HTTP: 127.0.0.1:{SIGNAL_HTTP_PORT}")
    print()
    
    # Check signal-cli exists
    if not os.path.exists(SIGNAL_CLI_PATH):
        print(f"❌ signal-cli not found at {SIGNAL_CLI_PATH}")
        sys.exit(1)
        
    # Handle shutdown gracefully
    bridge = SignalCLIBridge()
    
    def signal_handler(sig, frame):
        print("\n🛑 Shutting down...")
        bridge.running = False
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run bridge
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:
        pass
        
    print("👋 Bridge stopped")


if __name__ == "__main__":
    main()
