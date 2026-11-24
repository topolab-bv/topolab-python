"""Sync + async HTTP transport: header injection, retry/backoff, error mapping."""
from __future__ import annotations
import os
import time
import asyncio
import logging
import pathlib
import threading
from contextlib import contextmanager
from typing import Any, Iterator
import httpx
from ._version import __version__
from .errors import (TopolabError, error_from_response, retry_after_seconds,
                     ConnectionError as TLConnError)

USER_AGENT = f"topolab-python/{__version__} (+https://docs.topolab.nl)"
_RETRY_STATUS = {429, 500, 502, 503, 504}


class Transport:
    def __init__(self, *, api_key: str, base_url: str, timeout: float = 60.0,
                 max_retries: int = 3, proxy_url: str | None = None,
                 user_agent: str | None = None, _backoff_base: float = 0.5):
        self._headers = {
            "X-API-Key": api_key,
            "User-Agent": user_agent or USER_AGENT,
            "Accept": "application/json",
        }
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_base = _backoff_base
        self._sync = httpx.Client(base_url=self._base_url, headers=self._headers,
                                  timeout=timeout, proxy=proxy_url)
        self._async: httpx.AsyncClient | None = None
        self._proxy = proxy_url

    # --- signed links ---
    def _signed_client_kwargs(self) -> dict:
        # A signed link carries its own authorisation. The client that fetches
        # it is a separate one with only the User-Agent, so the API key never
        # leaves for the storage host.
        return dict(headers={"User-Agent": self._headers["User-Agent"]},
                    timeout=self._timeout, proxy=self._proxy, follow_redirects=True)

    def _signed_url(self, url: str) -> str:
        return str(httpx.URL(self._base_url + "/").join(url))

    # --- delay calc shared by sync/async ---
    def _delay(self, attempt: int, resp: httpx.Response | None) -> float:
        if resp is not None:
            try:
                body = resp.json()
            except Exception:
                body = None
            wait = retry_after_seconds(resp.headers, body)
            if wait is not None:
                return wait
        return self._backoff_base * (2 ** attempt)

    # --- sync ---
    def request(self, method: str, path: str, **kw) -> httpx.Response:
        last: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._sync.request(method, path, **kw)
            except httpx.TransportError as e:
                if attempt >= self._max_retries:
                    raise TLConnError(str(e)) from e
                time.sleep(self._delay(attempt, None))
                continue
            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                last = resp
                time.sleep(self._delay(attempt, resp))
                continue
            if resp.status_code >= 400:
                raise error_from_response(resp)
            return resp
        raise error_from_response(last)  # retries exhausted

    def get_json(self, path: str, **kw) -> Any:
        return self.request("GET", path, **kw).json()

    def stream_to_file(self, path: str, dest, **kw) -> None:
        self._stream_with(self._sync, path, dest, error_from_response, **kw)

    def fetch_signed_to_file(self, url: str, dest) -> None:
        """Stream a signed link to `dest` with a client that sends no API key."""
        url = self._signed_url(url)
        with _SIGNED_QUERIES.hiding() as hide, \
                httpx.Client(**self._signed_client_kwargs(),
                             event_hooks={"request": [lambda req: hide(str(req.url))]}) as client:
            hide(url)
            self._stream_with(client, url, dest, _signed_link_error, secret_url=url)

    def _stream_with(self, client: httpx.Client, path: str, dest, to_error,
                     secret_url: str | None = None, **kw) -> None:
        # streamed GET that never buffers the whole body in memory
        failure: TLConnError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                with client.stream("GET", path, **kw) as resp:
                    if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                        resp.read()
                        time.sleep(self._delay(attempt, resp))
                        continue
                    if resp.status_code >= 400:
                        resp.read()
                        raise to_error(resp)
                    # Stream to a sibling temp file and atomically replace, so a
                    # connection dropped mid-body never leaves a truncated file
                    # at `dest`.
                    tmp = f"{dest}.part"
                    try:
                        with open(tmp, "wb") as fh:
                            for chunk in resp.iter_bytes(65536):
                                fh.write(chunk)
                        os.replace(tmp, dest)
                    except BaseException:
                        pathlib.Path(tmp).unlink(missing_ok=True)
                        raise
                    return
            except httpx.TransportError as e:
                if attempt < self._max_retries:
                    time.sleep(self._delay(attempt, None))
                    continue
                failure = _connection_error(e, secret_url)
                break
        # Raised outside the except block, so the transport error is never its
        # implicit __context__ (see _connection_error).
        if failure is not None:
            raise failure

    def close(self) -> None:
        self._sync.close()

    # --- async ---
    def _ensure_async(self) -> httpx.AsyncClient:
        if self._async is None:
            self._async = httpx.AsyncClient(base_url=self._base_url, headers=self._headers,
                                            timeout=self._timeout, proxy=self._proxy)
        return self._async

    async def arequest(self, method: str, path: str, **kw) -> httpx.Response:
        client = self._ensure_async()
        last: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await client.request(method, path, **kw)
            except httpx.TransportError as e:
                if attempt >= self._max_retries:
                    raise TLConnError(str(e)) from e
                await asyncio.sleep(self._delay(attempt, None))
                continue
            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                last = resp
                await asyncio.sleep(self._delay(attempt, resp))
                continue
            if resp.status_code >= 400:
                raise error_from_response(resp)
            return resp
        raise error_from_response(last)

    async def aget_json(self, path: str, **kw) -> Any:
        return (await self.arequest("GET", path, **kw)).json()

    async def astream_to_file(self, path: str, dest, **kw) -> None:
        await self._astream_with(self._ensure_async(), path, dest, error_from_response, **kw)

    async def afetch_signed_to_file(self, url: str, dest) -> None:
        """Async twin of :meth:`fetch_signed_to_file`."""
        url = self._signed_url(url)
        with _SIGNED_QUERIES.hiding() as hide:
            async def on_request(req: httpx.Request) -> None:
                hide(str(req.url))

            async with httpx.AsyncClient(**self._signed_client_kwargs(),
                                         event_hooks={"request": [on_request]}) as client:
                hide(url)
                await self._astream_with(client, url, dest, _signed_link_error, secret_url=url)

    async def _astream_with(self, client: httpx.AsyncClient, path: str, dest, to_error,
                            secret_url: str | None = None, **kw) -> None:
        # Async streamed GET that never buffers the whole body in memory.
        # Mirrors _stream_with: temp .part + atomic os.replace so a dropped
        # connection never leaves a truncated file at `dest`.
        failure: TLConnError | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with client.stream("GET", path, **kw) as resp:
                    if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                        await resp.aread()
                        await asyncio.sleep(self._delay(attempt, resp))
                        continue
                    if resp.status_code >= 400:
                        await resp.aread()
                        raise to_error(resp)
                    tmp = f"{dest}.part"
                    try:
                        with open(tmp, "wb") as fh:
                            async for chunk in resp.aiter_bytes(65536):
                                fh.write(chunk)
                        os.replace(tmp, dest)
                    except BaseException:
                        pathlib.Path(tmp).unlink(missing_ok=True)
                        raise
                    return
            except httpx.TransportError as e:
                if attempt < self._max_retries:
                    await asyncio.sleep(self._delay(attempt, None))
                    continue
                failure = _connection_error(e, secret_url)
                break
        # Raised outside the except block, as in _stream_with.
        if failure is not None:
            raise failure

    async def aclose(self) -> None:
        if self._async is not None:
            await self._async.aclose()
        self._sync.close()


def _signed_link_error(resp: httpx.Response) -> TopolabError:
    """The error for a failed signed-link fetch. The class follows the status as
    everywhere else; the message never repeats the storage host's body, which
    can quote the link's signature."""
    err = error_from_response(resp)
    msg = (f"Fetching the file from its signed link failed with HTTP {resp.status_code}. "
           "Call again for a new link.")
    err.args = (msg,)
    err.message = msg
    err.messages = [msg]
    err.body = None
    return err


# --- signed links never reach a log or an error ------------------------------
#
# The query of a signed link is its signature: a bearer link to the file for
# ten minutes. httpx writes the full URL of every request to its INFO log, and
# a transport error can quote it, so both are stripped of the query while the
# request itself carries it byte for byte.

def _queries(url: str) -> list[str]:
    """The forms `url`'s query can take in a text, longest first."""
    found = {url.partition("?")[2].partition("#")[0]}
    try:
        found.add(httpx.URL(url).query.decode("ascii"))
    except Exception:
        pass
    return sorted((q for q in found if q), key=len, reverse=True)


def _without_query(text: str, queries: list[str]) -> str:
    for q in queries:
        text = text.replace("?" + q, "").replace(q, "[query removed]")
    return text


class _SignedQueryFilter(logging.Filter):
    """Removes the query of the signed links being fetched from httpx's log
    records. Records about anything else pass unchanged."""

    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._active: dict[str, int] = {}

    @contextmanager
    def hiding(self) -> Iterator:
        """Yields `hide(url)`; the queries it was given are hidden until exit."""
        # Installed again if a logging setup removed it since.
        httpx_logger = logging.getLogger("httpx")
        if self not in httpx_logger.filters:
            httpx_logger.addFilter(self)
        mine: list[str] = []

        def hide(url: str) -> None:
            with self._lock:
                for q in _queries(url):
                    self._active[q] = self._active.get(q, 0) + 1
                    mine.append(q)

        try:
            yield hide
        finally:
            with self._lock:
                for q in mine:
                    left = self._active.get(q, 0) - 1
                    if left > 0:
                        self._active[q] = left
                    else:
                        self._active.pop(q, None)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._active:
            return True
        with self._lock:
            queries = sorted(self._active, key=len, reverse=True)
        if isinstance(record.msg, str):
            record.msg = _without_query(record.msg, queries)
        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(self._clean(a, queries) for a in args)
        elif isinstance(args, dict):
            record.args = {k: self._clean(v, queries) for k, v in args.items()}
        return True

    @staticmethod
    def _clean(arg: Any, queries: list[str]) -> Any:
        if isinstance(arg, (str, httpx.URL)):
            text = str(arg)
            cleaned = _without_query(text, queries)
            if cleaned != text:
                return cleaned
        return arg


_SIGNED_QUERIES = _SignedQueryFilter()
logging.getLogger("httpx").addFilter(_SIGNED_QUERIES)


def _linked(e: BaseException) -> list[BaseException]:
    """`e` and every exception reachable from it through __cause__ and
    __context__, whatever __suppress_context__ says: error reporters and
    debuggers walk both."""
    seen: list[BaseException] = []
    todo: list[BaseException] = [e]
    while todo:
        x = todo.pop()
        if any(x is s for s in seen):
            continue
        seen.append(x)
        todo += [y for y in (x.__cause__, x.__context__) if y is not None]
    return seen


def _connection_error(e: httpx.TransportError, secret_url: str | None) -> TLConnError:
    """The SDK's ConnectionError for a transport failure, raised by the caller
    outside its except block so `e` is never the implicit __context__. For a
    signed link the message loses the link's query, and `e` is kept as the
    cause only when no exception linked to it (cause or context) carries the
    query in its text or repr."""
    if secret_url is None:
        err = TLConnError(str(e))
        err.__cause__ = e
        err.__suppress_context__ = True
        return err
    queries = _queries(secret_url)
    err = TLConnError(_without_query(str(e), queries))
    texts = [t for x in _linked(e) for t in (str(x), repr(x))]
    if not any(q in t for t in texts for q in queries):
        err.__cause__ = e
    err.__suppress_context__ = True
    return err
