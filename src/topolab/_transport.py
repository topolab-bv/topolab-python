"""Sync + async HTTP transport: header injection, retry/backoff, error mapping."""
from __future__ import annotations
import os
import time
import asyncio
import pathlib
from typing import Any
import httpx
from ._version import __version__
from .errors import error_from_response, ConnectionError as TLConnError

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

    # --- delay calc shared by sync/async ---
    def _delay(self, attempt: int, resp: httpx.Response | None) -> float:
        if resp is not None:
            try:
                body = resp.json()
                if isinstance(body, dict) and body.get("retryAfter") is not None:
                    return float(body["retryAfter"])
            except Exception:
                pass
            hdr = resp.headers.get("retry-after")
            if hdr:
                try:
                    return float(hdr)
                except ValueError:
                    pass
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
        # streamed GET that never buffers the whole body in memory
        for attempt in range(self._max_retries + 1):
            try:
                with self._sync.stream("GET", path, **kw) as resp:
                    if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                        resp.read()
                        time.sleep(self._delay(attempt, resp))
                        continue
                    if resp.status_code >= 400:
                        resp.read()
                        raise error_from_response(resp)
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
        # Async streamed GET that never buffers the whole body in memory.
        # Mirrors stream_to_file: temp .part + atomic os.replace so a dropped
        # connection never leaves a truncated file at `dest`.
        client = self._ensure_async()
        for attempt in range(self._max_retries + 1):
            try:
                async with client.stream("GET", path, **kw) as resp:
                    if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                        await resp.aread()
                        await asyncio.sleep(self._delay(attempt, resp))
                        continue
                    if resp.status_code >= 400:
                        await resp.aread()
                        raise error_from_response(resp)
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
