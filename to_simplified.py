"""一鍵繁體→簡體轉換工具（預設 OpenCC tw2sp：台灣正體→大陸簡體含用詞在地化）。

為什麼整庫一起轉：本專案的資料模型欄位名、引擎比對字串、prompt 範例、LLM 輸出、
前端 UI 與 JSON 資料都用中文，必須同一套字才不會「引擎比對不到 LLM 輸出」而靜默失效。
定位：用于「初次把繁体源整库转简体」。新增少量内容时请直接手写简体，别靠重跑本工具。
注意：OpenCC tw2sp 的短语/变体转换并非完全幂等——对已是简体的内容重跑，可能在
著/着、文件/文档、新增/添加 等边界产生无谓改动；其中「么」会被误转成「幺」，已在
_postfix 修回。若不得已要补转，转完务必 git diff 检查、丢弃无谓 churn。

用法：
    python to_simplified.py            # 實際轉換（tw2sp）
    python to_simplified.py --dry      # 只看會改哪些檔，不寫入
    python to_simplified.py --config t2s   # 只轉字形、保留台灣用詞

轉換範圍：backend/ frontend/src/ docs/ scenarios/ 與根目錄 *.md 下的 .py/.vue/.js/.md/.json。
排除：.git/.venv/node_modules/dist/data 與 *-lock.json。檔名含繁體字者一併改名。
"""
import sys
import os
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import opencc

ROOT = Path(__file__).resolve().parent

# OpenCC tw2sp 非幂等修正：它把「已是简体的『么』」当成繁体输入、经台湾变体转成「幺」，
# 于是「什么/怎么」被反复跑成「什幺/怎幺」。本项目内容无「幺」的合法用法，统一修回「么」，
# 确保本工具可重复跑（补转）而不会损坏既有简体。
_POSTFIX = {"幺": "么"}


def _postfix(s: str) -> str:
    for a, b in _POSTFIX.items():
        s = s.replace(a, b)
    return s
EXTS = {".py", ".vue", ".js", ".css", ".md", ".json"}
ROOTS = ["backend", "frontend/src", "docs", "scenarios"]
ROOT_FILES = ["README.md", "CLAUDE.md"]
EXCLUDE_DIRS = {".git", ".venv", "node_modules", "dist", "data", "__pycache__"}


def iter_targets():
    for name in ROOT_FILES:
        p = ROOT / name
        if p.is_file():
            yield p
    for r in ROOTS:
        base = ROOT / r
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in EXTS:
                continue
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            if p.name.endswith("-lock.json"):
                continue
            if p.name == "to_simplified.py":
                continue
            yield p


def main():
    dry = "--dry" in sys.argv
    config = "tw2sp"
    if "--config" in sys.argv:
        config = sys.argv[sys.argv.index("--config") + 1]
    cc = opencc.OpenCC(config)

    changed_content, renames = [], []
    for p in iter_targets():
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            print("  跳過（非 UTF-8）:", p)
            continue
        new = _postfix(cc.convert(text))
        # 內容
        if new != text:
            changed_content.append(p)
            if not dry:
                p.write_bytes(new.encode("utf-8"))
        # 檔名（含繁體字者改名）
        new_name = _postfix(cc.convert(p.name))
        if new_name != p.name:
            target = p.with_name(new_name)
            renames.append((p, target))
            if not dry:
                os.replace(p, target)

    tag = "（dry-run，未寫入）" if dry else ""
    print(f"\n[{config}] 內容已轉 {len(changed_content)} 檔{tag}")
    for p in changed_content:
        print("  ~", p.relative_to(ROOT))
    if renames:
        print(f"\n改名 {len(renames)} 檔{tag}：")
        for a, b in renames:
            print(f"  {a.name}  →  {b.name}")
    if not dry:
        print("\n完成。請接著：刪 data/games 舊存檔 → git add -A → 跑測試 → commit。")


if __name__ == "__main__":
    main()
