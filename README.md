# TRPG 原型 · 雨夜酒館

依據 [`docs/設計文件.md`](docs/設計文件.md) 的**戲劇引擎**做的最小可玩原型。
（設計文件原稿維護於 `../AICHAT/跑團互動遊戲_設計文件.md`，此處為對應本版程式的快照。）

**核心驗證問題**：LLM 讀「狀態帳本」做裁決，能不能產出連貫、一致、有戲的多 agent 對打？

## 範圍（v1）
- 單一手寫場景（雨夜酒館），固定三人：玩家＋阿青(隊友AI)＋刀疤(敵AI)
- 行動條排序、兩軸判定（反應/爭議）、運氣神諭
- 裁決 agent（行為+知識雙輸出）、GM 敘事、持久角色記憶、迷霧（gm秘密/暗號）
- **先不做**：多場景/場景圖/時間跳躍/編劇 agent/離場

## 架構
```
backend/
  config.py      常數（行動條門檻、速度、運氣權重、Grok 溫度）
  grok_client.py Grok API（x.ai，強制 JSON + Pydantic 驗證）
  models.py      兩層狀態 + LLM I/O 結構
  scene.py       手寫酒館場景（含埋的 gm 秘密）
  engine.py      純邏輯：行動條 / 兩軸 / 迷霧過濾 / delta 套用
  agents.py      裁決 / 敘事 / 角色意圖 / 角色反應（含 prompt）
  flow.py        推進迴圈 + 玩家行動/反應注入點
  main.py        FastAPI
  smoke_test.py  純邏輯測試（免 API）
frontend/        極簡網頁（同源由 uvicorn 掛載）
```

## 安裝與執行（Windows PowerShell）
```powershell
cd trpg-drama-engine
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 1) 免 API 的純邏輯測試（驗證行動條/迷霧/兩軸/delta）
.\.venv\Scripts\python.exe -m backend.smoke_test

# 2) 起服務（會用 .env 裡的 GROK_API_KEY 呼叫 grok-3）
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --port 8100
# 瀏覽器開 http://127.0.0.1:8100/
```

## 玩法
開始 → 場景載入 → 行動條推進，輪到你時輸入「行動/目標/方式」；
被 NPC 鎖定攻擊時，先輸入你的「反應」。
展開「帳本除錯」可看含 gm 秘密的全貌（開發用）。

## 單拍流程
行動條選人 → (玩家暫停輸入) → 兩軸(收反應?/爭議擲運氣?) →
裁決(行為delta+感知分發) → 套用delta → GM逐對象敘事 → 分發回灌記憶 → 扣行動條
