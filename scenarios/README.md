# scenarios/: developer reference samples (**not** a data source; never read at runtime)

All **scenarios, games, users and feedback messages live in the database** (local Docker PostgreSQL on port 5433, or the managed cloud database when it was deployed). `game_store.py` states it explicitly: **the database is the single source of truth; there is no in-memory cache.**

No code reads the `*.json` files in this directory. On first startup the database is seeded with a single admin account (from the `ADMIN_*` environment variables) and **no demo scenarios**. Scenarios are always created by users through the **authoring page or API** and stored in the database.

The files here are purely **reference samples for developers (and AI assistants)** that show the full JSON shape of a scenario. To actually play one, save its content to the database through the authoring page or API; leaving it in this directory does nothing.

## Full field reference
[`example-fantasy-broken-sword-inn.json`](example-fantasy-broken-sword-inn.json) deliberately **uses every field**, so it works as a template for writing scenarios:
- `CharCard`: every role-play and adjudication field, including `directive` (a user-written, highest-priority character rule that is only fed to the character agent);
- `CharLedger`: `conditions / status_effects / carried / items / posture / speed / perception / gauge`;
- `Condition`: `severity / gates / source / lifetime / ttl / created_turn`, plus all four visibility forms:
  `public / gm / faction:<faction> / self:<char_id>`;
- every `Item` field, `faction_private.<faction>.plans`, and all three factions (`ally` / `enemy` / `neutral`).

`backend/models.py` is the authoritative definition of these fields. Renaming a field means updating models, engine, scenario, agents, the frontend and the database together.
