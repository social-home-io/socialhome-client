# AGENTS.md — socialhome-client

AI agent instruction file. Read before editing. Canonical spec:
`spec_work.md` §6 in the Social Home meta-repo.

### Architecture rules
- Python 3.13 floor (HA Core runs on 3.13 — do not raise it).
- Never import from `social_home` (core). Only runtime dep: `aiohttp>=3.9`.
- All I/O is async; no `time.sleep`, no blocking calls.
- All imports at the top of the file; only `if TYPE_CHECKING:` exceptions.
- Domain exceptions descend from `SHClientError`. Every HTTP helper
  raises `SHAuthError` (401), `SHNotFoundError` (404), or
  `SHClientError` (other non-2xx).
- Responses deserialise into typed `@dataclass` objects from
  `models.py`. No raw `dict`s in the public return types.
- The public surface is documented in spec §6.1. New methods need a
  spec update first.

### Testing
- Plain `async def test_xxx()` functions; no `TestXxx` classes.
- One test file per module, matching the tree.
- `aioresponses` for HTTP stubbing; a fake WS for `ws_manager`.
- Coverage gate: 85 % branch.

### Keep docs in sync
Docs live in `docs/`. Ship the matching doc update in the same
commit:
- New / renamed / removed public method on `SocialHomeClient` →
  update the resource table in `docs/architecture.md`. Touch
  `README.md`'s usage block if the example references the method.
- Changed `SocialHomeWsManager` reconnect schedule, heartbeat, or
  connect timeout → update the constants block + sequence diagram
  in `docs/architecture.md`.
- Changed the exception hierarchy (new `SHClient*Error`, changed
  status mapping) → update `docs/architecture.md` and the
  exception-hierarchy section in `docs/principles.md`.
- Test-strategy change (coverage gate, mock approach, shared
  fixtures) → `docs/testing.md`.
- §6 invariant touched (raise the Python floor, add a runtime
  dependency, import from core, drop type hints from a public
  surface) → `docs/principles.md`, **and** flag in the PR
  description for explicit reviewer sign-off.
- New top-level doc file under `docs/` → link from `docs/README.md`
  and from the repo-root `README.md`.

### File locations
- Library code: `socialhome_client/`
- Tests: `tests/` (mirrors the module tree)
- Docs: `docs/` (principles, architecture, testing)
