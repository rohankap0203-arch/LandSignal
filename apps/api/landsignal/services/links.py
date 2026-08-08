from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

log = structlog.get_logger()

# In-memory cache: url -> {ok, checked}
_LINK_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = asyncio.Lock()


async def validate_url(url: str, timeout: float = 3.5) -> dict[str, Any]:
    if not url:
        return {"url": url, "ok": False, "reason": "missing", "status_code": None}
    async with _CACHE_LOCK:
        cached = _LINK_CACHE.get(url)
        if cached:
            return cached
    ok = False
    reason = "unreachable"
    status_code = None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = None
            try:
                head = await client.head(url)
                # Many agency sites reject HEAD — fall through to GET
                if head.status_code in (405, 501) or head.status_code >= 400:
                    resp = await client.get(url)
                else:
                    resp = head
            except Exception:
                resp = await client.get(url)
            status_code = resp.status_code
            # Treat soft errors / HTML "not available" pages as dead
            text_sample = ""
            ctype = (resp.headers.get("content-type") or "").lower()
            if status_code >= 400:
                ok = False
                reason = f"http_{status_code}"
            else:
                if "text/html" in ctype or status_code == 200:
                    # Prefer a small GET body sample when HEAD skipped body
                    if not getattr(resp, "text", None) or len(resp.text or "") < 40:
                        try:
                            get_resp = await client.get(url)
                            resp = get_resp
                            status_code = get_resp.status_code
                            ctype = (resp.headers.get("content-type") or "").lower()
                        except Exception:
                            pass
                    try:
                        text_sample = (resp.text or "")[:3500].lower()
                    except Exception:
                        text_sample = ""
                    dead_markers = [
                        "not currently available",
                        "page not found",
                        "document not found",
                        "document is not currently available",
                        "no longer available",
                        "this page isn't available",
                        "we can't find that page",
                    ]
                    if status_code >= 400:
                        ok = False
                        reason = f"http_{status_code}"
                    elif any(m in text_sample for m in dead_markers):
                        ok = False
                        reason = "content_unavailable"
                    else:
                        ok = True
                        reason = "ok"
                else:
                    ok = True
                    reason = "ok"
    except Exception as exc:  # noqa: BLE001
        ok = False
        reason = str(exc)[:120]
        log.info("link_validate_failed", url=url, error=reason)
    result = {"url": url, "ok": ok, "reason": reason, "status_code": status_code}
    async with _CACHE_LOCK:
        _LINK_CACHE[url] = result
    return result


async def annotate_links(links: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not links:
        return []
    results = await asyncio.gather(*[validate_url(l["url"]) for l in links])
    out = []
    for link, check in zip(links, results):
        out.append(
            {
                **link,
                "available": bool(check["ok"]),
                "availability_reason": check["reason"],
                "status_code": check.get("status_code"),
            }
        )
    # Prefer available primary; if primary dead, promote next available non-map or keep grayed
    return out
