## 任务：可控编辑落盘 + 双分支多轮实验

**背景**：本地默认把会话树和 artifact 元数据放在内存里，重启后端后修改树会消失。用户要跑一轮双分支修改并保存，同时要求之后每次操作都持久化。
**影响范围**：
- `backend/app/controlled_edit/repository.py`：JSON 仓储，每次写入落盘
- `backend/app/production/artifacts.py`：artifact 元数据同步落盘
- `backend/tests/controlled_edit/test_cedit_repository.py`
- `scripts/cedit_two_branch.py`：双分支实验
- `.gitignore`：忽略 `data/cedit/`
**前置条件**：多轮可控编辑与 Qwen 场景解析已可用；后端正在运行

### Stage 1: JSON 落盘
- **目标**：memory 模式下，会话/版本/artifact 元数据写入 `data/cedit/`，每次 create/save 立即落盘
- **成功标准**：单测覆盖写入后换实例仍能读回；重启后端后 `/sessions` 仍能列出
- **状态**：Complete

### Stage 2: 双分支实验并归档
- **目标**：从骑士源图出发，A 支改武器→盾牌→盔甲，B 支改发型→帽子→背景；每轮立刻写图和 summary
- **成功标准**：`data/logs/20261006_cedit_two_branch/` 含 6 张结果图、`tree.json`、`summary.json`；Studio 能打开完整树
- **状态**：Complete

**待确认事项**：用户已回复「执行」，按此范围实施。

## 完成记录

**完成时间**：2026-10-06

**实际结果**：
- `JsonEditRepository` / `JsonArtifactRepository`：每次写入落盘到 `data/cedit/`。重启后端后会话 `Two-branch knight` 仍在，Studio 能打开 7 节点双分支树。
- 实验归档：`data/logs/20261006_cedit_two_branch/`（源图、A/B 各 3 张、`summary.json`、`tree.json`）。六轮均一次通过。
- 单测：JSON 仓储重载、artifact 索引重载通过。

**偏差说明**：只锁定了 `character.face`，避免改武器/发型时触发祖先锁定冲突。A 支火焰弯刀偏成金色波刃剑，骷髅盾更像盾上嵌了一颗头骨。
