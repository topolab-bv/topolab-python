"""Sync + async HTTP transport: header injection, retry/backoff, error mapping."""
from __future__ import annotations
import os
import time
import asyncio
import pathlib
from typing import Any
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
        with httpx.Client(**self._signed_client_kwargs()) as client:
            self._stream_with(client, self._signed_url(url), dest, _signed_link_error)

    def _stream_with(self, client: httpx.Client, path: str, dest, to_error, **kw) -> None:
        # streamed GET that never buffers the whole body in memory
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
                if attempt >= self._max_retries:
                    raise TLConnError(str(e)) from e
                time.sleep(self._delay(attempt, None))

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
        async with httpx.AsyncClient(**self._signed_client_kwargs()) as client:
            await self._astream_with(client, self._signed_url(url), dest, _signed_link_error)

    async def _astream_with(self, client: httpx.AsyncClient, path: str, dest, to_error,
                            **kw) -> None:
        # Async streamed GET that never buffers the whole body in memory.
        # Mirrors _stream_with: temp .part + atomic os.replace so a dropped
        # connection never leaves a truncated file at `dest`.
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
                if attempt >= self._max_retries:
                    raise TLConnError(str(e)) from e
                await asyncio.sleep(self._delay(attempt, None))

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
