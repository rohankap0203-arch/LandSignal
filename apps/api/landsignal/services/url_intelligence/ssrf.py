"""SSRF and URL validation for user-pasted listing URLs."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse, urlunparse

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".intranet", ".corp")
_MAX_URL_LEN = 2000


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (ip.version == 4 and ip in ipaddress.ip_network("169.254.0.0/16"))
        or (ip.version == 6 and ip in ipaddress.ip_network("fc00::/7"))
    )


def validate_listing_url(url: str) -> dict[str, Any]:
    """Validate URL shape and block private/metadata targets.

    Returns {ok, error?, canonical_url?, domain?, parsed?}
    """
    raw = (url or "").strip()
    if not raw or len(raw) > _MAX_URL_LEN:
        return {"ok": False, "error": "Enter a full http(s) listing URL."}
    if raw.lower().startswith("file:"):
        return {"ok": False, "error": "File URLs are not allowed."}

    parsed = urlparse(raw)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES or not parsed.netloc:
        return {"ok": False, "error": "Enter a full http(s) listing URL."}

    host = (parsed.hostname or "").lower().strip(".")
    if not host:
        return {"ok": False, "error": "Enter a full http(s) listing URL."}
    if host in _BLOCKED_HOSTNAMES or any(host.endswith(s) for s in _BLOCKED_SUFFIXES):
        return {"ok": False, "error": "That URL cannot be fetched for security reasons."}
    if host.endswith(".nip.io") or host.endswith(".sslip.io"):
        return {"ok": False, "error": "That URL cannot be fetched for security reasons."}

    # Literal IP in hostname
    try:
        ip = ipaddress.ip_address(host)
        if _is_blocked_ip(ip):
            return {"ok": False, "error": "That URL cannot be fetched for security reasons."}
    except ValueError:
        # Resolve DNS and reject private answers (best-effort)
        try:
            infos = socket.getaddrinfo(host, None)
            for info in infos:
                addr = info[4][0]
                try:
                    if _is_blocked_ip(ipaddress.ip_address(addr)):
                        return {
                            "ok": False,
                            "error": "That URL cannot be fetched for security reasons.",
                        }
                except ValueError:
                    continue
        except OSError:
            # Unresolvable — still allow; fetch layer will fail gracefully
            pass

    # Strip fragments; keep query (listing IDs often live there)
    canonical = urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.params, parsed.query, "")
    )
    # Likely real-estate listing heuristic (soft — never hard-block)
    path_l = (parsed.path or "").lower()
    listing_hints = (
        "property",
        "listing",
        "land",
        "acre",
        "lot",
        "parcel",
        "homedetails",
        "realestate",
        "forsale",
        "for-sale",
        "auction",
    )
    likely_listing = any(h in path_l or h in host for h in listing_hints) or bool(parsed.query)

    return {
        "ok": True,
        "error": None,
        "canonical_url": canonical,
        "domain": host,
        "scheme": parsed.scheme.lower(),
        "likely_listing": likely_listing,
        "parsed": parsed,
    }
