"""Typed error hierarchy mapped from API responses (status + body)."""
from __future__ import annotations
import re
from typing import Any, Union

#: The error envelope's ``code``: a string such as ``"SPENDING_LIMIT_EXCEEDED"``
#: when the engine throws a named code, otherwise the numeric HTTP status.
ErrorCode = Union[str, int]

# Add-on identifiers are hyphenated slugs (api-access, archived-data, …) and the
# message spells them either as the slug or in prose ("the Archived Data add-on"),
# so the capture is non-greedy and normalised rather than \w+ (which stops at the
# hyphen and therefore matched nothing).
_ADDON_RE = re.compile(r"requires the (.+?) add-?on", re.IGNORECASE)


def _addon_slug(raw: str) -> str:
    return raw.strip().lower().replace(" ", "-")


class TopolabError(Exception):
    """Base class for every SDK error.

    Attributes:
        message: the server's message, or the SDK's for client-side errors.
        status: the HTTP status of the response, always an ``int``; ``None``
            when no response exists (network failure, client-side check).
        status_code: the same value as ``status``, kept for compatibility.
        code: the error envelope's ``code``. A string such as
            ``"SPENDING_LIMIT_EXCEEDED"`` when the error has its own code,
            otherwise the numeric HTTP status. ``None`` without a response.
            Compare string codes by equality and read ``status`` for the
            HTTP status.
        details: the envelope's allow-listed ``details`` dict, or ``None``.
        request_id: the ``X-Request-Id`` header, else the body's ``requestId``.
        body: the decoded response body.
    """

    def __init__(self, message: str, *, status: int | None = None,
                 status_code: int | None = None, code: ErrorCode | None = None,
                 details: dict[str, Any] | None = None,
                 request_id: str | None = None, body: Any = None):
        super().__init__(message)
        self.message = message
        self.status = status if status is not None else status_code
        self.code = code
        self.details = details
        self.request_id = request_id
        self.body = body

    @property
    def status_code(self) -> int | None:
        """Alias of ``status``, kept for code written against 0.1."""
        return self.status

    @status_code.setter
    def status_code(self, value: int | None) -> None:
        self.status = value


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


class QueryTimeoutError(TopolabError): ...


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


def _code(body: dict, status: int) -> ErrorCode:
    """The envelope's ``code`` (a non-empty string or an integer), else the
    HTTP status, so a proxy's error page still yields a usable code."""
    code = body.get("code")
    if isinstance(code, bool):
        return status
    if isinstance(code, str) and code:
        return code
    if isinstance(code, int):
        return code
    if isinstance(code, float) and code.is_integer():
        return int(code)
    return status


def _details(body: dict) -> dict[str, Any] | None:
    details = body.get("details")
    return details if isinstance(details, dict) else None


def error_from_response(resp) -> TopolabError:
    body = _body(resp)
    msg = body.get("message") or body.get("error") or "request failed"
    rid = (getattr(resp, "headers", {}) or {}).get("x-request-id") or body.get("requestId")
    sc = resp.status_code
    # The class is chosen from the HTTP status; `code` only refines it (a 403
    # with SPENDING_LIMIT_EXCEEDED is still an AccessDeniedError).
    common = dict(status=sc, code=_code(body, sc), details=_details(body),
                  request_id=rid, body=body)
    if sc == 401:
        return AuthenticationError(msg, **common)
    if sc == 402:
        d = common["details"] or {}
        return InsufficientCreditsError(msg, required=d.get("required"),
                                        available=d.get("available"), **common)
    if sc == 403:
        m = _ADDON_RE.search(msg)
        if m:
            return AddonRequiredError(msg, addon=_addon_slug(m.group(1)), **common)
        return AccessDeniedError(msg, **common)
    if sc == 404:
        return NotFoundError(msg, **common)
    if sc == 408:
        return QueryTimeoutError(msg, **common)
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
