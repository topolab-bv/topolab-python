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

## Retries

Transient failures (`429`, `500`, `502`, `503`, `504`) and network errors are
retried with exponential backoff, honouring a `Retry-After` header or
`retryAfter` body field when present. `max_retries` (default 3) is the number of
retries **after** the first attempt.
