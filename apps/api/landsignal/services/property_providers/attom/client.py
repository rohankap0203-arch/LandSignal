"""Secure ATTOM HTTP client — server-side only. Never log the API key."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from landsignal.services.property_providers import IntelligenceProviderState, ProviderResult
from landsignal.services.property_providers.cache import AttomResponseCache, CircuitBreaker

log = structlog.get_logger()

ATTOM_GATEWAY = "https://api.gateway.attomdata.com"
ATTOM_PROPERTY_BASE = f"{ATTOM_GATEWAY}/propertyapi/v1.0.0"


def _safe_error_message(status_code: int, body: str) -> str:
    """User/ops-safe message — never echo API keys or raw entitlement dumps."""
    lower = (body or "").lower()
    if status_code in (401, 403):
        if "trial" in lower or "expired" in lower:
            return "ATTOM trial or entitlement expired"
        return "ATTOM authentication failed"
    if status_code == 429:
        return "ATTOM rate limited"
    if status_code in (402, 413) or "quota" in lower:
        return "ATTOM quota exceeded"
    if status_code >= 500:
        return "ATTOM upstream unavailable"
    return f"ATTOM request failed ({status_code})"


def _classify_http(status_code: int, body: str) -> IntelligenceProviderState:
    lower = (body or "").lower()
    if status_code in (401, 403):
        if "trial" in lower or "expired" in lower:
            return IntelligenceProviderState.TRIAL_EXPIRED
        return IntelligenceProviderState.AUTH_ERROR
    if status_code == 429:
        return IntelligenceProviderState.RATE_LIMITED
    if "quota" in lower or status_code == 402:
        return IntelligenceProviderState.QUOTA_EXCEEDED
    return IntelligenceProviderState.UNAVAILABLE


class AttomClient:
    def __init__(
        self,
        api_key: str | None,
        *,
        timeout: float = 20.0,
        cache: AttomResponseCache | None = None,
        breaker: CircuitBreaker | None = None,
        data_mode: str = "api",
    ):
        self._api_key = (api_key or "").strip() or None
        self.timeout = timeout
        self.cache = cache or AttomResponseCache()
        self.breaker = breaker or CircuitBreaker()
        self.data_mode = (data_mode or "api").lower()
        self.requests = 0
        self.successes = 0
        self.failures = 0
        self.rate_limits = 0
        self.total_latency_ms = 0.0

    @property
    def configured(self) -> bool:
        return bool(self._api_key) and self.data_mode != "disabled"

    def health_state(self) -> IntelligenceProviderState:
        if self.data_mode == "disabled":
            return IntelligenceProviderState.DISABLED
        if not self._api_key:
            return IntelligenceProviderState.NOT_CONFIGURED
        snap = self.breaker.snapshot()
        if snap["open"]:
            return IntelligenceProviderState(snap["state"])
        return IntelligenceProviderState.AVAILABLE

    async def get(
        self,
        resource_path: str,
        params: dict[str, Any] | None = None,
        *,
        use_cache: bool = True,
    ) -> ProviderResult[dict[str, Any]]:
        if self.data_mode == "disabled":
            return ProviderResult(False, IntelligenceProviderState.DISABLED, error="ATTOM disabled")
        if not self._api_key:
            return ProviderResult(False, IntelligenceProviderState.NOT_CONFIGURED, error="ATTOM_API_KEY not set")
        if not self.breaker.allow_request():
            return ProviderResult(
                False,
                IntelligenceProviderState(self.breaker.snapshot()["state"]),
                error="ATTOM circuit open — using non-ATTOM sources",
            )

        path = resource_path if resource_path.startswith("/") else f"/{resource_path}"
        # Normalize to propertyapi path
        if not path.startswith("/propertyapi"):
            path = f"/propertyapi/v1.0.0{path}"

        clean_params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        if use_cache:
            cached = self.cache.get("GET", path, clean_params)
            if cached is not None:
                return ProviderResult(True, IntelligenceProviderState.AVAILABLE, data=cached, meta={"cache": "hit"})

        url = f"{ATTOM_GATEWAY}{path}"
        if clean_params:
            url = f"{url}?{urlencode(clean_params, doseq=True)}"

        headers = {
            "accept": "application/json",
            "apikey": self._api_key,
        }
        started = time.perf_counter()
        self.requests += 1
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=headers)
            latency = (time.perf_counter() - started) * 1000
            self.total_latency_ms += latency
            body_text = resp.text or ""
            if resp.status_code == 429:
                self.rate_limits += 1
            if resp.status_code >= 400:
                self.failures += 1
                state = _classify_http(resp.status_code, body_text)
                msg = _safe_error_message(resp.status_code, body_text)
                self.breaker.record_failure(state, msg)
                # Never log headers / key / full bodies
                log.warning("attom_http_error", status=resp.status_code, path=path, state=state.value)
                return ProviderResult(False, state, error=msg, meta={"latency_ms": latency})

            try:
                payload = resp.json()
            except Exception:
                self.failures += 1
                self.breaker.record_failure(IntelligenceProviderState.UNAVAILABLE, "malformed ATTOM response")
                return ProviderResult(
                    False,
                    IntelligenceProviderState.UNAVAILABLE,
                    error="malformed ATTOM response",
                )

            status = payload.get("status") or {}
            code = status.get("code")
            # ATTOM sometimes returns HTTP 200 with status.code != 0
            if code not in (0, "0", None) and status.get("msg") not in (
                "SuccessWithResult",
                "SuccessWithoutResult",
                "SuccessWithWarning",
            ):
                msg = _safe_error_message(400, str(status.get("msg") or ""))
                self.failures += 1
                state = IntelligenceProviderState.UNAVAILABLE
                self.breaker.record_failure(state, msg)
                return ProviderResult(False, state, error=msg)

            self.successes += 1
            self.breaker.record_success()
            if use_cache:
                self.cache.set("GET", path, clean_params, payload)
            return ProviderResult(
                True,
                IntelligenceProviderState.AVAILABLE,
                data=payload,
                meta={"latency_ms": latency, "cache": "miss"},
            )
        except httpx.TimeoutException:
            self.failures += 1
            self.breaker.record_failure(IntelligenceProviderState.UNAVAILABLE, "ATTOM timeout")
            log.warning("attom_timeout", path=path)
            return ProviderResult(False, IntelligenceProviderState.UNAVAILABLE, error="ATTOM timeout")
        except Exception as exc:  # noqa: BLE001
            self.failures += 1
            self.breaker.record_failure(IntelligenceProviderState.UNAVAILABLE, "ATTOM upstream error")
            log.warning("attom_request_failed", path=path, error_type=type(exc).__name__)
            return ProviderResult(False, IntelligenceProviderState.UNAVAILABLE, error="ATTOM upstream error")

    def stats(self) -> dict[str, Any]:
        avg = (self.total_latency_ms / self.successes) if self.successes else None
        return {
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "rate_limits_429": self.rate_limits,
            "avg_latency_ms": avg,
            "cache": self.cache.stats(),
            "circuit": self.breaker.snapshot(),
            "data_mode": self.data_mode,
            "configured": self.configured,
            # Never include the key
        }
