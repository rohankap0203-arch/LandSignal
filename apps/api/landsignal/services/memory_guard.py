"""Process memory guard — keep LandSignal from OOM-killing the cloud VM.

Cloud agent VMs are typically ~15Gi with no swap. A nationwide discover that
scores + enriches every parcel used to climb past 10Gi RSS and get the process
(and sometimes the whole environment) killed — which surfaces as
"execution environment has become unreachable" / API not reachable.

This module is the single choke point: discover / persist / startup must stop
or thin out work before we cross the hard RSS ceiling.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import structlog

log = structlog.get_logger()

# Leave headroom for Next.js (~0.5–1Gi), the agent runtime, and OS page cache.
_DEFAULT_HARD_RSS_MB = 7_500
_DEFAULT_SOFT_RSS_MB = 6_000
_DEFAULT_MIN_AVAILABLE_MB = 1_200


@lru_cache(maxsize=1)
def _page_size() -> int:
    try:
        return os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return 4096


def rss_bytes() -> int:
    """Current process RSS in bytes (Linux /proc). Returns 0 if unavailable."""
    try:
        with open("/proc/self/statm", encoding="utf-8") as f:
            parts = f.read().split()
        # statm[1] = resident pages
        return int(parts[1]) * _page_size()
    except Exception:
        return 0


def available_bytes() -> int:
    """Approx MemAvailable from /proc/meminfo."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    return 0


def hard_rss_limit_bytes() -> int:
    mb = int(os.environ.get("LANDSIGNAL_HARD_RSS_MB", _DEFAULT_HARD_RSS_MB) or _DEFAULT_HARD_RSS_MB)
    return max(2_000, mb) * 1024 * 1024


def soft_rss_limit_bytes() -> int:
    mb = int(os.environ.get("LANDSIGNAL_SOFT_RSS_MB", _DEFAULT_SOFT_RSS_MB) or _DEFAULT_SOFT_RSS_MB)
    return max(1_500, mb) * 1024 * 1024


def min_available_bytes() -> int:
    mb = int(
        os.environ.get("LANDSIGNAL_MIN_AVAILABLE_MB", _DEFAULT_MIN_AVAILABLE_MB)
        or _DEFAULT_MIN_AVAILABLE_MB
    )
    return max(256, mb) * 1024 * 1024


def snapshot() -> dict[str, Any]:
    rss = rss_bytes()
    avail = available_bytes()
    hard = hard_rss_limit_bytes()
    soft = soft_rss_limit_bytes()
    return {
        "rss_mb": round(rss / (1024 * 1024), 1),
        "available_mb": round(avail / (1024 * 1024), 1) if avail else None,
        "hard_rss_mb": round(hard / (1024 * 1024), 1),
        "soft_rss_mb": round(soft / (1024 * 1024), 1),
        "over_soft": rss >= soft if rss else False,
        "over_hard": rss >= hard if rss else False,
        "low_available": bool(avail and avail < min_available_bytes()),
    }


def should_stop_heavy_work() -> tuple[bool, str]:
    """Return (stop, reason) when discover/rescore must pause to protect the VM."""
    snap = snapshot()
    if snap["over_hard"]:
        return True, f"RSS {snap['rss_mb']}MB >= hard limit {snap['hard_rss_mb']}MB"
    if snap["low_available"]:
        return True, f"MemAvailable {snap['available_mb']}MB below floor"
    return False, ""


def should_throttle() -> bool:
    snap = snapshot()
    return bool(snap["over_soft"] or snap["low_available"])


# Keys safe to keep on listing.raw at nationwide scale. Everything else
# (full GIS attribute dumps) is the #1 memory amplifier after polygons.
_RAW_KEEP = {
    "provider_id",
    "external_id",
    "source_id",
    "source_url",
    "source_name",
    "title",
    "description",
    "state",
    "county",
    "apn",
    "address",
    "acreage",
    "asking_price_usd",
    "assessed_land_usd",
    "assessed_total_usd",
    "latitude",
    "longitude",
    "days_on_market",
    "market_channel",
    "sale_type",
    "owner_name",
    "zoning",
    "land_use",
    "bldg_no",
    "parcel_id",
    "blm_serial",
    "case_id",
    "ask_role",
    "price_role",
    "contact_phone",
    "contact_website",
    "links",
}


def slim_listing_raw(raw: dict[str, Any] | None, *, max_desc: int = 280) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for k in _RAW_KEEP:
        if k not in raw:
            continue
        v = raw[k]
        if v is None:
            continue
        if k == "description" and isinstance(v, str) and len(v) > max_desc:
            out[k] = v[: max_desc - 1].rstrip() + "…"
        elif k == "title" and isinstance(v, str) and len(v) > 160:
            out[k] = v[:159].rstrip() + "…"
        elif k == "links" and isinstance(v, list):
            out[k] = v[:8]
        elif isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, dict) and len(v) <= 12:
            # Tiny nested maps only (e.g. contact blobs)
            out[k] = {
                sk: sv
                for sk, sv in list(v.items())[:12]
                if isinstance(sv, (str, int, float, bool)) or sv is None
            }
    return out


def trim_score_lists(store: Any, *, keep: int = 1) -> int:
    """Drop older score versions in-place. Returns number of score rows removed."""
    removed = 0
    scores = getattr(store, "scores", None)
    if not isinstance(scores, dict):
        return 0
    for pid, rows in list(scores.items()):
        if not isinstance(rows, list) or len(rows) <= keep:
            continue
        removed += len(rows) - keep
        scores[pid] = rows[-keep:]
    return removed
