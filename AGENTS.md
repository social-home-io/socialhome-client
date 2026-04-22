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
- Changed a public method signature? Update \`README.md\`'s usage
  block if the example touches the method, and update any CLAUDE.md
  notes that cite it.
- Changed the exception hierarchy? Update CLAUDE.md's "Hard rules".

### File locations
- Library code: `socialhome_client/`
- Tests: `tests/` (mirrors the module tree)
