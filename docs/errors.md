# Errors

Every failure raises a subclass of `TopolabError`, so you never parse raw JSON.

| Error | When |
|---|---|
| `AuthenticationError` | missing or invalid API key (401) |
| `AddonRequiredError` | key lacks the add-on — `.addon` names it (403) |
| `AccessDeniedError` | dataset not accessible to your organization (403) |
| `InsufficientCreditsError` | not enough credits — `.required` / `.available` (402) |
| `NotFoundError` | unknown dataset or collection (404) |
| `ValidationError` | invalid request parameters (400/4xx) |
| `QueryTimeoutError` | SQL query exceeded the server statement timeout (408) |
| `RateLimitError` | rate limited — `.retry_after`, retried automatically (429) |
| `ConfigurationError` | client misconfiguration (e.g. missing/invalid key or base URL) |
| `ServerError` | upstream error (5xx), retried automatically |
| `ConnectionError` | network failure / timeout after retries |

```python
from topolab import Client, AddonRequiredError

tl = Client(api_key="tlb_prod_...")
try:
    tl.dataset("nl-domino-poi").to_geojson()
except AddonRequiredError as e:
    print("Your key needs:", e.addon)
```

## The error envelope

Every failure carries the same body, produced by the engine's global exception
filter:

```json
{ "code": 403, "message": "This endpoint requires the api-access add-on",
  "path": "/v1/dataset/{table}/files/geojson", "method": "GET",
  "time": "2026-09-08T23:42:15.819Z", "requestId": "25c2a6a1…" }
```

There is **no `statusCode` field** — the SDK maps errors from the HTTP status,
never from a body field. `request_id` comes from the `X-Request-Id` header and
falls back to the body's `requestId`; quote it in support requests.

## Add-on requirements

A 403 whose message names an add-on becomes an `AddonRequiredError`, and
`.addon` is the normalised hyphenated slug (`api-access`, `gis-access`,
`archived-data`, `high-value-data`, `sql-access`). Both message shapes the API
emits normalise to the same value:

| Message | `.addon` |
|---|---|
| `This endpoint requires the api-access add-on` | `api-access` |
| `Archive access requires the Archived Data add-on. Please upgrade to access historical data.` | `archived-data` |

Any other 403 on a data route is an `AccessDeniedError` — the dataset is unknown
to you, or not licensed.

## Archives: 400 vs 404

An impossible `month` (`2026-13`, `2026-07-99`, `2026-02-29`) never reaches the
network: `archive()` validates it as a calendar value and raises `ValueError`.
The same value sent by hand answers **400**. A **404** means no archive is
available for a real month — including months outside your retention window and
months that have not started, which are deliberately indistinguishable.

## Retries

Transient failures (`429`, `500`, `502`, `503`, `504`) and network errors are
retried with exponential backoff, honouring a `Retry-After` header or
`retryAfter` body field when present. `max_retries` (default 3) is the number of
retries **after** the first attempt.
