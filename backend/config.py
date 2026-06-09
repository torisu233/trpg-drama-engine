"""全域設定與平衡常數（原型）。"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── 行動條 ──
ACTION_THRESHOLD = 20          # 行動值達此即可行動
SPEED_PLAYER = 7               # 玩家預設略高
SPEED_FAST = 6
SPEED_NORMAL = 5
SPEED_SLOW = 4
SPEED_HEAVY_WOUND = 3          # 重傷
SPEED_DYING = 2               # 瀕死／被壓制
SPEED_DOWN = 0                # 昏迷／重縛（自然排不進來）

# ── 滾動摘要 ──
KEEP_RECENT = 5               # 保留窗 W：記憶達 2W 時，把最舊 W 條摺進摘要

# ── 帳本整理 ──
CONSOLIDATE_THRESHOLD = 4     # 某清單的「公開且持久」條目達此數，就觸發 LLM 合併近義/清冗餘

# ── 運氣神諭（爭議行動才擲；對角色隱藏）──
LUCK_TIERS = ["霉運", "平", "好運"]
LUCK_WEIGHTS = [0.25, 0.50, 0.25]

# ── Grok ──
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "2000"))
TEMP_ADJUDICATOR = 0.35       # 裁決要穩、可審計
TEMP_NARRATOR = 0.9           # 敘事要生動
TEMP_CHARACTER = 0.85         # 角色要有個性

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
