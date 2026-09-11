import httpx
import respx
import pytest
from topolab import Client
from topolab.errors import AddonRequiredError, NotFoundError, QueryTimeoutError
from topolab.models import CoordinateRow

BASE = "https://api.topolab.nl"
TABLE = "business_professional_services_autocrew"


def client() -> Client:
    return Client(api_key="k", base_url=BASE)


def owned_page(tables, total, limit, offset):
    return {"items": [{"table": t, "name": t, "links": {}} for t in tables],
            "total": total, "limit": limit, "offset": offset}


# --- owned ---

@respx.mock
def test_owned_page(fx_owned):
    route = respx.get(f"{BASE}/v1/dataset/owned").mock(
        return_value=httpx.Response(200, json=fx_owned("owned.json")))
    page = client().datasets.owned(limit=2)
    assert page.total == 193 and page.limit == 2 and page.offset == 0
    assert len(page.items) == 2
    first = page.items[0]
    assert first.table == TABLE
    assert first.recordCount == 119
    assert first.latestArchiveMonth == "2026-07"
    assert first.archiveMonthsAvailable == 11
    assert "{format}" in first.links.current
    assert "{format}" in first.links.latestArchive
    assert first.links.archives.endswith("/archives/list")
    assert route.calls.last.request.url.params["limit"] == "2"


@respx.mock
def test_owned_omits_unset_params():
    route = respx.get(f"{BASE}/v1/dataset/owned").mock(
        return_value=httpx.Response(200, json=owned_page(["a"], 1, 50, 0)))
    client().datasets.owned()
    assert route.calls.last.request.url.params == httpx.QueryParams()


@pytest.mark.parametrize("limit,offset", [(0, None), (201, None), (None, -1)])
def test_owned_rejects_out_of_range(limit, offset):
    with pytest.raises(ValueError):
        client().datasets.owned(limit=limit, offset=offset)


@respx.mock
def test_iter_owned_pages_without_repeats_or_gaps():
    route = respx.get(f"{BASE}/v1/dataset/owned").mock(side_effect=[
        httpx.Response(200, json=owned_page(["a", "b"], 5, 2, 0)),
        httpx.Response(200, json=owned_page(["c", "d"], 5, 2, 2)),
        httpx.Response(200, json=owned_page(["e"], 5, 2, 4)),
    ])
    tables = [d.table for d in client().datasets.iter_owned(page_size=2)]
    assert tables == ["a", "b", "c", "d", "e"]
    assert len(set(tables)) == 5
    assert [c.request.url.params["offset"] for c in route.calls] == ["0", "2", "4"]


@respx.mock
def test_iter_owned_stops_when_total_reached():
    route = respx.get(f"{BASE}/v1/dataset/owned").mock(
        return_value=httpx.Response(200, json=owned_page(["a", "b"], 2, 2, 0)))
    assert len(list(client().datasets.iter_owned(page_size=2))) == 2
    assert route.call_count == 1        # total reached; no empty trailing page


@respx.mock
def test_iter_owned_stops_on_short_page():
    # total over-reports; a short page still terminates the loop
    route = respx.get(f"{BASE}/v1/dataset/owned").mock(
        return_value=httpx.Response(200, json=owned_page(["a"], 99, 2, 0)))
    assert [d.table for d in client().datasets.iter_owned(page_size=2)] == ["a"]
    assert route.call_count == 1


@respx.mock
def test_iter_owned_total_limit():
    respx.get(f"{BASE}/v1/dataset/owned").mock(
        return_value=httpx.Response(200, json=owned_page(["a", "b"], 99, 2, 0)))
    assert len(list(client().datasets.iter_owned(page_size=2, total_limit=1))) == 1


# --- archives ---

@respx.mock
def test_archives_newest_first(fx_owned):
    respx.get(f"{BASE}/v1/dataset/{TABLE}/archives/list").mock(
        return_value=httpx.Response(200, json=fx_owned("archives.json")))
    archives = client().dataset(TABLE).archives()
    months = [a.month for a in archives]
    assert len(archives) == 11
    assert months[0] == "2026-07"
    assert months == sorted(months, reverse=True)
    assert "shp" in archives[0].formats
    assert archives[0].archiveDate == "2026-07-01"


@respx.mock
def test_archives_addon_error(fx):
    respx.get(f"{BASE}/v1/dataset/{TABLE}/archives/list").mock(
        return_value=httpx.Response(403, json=fx("error-403-addon-archive.json")))
    with pytest.raises(AddonRequiredError) as e:
        client().dataset(TABLE).archives()
    assert e.value.addon == "archived-data"


@respx.mock
def test_archive_streams_to_disk(tmp_path):
    route = respx.get(f"{BASE}/v1/dataset/{TABLE}/archives/latest/geojson").mock(
        return_value=httpx.Response(200, content=b"PK\x03\x04zip"))
    out = tmp_path / "a.zip"
    assert client().dataset(TABLE).archive(str(out)) == str(out)
    assert out.read_bytes() == b"PK\x03\x04zip"
    assert route.call_count == 1


@respx.mock
def test_archive_addresses_an_explicit_month(tmp_path):
    route = respx.get(f"{BASE}/v1/dataset/{TABLE}/archives/2026-07-15/csv").mock(
        return_value=httpx.Response(200, content=b"zip"))
    client().dataset(TABLE).archive(str(tmp_path / "a.zip"), month="2026-07-15", format="csv")
    assert route.call_count == 1


@respx.mock
def test_archive_missing_month_is_not_found(tmp_path, fx_owned):
    respx.get(f"{BASE}/v1/dataset/{TABLE}/archives/2026-01/csv").mock(
        return_value=httpx.Response(404, json=fx_owned("error-404-archive.json")))
    with pytest.raises(NotFoundError):
        client().dataset(TABLE).archive(str(tmp_path / "a.zip"), month="2026-01", format="csv")


@pytest.mark.parametrize("month", ["latest", "LATEST", "2026-07", "2026-07-15", "2024-02-29"])
def test_archive_accepts_valid_months(month, tmp_path):
    with respx.mock:
        route = respx.get(url__regex=rf"{BASE}/v1/dataset/{TABLE}/archives/.+/geojson").mock(
            return_value=httpx.Response(200, content=b"zip"))
        client().dataset(TABLE).archive(str(tmp_path / "a.zip"), month=month)
        assert route.call_count == 1


@pytest.mark.parametrize("month", [
    "2026-13", "2026-00", "2026-07-99", "2026-07-00", "2026-02-29",
    "julyish", "2026-7", "26-07", "2026-07-15T00:00:00", "", "latest ",
])
def test_archive_rejects_impossible_months(month, tmp_path):
    with pytest.raises(ValueError):
        client().dataset(TABLE).archive(str(tmp_path / "a.zip"), month=month)


def test_archive_rejects_unknown_format(tmp_path):
    with pytest.raises(ValueError):
        client().dataset(TABLE).archive(str(tmp_path / "a.zip"), format="xlsx")


# --- coordinates ---

@respx.mock
def test_coordinates_reads_paging_headers(fx_owned):
    rows = fx_owned("coordinates.json")
    route = respx.get(f"{BASE}/v1/dataset/{TABLE}/coordinates").mock(
        return_value=httpx.Response(200, json=rows, headers={
            "X-Total-Count": "119", "X-Returned-Count": "2", "X-Offset": "10"}))
    page = client().dataset(TABLE).coordinates(limit=2, offset=10)
    assert page.total == 119 and page.returned == 2 and page.offset == 10
    assert len(page.rows) == 2
    assert route.calls.last.request.url.params["limit"] == "2"


@respx.mock
def test_coordinates_keeps_lat_lon_as_strings(fx_owned):
    respx.get(f"{BASE}/v1/dataset/{TABLE}/coordinates").mock(
        return_value=httpx.Response(200, json=fx_owned("coordinates.json")))
    row = client().dataset(TABLE).coordinates().rows[0]
    assert row.latitude == "51.49638600" and row.longitude == "3.65532100"
    assert row.location["type"] == "Point"
    assert row.metadata["city"] == "Middelburg"


@respx.mock
def test_coordinates_without_headers_falls_back(fx_owned):
    respx.get(f"{BASE}/v1/dataset/{TABLE}/coordinates").mock(
        return_value=httpx.Response(200, json=fx_owned("coordinates.json")))
    page = client().dataset(TABLE).coordinates()
    assert page.total == 2 and page.returned == 2 and page.offset == 0


@respx.mock
def test_coordinates_with_unparseable_headers_falls_back(fx_owned):
    respx.get(f"{BASE}/v1/dataset/{TABLE}/coordinates").mock(
        return_value=httpx.Response(200, json=fx_owned("coordinates.json"), headers={
            "X-Total-Count": "many", "X-Returned-Count": "", "X-Offset": "nope"}))
    page = client().dataset(TABLE).coordinates()
    assert page.total == 2 and page.returned == 2 and page.offset == 0


@pytest.mark.parametrize("raw,expected", [
    ("51.49638600", "51.49638600"),   # what the API returns: fixed-scale decimal
    (51, "51"),                       # numeric response degrades, never raises
    (51.496386, "51.496386"),
])
def test_coordinate_row_tolerates_numeric_lat_lon(raw, expected):
    row = CoordinateRow.model_validate({"latitude": raw, "longitude": raw})
    assert row.latitude == expected and row.longitude == expected


@pytest.mark.parametrize("limit,offset", [(0, None), (50001, None), (None, -1)])
def test_coordinates_rejects_out_of_range(limit, offset):
    with pytest.raises(ValueError):
        client().dataset(TABLE).coordinates(limit=limit, offset=offset)


# --- sql ---

@respx.mock
def test_sql(fx_owned):
    route = respx.post(f"{BASE}/v1/sql/query").mock(
        return_value=httpx.Response(200, json=fx_owned("sql-result.json")))
    res = client().sql("SELECT city, count(*) n FROM t GROUP BY 1", max_rows=5)
    assert res.columns == ["city", "n"]
    assert res.rowCount == 2 and res.truncated is False
    assert res.rows[0]["city"] == "Amsterdam"
    assert res.datasets == [TABLE]
    import json
    body = json.loads(route.calls.last.request.content)
    assert body == {"sql": "SELECT city, count(*) n FROM t GROUP BY 1", "maxRows": 5}


@respx.mock
def test_sql_omits_max_rows_when_unset(fx_owned):
    route = respx.post(f"{BASE}/v1/sql/query").mock(
        return_value=httpx.Response(200, json=fx_owned("sql-result.json")))
    client().sql("SELECT 1")
    import json
    assert json.loads(route.calls.last.request.content) == {"sql": "SELECT 1"}


@respx.mock
def test_sql_requires_the_addon(fx_owned):
    respx.post(f"{BASE}/v1/sql/query").mock(
        return_value=httpx.Response(403, json=fx_owned("error-403-sql-access.json")))
    with pytest.raises(AddonRequiredError) as e:
        client().sql("SELECT 1")
    assert e.value.addon == "sql-access"


@respx.mock
def test_sql_timeout_maps_to_query_timeout():
    respx.post(f"{BASE}/v1/sql/query").mock(
        return_value=httpx.Response(408, json={"code": 408, "message": "Query exceeded the time limit"}))
    with pytest.raises(QueryTimeoutError):
        client().sql("SELECT pg_sleep(60)")
