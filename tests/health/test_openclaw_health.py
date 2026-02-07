"""
OpenClaw Gateway Health Checks

Tests for OpenClaw gateway availability and operations:
- HTTP health endpoint
- WebSocket connectivity
- Echo/response validation
- Active session count
"""

import asyncio
import json
import os
import time
from typing import Dict, Any
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# WebSocket imports with graceful failure
try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    websockets = MagicMock()

# HTTP client with graceful failure
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    aiohttp = MagicMock()


@pytest.fixture
def openclaw_config() -> Dict[str, str]:
    """OpenClaw gateway configuration from environment."""
    return {
        "ws_url": os.getenv("OPENCLAW_WS_URL", "ws://localhost:18789"),
        "http_url": os.getenv("OPENCLAW_HTTP_URL", "http://localhost:18789"),
        "token": os.getenv("OPENCLAW_TOKEN", ""),
    }


@pytest.mark.health
@pytest.mark.openclaw
class TestOpenClawHTTPEndpoint:
    """Test OpenClaw HTTP health endpoint."""

    @pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not installed")
    def test_http_health_endpoint(self, openclaw_config: Dict[str, str]):
        """Verify HTTP health endpoint responds correctly."""
        async def check_http():
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{openclaw_config['http_url']}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert "status" in data or "service" in data

        try:
            asyncio.run(check_http())
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            pytest.skip(f"OpenClaw gateway not available: {e}")

    @pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not installed")
    def test_http_response_time(self, openclaw_config: Dict[str, str]):
        """Verify HTTP endpoint responds quickly."""
        async def check_timing():
            start = time.time()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{openclaw_config['http_url']}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    await resp.read()
            elapsed_ms = (time.time() - start) * 1000
            return elapsed_ms

        try:
            latency_ms = asyncio.run(check_timing())
            assert latency_ms < 5000, f"HTTP response took {latency_ms:.2f}ms, expected < 5000ms"
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            pytest.skip(f"OpenClaw gateway not available: {e}")


@pytest.mark.health
@pytest.mark.openclaw
class TestOpenClawWebSocket:
    """Test OpenClaw WebSocket connectivity."""

    @pytest.mark.skipif(not HAS_WEBSOCKETS, reason="websockets not installed")
    def test_websocket_connect(self, openclaw_config: Dict[str, str]):
        """Verify WebSocket connection can be established."""
        async def check_ws():
            try:
                async with websockets.connect(
                    openclaw_config["ws_url"],
                    close_timeout=5
                ) as ws:
                    # Connection established
                    return True
            except (OSError, ConnectionRefusedError, asyncio.TimeoutError):
                return False

        try:
            connected = asyncio.run(check_ws())
            if not connected:
                pytest.skip("OpenClaw gateway not available")
        except Exception as e:
            pytest.skip(f"WebSocket connection failed: {e}")

    @pytest.mark.skipif(not HAS_WEBSOCKETS, reason="websockets not installed")
    def test_websocket_handshake(self, openclaw_config: Dict[str, str]):
        """Verify WebSocket handshake with OpenClaw protocol."""
        async def check_handshake():
            try:
                async with websockets.connect(
                    openclaw_config["ws_url"],
                    close_timeout=5
                ) as ws:
                    # Send connect frame
                    connect_msg = {
                        "type": "connect",
                        "role": "operator",
                        "token": openclaw_config.get("token", ""),
                        "scopes": ["operator.admin"]
                    }
                    await ws.send(json.dumps(connect_msg))

                    # Wait for response
                    response = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(response)

                    return data
            except (OSError, ConnectionRefusedError, asyncio.TimeoutError) as e:
                raise

        try:
            response = asyncio.run(check_handshake())
            # Response should be a dict with type field
            assert isinstance(response, dict)
            assert "type" in response
        except (OSError, ConnectionRefusedError, asyncio.TimeoutError) as e:
            pytest.skip(f"OpenClaw gateway not available: {e}")


@pytest.mark.health
@pytest.mark.openclaw
class TestOpenClawEcho:
    """Test OpenClaw echo/response functionality."""

    @pytest.mark.skipif(not HAS_WEBSOCKETS, reason="websockets not installed")
    def test_echo_response(self, openclaw_config: Dict[str, str]):
        """Verify gateway responds to messages."""
        async def check_echo():
            try:
                async with websockets.connect(
                    openclaw_config["ws_url"],
                    close_timeout=5
                ) as ws:
                    # Connect first
                    connect_msg = {
                        "type": "connect",
                        "role": "operator",
                        "token": openclaw_config.get("token", ""),
                        "scopes": ["operator.admin"]
                    }
                    await ws.send(json.dumps(connect_msg))
                    await asyncio.wait_for(ws.recv(), timeout=5)

                    # Send a ping/echo message
                    ping_msg = {
                        "type": "ping",
                        "timestamp": time.time()
                    }
                    await ws.send(json.dumps(ping_msg))

                    # Wait for response
                    response = await asyncio.wait_for(ws.recv(), timeout=5)
                    return json.loads(response)
            except (OSError, ConnectionRefusedError, asyncio.TimeoutError):
                raise

        try:
            response = asyncio.run(check_echo())
            assert isinstance(response, dict)
        except (OSError, ConnectionRefusedError, asyncio.TimeoutError) as e:
            pytest.skip(f"OpenClaw gateway not available: {e}")


def check_openclaw_health(config: Dict[str, str], timeout_ms: int = 5000) -> Dict[str, Any]:
    """
    Run comprehensive OpenClaw health check.

    Args:
        config: OpenClaw gateway configuration
        timeout_ms: Max acceptable latency in milliseconds

    Returns:
        Health check result with status, latency, and details
    """
    start = time.time()
    result = {
        "status": "pass",
        "latency_ms": 0,
        "details": {
            "ws_connected": False,
            "http_healthy": False,
        }
    }

    # Check HTTP health endpoint
    if HAS_AIOHTTP:
        try:
            async def check_http():
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{config['http_url']}/health",
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        data = await resp.json()
                        return resp.status, data

            status, data = asyncio.run(check_http())
            if status == 200:
                result["details"]["http_healthy"] = True
                result["details"].update(data)
            else:
                result["status"] = "fail"
        except Exception as e:
            result["details"]["http_error"] = str(e)

    # Check WebSocket connectivity
    if HAS_WEBSOCKETS:
        try:
            async def check_ws():
                async with websockets.connect(
                    config["ws_url"],
                    close_timeout=5
                ) as ws:
                    return True

            result["details"]["ws_connected"] = asyncio.run(check_ws())
        except Exception as e:
            result["details"]["ws_error"] = str(e)

    # Determine overall status
    http_ok = result["details"].get("http_healthy", False)
    ws_ok = result["details"].get("ws_connected", False)

    if http_ok and ws_ok:
        result["status"] = "pass"
    elif http_ok or ws_ok:
        result["status"] = "warn"
    else:
        result["status"] = "fail"

    result["latency_ms"] = round((time.time() - start) * 1000)
    return result


@pytest.mark.health
@pytest.mark.openclaw
def test_openclaw_health_check_function(openclaw_config: Dict[str, str]):
    """Test the health check function itself."""
    result = check_openclaw_health(openclaw_config)

    assert "status" in result
    assert "latency_ms" in result
    assert "details" in result
    assert "ws_connected" in result["details"]
    assert "http_healthy" in result["details"]
