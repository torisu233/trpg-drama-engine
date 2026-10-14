"""Global settings and balance constants (prototype)."""
import os
from dotenv import load_dotenv

load_dotenv()

# ── action_bar ──
ACTION_THRESHOLD = 20          # a character may act once their gauge reaches this
SPEED_PLAYER = 7               # player default is slightly higher
SPEED_FAST = 6
SPEED_NORMAL = 5
SPEED_SLOW = 4
SPEED_HEAVY_WOUND = 3          # seriously wounded
SPEED_DYING = 2               # dying / pinned down
SPEED_DOWN = 0                # unconscious / tightly bound (never gets a turn)

# ── rolling summary ──
KEEP_RECENT = 5               # window W: when memory reaches 2W, fold the oldest W entries into the summary

# ── ledger consolidation ──
CONSOLIDATE_THRESHOLD = 4     # once a list has this many public, persistent entries, an LLM pass merges near-duplicates
CONSOLIDATE_THRESHOLD_STATE = 2  # character conditions stack near-duplicates more easily (one person's state escalating), so merge earlier; scene lists stay at 4 (many independent facts, too low a threshold over-merges)

# ── luck oracle (rolled only for contested actions; hidden from characters) ──
LUCK_TIERS = ["bad_luck", "even", "good_luck"]
LUCK_WEIGHTS = [0.25, 0.50, 0.25]

# ── LLM provider (OpenAI-compatible; currently DeepSeek) ──
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")   # DeepSeek V4 Flash (non-thinking); the old name is deprecated after 2026/07/24, switch to deepseek-v4-flash
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))
TEMP_ADJUDICATOR = 0.35       # adjudication should be stable and auditable
TEMP_NARRATOR = 0.9           # narration should be vivid
TEMP_CHARACTER = 0.85         # characters should have personality

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── database (PostgreSQL both locally and in the cloud, for consistent behavior) ──
# local default connects to the PG started by docker-compose; in the cloud set DATABASE_URL to the managed instance
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://trpg:trpg@localhost:5433/trpg")

# ── Auth ──
JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-in-production-please")   # ≥32 bytes; always set a truly random value in the cloud
JWT_TTL_DAYS = int(os.getenv("JWT_TTL_DAYS", "7"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")                 # admin is seeded only if set
