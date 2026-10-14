# Database and Auth Design (final)

Moves storage from local JSON files to **PostgreSQL via SQLAlchemy** (a managed cloud database in production) and adds user authentication. Everything was built and verified locally first, then deployed.

## Principles
- **The database is the single source of truth.** Apart from the **admin account and API keys (which come from environment variables)**, all data lives in the database.
- **Scenarios live only in the database.** Users create them through the authoring page or API; database initialization **does not seed any demo scenarios**. `scenarios/*.json` are developer reference samples only and are never read at runtime.
- **Soft delete**: rows are never physically deleted; an `is_active` column marks them active or inactive, and queries default to `is_active=true`.
- **PostgreSQL everywhere: local, tests and cloud** (identical dev/prod behavior, no SQLite). Locally, `docker-compose.yml` starts Postgres on host port **5433** (to avoid a native Postgres on 5432); in the cloud it is a managed instance. `DATABASE_URL` switches between them. Start the local database with `docker compose up -d --wait`.
- Database column names are English (friendly to drivers, tools and Alembic); JSON columns hold Pydantic model dumps.

## Three tables
**users**: `id` (PK) · `username` (unique) · `password_hash` (bcrypt) · `is_admin` (bool) · `is_active` (bool, soft delete) · `created_at`

**scenarios**: `id` (int PK) · `title` · `author_id` (FK users) · `visibility` (`private` / `published`, default `private`) · `content` (JSON = the whole `Scenario`) · `is_active` · `created_at` / `updated_at`

**games** (play history, **always private**): `id` (str PK, UUID) · `user_id` (FK users) · `scenario_id` (FK scenarios, nullable) · `state` (JSON = the whole `Session`) · `turn_count` / `ended` (for list views) · `is_active` · `created_at` / `updated_at`

Relationships: a user has many scenarios (as author) and many games (as owner); a scenario has many games (as their source). A game embeds its full `Session`, so it stays playable even after its scenario is soft-deleted.

## Permissions and visibility
| Operation | Rule |
|---|---|
| List scenarios | `published` or `author_id = me`; **admins see all** |
| Read a scenario | Anyone can read `published`; `private` only the author or an admin |
| Update / delete a scenario | Author or admin only (delete = soft delete, `is_active=false`) |
| List / read / delete games | Only `user_id = me`, or an admin (games are always private) |
| **Admin** | Sees and manages **all** scenarios and play histories; **when an admin is logged in, the frontend shows each item's owner (username)** |

## Auth
- Register: `POST /api/auth/register {username, password}` (open self-service sign-up; username 3-32 characters, password at least 6) -> bcrypt hash -> issue a JWT.
- Log in: `POST /api/auth/login` -> issue a **JWT** (contains `user_id` and `is_admin`, signed with `JWT_SECRET`, 7-day TTL, no refresh token).
- `GET /api/auth/me` -> the current user (used by the frontend to probe login state and to read `is_admin`, which decides whether owners are shown).
- Requests send `Authorization: Bearer <jwt>`, which **replaces the old shared `X-App-Password` gate**. Public endpoints: `/api/health`, `/api/auth/register`, `/api/auth/login`.
- The admin is an ordinary row in the users table with `is_admin=true`, seeded idempotently at startup from `ADMIN_USERNAME` / `ADMIN_PASSWORD`.
- Logout = the frontend discards the token. The token is kept in localStorage and sent as a Bearer header (accepting the XSS tradeoff).

## Environment variable changes
- **Removed** `APP_PASSWORD` (superseded by auth).
- **Added** `DATABASE_URL`, `JWT_SECRET`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
- Kept the LLM key, `LLM_API_KEY` (formerly a provider-specific name).

## Architecture notes
- **Removed the in-memory `game_store._cache`.** With the database as the single source of truth, each request loads from the database, modifies, and saves back; streaming endpoints save after every beat. This is what keeps multiple container instances consistent, which is exactly why the cloud deployment needs a database.
- Concurrent edits to the same game are last-write-wins (turn-based and single-player, so no optimistic locking yet).
- **Alembic from day one**: every schema change has a migration and no data is lost.

## Build order (local, verified step by step)
1. **Database foundation**: `db.py` (engine / Session / Base / `get_db`) + `models_db.py` (User / Scenario / Game) + `DATABASE_URL` in config + the first Alembic migration.
2. **Auth**: register / login / me + JWT + `current_user` / `current_admin` dependencies + admin seeding.
3. **Scenarios -> database**: list / get / create / update / delete + visibility and ownership (users create their own scenarios in the database; no demo scenarios are seeded).
4. **Games -> database**: remove `_cache`; create / get / save / list / delete scoped to the user.
5. **Frontend**: login / register + Bearer header + integer ids + owner display for admins.
6. **Tests**: a DB fixture (test database on the local Docker Postgres) + auth fixtures, rewrite `test_api` / `test_scenario`; CI adds a `services: postgres` container so tests run on the same engine as production.
7. (Later) managed cloud database + new environment variables + deployment.

## Follow-up features (implemented)
- **Copy a scenario**: `POST /api/scenarios/{sid}/copy`: checks that the caller can read it (published / own / admin), then clones it as the caller's own `private` copy (title suffixed with "(copy)"). No new table.
- **Change password**: `POST /api/auth/change-password {old_password, new_password}`: verifies the old password, then stores the new hash. JWTs are stateless and don't contain the password, so existing tokens remain valid until they expire.
- **Feedback chat** (fourth table): **feedback_messages**: `id` (PK) · `thread_user_id` (FK users; the regular user the thread belongs to) · `sender_is_admin` (bool) · `body` (text) · `is_read` (bool; whether an admin has read the user's message) · `created_at`. Each regular user has one thread, addressed to "the admins" collectively.
  - User side: `GET/POST /api/feedback` (`current_user`, only their own thread). Admin side: `GET /api/feedback/threads` (list + unread counts), `GET /api/feedback/{user_id}` (read and mark as read), `POST /api/feedback/{user_id}` (reply), all behind `current_admin`. **All authorization is enforced in the backend; the frontend only shows or hides entry points by role, for UX.**
  - Frontend: a dedicated page for users at `/feedback` and for admins at `/admin/feedback` (user list on the left, conversation on the right), sharing a `ChatThread` component. Messages load on open and then poll every 8 seconds (no WebSocket; enough at this scale).
  - Migration `f159fc1ec85e_feedback_messages`; in the cloud the table is created automatically by `alembic upgrade head` at container startup.
