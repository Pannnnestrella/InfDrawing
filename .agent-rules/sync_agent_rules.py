#!/usr/bin/env python3
"""Sync canonical agent rules from .agent-rules/ to Cursor config files.

Usage:
    python .agent-rules/sync_agent_rules.py

Targets:
    AGENTS.md                         — Cursor Agent 主指令（根目录）
    .cursor/rules/00_synced.mdc       — 全局项目规则（alwaysApply）
    .cursor/rules/01_commands.mdc     — 项目命令（alwaysApply）

Customization:
    Edit AGENTS_HEADER, CURSOR_COMMANDS_RULE, and CURSOR_FRONTMATTER below
    to match your project name and commands, then run this script.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
RULES_DIR = REPO_ROOT / ".agent-rules"


def load_canonical() -> str:
    files = sorted(f for f in RULES_DIR.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"No .md files found in {RULES_DIR}")
    sections = []
    for f in files:
        sections.append(f.read_text(encoding="utf-8").strip())
    return "\n\n---\n\n".join(sections)


SYNC_NOTE = (
    "<!-- AUTO-GENERATED — edit .agent-rules/*.md and run "
    "python .agent-rules/sync_agent_rules.py to update -->"
)

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOMIZE: Replace {{PROJECT_NAME}} and the Commands block for your project.
# ─────────────────────────────────────────────────────────────────────────────
AGENTS_HEADER = """\
# InfDrawing — Cursor Agent 指令

<!-- AUTO-GENERATED — edit .agent-rules/*.md and run python .agent-rules/sync_agent_rules.py to update -->

> 适用于 Cursor Agent（Agent / Chat / Composer）。
> 规则由 `.agent-rules/*.md` 同步至 `AGENTS.md` 与 `.cursor/rules/`。
> 修改规则请编辑 `.agent-rules/*.md` 后运行 `python .agent-rules/sync_agent_rules.py`。

---
"""

CURSOR_COMMANDS_RULE = """\
---
description: >-
  InfDrawing 项目命令与规则同步说明
alwaysApply: true
---

# 项目命令

```bash
# InfDrawing 前后端开发命令（脚手架搭建后更新具体命令）

# 前端开发（待脚手架确定后更新）
cd frontend && npm run dev

# 前端构建
cd frontend && npm run build

# 后端开发（待脚手架确定后更新）
cd backend && .venv/bin/uvicorn app.main:app --reload

# 后端测试
cd backend && .venv/bin/pytest tests/

# 同步 Agent 规则
python .agent-rules/sync_agent_rules.py
```

Windows 用户可将 `.venv/bin/` 替换为 `.venv\\Scripts\\`。

## 规则维护

- **Source of truth**：`.agent-rules/*.md`
- **勿直接编辑** `AGENTS.md` 或 `.cursor/rules/00_synced.mdc` — 会被同步脚本覆盖
- 修改规则后运行 `python .agent-rules/sync_agent_rules.py` 并一并 commit 源文件与生成文件
"""

CURSOR_FRONTMATTER = """\
---
description: >-
  InfDrawing 全局规则（Auto-synced from .agent-rules/）
  编辑 .agent-rules/*.md 后运行 python .agent-rules/sync_agent_rules.py
alwaysApply: true
---

"""
# ─────────────────────────────────────────────────────────────────────────────


def write_if_changed(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        print(f"  [unchanged] {path.relative_to(REPO_ROOT)}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"  [updated]   {path.relative_to(REPO_ROOT)}")


def main() -> None:
    canonical = load_canonical()
    md_files = sorted(f for f in RULES_DIR.glob("*.md"))
    print(f"Loaded {len(md_files)} canonical files from .agent-rules/\n")

    targets = [
        (REPO_ROOT / "AGENTS.md", AGENTS_HEADER + canonical + "\n"),
        (REPO_ROOT / ".cursor/rules/00_synced.mdc", CURSOR_FRONTMATTER + canonical + "\n"),
        (REPO_ROOT / ".cursor/rules/01_commands.mdc", CURSOR_COMMANDS_RULE + "\n"),
    ]

    print("Syncing:")
    for path, content in targets:
        write_if_changed(path, content)

    print("\nDone. Commit all changed files together.")


if __name__ == "__main__":
    main()
