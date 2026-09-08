# Changelog

## Unreleased
- `tl.datasets.owned()` and `tl.datasets.iter_owned()` — list and page the datasets
  the organization licences, with absolute `links` to current files and archives.
- `ds.archives()` and `ds.archive(path, month=, format=)` — list monthly archives
  and stream one to disk. `month` accepts `latest`, `YYYY-MM` or `YYYY-MM-DD` and
  is validated as a real calendar value before the request is sent.
- `ds.coordinates(limit=, offset=)` — coordinate rows plus the paging counts the
  route returns as `X-Total-Count` / `X-Returned-Count` / `X-Offset` headers.
  `latitude`/`longitude` stay the fixed-scale decimal strings the API returns; a
  numeric value degrades to its string form instead of failing the page.
- `tl.sql(query, max_rows=)` — read-only SELECT across licensed datasets
  (Enterprise `sql-access` entitlement).
- New models: `OwnedDatasets`, `OwnedDataset`, `OwnedDatasetLinks`, `Archive`,
  `CoordinatePage`, `CoordinateRow`, `SqlResult`.
- New error `QueryTimeoutError` (408).
- Fixed: add-on 403s were never recognised — the message pattern stopped at the
  hyphen in identifiers like `api-access`, so every add-on error surfaced as
  `AccessDeniedError`. Both message shapes now normalise to the add-on slug.
- Fixed: `request_id` falls back to the envelope's `requestId` when the
  `X-Request-Id` header is absent.
- Every addition has an `AsyncClient` twin.

## [0.1.0] - initial preview
- Sync `Client` and async `AsyncClient`.
- Dataset catalog, metadata, sample, bulk GeoJSON, streaming download.
- OGC spatial `items()` with slug→collection resolution and `iter_items()` pagination.
- Optional `to_geodataframe()` via the `[geo]` extra.
- Typed error hierarchy with retry/backoff.
