# Test strategy

How tests are organised, what coverage is gated, and how mocks
work. Distilled from §6 / §27 of `spec_work.md` plus the existing
`tests/` tree.

## Principles

- **Branch coverage gate: 85 %.** Configured in `pyproject.toml`
  (`[tool.coverage.report] fail_under = 85`). Lower than the core's
  90 % because this library is mostly thin wrappers — the per-method
  branches are shallow and the integration's tests cover end-to-end
  behaviour.
- **`pytest` only; no `unittest.TestCase`.** Async tests use
  `pytest-asyncio` with `asyncio_mode = "auto"`, so `@pytest.mark.asyncio`
  is implicit.
- **Plain `async def test_xxx()` functions, no `TestXxx` classes.**
  One test file per module, mirroring the source tree.
- **No real network, no real sockets.** HTTP is stubbed with
  `aioresponses`; WebSocket uses a hand-written fake
  `aiohttp.ClientWebSocketResponse`. CI never hits a live HFS.
- **Tests mock at the test boundary.** Production code never carries
  env-var-gated stubs or test-only branches. Mocks live in
  `conftest.py` or per-test fixtures, not in `socialhome_client/`.

## Layout

```
tests/
├── __init__.py
├── conftest.py            shared fixtures (fake ws, aioresponses helpers)
├── test_client.py         every resource method + HTTP helper
├── test_ws_manager.py     reconnect, heartbeat, frame dispatch
├── test_models.py         from_api() round-trips
└── test_exceptions.py     status → exception mapping
```

The tree mirrors `socialhome_client/`. A new module needs a matching
`tests/test_<module>.py`; a new resource method needs at least one
test in `test_client.py`.

## Stubbing HTTP with `aioresponses`

`aioresponses` registers handlers that intercept `aiohttp.ClientSession`
calls. The pattern:

```python
async def test_me_get(client_with_session):
    with aioresponses() as m:
        m.get(
            "http://example/api/me",
            payload={"user_id": "u1", "username": "alice", ...},
        )
        user = await client_with_session.me.get()
    assert user.username == "alice"
```

`conftest.py` provides `client_with_session` — a `SocialHomeClient`
already bound to a fixed base URL and token, with the session
opened. Tests don't touch `aiohttp.ClientSession` directly.

## Stubbing the WebSocket

`tests/test_ws_manager.py` ships a hand-written
`FakeClientWebSocketResponse` that implements the `__aiter__` /
`receive_json` / `send_json` / `close` surface the manager actually
uses. The fake exposes hooks to inject frames, simulate close, and
assert what was sent — so the reconnect schedule
(`5s → 15s → 30s → 60s` cap) and frame-dispatch behaviour can be
exercised without `asyncio.sleep` or sockets.

## Running locally

```sh
pip install -e .[dev]
pytest                                   # full suite, gated at 85 %
pytest -k test_ws_manager                # one file
ruff check socialhome_client/ tests/
mypy socialhome_client/
```

`pre-commit install` runs the same set on every commit.

## Releasing

CalVer tag without a `v` prefix triggers the GitHub Actions release
workflow:

```sh
git tag 2026.4.22
git push origin 2026.4.22
```

The action runs the test suite, builds the wheel + sdist, and
publishes to PyPI via OIDC trusted publishing. Don't edit the
version in `pyproject.toml` — it's dynamic via `hatch-vcs` and
sourced from the tag.

## Spec references

- §6 — repository overview (client design)
- §27 — core's test strategy (this library follows the same
  principles, with a lower coverage gate)
- §27.1 — testing principles (no real network, no real disk in
  unit tests)
