"""Downloads through the link route, with a per-call fallback to the old routes.

`POST /v1/dataset/{table}/exports` answers 200 with a short-lived signed URL to
a ready file, or 202 while the file is being prepared. The signed URL is
fetched with a separate HTTP client that never sends the API key.

A server without the link route answers it with 404 (or 405). The call then
goes to the old route (`GET .../files/{format}` or
`GET .../archives/{month}/{format}`) with today's behaviour and retries. Nothing
is remembered between calls, so a script keeps working while servers gain or
lose the route. Every other error (402, 403, 5xx, ...) is raised.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from .errors import ServerError, TopolabError, _seconds, retry_after_seconds

#: Answers from the link route that mean "this server has no link route".
FALLBACK_STATUS = frozenset({404, 405})
#: Wait between polls when the server names no wait.
DEFAULT_POLL_SECONDS = 5.0
#: Shortest wait between polls, whatever the server says.
MIN_POLL_SECONDS = 1.0
#: How long one call waits for a file that is being prepared. The build keeps
#: going on the server, so a later call finds the file ready.
MAX_WAIT_SECONDS = 30 * 60.0

# Indirections the tests replace, looked up at call time.
_sleep = time.sleep
_asleep = asyncio.sleep
_clock = time.monotonic


def link_path(slug: str) -> str:
    return f"/v1/dataset/{slug}/exports"


@dataclass
class _Ready:
    url: str


@dataclass
class _Preparing:
    wait: float
    build: Any
    status: int
    body: dict


def _poll_seconds(resp, body: dict) -> float:
    wait = _seconds(body.get("retryAfterSeconds"))
    if wait is None:
        wait = retry_after_seconds(getattr(resp, "headers", None), None)
    if wait is None:
        wait = DEFAULT_POLL_SECONDS
    return max(wait, MIN_POLL_SECONDS)


def _unexpected(resp, body: Any) -> ServerError:
    return ServerError(
        f"The link route answered HTTP {resp.status_code} without a ready link "
        "or a preparing state.",
        status=resp.status_code, code=resp.status_code, body=body)


def _read_answer(resp) -> _Ready | _Preparing:
    try:
        body = resp.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        raise _unexpected(resp, body)
    state = body.get("state")
    if resp.status_code == 202 or state == "preparing":
        return _Preparing(wait=_poll_seconds(resp, body), build=body.get("build"),
                          status=resp.status_code, body=body)
    url = body.get("url")
    if resp.status_code == 200 and state == "ready" and isinstance(url, str) and url:
        return _Ready(url=url)
    raise _unexpected(resp, body)


def _still_preparing(answer: _Preparing) -> ServerError:
    minutes = round(MAX_WAIT_SECONDS / 60)
    return ServerError(
        "The file is still being prepared, and the next wait would pass this "
        f"call's {minutes}-minute limit. It keeps building on the server; "
        "call again later.",
        status=answer.status, code="FILE_PREPARING",
        details={"build": answer.build, "retryAfter": answer.wait}, body=answer.body)


def _past_budget(started: float, wait: float) -> bool:
    return _clock() - started + wait > MAX_WAIT_SECONDS


def fetch(transport, slug: str, body: dict, fallback_path: str, dest: str) -> None:
    """Write the file the link route names to `dest`, or the old route's file."""
    started = _clock()
    while True:
        try:
            resp = transport.request("POST", link_path(slug), json=body)
        except TopolabError as err:
            if err.status in FALLBACK_STATUS:
                transport.stream_to_file(fallback_path, dest)
                return
            raise
        answer = _read_answer(resp)
        if isinstance(answer, _Ready):
            transport.fetch_signed_to_file(answer.url, dest)
            return
        if _past_budget(started, answer.wait):
            raise _still_preparing(answer)
        _sleep(answer.wait)


async def afetch(transport, slug: str, body: dict, fallback_path: str, dest: str) -> None:
    """Async twin of :func:`fetch`."""
    started = _clock()
    while True:
        try:
            resp = await transport.arequest("POST", link_path(slug), json=body)
        except TopolabError as err:
            if err.status in FALLBACK_STATUS:
                await transport.astream_to_file(fallback_path, dest)
                return
            raise
        answer = _read_answer(resp)
        if isinstance(answer, _Ready):
            await transport.afetch_signed_to_file(answer.url, dest)
            return
        if _past_budget(started, answer.wait):
            raise _still_preparing(answer)
        await _asleep(answer.wait)
