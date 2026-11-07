"""Typed error hierarchy mapped from API responses (status + body)."""
from __future__ import annotations
import email.utils
import math
import re
import time
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
        messages: every message as a list. The engine's request validation
            sends a list of messages; ``message`` joins them with ``"; "``.
            A single message gives a one-item list.
    """

    def __init__(self, message: str, *, status: int | None = None,
                 status_code: int | None = None, code: ErrorCode | None = None,
                 details: dict[str, Any] | None = None,
                 request_id: str | None = None, body: Any = None,
                 messages: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.messages = list(messages) if messages is not None else [message]
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


def _messages(body: dict) -> list[str]:
    """The body's message(s) as a list. The engine's request validation sends
    ``message`` as a list of strings; everything else sends one string."""
    raw = body.get("message")
    if isinstance(raw, list):
        items = [str(m) for m in raw if m is not None and str(m) != ""]
    elif raw is not None and raw != "":
        items = [str(raw)]
    else:
        items = []
    if not items:
        fallback = body.get("error")
        items = [str(fallback)] if fallback else ["request failed"]
    return items


def _seconds(value: Any) -> float | None:
    """A non-negative, finite number of seconds, or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, str):
        try:
            seconds = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _header_seconds(value: str | None) -> float | None:
    """A ``Retry-After`` header as seconds: delay-seconds or an HTTP-date
    (RFC 9110, section 10.2.3)."""
    if not value:
        return None
    seconds = _seconds(value)
    if seconds is not None:
        return seconds
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    return max(0.0, when.timestamp() - time.time())


def retry_after_seconds(headers: Any, body: Any) -> float | None:
    """How long the server asked the client to wait, in seconds, or None.

    The ``Retry-After`` header comes first: the engine sends it on every 429
    that carries a wait, rounded up to whole seconds. Then ``details.retryAfter``
    (engine #650 and later), then a top-level ``retryAfter`` from older engines.
    """
    header = None
    if headers is not None:
        try:
            header = headers.get("retry-after")
        except AttributeError:
            header = None
    seconds = _header_seconds(header)
    if seconds is not None:
        return seconds
    if isinstance(body, dict):
        details = body.get("details")
        if isinstance(details, dict):
            seconds = _seconds(details.get("retryAfter"))
            if seconds is not None:
                return seconds
        return _seconds(body.get("retryAfter"))
    return None


def error_from_response(resp) -> TopolabError:
    body = _body(resp)
    messages = _messages(body)
    msg = "; ".join(messages)
    rid = (getattr(resp, "headers", {}) or {}).get("x-request-id") or body.get("requestId")
    sc = resp.status_code
    # The class is chosen from the HTTP status; `code` only refines it (a 403
    # with SPENDING_LIMIT_EXCEEDED is still an AccessDeniedError).
    common = dict(status=sc, code=_code(body, sc), details=_details(body),
                  request_id=rid, body=body, messages=messages)
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
        return RateLimitError(
            msg,
            retry_after=retry_after_seconds(getattr(resp, "headers", None), body),
            **common,
        )
    if sc == 400:
        if "organization" in msg.lower():
            return ConfigurationError(msg, **common)
        return ValidationError(msg, **common)
    if 400 <= sc < 500:
        return ValidationError(msg, **common)
    return ServerError(msg, **common)
