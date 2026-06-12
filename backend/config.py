"""全域设置与平衡常数（原型）。"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── 行动条 ──
ACTION_THRESHOLD = 20          # 行动值达此即可行动
SPEED_PLAYER = 7               # 玩家预设略高
SPEED_FAST = 6
SPEED_NORMAL = 5
SPEED_SLOW = 4
SPEED_HEAVY_WOUND = 3          # 重伤
SPEED_DYING = 2               # 濒死／被压制
SPEED_DOWN = 0                # 昏迷／重缚（自然排不进来）

# ── 滚动摘要 ──
KEEP_RECENT = 5               # 保留窗 W：记忆达 2W 时，把最旧 W 条折进摘要

# ── 帐本整理 ──
CONSOLIDATE_THRESHOLD = 4     # 某清单的「公开且持久」条目达此数，就触发 LLM 合并近义/清冗余

# ── 运气神谕（争议行动才掷；对角色隐藏）──
LUCK_TIERS = ["霉运", "平", "好运"]
LUCK_WEIGHTS = [0.25, 0.50, 0.25]

# ── Grok ──
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))
TEMP_ADJUDICATOR = 0.35       # 裁决要稳、可审计
TEMP_NARRATOR = 0.9           # 叙事要生动
TEMP_CHARACTER = 0.85         # 角色要有个性

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── 公开访问密码闸（旧；将被 auth 取代）──
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

# ── 数据库（本地与云端皆 PostgreSQL，确保行为一致）──
# 本地默认连 docker-compose 起的 PG；云端设 DATABASE_URL 指向 RDS
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://trpg:trpg@localhost:5433/trpg")

# ── Auth ──
JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret-change-in-production-please")   # ≥32 字节；云端务必设真随机值
JWT_TTL_DAYS = int(os.getenv("JWT_TTL_DAYS", "7"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")                 # 设了才 seed admin
