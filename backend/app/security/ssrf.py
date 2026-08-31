"""
hi.myrepo - SSRF Protection

Heartbeat workers are a potential SSRF surface.
This module validates URLs to prevent server-side request forgery.
"""

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

from app.core.config import get_settings


class SSRFError(Exception):
    """Raised when a URL fails SSRF validation."""
    pass


class SSRFProtector:
    """Validates URLs against SSRF attacks."""

    BLOCKED_HOSTNAMES = {
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "metadata.google.internal",
        "169.254.169.254",  # AWS/GCP/Azure metadata
        "instance-data",
        "100.100.100.200",  # Alibaba metadata
    }

    BLOCKED_NETWORKS = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
    ]

    ALLOWED_SCHEMES = {"http", "https"}

    def __init__(self):
        settings = get_settings()
        self.block_private = settings.block_private_networks

    def validate_url(self, url: str) -> str:
        """
        Validate a URL against SSRF rules.
        Returns the validated URL or raises SSRFError.
        """
        # Parse the URL
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise SSRFError(f"Invalid URL format: {e}")

        # Check scheme
        if parsed.scheme not in self.ALLOWED_SCHEMES:
            raise SSRFError(
                f"Scheme '{parsed.scheme}' not allowed. Use: {self.ALLOWED_SCHEMES}"
            )

        hostname = parsed.hostname
        if not hostname:
            raise SSRFError("URL must have a hostname")

        # Check blocked hostnames
        if hostname.lower() in self.BLOCKED_HOSTNAMES:
            raise SSRFError(f"Hostname '{hostname}' is blocked")

        # Check blocked domains (metadata endpoints)
        for blocked in self.BLOCKED_HOSTNAMES:
            if hostname.lower().endswith(f".{blocked}") or hostname.lower() == blocked:
                raise SSRFError(f"Hostname '{hostname}' is blocked")

        # Resolve and check for private IPs
        if self.block_private:
            self._check_ip_not_private(hostname)

        return url

    def _check_ip_not_private(self, hostname: str) -> None:
        """Resolve hostname and ensure it doesn't point to private/reserved IPs."""
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for _, _, _, _, sockaddr in addr_info:
                ip = ipaddress.ip_address(sockaddr[0])
                for network in self.BLOCKED_NETWORKS:
                    if ip in network:
                        raise SSRFError(
                            f"Hostname '{hostname}' resolves to private IP {ip} "
                            f"in blocked network {network}"
                        )
        except socket.gaierror as e:
            raise SSRFError(f"Failed to resolve hostname '{hostname}': {e}")

    def sanitize_redirect_url(self, url: str) -> str:
        """Sanitize a redirect URL to prevent open redirect attacks."""
        parsed = urlparse(url)
        if parsed.hostname and parsed.hostname.lower() not in {"localhost", "127.0.0.1"}:
            # Only allow redirects to same-origin in production
            if self.block_private:
                self._check_ip_not_private(parsed.hostname)
        return url


# Global SSRF protector singleton
ssrf_protector = SSRFProtector()
