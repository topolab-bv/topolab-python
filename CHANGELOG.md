# Changelog

## [0.2.0]
- **Errors expose `status`, `code` and `details`.** The engine's error envelope
  now carries a string `code` when the error has its own (upper-snake, such as
  `SPENDING_LIMIT_EXCEEDED`), and otherwise the numeric HTTP status, so `code` no
  longer always equals the status.
  - `TopolabError.code` is `str | int` (exported as `topolab.ErrorCode`); it falls
    back to the HTTP status when the body has no usable code.
  - `TopolabError.status` is the HTTP status of the response, always an `int`.
    `status_code` is kept as an alias, so existing code keeps working.
  - `TopolabError.details` is the envelope's allow-listed `details` dict, or
    `None`.
  - Error classes are still chosen from the HTTP status: a 403 with
    `SPENDING_LIMIT_EXCEEDED` is an `AccessDeniedError`.
  - `docs/errors.md` lists the known string codes and what they mean.
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
