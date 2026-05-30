# Contributing to topolab (Python)

Thanks for your interest in improving the Topolab Python SDK.

## Development setup

```bash
uv venv
uv pip install -e ".[dev,geo]"
```

## Tests

```bash
uv run pytest -q          # full suite (sync, async, geo, conventions, examples)
```

Tests mock HTTP with [`respx`](https://lundberg.github.io/respx/) and read shared
golden fixtures from the sibling [`topolab-sdk-spec`](../topolab-sdk-spec)
repository — keep both checked out side by side.

## Conventions

The public surface (method names, parameters, error types) is defined in
`topolab-sdk-spec/conventions.yaml` and enforced by `tests/test_conventions.py`.
If you change the public API, update the convention file in the same change so
all three SDKs stay aligned.

## Before opening a PR

- `uv run pytest -q` passes
- `uv build` produces a wheel without errors
- New behaviour has a test
- Public changes are reflected in `conventions.yaml` and the README

## Releasing

Releases are gated until publishing is enabled. The PyPI workflow uses OIDC
trusted publishing and triggers on a published GitHub release.
