# 测试策略（tests/）

离线、确定性、不打 Grok 的 pytest 套件。跑：`pip install -r requirements-dev.txt` 后 `pytest`。

## 设计思路（一句话）
**确定性的机器全测，不确定的 LLM 刻意不测。** 这条线是主动画的，不是测不动——所以
70% 覆盖 = 纯逻辑 83–100% + LLM 层 ~13%（由 live 诊断脚本人工验，不进 CI）。

## 测了什么 / 没测什么
| 层 | 模块 | 测法 | 覆盖 |
|---|---|---|---|
| 确定性核心 | engine / models / scenario / game_store | 单元 + 集成 | 80–100% |
| Web 管线 | main（含密码闸）/ routes（非串流部分） | 集成（TestClient） | 59–94% |
| LLM 代理 | agents.py（prompt） | **不测**，改 live 诊断 | 13% |
| 编排 | flow.py（呼叫 Grok 的逐拍/串流） | 只测「每拍维护」，LLM 段用 monkeypatch 隔离 | 48% |
| 前端 | Vue | 暂无（未来 Vitest） | — |

## 文件分工
- `conftest.py` — 夹具：`sess`（全新酒馆 Session）/ `client`（TestClient）/ `tavern_id`（临时剧本，yield 后清理）。开头设 dummy `GROK_API_KEY` 让 client 能建构但不连网。
- `test_engine.py` — 单元：行动条 / 迷雾 / 两轴（parametrize）/ delta / TTL / 结构化日志。
- `test_flow.py` — 每拍维护：摘要压缩 / 帐本整理（`monkeypatch` 换掉会打 Grok 的函式）。
- `test_scenario.py` — 剧本来回无损 + 编剧合并（空栏不误清）。
- `test_api.py` — 集成：health / 剧本 CRUD / 开局快照（迷雾·面板·日志）/ 密码闸（parametrize）。

## 用的技术 + 注意点
- **fixtures**：靠参数名注入，别手动 import；默认 **function 级**（每测一份新的，互不污染），别贪快改 session 级。
- **`@pytest.mark.parametrize`**：表格化多组输入，各自报告；中文值用 `ids=` 给可读名。
- **`monkeypatch`**：打桩**测完自动还原**——改 `config.APP_PASSWORD` 必须用它（直接 `os.environ` 会漏给别的测试）。
- **`TestClient`**：in-process 跑真实 app（中间件+路由），不起服务器。
- **`is` 只用于 `True/False/None`**（单例身分比较），别用来比字串/数字。
- **随机**（`roll_luck`）不测结果、只测周围确定性分支。
- 本专案的模块级共享状态（`game_store._cache` / `deps._grok` / `config.APP_PASSWORD`）动了要还原。

## 维护工作流（频繁改项目时）
1. 改码 → `pytest` → 红了吗？
2. 红了只问一句：**「我是不是『故意』改了这个行为？」**
   - 不是 → 真回归 → **改码**，测试别动。
   - 是 → 旧期望过时 → **改测试期望**（和码放**同一个 commit**）。
   - 行为没变却红 → 测试绑死了实作 → 改测试去验行为。
3. **禁忌**：绝不为了变绿而删/弱化一条揭露真 bug 的测试。
4. 新功能 → 同一次加新测试；改 snapshot 形状 → 改 `test_api` 断言；改 prompt → 不动 pytest（跑 live 诊断）；改剧本资料 → 不动测试（测试用 `scene.py` 夹具，与可玩剧本解耦）。

快捷：`pytest tests/test_engine.py`（单档）、`pytest -k fog`（按名）、`pytest -x`（首红即停）、`pytest --lf`（只重跑上次失败）。
