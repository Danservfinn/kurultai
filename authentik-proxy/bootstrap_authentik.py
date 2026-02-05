#!/usr/bin/env python3
"""
Authentik Bootstrap and Configuration Script

This script configures Authentik resources via the API instead of direct DB access.
It is idempotent and can be run multiple times safely.

Environment Variables Required:
- AUTHENTIK_URL: Internal Authentik URL (e.g., http://authentik-server:9000)
- AUTHENTIK_BOOTSTRAP_TOKEN: Bootstrap token for API access (created on first run)
- AUTHENTIK_BOOTSTRAP_PASSWORD: Initial admin password (only used on first setup)
"""

import os
import sys
import time
import json
import logging
from typing import Optional, Dict, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AuthentikAPI:
    """Client for Authentik API with retry logic and error handling."""

    def __init__(self, base_url: str, token: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.session = requests.Session()

        # Configure retries for resilience
        retry_strategy = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "PATCH"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def wait_for_ready(self, timeout: int = 300) -> bool:
        """Wait for Authentik to be ready."""
        logger.info(f"Waiting for Authentik at {self.base_url}...")
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = self.session.get(
                    f"{self.base_url}/-/health/ready/",
                    timeout=5
                )
                if resp.status_code == 200:
                    logger.info("Authentik is ready!")
                    return True
            except requests.exceptions.RequestException:
                pass
            time.sleep(5)
        logger.error("Timeout waiting for Authentik")
        return False

    def get_or_create_token(self, bootstrap_password: str) -> Optional[str]:
        """Get or create API token using bootstrap password."""
        # First, try to authenticate and get a token
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v3/core/users/me/token/set/",
                headers={"Content-Type": "application/json"},
                json={"password": bootstrap_password},
                timeout=30
            )
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("token")
                if token:
                    logger.info("Successfully obtained API token")
                    self.token = token
                    return token
        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not get token via password: {e}")

        # Alternative: check if token is already in environment
        env_token = os.environ.get("AUTHENTIK_API_TOKEN")
        if env_token:
            self.token = env_token
            return env_token

        return None

    def get_flow(self, name: str) -> Optional[Dict[str, Any]]:
        """Get flow by name."""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/v3/flows/instances/",
                headers=self._headers(),
                params={"search": name},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            for flow in data.get("results", []):
                if flow.get("name") == name:
                    return flow
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting flow: {e}")
        return None

    def create_flow(self, slug: str, name: str, designation: str) -> Optional[Dict[str, Any]]:
        """Create a new flow."""
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v3/flows/instances/",
                headers=self._headers(),
                json={
                    "slug": slug,
                    "name": name,
                    "designation": designation,
                    "authentication": "require_authenticated",
                    "layout": "stacked"
                },
                timeout=30
            )
            if resp.status_code == 201:
                logger.info(f"Created flow: {name}")
                return resp.json()
            elif resp.status_code == 400 and "already exists" in resp.text:
                logger.info(f"Flow already exists: {name}")
                return self.get_flow(name)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating flow: {e}")
        return None

    def get_provider(self, name: str) -> Optional[Dict[str, Any]]:
        """Get proxy provider by name."""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/v3/providers/proxy/",
                headers=self._headers(),
                params={"search": name},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            for provider in data.get("results", []):
                if provider.get("name") == name:
                    return provider
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting provider: {e}")
        return None

    def create_proxy_provider(
        self,
        name: str,
        external_host: str,
        internal_host: str,
        flow: str
    ) -> Optional[Dict[str, Any]]:
        """Create a proxy provider."""
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v3/providers/proxy/",
                headers=self._headers(),
                json={
                    "name": name,
                    "external_host": external_host,
                    "internal_host": internal_host,
                    "authorization_flow": flow,
                    "mode": "forward_domain"
                },
                timeout=30
            )
            if resp.status_code == 201:
                logger.info(f"Created proxy provider: {name}")
                return resp.json()
            elif resp.status_code == 400 and "already exists" in resp.text:
                logger.info(f"Provider already exists: {name}")
                return self.get_provider(name)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating provider: {e}")
        return None

    def get_application(self, slug: str) -> Optional[Dict[str, Any]]:
        """Get application by slug."""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/v3/core/applications/",
                headers=self._headers(),
                params={"slug": slug},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            for app in data.get("results", []):
                if app.get("slug") == slug:
                    return app
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting application: {e}")
        return None

    def create_application(
        self,
        slug: str,
        name: str,
        provider_id: str
    ) -> Optional[Dict[str, Any]]:
        """Create an application."""
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v3/core/applications/",
                headers=self._headers(),
                json={
                    "slug": slug,
                    "name": name,
                    "provider": provider_id,
                    "meta_launch_url": ""
                },
                timeout=30
            )
            if resp.status_code == 201:
                logger.info(f"Created application: {name}")
                return resp.json()
            elif resp.status_code == 400 and "already exists" in resp.text:
                logger.info(f"Application already exists: {name}")
                return self.get_application(slug)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating application: {e}")
        return None

    def get_outpost(self, name: str = "authentik Embedded Outpost") -> Optional[Dict[str, Any]]:
        """Get embedded outpost."""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/v3/outposts/instances/",
                headers=self._headers(),
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            for outpost in data.get("results", []):
                if outpost.get("name") == name:
                    return outpost
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting outpost: {e}")
        return None

    def update_outpost_providers(self, outpost_id: str, provider_ids: list) -> bool:
        """Update outpost with providers."""
        try:
            resp = self.session.patch(
                f"{self.base_url}/api/v3/outposts/instances/{outpost_id}/",
                headers=self._headers(),
                json={"providers": provider_ids},
                timeout=30
            )
            if resp.status_code in [200, 201, 204]:
                logger.info("Updated outpost providers")
                return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating outpost: {e}")
        return False

    def configure_rate_limits(self) -> bool:
        """Configure rate limiting policies."""
        # Note: Rate limiting in Authentik is typically done via policies
        # This is a placeholder for future implementation
        logger.info("Rate limiting should be configured via Authentik UI:")
        logger.info("  1. Go to Customization > Policies")
        logger.info("  2. Create Reputation Policy for login endpoints")
        logger.info("  3. Set thresholds: 5 attempts per IP per minute")
        return True


def main():
    """Main bootstrap function."""
    authentik_url = os.environ.get("AUTHENTIK_URL", "http://authentik-server:9000")
    bootstrap_password = os.environ.get("AUTHENTIK_BOOTSTRAP_PASSWORD")
    external_host = os.environ.get("AUTHENTIK_EXTERNAL_HOST", "https://kublai.kurult.ai")
    internal_host = os.environ.get("AUTHENTIK_INTERNAL_HOST", "http://moltbot:8080")

    if not bootstrap_password:
        logger.error("AUTHENTIK_BOOTSTRAP_PASSWORD environment variable is required")
        sys.exit(1)

    api = AuthentikAPI(authentik_url)

    # Wait for Authentik to be ready
    if not api.wait_for_ready(timeout=300):
        logger.error("Authentik did not become ready in time")
        sys.exit(1)

    # Get API token
    token = api.get_or_create_token(bootstrap_password)
    if not token:
        logger.error("Could not obtain API token")
        sys.exit(1)

    # Update API client with token
    api = AuthentikAPI(authentik_url, token)

    # Wait a bit for services to fully initialize
    time.sleep(5)

    # Create or get WebAuthn authentication flow
    logger.info("Setting up WebAuthn authentication flow...")
    auth_flow = api.create_flow(
        slug="kublai-webauthn-auth",
        name="Kublai WebAuthn Authentication",
        designation="authentication"
    )

    if not auth_flow:
        logger.error("Failed to create authentication flow")
        sys.exit(1)

    # Create proxy provider
    logger.info("Setting up proxy provider...")
    provider = api.create_proxy_provider(
        name="Kublai Proxy Provider",
        external_host=external_host,
        internal_host=internal_host,
        flow=auth_flow.get("pk")
    )

    if not provider:
        logger.error("Failed to create proxy provider")
        sys.exit(1)

    # Create application
    logger.info("Setting up application...")
    application = api.create_application(
        slug="kublai-control-ui",
        name="Kublai Control UI",
        provider_id=provider.get("pk")
    )

    if not application:
        logger.error("Failed to create application")
        sys.exit(1)

    # Update embedded outpost with provider
    logger.info("Configuring embedded outpost...")
    outpost = api.get_outpost()
    if outpost:
        current_providers = [p.get("pk") for p in outpost.get("providers", [])]
        if provider.get("pk") not in current_providers:
            current_providers.append(provider.get("pk"))
            api.update_outpost_providers(outpost.get("pk"), current_providers)
    else:
        logger.warning("Could not find embedded outpost - may need manual configuration")

    # Configure rate limits
    api.configure_rate_limits()

    logger.info("=" * 60)
    logger.info("Authentik bootstrap complete!")
    logger.info(f"Application: {application.get('name')}")
    logger.info(f"External Host: {external_host}")
    logger.info(f"Internal Host: {internal_host}")
    logger.info("=" * 60)
    logger.info("\nNext steps:")
    logger.info("1. Access Authentik admin at: {}/if/admin/".format(external_host))
    logger.info("2. Log in with akadmin / AUTHENTIK_BOOTSTRAP_PASSWORD")
    logger.info("3. Configure WebAuthn in the authentication flow")
    logger.info("4. Test biometric authentication")


if __name__ == "__main__":
    main()
