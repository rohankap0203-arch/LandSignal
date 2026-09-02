"""Resolve the authenticated LandSignal user for API requests.

The Next.js BFF (`/v1/[...path]`) attaches `X-LandSignal-User-Id` from the
Auth.js session. Anonymous callers have no personal Land Alerts / watchlist
data; mutations that require an account return 401.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Header, HTTPException, Request

DEMO_USER_ID = UUID("00000000-0000-4000-8000-000000000002")
USER_HEADER = "x-landsignal-user-id"


def parse_user_id(raw: str | None) -> UUID | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return UUID(text)
    except ValueError:
        return None


def user_id_from_request(request: Request) -> UUID | None:
    return parse_user_id(request.headers.get(USER_HEADER))


def optional_user_id(
    x_landsignal_user_id: str | None = Header(default=None, alias="X-LandSignal-User-Id"),
) -> UUID | None:
    """Signed-in user id, or None for anonymous browse."""
    return parse_user_id(x_landsignal_user_id)


def current_user_id(
    x_landsignal_user_id: str | None = Header(default=None, alias="X-LandSignal-User-Id"),
) -> UUID:
    """FastAPI dependency — signed-in user when present, else demo sandbox."""
    return parse_user_id(x_landsignal_user_id) or DEMO_USER_ID


def require_user_id(
    x_landsignal_user_id: str | None = Header(default=None, alias="X-LandSignal-User-Id"),
) -> UUID:
    """FastAPI dependency — mutations that must belong to a real account."""
    uid = parse_user_id(x_landsignal_user_id)
    if not uid:
        raise HTTPException(
            status_code=401,
            detail="Sign in to save Land Alerts and watchlists to your account.",
        )
    return uid
