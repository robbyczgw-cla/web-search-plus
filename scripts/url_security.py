"""Outbound URL validation (SSRF guard) for user-supplied URLs.

Mirrors the SearXNG SSRF guard used across the Web Search Plus family: only
http/https schemes are allowed, cloud metadata endpoints are always blocked,
and hostnames that resolve to private/loopback/link-local/reserved addresses
are rejected unless the operator explicitly opts in for trusted private
networks (``WSP_ALLOW_PRIVATE_URLS=1`` or an explicit ``--allow-private-urls``
flag).
"""

import ipaddress
import os
import socket
from urllib.parse import urlparse

ALLOW_PRIVATE_ENV = "WSP_ALLOW_PRIVATE_URLS"

# Cloud metadata endpoints are blocked even when private URLs are allowed.
BLOCKED_METADATA_HOSTS = {
    "169.254.169.254",        # AWS/GCP/Azure metadata
    "metadata.google.internal",
    "metadata.internal",
}


def private_urls_allowed() -> bool:
    """True when the operator opted in to private/internal targets via env."""
    return os.environ.get(ALLOW_PRIVATE_ENV, "").strip() == "1"


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


def validate_outbound_url(url: str, allow_private: bool = False, label: str = "URL") -> str:
    """Validate a user-supplied URL before it is fetched or forwarded.

    Returns the URL unchanged when safe; raises ValueError otherwise.
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"{label} blocked: scheme must be http or https, got {parsed.scheme or 'none'!r}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"{label} blocked: missing hostname")

    if hostname.lower() in BLOCKED_METADATA_HOSTS:
        raise ValueError(f"{label} blocked: {hostname} is a cloud metadata endpoint")

    if allow_private or private_urls_allowed():
        return url

    try:
        candidates = [ipaddress.ip_address(hostname)]
    except ValueError:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            resolved = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            raise ValueError(f"{label} blocked: cannot resolve hostname {hostname}")
        candidates = []
        for _family, _type, _proto, _canonname, sockaddr in resolved:
            try:
                candidates.append(ipaddress.ip_address(sockaddr[0]))
            except ValueError:
                continue

    for ip in candidates:
        if _is_blocked_ip(ip):
            raise ValueError(
                f"{label} blocked: {hostname} resolves to private/internal IP {ip}. "
                f"If this is intentional (trusted private network), set {ALLOW_PRIVATE_ENV}=1 "
                f"or pass --allow-private-urls."
            )

    return url
