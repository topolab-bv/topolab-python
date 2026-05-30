"""Typed error hierarchy mapped from API responses (status + body)."""
from __future__ import annotations
import re
from typing import Any

_ADDON_RE = re.compile(r"requires the (\w+) add-?on", re.IGNORECASE)


class TopolabError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None,
                 request_id: str | None = None, body: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id
        self.body = body


class ConnectionError(TopolabError): ...
class AuthenticationError(TopolabError): ...
class ConfigurationError(TopolabError): ...
class NotFoundError(TopolabError): ...
class ValidationError(TopolabError): ...
class ServerError(TopolabError): ...


class AddonRequiredError(TopolabError):
    def __init__(self, message: str, *, addon: str | None = None, **kw):
        super().__init__(message, **kw)
        self.addon = addon


class AccessDeniedError(TopolabError): ...


class InsufficientCreditsError(TopolabError):
    def __init__(self, message: str, *, required: int | None = None,
                 available: int | None = None, **kw):
        super().__init__(message, **kw)
        self.required = required
        self.available = available


class RateLimitError(TopolabError):
    def __init__(self, message: str, *, retry_after: float | None = None, **kw):
        super().__init__(message, **kw)
        self.retry_after = retry_after


def _body(resp) -> dict:
    try:
        b = resp.json()
        return b if isinstance(b, dict) else {"message": str(b)}
    except Exception:
        return {"message": getattr(resp, "text", "") or "request failed"}


def error_from_response(resp) -> TopolabError:
    body = _body(resp)
    msg = body.get("message") or body.get("error") or "request failed"
    rid = (getattr(resp, "headers", {}) or {}).get("x-request-id")
    sc = resp.status_code
    common = dict(status_code=sc, request_id=rid, body=body)
    if sc == 401:
        return AuthenticationError(msg, **common)
    if sc == 402:
        d = body.get("details") or {}
        return InsufficientCreditsError(msg, required=d.get("required"),
                                        available=d.get("available"), **common)
    if sc == 403:
        m = _ADDON_RE.search(msg)
        if m:
            return AddonRequiredError(msg, addon=m.group(1), **common)
        return AccessDeniedError(msg, **common)
    if sc == 404:
        return NotFoundError(msg, **common)
    if sc == 429:
        ra = body.get("retryAfter")
        hdr = (getattr(resp, "headers", {}) or {}).get("retry-after")
        return RateLimitError(
            msg,
            retry_after=ra if ra is not None else (float(hdr) if hdr else None),
            **common,
        )
    if sc == 400:
        if "organization" in msg.lower():
            return ConfigurationError(msg, **common)
        return ValidationError(msg, **common)
    if 400 <= sc < 500:
        return ValidationError(msg, **common)
    return ServerError(msg, **common)
