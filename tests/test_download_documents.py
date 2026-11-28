"""download() writes the build's documents beside the file (the link route's 200 `documents`).

The engine's link route names signed links to the build's `columns.json` and each
notice file (licences and attributions the data needs). `download()` fetches them
the same way as the file, without the API key, and writes them as
`<file>.columns.json` and `<file>.notices/<name>`; a notice whose name is not a
plain file name is skipped, and a document that cannot be fetched fails the call.
`archive()` writes the zip only: it holds the documents itself.
"""
import httpx
import pytest

from topolab import AsyncClient, Client
from topolab import _links
from topolab.errors import TopolabError

pytestmark = pytest.mark.respx(assert_all_called=False)

BASE = "https://api.topolab.nl"
TABLE = "dining_drinking_mcdonalds"
LINK = f"{BASE}/v1/dataset/{TABLE}/exports"
HOST = "storage.googleapis.com"
PREFIX = f"/platform-staging-datasets/exports/{TABLE}/2026-12/standard/20261202T020000Z-a1b2c3d4-w1"
QUERY = "?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Expires=600&X-Goog-SignedHeaders=host&X-Goog-Signature=5f2d0c9e"
FILE_PATH = f"{PREFIX}/{TABLE}.csv"
COLUMNS_PATH = f"{PREFIX}/columns.json"
NOTICE_PATH = f"{PREFIX}/notices/osm.txt"
CSV = b"location_name,city\nMcDonald's Amsterdam Centraal,Amsterdam\n"
COLUMNS = b'{"tier":"standard","columns":[{"name":"location_name"},{"name":"city"}]}'
NOTICE = b"OpenStreetMap contributors, ODbL 1.0\n"


def ready(documents) -> dict:
    return {"state": "ready", "url": f"https://{HOST}{FILE_PATH}{QUERY}", "expiresAt": "2026-12-03T10:10:00.000Z",
            "filename": f"{TABLE}.csv", "bytes": len(CSV), "tier": "standard", "month": "2026-12",
            "build": "7d3f6c2a-1b4e-4c8d-9a0f-5e6b7c8d9e0f", "documents": documents}


DOCUMENTS = {"columns": f"https://{HOST}{COLUMNS_PATH}{QUERY}",
             "notices": [{"name": "osm.txt", "url": f"https://{HOST}{NOTICE_PATH}{QUERY}"}]}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(_links, "_sleep", lambda seconds: None)


def routes(respx_mock, notice=None):
    file = respx_mock.get(host=HOST, path=FILE_PATH).mock(return_value=httpx.Response(200, content=CSV))
    columns = respx_mock.get(host=HOST, path=COLUMNS_PATH).mock(return_value=httpx.Response(200, content=COLUMNS))
    notices = respx_mock.get(host=HOST, path=NOTICE_PATH).mock(return_value=notice or httpx.Response(200, content=NOTICE))
    return file, columns, notices


def test_download_writes_the_documents_beside_the_file_without_the_key(tmp_path, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready(DOCUMENTS)))
    _, columns, notices = routes(respx_mock)
    out = tmp_path / "mcdonalds.csv"

    Client(api_key="tlb_test_key", base_url=BASE).dataset(TABLE).download(str(out), format="csv")

    assert out.read_bytes() == CSV
    assert (tmp_path / "mcdonalds.csv.columns.json").read_bytes() == COLUMNS
    assert (tmp_path / "mcdonalds.csv.notices" / "osm.txt").read_bytes() == NOTICE
    for route in (columns, notices):
        sent = route.calls.last.request
        assert "x-api-key" not in sent.headers
        assert str(sent.url).endswith(QUERY)


def test_a_notice_whose_name_is_not_a_plain_file_name_is_skipped(tmp_path, respx_mock):
    unsafe = {"columns": None, "notices": [{"name": "../escape.txt", "url": f"https://{HOST}{NOTICE_PATH}{QUERY}"}]}
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready(unsafe)))
    _, columns, notices = routes(respx_mock)
    out = tmp_path / "mcdonalds.csv"

    Client(api_key="tlb_test_key", base_url=BASE).dataset(TABLE).download(str(out), format="csv")

    assert out.read_bytes() == CSV
    assert not (tmp_path / "escape.txt").exists()
    assert not (tmp_path / "mcdonalds.csv.columns.json").exists()
    assert notices.call_count == 0 and columns.call_count == 0


def test_a_document_that_cannot_be_fetched_fails_the_call(tmp_path, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready(DOCUMENTS)))
    routes(respx_mock, notice=httpx.Response(403, content=b"<Error>SignatureDoesNotMatch</Error>"))

    with pytest.raises(TopolabError) as raised:
        Client(api_key="tlb_test_key", base_url=BASE, max_retries=0).dataset(TABLE).download(str(tmp_path / "m.csv"), format="csv")
    assert "X-Goog-Signature" not in str(raised.value)


def test_archive_writes_the_zip_only(tmp_path, respx_mock):
    body = ready(DOCUMENTS)
    body["url"] = f"https://{HOST}{PREFIX}/{TABLE}_2026-12.csv.zip{QUERY}"
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=body))
    respx_mock.get(host=HOST, path=f"{PREFIX}/{TABLE}_2026-12.csv.zip").mock(return_value=httpx.Response(200, content=b"PK\x03\x04"))
    _, columns, notices = routes(respx_mock)
    out = tmp_path / "december.zip"

    Client(api_key="tlb_test_key", base_url=BASE).dataset(TABLE).archive(str(out), month="2026-12", format="csv")

    assert out.read_bytes() == b"PK\x03\x04"
    assert columns.call_count == 0 and notices.call_count == 0
    assert sorted(path.name for path in tmp_path.iterdir()) == ["december.zip"]


async def test_async_download_writes_the_documents_beside_the_file(tmp_path, respx_mock):
    respx_mock.post(LINK).mock(return_value=httpx.Response(200, json=ready(DOCUMENTS)))
    routes(respx_mock)
    out = tmp_path / "x.csv"

    async with AsyncClient(api_key="tlb_test_key", base_url=BASE) as tl:
        await tl.dataset(TABLE).download(str(out), format="csv")

    assert (tmp_path / "x.csv.columns.json").read_bytes() == COLUMNS
    assert (tmp_path / "x.csv.notices" / "osm.txt").read_bytes() == NOTICE
