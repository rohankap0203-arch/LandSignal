from uuid import UUID

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from landsignal.auth_user import (
    DEMO_USER_ID,
    current_user_id,
    optional_user_id,
    parse_user_id,
    require_user_id,
    user_id_from_request,
)


def test_parse_user_id_accepts_uuid():
    uid = UUID("11111111-1111-4111-8111-111111111111")
    assert parse_user_id(str(uid)) == uid
    assert parse_user_id(" not-a-uuid ") is None
    assert parse_user_id(None) is None


def test_current_user_falls_back_to_demo():
    assert current_user_id(None) == DEMO_USER_ID
    assert current_user_id("bogus") == DEMO_USER_ID


def test_optional_user_none_when_anonymous():
    assert optional_user_id(None) is None
    assert optional_user_id("bogus") is None


def test_current_user_uses_header():
    uid = UUID("22222222-2222-4222-8222-222222222222")
    assert current_user_id(str(uid)) == uid
    assert optional_user_id(str(uid)) == uid


def test_require_user_rejects_anonymous():
    with pytest.raises(HTTPException) as exc:
        require_user_id(None)
    assert exc.value.status_code == 401


def test_require_user_accepts_uuid():
    uid = UUID("33333333-3333-4333-8333-333333333333")
    assert require_user_id(str(uid)) == uid


def test_user_id_from_request_header():
    uid = UUID("44444444-4444-4444-8444-444444444444")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [(b"x-landsignal-user-id", str(uid).encode())],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    request = Request(scope)
    assert user_id_from_request(request) == uid
