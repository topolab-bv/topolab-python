"""download() and archive() through the link route (POST /v1/dataset/:table/exports).

The link route answers 200 with a 10-minute signed URL, or 202 while the file is
being prepared. The SDK fetches the signed URL with a separate client that never
sends the API key. A server without the route (404, or 405) gets today's call to
the old route instead, decided on every call. 402, 403 and 5xx are raised.

Shapes: the 404 body is what staging answered on 2026-11-24 for
`POST /v1/dataset/dining_drinking_mcdonalds/exports`; the 200 and 202 bodies and
the FILE_* codes follow the engine's route contract.
"""
import logging
import socket

import httpx
import pytest
import respx

from topolab import AsyncClient, Client
from topolab import _links
from topolab.errors import AccessDeniedError, InsufficientCreditsError, ServerError
from topolab.errors import ConnectionError as TLConnectionError

# Every spec states the routes the server has; the ones a spec expects untouched
# are asserted by call count rather than by leaving them out.
pytestmark = pytest.mark.respx(assert_all_called=False)

BASE = "https://api.topolab.nl"
TABLE = "dining_drinking_mcdonalds"
LINK = f"{BASE}/v1/dataset/{TABLE}/exports"
FILES_CSV = f"{BASE}/v1/dataset/{TABLE}/files/csv"
ARCHIVE_CSV = f"{BASE}/v1/dataset/{TABLE}/archives/2026-11/csv"
BUILD = "7d3f6c2a-1b4e-4c8d-9a0f-5e6b7c8d9e0f"
SIGNED_HOST = "storage.googleapis.com"
SIGNED_PATH = (f"/platform-staging-datasets/exports/{TABLE}/2026-12/standard/"
               f"20261202T020000Z-a1b2c3d4-w1/{TABLE}_2026-12.csv")
SIGNED_URL = (f"https://{SIGNED_HOST}{SIGNED_PATH}?X-Goog-Algorithm=GOOG4-RSA-SHA256"
              "&X-Goog-Credential=engine%40example.iam.gserviceaccount.com%2F20261203%2Fauto"
              "%2Fstorage%2Fgoog4_request&X-Goog-Date=20261203T100000Z&X-Goog-Expires=600"
              "&X-Goog-SignedHeaders=host&X-Goog-Signature=5f2d0c9e")
LINK_CSV = b"id,location_name,city\n1,McDonald's Amsterdam Centraal,Amsterdam\n"
OLD_CSV = b"id,location_name,city\n1,McDonald's Utrecht Centraal,Utrecht\n"
ZIP = b"PK\x03\x04dining_drinking_mcdonalds_2026-11.csv"


def ready(**over) -> dict:
    body = {"state": "ready", "url": SIGNED_URL, "expiresAt": "2026-12-03T10:10:00.000Z",
            "filename": f"{TABLE}_2026-12.csv", "bytes": len(LINK_CSV),
            "sha256": "9b2f6a0c" * 8, "tier": "standard", "month": "2026-12", "build": BUILD}
    body.update(over)
    return body


def preparing(seconds=4) -> dict:
    body = {"state": "preparing", "build": BUILD, "statusUrl": f"/v1/dataset/exports/{BUILD}"}
    if seconds is not None:
        body["retryAfterSeconds"] = seconds
    return body


def no_route(method: str = "POST") -> dict:
    # What staging answers today: Nest's 404 for a route it does not have.
    return {"path": f"/v1/dataset/{TABLE}/exports", "method": method, "code": 404,
            "message": f"Cannot {method} /v1/dataset/{TABLE}/exports",
            "time": "2026-11-23T23:43:35.228Z", "requestId": "2b12c5708156347fdeffee2d7be873a7"}


def build_failed() -> httpx.Response:
    return httpx.Response(
        503, headers={"retry-after": "0"},
        json={"code": "FILE_BUILD_FAILED", "message": "This file could not be built.",
              "details": {"retryAfter": 0, "linkRoute": f"/v1/dataset/{TABLE}/exports"}})


@pytest.fixture
def waits(monkeypatch):
    """Record the poll waits instead of sleeping; the clock moves with them."""
    slept: list[float] = []
    now = [1000.0]

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    async def asleep(seconds):
        sleep(seconds)

    monkeypatch.setattr(_links, "_sleep", sleep)
    monkeypatch.setattr(_links, "_asleep", asleep)
    monkeypatch.setattr(_links, "_clock", lambda: now[0])
    return slept


def client() -> Client:
    return Client(api_key="tlb_test_key", base_url=BASE)


def signed_route(router):
    return router.get(host=SIGNED_HOST, path=SIGNED_PATH)


# --- ready -----------------------------------------------------------------

def test_download_posts_the_link_route_and_fetches_the_signed_url_without_the_key(
        tmp_path, waits, respx_mock):
    link = respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready()))
    signed = signed_route(respx_mock).mock(return_value=httpx.Response(200, content=LINK_CSV))
    old = respx_mock.get(FILES_CSV).mock(return_value=httpx.Response(200, content=OLD_CSV))
    out = tmp_path / "mcdonalds.csv"

    assert client().dataset(TABLE).download(str(out), format="csv") == str(out)

    assert out.read_bytes() == LINK_CSV
    sent = link.calls.last.request
    assert sent.headers["x-api-key"] == "tlb_test_key"
    assert sent.headers["content-type"] == "application/json"
    assert httpx.Response(200, content=sent.content).json() == {"format": "csv", "bundle": "file"}
    fetched = signed.calls.last.request
    assert "x-api-key" not in fetched.headers
    assert "authorization" not in fetched.headers
    assert str(fetched.url) == SIGNED_URL  # the signed query is sent byte for byte
    assert fetched.headers["user-agent"].startswith("topolab-python/")
    assert old.call_count == 0
    assert waits == []


def test_archive_sends_the_month_and_asks_for_the_zip(tmp_path, waits, respx_mock):
    link = respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready(month="2026-11")))
    signed_route(respx_mock).mock(return_value=httpx.Response(200, content=ZIP))
    old = respx_mock.get(ARCHIVE_CSV).mock(return_value=httpx.Response(200, content=ZIP))
    ds = client().dataset(TABLE)

    out = tmp_path / "november.zip"
    assert ds.archive(str(out), month="2026-11", format="csv") == str(out)
    ds.archive(str(tmp_path / "latest.zip"), month="LATEST")

    bodies = [httpx.Response(200, content=c.request.content).json() for c in link.calls]
    assert bodies == [{"format": "csv", "month": "2026-11", "bundle": "zip"},
                      {"format": "geojson", "month": "latest", "bundle": "zip"}]
    assert out.read_bytes() == ZIP
    assert old.call_count == 0


def test_archive_still_rejects_an_impossible_month_before_any_request(tmp_path):
    with respx.mock() as router:
        with pytest.raises(ValueError):
            client().dataset(TABLE).archive(str(tmp_path / "x.zip"), month="2026-02-29")
        assert router.calls.call_count == 0


# --- preparing ---------------------------------------------------------------

def test_download_polls_the_link_route_honouring_retry_after_seconds(tmp_path, waits, respx_mock):
    link = respx_mock.post(LINK).mock(side_effect=[
        httpx.Response(202, json=preparing(4)),
        httpx.Response(202, json=preparing(2)),
        httpx.Response(200, json=ready()),
    ])
    signed = signed_route(respx_mock).mock(return_value=httpx.Response(200, content=LINK_CSV))
    out = tmp_path / "mcdonalds.csv"

    client().dataset(TABLE).download(str(out), format="csv")

    assert waits == [4, 2]
    assert link.call_count == 3
    assert signed.call_count == 1
    assert out.read_bytes() == LINK_CSV


def test_poll_wait_reads_the_header_when_the_body_has_none_and_never_spins(
        tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(side_effect=[
        httpx.Response(202, json=preparing(None), headers={"retry-after": "7"}),
        httpx.Response(202, json=preparing(None)),
        httpx.Response(202, json=preparing(0)),
        httpx.Response(200, json=ready()),
    ])
    signed_route(respx_mock).mock(return_value=httpx.Response(200, content=LINK_CSV))

    client().dataset(TABLE).download(str(tmp_path / "x.csv"), format="csv")

    # header 7 s; nothing at all: 5 s; a zero: the 1 s floor.
    assert waits == [7, 5, 1]


def test_download_gives_up_after_the_wait_budget_with_file_preparing(
        tmp_path, waits, monkeypatch, respx_mock):
    monkeypatch.setattr(_links, "MAX_WAIT_SECONDS", 10)
    link = respx_mock.post(LINK).mock(return_value=httpx.Response(202, json=preparing(4)))
    signed = signed_route(respx_mock).mock(return_value=httpx.Response(200, content=LINK_CSV))
    out = tmp_path / "x.csv"

    with pytest.raises(ServerError) as exc:
        client().dataset(TABLE).download(str(out), format="csv")

    assert exc.value.code == "FILE_PREPARING"
    assert exc.value.status == 202
    assert exc.value.details == {"build": BUILD, "retryAfter": 4}
    assert waits == [4, 4]          # a third wait would pass the 10 s budget
    assert link.call_count == 3
    assert signed.call_count == 0
    assert not out.exists()


# --- failed ----------------------------------------------------------------

def test_a_failed_build_is_raised_and_never_falls_back(tmp_path, waits, respx_mock):
    link = respx_mock.post(LINK).mock(return_value=build_failed())
    old = respx_mock.get(FILES_CSV).mock(return_value=httpx.Response(200, content=OLD_CSV))
    out = tmp_path / "x.csv"

    with pytest.raises(ServerError) as exc:
        client().dataset(TABLE).download(str(out), format="csv")

    assert exc.value.code == "FILE_BUILD_FAILED"
    assert exc.value.status == 503
    assert link.call_count == 4     # today's 503 retries: 1 try + 3 retries
    assert old.call_count == 0
    assert not out.exists()


def test_a_server_error_from_the_link_route_never_falls_back(tmp_path, waits, respx_mock):
    link = respx_mock.post(LINK).mock(return_value=httpx.Response(
        500, headers={"retry-after": "0"}, json={"code": 500, "message": "Internal server error"}))
    old = respx_mock.get(FILES_CSV).mock(return_value=httpx.Response(200, content=OLD_CSV))

    with pytest.raises(ServerError):
        client().dataset(TABLE).download(str(tmp_path / "x.csv"), format="csv")
    assert link.call_count == 4
    assert old.call_count == 0


def test_an_unexpected_answer_is_a_server_error(tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json={"state": "ready"}))

    with pytest.raises(ServerError) as exc:
        client().dataset(TABLE).download(str(tmp_path / "x.csv"), format="csv")
    assert exc.value.status == 200


# --- fallback on 404 and 405 -------------------------------------------------

def test_404_from_the_link_route_falls_back_to_the_files_route(tmp_path, waits, respx_mock):
    link = respx_mock.post(LINK).mock(return_value=httpx.Response(404, json=no_route()))
    old = respx_mock.get(FILES_CSV).mock(return_value=httpx.Response(200, content=OLD_CSV))
    signed = signed_route(respx_mock).mock(return_value=httpx.Response(200, content=LINK_CSV))
    out = tmp_path / "mcdonalds.csv"

    assert client().dataset(TABLE).download(str(out), format="csv") == str(out)

    assert out.read_bytes() == OLD_CSV
    assert link.call_count == 1
    assert old.call_count == 1
    assert old.calls.last.request.headers["x-api-key"] == "tlb_test_key"
    assert signed.call_count == 0


def test_405_from_the_link_route_falls_back_to_the_archive_route(tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(
        405, json={"code": 405, "message": "Method Not Allowed"}))
    old = respx_mock.get(ARCHIVE_CSV).mock(return_value=httpx.Response(200, content=ZIP))
    out = tmp_path / "november.zip"

    client().dataset(TABLE).archive(str(out), month="2026-11", format="csv")

    assert out.read_bytes() == ZIP
    assert old.call_count == 1


def test_the_fallback_keeps_the_old_routes_retries_and_answer(tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(404, json=no_route()))
    old = respx_mock.get(FILES_CSV).mock(side_effect=[
        httpx.Response(503, headers={"retry-after": "0"},
                       json={"code": "FILE_PREPARING", "message": "This file is being prepared.",
                             "details": {"retryAfter": 0}}),
        httpx.Response(200, content=OLD_CSV),
    ])
    out = tmp_path / "x.csv"

    client().dataset(TABLE).download(str(out), format="csv")

    assert old.call_count == 2
    assert out.read_bytes() == OLD_CSV


def test_a_404_from_the_old_route_after_the_fallback_is_raised(tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(404, json=no_route()))
    respx_mock.get(ARCHIVE_CSV).mock(return_value=httpx.Response(
        404, json={"code": 404, "message": "No archive for 2026-11"}))

    from topolab.errors import NotFoundError
    with pytest.raises(NotFoundError):
        client().dataset(TABLE).archive(str(tmp_path / "x.zip"), month="2026-11", format="csv")


def test_the_fallback_is_decided_on_every_call(tmp_path, waits, respx_mock):
    link = respx_mock.post(LINK).mock(side_effect=[
        httpx.Response(404, json=no_route()),
        httpx.Response(200, json=ready()),
    ])
    old = respx_mock.get(FILES_CSV).mock(return_value=httpx.Response(200, content=OLD_CSV))
    signed = signed_route(respx_mock).mock(return_value=httpx.Response(200, content=LINK_CSV))
    ds = client().dataset(TABLE)

    ds.download(str(tmp_path / "first.csv"), format="csv")
    ds.download(str(tmp_path / "second.csv"), format="csv")

    assert (tmp_path / "first.csv").read_bytes() == OLD_CSV
    assert (tmp_path / "second.csv").read_bytes() == LINK_CSV
    assert (link.call_count, old.call_count, signed.call_count) == (2, 1, 1)


# --- 402 and 403 are raised ----------------------------------------------------

def test_403_from_the_link_route_is_raised_without_a_fallback(tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(
        403, json={"code": 403, "message": "Your organization has no licence for this dataset"}))
    old = respx_mock.get(FILES_CSV).mock(return_value=httpx.Response(200, content=OLD_CSV))
    out = tmp_path / "x.csv"

    with pytest.raises(AccessDeniedError):
        client().dataset(TABLE).download(str(out), format="csv")
    assert old.call_count == 0
    assert not out.exists()


def test_402_from_the_link_route_is_raised_without_a_fallback(tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(
        402, json={"code": 402, "message": "Insufficient credits",
                   "details": {"required": 20, "available": 3}}))
    old = respx_mock.get(ARCHIVE_CSV).mock(return_value=httpx.Response(200, content=ZIP))

    with pytest.raises(InsufficientCreditsError) as exc:
        client().dataset(TABLE).archive(str(tmp_path / "x.zip"), month="2026-11", format="csv")
    assert exc.value.required == 20
    assert old.call_count == 0


# --- the signed URL ----------------------------------------------------------

def test_an_error_from_the_signed_url_is_raised_without_the_link_and_leaves_no_file(
        tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready()))
    signed_route(respx_mock).mock(return_value=httpx.Response(
        400, headers={"content-type": "application/xml"},
        content=(b"<?xml version='1.0' encoding='UTF-8'?><Error><Code>ExpiredToken</Code>"
                 b"<Message>Invalid argument.</Message><Details>X-Goog-Signature=5f2d0c9e"
                 b"</Details></Error>")))
    out = tmp_path / "x.csv"

    with pytest.raises(Exception) as exc:
        client().dataset(TABLE).download(str(out), format="csv")

    assert exc.value.status == 400
    assert "X-Goog-Signature" not in str(exc.value)
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_the_signed_url_is_retried_on_a_transient_answer(tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready()))
    signed = signed_route(respx_mock).mock(side_effect=[
        httpx.Response(503, headers={"retry-after": "0"}, content=b"<Error/>"),
        httpx.Response(200, content=LINK_CSV),
    ])
    out = tmp_path / "x.csv"

    client().dataset(TABLE).download(str(out), format="csv")

    assert signed.call_count == 2
    assert out.read_bytes() == LINK_CSV


# --- sample() is unchanged ---------------------------------------------------

def test_sample_reads_the_sample_route_and_never_the_link_route():
    with respx.mock() as router:
        sample = router.get(f"{BASE}/v1/dataset/{TABLE}/sample/geojson").mock(
            return_value=httpx.Response(200, json={"type": "FeatureCollection", "features": []}))
        fc = client().dataset(TABLE).sample()
        assert sample.call_count == 1
        assert router.calls.call_count == 1
    assert fc == {"type": "FeatureCollection", "features": []}


# --- async ---------------------------------------------------------------------

async def test_async_download_through_the_link_route(tmp_path, waits, respx_mock):
    link = respx_mock.post(LINK).mock(side_effect=[
        httpx.Response(202, json=preparing(3)),
        httpx.Response(200, json=ready()),
    ])
    signed = signed_route(respx_mock).mock(return_value=httpx.Response(200, content=LINK_CSV))
    out = tmp_path / "x.csv"

    async with AsyncClient(api_key="tlb_test_key", base_url=BASE) as tl:
        assert await tl.dataset(TABLE).download(str(out), format="csv") == str(out)

    assert waits == [3]
    assert httpx.Response(200, content=link.calls.last.request.content).json() == \
        {"format": "csv", "bundle": "file"}
    assert "x-api-key" not in signed.calls.last.request.headers
    assert out.read_bytes() == LINK_CSV


async def test_async_archive_through_the_link_route(tmp_path, waits, respx_mock):
    link = respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready(month="2026-11")))
    signed_route(respx_mock).mock(return_value=httpx.Response(200, content=ZIP))
    out = tmp_path / "x.zip"

    async with AsyncClient(api_key="tlb_test_key", base_url=BASE) as tl:
        await tl.dataset(TABLE).archive(str(out), month="2026-11", format="csv")

    assert httpx.Response(200, content=link.calls.last.request.content).json() == \
        {"format": "csv", "month": "2026-11", "bundle": "zip"}
    assert out.read_bytes() == ZIP


async def test_async_404_and_405_fall_back(tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(side_effect=[
        httpx.Response(404, json=no_route()),
        httpx.Response(405, json={"code": 405, "message": "Method Not Allowed"}),
    ])
    files = respx_mock.get(FILES_CSV).mock(return_value=httpx.Response(200, content=OLD_CSV))
    archive = respx_mock.get(ARCHIVE_CSV).mock(return_value=httpx.Response(200, content=ZIP))

    async with AsyncClient(api_key="tlb_test_key", base_url=BASE) as tl:
        ds = tl.dataset(TABLE)
        await ds.download(str(tmp_path / "x.csv"), format="csv")
        await ds.archive(str(tmp_path / "x.zip"), month="2026-11", format="csv")

    assert (files.call_count, archive.call_count) == (1, 1)
    assert (tmp_path / "x.csv").read_bytes() == OLD_CSV
    assert (tmp_path / "x.zip").read_bytes() == ZIP


async def test_async_403_and_failed_build_are_raised(tmp_path, waits, respx_mock):
    respx_mock.post(LINK).mock(side_effect=[
        httpx.Response(403, json={"code": 403, "message": "No licence"}),
        build_failed(), build_failed(), build_failed(), build_failed(),
    ])
    old = respx_mock.get(FILES_CSV).mock(return_value=httpx.Response(200, content=OLD_CSV))

    async with AsyncClient(api_key="tlb_test_key", base_url=BASE) as tl:
        ds = tl.dataset(TABLE)
        with pytest.raises(AccessDeniedError):
            await ds.download(str(tmp_path / "x.csv"), format="csv")
        with pytest.raises(ServerError) as exc:
            await ds.download(str(tmp_path / "x.csv"), format="csv")

    assert exc.value.code == "FILE_BUILD_FAILED"
    assert old.call_count == 0


# --- the signed query never reaches a log record or an error ---------------------
#
# The query of a signed link is its signature: a working bearer link to a paid
# file for ten minutes. httpx writes every request's full URL to its INFO log,
# so a program with `logging.basicConfig(level=logging.INFO)` would store the
# link. The request itself still carries the query byte for byte.

SIGNED_QUERY = SIGNED_URL.split("?", 1)[1]
QUERY_PARTS = ("X-Goog-Signature", "5f2d0c9e", "X-Goog-Credential", SIGNED_QUERY)


def assert_no_query(*texts: str) -> None:
    for text in texts:
        for part in QUERY_PARTS:
            assert part not in text, f"carries the signed query ({part!r}): {text}"


def log_texts(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records] + [caplog.text]


def chain_text(err: BaseException) -> str:
    import traceback
    return "".join(traceback.format_exception(type(err), err, err.__traceback__))


def calls(kind: str):
    """The four ways a signed link is fetched: (sync|async) x (download|archive)."""
    async def run(tmp_path):
        if kind.startswith("async"):
            async with AsyncClient(api_key="tlb_test_key", base_url=BASE, max_retries=0) as tl:
                ds = tl.dataset(TABLE)
                if kind.endswith("download"):
                    await ds.download(str(tmp_path / "x.csv"), format="csv")
                else:
                    await ds.archive(str(tmp_path / "x.zip"), month="2026-11", format="csv")
        else:
            ds = Client(api_key="tlb_test_key", base_url=BASE, max_retries=0).dataset(TABLE)
            if kind.endswith("download"):
                ds.download(str(tmp_path / "x.csv"), format="csv")
            else:
                ds.archive(str(tmp_path / "x.zip"), month="2026-11", format="csv")
    return run


KINDS = ["sync download", "sync archive", "async download", "async archive"]


@pytest.mark.parametrize("kind", KINDS)
async def test_the_signed_query_reaches_no_log_record(tmp_path, waits, respx_mock, caplog, kind):
    caplog.set_level(logging.DEBUG)
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready()))
    signed = signed_route(respx_mock).mock(return_value=httpx.Response(200, content=LINK_CSV))

    await calls(kind)(tmp_path)

    assert str(signed.calls.last.request.url) == SIGNED_URL
    assert any("HTTP Request" in r.getMessage() and SIGNED_PATH in r.getMessage()
               for r in caplog.records), "httpx's request line is still logged, without the query"
    assert_no_query(*log_texts(caplog))


@pytest.mark.parametrize("kind", KINDS)
async def test_a_signed_link_connection_error_carries_no_query(
        tmp_path, waits, respx_mock, caplog, kind):
    caplog.set_level(logging.DEBUG)
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready()))
    signed_route(respx_mock).mock(side_effect=httpx.ConnectError(
        f"connect failed for {SIGNED_URL}", request=httpx.Request("GET", SIGNED_URL)))

    with pytest.raises(TLConnectionError) as exc:
        await calls(kind)(tmp_path)

    assert_no_query(str(exc.value), repr(exc.value), chain_text(exc.value), *log_texts(caplog))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["sync download", "async archive"])
async def test_an_unreachable_signed_host_carries_no_query(tmp_path, waits, respx_mock, caplog, kind):
    # A real connection to a closed port: httpx and httpcore raise and log as
    # they do in production.
    caplog.set_level(logging.DEBUG)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}{SIGNED_PATH}?{SIGNED_QUERY}"
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready(url=url)))
    respx_mock.route(host="127.0.0.1").pass_through()

    with pytest.raises(TLConnectionError) as exc:
        await calls(kind)(tmp_path)

    assert_no_query(str(exc.value), repr(exc.value), chain_text(exc.value), *log_texts(caplog))


async def test_a_real_signed_fetch_logs_no_query(tmp_path, waits, respx_mock, caplog):
    # A real storage host on localhost, so httpcore's DEBUG trace runs too.
    import http.server
    import threading

    seen: list[str] = []

    class Storage(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", str(len(LINK_CSV)))
            self.end_headers()
            self.wfile.write(LINK_CSV)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Storage)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        caplog.set_level(logging.DEBUG)
        url = f"http://127.0.0.1:{server.server_port}{SIGNED_PATH}?{SIGNED_QUERY}"
        respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready(url=url)))
        respx_mock.route(host="127.0.0.1").pass_through()

        await calls("sync download")(tmp_path)
        await calls("async download")(tmp_path)
    finally:
        server.shutdown()
        server.server_close()

    assert seen == [f"{SIGNED_PATH}?{SIGNED_QUERY}"] * 2
    assert (tmp_path / "x.csv").read_bytes() == LINK_CSV
    assert_no_query(*log_texts(caplog))


def test_the_api_request_log_is_left_as_httpx_writes_it(respx_mock, caplog):
    # Only signed links lose their query in the log; the API's own lines stay.
    caplog.set_level(logging.INFO)
    respx_mock.get(f"{BASE}/v1/dataset/{TABLE}/archives/list").mock(
        return_value=httpx.Response(200, json=[]))

    client().dataset(TABLE).archives()

    assert any(f"{BASE}/v1/dataset/{TABLE}/archives/list" in r.getMessage() for r in caplog.records)


def test_the_query_stays_out_after_a_logging_setup_cleared_the_filters(tmp_path, waits, respx_mock, caplog):
    caplog.set_level(logging.INFO)
    httpx_logger = logging.getLogger("httpx")
    saved = list(httpx_logger.filters)
    httpx_logger.filters.clear()
    try:
        respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready()))
        signed_route(respx_mock).mock(return_value=httpx.Response(200, content=LINK_CSV))

        client().dataset(TABLE).download(str(tmp_path / "x.csv"), format="csv")
    finally:
        httpx_logger.filters[:] = saved

    assert_no_query(*log_texts(caplog))
