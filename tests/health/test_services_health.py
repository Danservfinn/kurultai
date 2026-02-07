"""
Service Endpoint Health Checks

Tests for HTTP service endpoints:
- Authentik proxy health
- Moltbot service health
- Neo4j endpoint availability
- Response time validation
"""

import os
import time
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch

import pytest

# HTTP client with graceful failure
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    requests = MagicMock()

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    aiohttp = MagicMock()


@pytest.fixture
def service_config() -> Dict[str, str]:
    """Service endpoint configuration from environment."""
    return {
        "authentik_proxy": os.getenv(
            "AUTHENTIK_PROXY_URL",
            "http://localhost:9000"
        ),
        "moltbot": os.getenv(
            "MOLTBOT_URL",
            "http://localhost:18789"
        ),
        "neo4j": os.getenv(
            "NEO4J_URI",
            "http://localhost:7474"
        ),
        "timeout_s": int(os.getenv("HEALTH_TIMEOUT_S", "5")),
    }


@pytest.mark.health
@pytest.mark.services
class TestServiceEndpoints:
    """Test HTTP service endpoint availability."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_authentik_proxy_health(self, service_config: Dict[str, str]):
        """Check Authentik proxy health endpoint."""
        try:
            response = requests.get(
                f"{service_config['authentik_proxy']}/health",
                timeout=5
            )
            # Accept 200 (OK) or 401 (auth required - means service is up)
            assert response.status_code in [200, 401, 302]
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Authentik proxy not available: {e}")

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_moltbot_health(self, service_config: Dict[str, str]):
        """Check Moltbot health endpoint."""
        try:
            response = requests.get(
                f"{service_config['moltbot']}/health",
                timeout=5
            )
            assert response.status_code == 200
            data = response.json()
            assert "status" in data or "service" in data
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Moltbot not available: {e}")

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_neo4j_http_endpoint(self, service_config: Dict[str, str]):
        """Check Neo4j HTTP endpoint."""
        try:
            # Convert bolt:// to http://
            http_url = service_config["neo4j"].replace(
                "bolt://", "http://"
            ).replace("7687", "7474")

            response = requests.get(
                f"{http_url}/",
                timeout=5
            )
            # Neo4j browser endpoint should be accessible
            assert response.status_code in [200, 404]
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Neo4j HTTP endpoint not available: {e}")


@pytest.mark.health
@pytest.mark.services
class TestServiceResponseTimes:
    """Test service endpoint response times."""

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_moltbot_response_time(self, service_config: Dict[str, str]):
        """Verify Moltbot responds within acceptable time."""
        try:
            start = time.time()
            response = requests.get(
                f"{service_config['moltbot']}/health",
                timeout=5
            )
            elapsed_ms = (time.time() - start) * 1000

            assert response.status_code == 200
            assert elapsed_ms < 5000, f"Response took {elapsed_ms:.2f}ms"
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Moltbot not available: {e}")

    @pytest.mark.skipif(not HAS_REQUESTS, reason="requests not installed")
    def test_authentik_proxy_response_time(self, service_config: Dict[str, str]):
        """Verify Authentik proxy responds within acceptable time."""
        try:
            start = time.time()
            response = requests.get(
                f"{service_config['authentik_proxy']}/health",
                timeout=5
            )
            elapsed_ms = (time.time() - start) * 1000

            # Accept 200, 401, or 302 (auth redirect)
            assert response.status_code in [200, 401, 302]
            assert elapsed_ms < 5000, f"Response took {elapsed_ms:.2f}ms"
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Authentik proxy not available: {e}")


def check_services_health(config: Dict[str, str], timeout_ms: int = 5000) -> Dict[str, Any]:
    """
    Run comprehensive services health check.

    Args:
        config: Service endpoint configuration
        timeout_ms: Max acceptable latency in milliseconds

    Returns:
        Health check result with status, latency, and details
    """
    start = time.time()
    result = {
        "status": "pass",
        "latency_ms": 0,
        "details": {
            "total_services": 0,
            "healthy_services": 0,
            "degraded_services": 0,
            "unhealthy_services": 0,
            "services": []
        }
    }

    services = [
        ("authentik_proxy", config.get("authentik_proxy", "http://localhost:9000")),
        ("moltbot", config.get("moltbot", "http://localhost:18789")),
        ("neo4j_http", config.get("neo4j", "http://localhost:7474").replace("bolt://", "http://").replace(":7687", ":7474")),
    ]

    for name, url in services:
        result["details"]["total_services"] += 1
        service_result = {
            "name": name,
            "url": url,
            "status": "unknown",
            "latency_ms": 0,
            "error": None
        }

        if HAS_REQUESTS:
            try:
                service_start = time.time()
                response = requests.get(f"{url}/health", timeout=5)
                service_latency_ms = (time.time() - service_start) * 1000

                service_result["latency_ms"] = round(service_latency_ms, 2)

                if response.status_code == 200:
                    service_result["status"] = "healthy"
                    result["details"]["healthy_services"] += 1
                elif response.status_code in [401, 302]:
                    # Service is up but requires auth - consider healthy
                    service_result["status"] = "healthy"
                    result["details"]["healthy_services"] += 1
                else:
                    service_result["status"] = "degraded"
                    result["details"]["degraded_services"] += 1

            except requests.exceptions.Timeout:
                service_result["status"] = "timeout"
                service_result["error"] = "Request timed out"
                result["details"]["unhealthy_services"] += 1
            except requests.exceptions.ConnectionError:
                service_result["status"] = "unreachable"
                service_result["error"] = "Connection refused"
                result["details"]["unhealthy_services"] += 1
            except Exception as e:
                service_result["status"] = "error"
                service_result["error"] = str(e)
                result["details"]["unhealthy_services"] += 1
        else:
            service_result["status"] = "skip"
            service_result["error"] = "requests library not installed"

        result["details"]["services"].append(service_result)

    # Determine overall status
    unhealthy = result["details"]["unhealthy_services"]
    total = result["details"]["total_services"]

    if unhealthy == 0:
        result["status"] = "pass"
    elif unhealthy < total:
        result["status"] = "warn"
    else:
        result["status"] = "fail"

    result["latency_ms"] = round((time.time() - start) * 1000)
    return result


@pytest.mark.health
@pytest.mark.services
def test_services_health_check_function(service_config: Dict[str, str]):
    """Test the health check function itself."""
    result = check_services_health(service_config)

    assert "status" in result
    assert "latency_ms" in result
    assert "details" in result
    assert "total_services" in result["details"]
    assert "services" in result["details"]
