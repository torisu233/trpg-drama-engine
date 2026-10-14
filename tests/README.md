# Testing strategy (tests/)

A deterministic pytest suite that never calls a real LLM. Run it with `pip install -r requirements-dev.txt`, then `pytest`.

**Database**: the integration tests (`test_api`) run against a **real PostgreSQL** instance (same engine in dev and prod) using a dedicated test database, `trpg_test`, and never touch the real saves in the local `trpg` database. Locally, start Postgres first with `docker compose up -d --wait` (host port 5433); CI uses a Postgres service container (see the `test` job in `.github/workflows/ci.yml`). The pure-logic tests (engine / flow / scenario / LLM contract) **do not touch the database** and run without Postgres. Override the connection with `TEST_DATABASE_URL`.

## Philosophy in one line
**Test the deterministic machinery thoroughly; deliberately don't unit-test what the LLM writes.** That line is drawn on purpose, not because the code is untestable. Prompt quality is checked by hand with live diagnostic scripts, outside CI. What *is* tested is the **boundary**: whatever schema-valid output the LLM returns, the engine must handle it correctly. Per-module coverage is reported by `pytest --cov` (enabled by default in `pyproject.toml`).

## What is tested and what isn't
| Layer | Modules | Approach |
|---|---|---|
| Deterministic core | engine / models / scenario / game_store | Unit + integration |
| Web layer | main / routes (non-streaming parts) | Integration (TestClient + real Postgres) |
| Auth | auth (JWT / bcrypt) / visibility / ownership | Integration (create users, issue tokens, hit endpoints) |
| LLM boundary | flow + engine driven by a `FakeLLM` | Contract test: a full beat with adversarial but schema-valid LLM output |
| LLM agents | agents.py (prompts) | **Not unit-tested**; checked with live diagnostics |
| Orchestration | flow.py (per-beat / streaming calls to the LLM) | Per-beat maintenance tested, LLM calls isolated with `monkeypatch`; the full beat is covered by the contract test |
| Frontend | Vue | None yet (Vitest planned) |

## Files
- `conftest.py`: fixtures. `sess` (a fresh tavern `Session`, pure logic) / `client` (TestClient, does not enter lifespan, so nothing is seeded) / `db` (direct DB session; truncates all tables before use) / `make_user`, `user_headers`, `admin_headers` (create users and issue JWTs) / `tavern_scenario` (stores a published tavern scenario and returns its id plus owner headers). The session-scoped `_db_ready` creates the test database and tables once. At import it sets a dummy `LLM_API_KEY`, an empty `ADMIN_PASSWORD`, and the test `DATABASE_URL`.
- `test_engine.py`: unit tests for the action bar / fog of war / two-axis checks (parametrized) / ledger deltas / TTL / structured log.
- `test_flow.py`: per-beat maintenance: summary compression and ledger consolidation (functions that would call the LLM are swapped out with `monkeypatch`).
- `test_scenario.py`: lossless scenario round-trip, plus author-agent merging (empty fields never wipe existing content).
- `test_llm_contract.py`: **LLM-boundary contract test.** A `FakeLLM` stands in for the real client (`backend/llm_client.py`) and returns output that is schema-valid but hostile: every character-keyed field uses character **names** instead of ids, `self:<name>` visibility, and keys for characters that don't exist. It drives a real beat end to end through `flow` (intent -> reaction -> adjudication -> apply -> narration -> distribution -> log) and asserts that nothing crashes or hangs, name-keyed deltas / speed / faction / perception / private narration land on the right character, `self:<name>` is normalized to `self:<id>`, and made-up keys are silently skipped. The fixture is deliberately not tavern-shaped (the player id is not `"player"`, ids differ from names) to force the name/id distinction. This test reproduces a class of production bugs (e.g. a `KeyError` when the LLM keyed perception by name) that the rest of the suite could not see.
- `test_api.py`: integration: health / register, login, me (with validation) / change password / scenario CRUD, visibility, ownership, copy / new-game snapshot (fog, panels, log) / game ownership (404, no existence leak) / AI move suggestions / feedback chat. Covers the 401 / 403 / 404 authorization boundaries.

## Techniques and gotchas
- **Fixtures** are injected by parameter name; don't import them manually. They default to **function scope** (a fresh one per test, no cross-contamination); don't switch to session scope for speed.
- **`@pytest.mark.parametrize`** turns several inputs into a table, each reported separately; use `ids=` to give cases readable names.
- **`monkeypatch`** stubs are **reverted automatically after each test**. Use it for any module-level state (e.g. `config` constants or the cached LLM client in `deps`); setting `os.environ` directly leaks into other tests.
- **`TestClient`** runs the real app in-process (middleware + routes) without starting a server. It is used **without `with`**, so lifespan never runs and nothing is seeded; tests own their data.
- **DB isolation**: a dedicated test database, and every DB test that takes the `db` fixture starts with `TRUNCATE ... RESTART IDENTITY CASCADE`, giving a clean slate and predictable auto-increment ids. **No** SQLite (it behaves differently from production Postgres) and **no** transaction rollback (streaming endpoints open their own connections, and cross-connection rollback is unreliable).
- **Auth fixtures**: the `make_user(admin=?)` factory writes the user directly and issues a Bearer token via `create_token`, for regular or admin users. Authorization tests must cover all three boundaries: 401 (not logged in), 403 (not allowed) and 404 (existence not leaked).
- **Use `is` only for `True` / `False` / `None`** (singleton identity), never to compare strings or numbers.
- **Randomness** (`roll_luck`): don't test the outcome; test the deterministic branches around it.
- Module-level shared state (such as the LLM client cached in `deps`) must be restored after changes; use `monkeypatch`. Games are stored purely in the database, with no in-memory cache.

## Maintenance workflow (when the project changes often)
1. Change code -> `pytest` -> is anything red?
2. If so, ask one question: **"Did I change this behavior on purpose?"**
   - No -> it's a real regression -> **fix the code** and leave the test alone.
   - Yes -> the old expectation is out of date -> **update the test** (in the **same commit** as the code).
   - The behavior didn't change but the test is red -> the test is coupled to implementation details -> rewrite it to check behavior.
3. **Never** delete or weaken a test that exposes a real bug just to get green.
4. New feature -> add tests in the same change; snapshot shape changes -> update the `test_api` assertions; prompt changes -> no pytest changes (run the live diagnostics); scenario data changes -> no test changes (tests use the `scene.py` fixture, decoupled from playable scenarios).

Shortcuts: `pytest tests/test_engine.py` (one file), `pytest -k fog` (by name), `pytest -x` (stop at first failure), `pytest --lf` (rerun last failures). Coverage is reported on every run (`addopts` in `pyproject.toml` enables `--cov=backend`).
