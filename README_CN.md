# Project Brain MCP v0.2 — Workspace 版

这版不再把“一个项目”当最高层，而是把你的**整个本地 Agent / Codex 工作区**当最高层。

典型结构：

```text
E:\                       <- workspace root（只登记一次）
├─ .agents\                <- area: agents
├─ .codex\                 <- area: codex
├─ memory\                 <- area: memory
├─ workbench\              <- area: workbench
│  ├─ project-a\           <- 可自动发现的 Git 仓库/项目
│  └─ project-b\
├─ skills\
├─ prompts\
├─ docs\
├─ sources\
├─ state\
├─ AGENTS.md               <- 可单独允许的 root file
├─ MEMORY.md
└─ ...
```

关键点：**登记 workspace 根目录不等于 AI 可以读整个盘。** 真正的读取权限由 `areas` 与 `root_files` 白名单决定。未选择的目录默认看不到内容。

## 你现在怎么用

1. 解压。
2. 双击 `install.bat`。
3. 双击 `configure_workspace.bat`。
4. Workspace name 建议填 `agent-v2`。
5. Workspace path 填你的 Agent V2 大根目录。如果截图就是根目录，可填 `E:\`。
6. 配置器会扫描第一层文件夹并编号；直接回车会采用建议白名单，也可以自己输入编号。
7. 它会再让你选择根目录中的上下文文件（如 `AGENTS.md / CLAUDE.md / MEMORY.md / USER.md`）。
8. 双击 `show_config.bat` 检查登记结果。
9. 双击 `start_http.bat`，本机 MCP 地址仍为 `http://127.0.0.1:8765/mcp`。

以后需要改“AI 能看哪些区域”，重新运行 `configure_workspace.bat`，使用同一个 workspace name 即可覆盖白名单。

## 针对你截图，默认会建议哪些区域

配置器会优先建议：

`.agents / .claude / .codex / automations / config / docs / ingestion / memory / prompts / runs / scripts / skills / sources / state / workbench`

以及这些根文件（存在才会出现）：

`AGENTS.md / CLAUDE.md / HEARTBEAT.md / IDENTITY.md / INGESTION.md / MEMORY.md / SOUL.md / START-HERE.md / TOOLS.md / USER.md`

像 `.git / .idea / .pytest_cache / .ruff_cache / .venv / node_modules` 不作为内容区开放。

## MCP 现在能干什么

- `list_workspaces()`：知道有哪些大工作区。
- `list_workspace_areas(workspace)`：知道这个工作区允许读哪些区域。
- `get_workspace_overview(workspace)`：看 areas、最近文件、根上下文文件、工作区 Git 状态概况。
- `find_workspace_files(...)`：跨区域找文件。
- `read_workspace_file(...)`：读白名单内文本文件，可分段。
- `search_workspace_text(...)`：跨 `memory/workbench/skills/...` 搜关键词，可限定 area 和 docs/logs/tests/code。
- `list_git_repositories(...)`：自动发现工作区根 Git 和 `workbench` 等区域里的嵌套 Git 项目。
- `get_git_repository_state(...)`：读取任一发现到的 repo 当前状态。
- `get_git_history(...)` / `get_git_diff(...)`：读历史与 diff。
- `get_recent_errors(...)`：跨区域找日志错误。
- `get_test_results(...)`：跨区域找测试结果。

这意味着你不需要预先把 `workbench` 里的每个项目逐个登记。它可以先 `list_git_repositories`，再按需进入某个项目。

## 模型以后可以按这种顺序工作

```text
1. list_workspaces
2. list_workspace_areas("agent-v2")
3. read_workspace_file("agent-v2", "START-HERE.md")
4. search_workspace_text("agent-v2", "财富自由指南", area="memory")
5. list_git_repositories("agent-v2", area="workbench")
6. get_git_repository_state("agent-v2", "workbench/xxx")
7. 按需继续读项目文档、diff、日志、测试
```

它不需要一上来扫描完整个 Agent V2。MCP 的价值正是**先知道有哪些数据入口，再按问题按需取事实**。

## 安全边界

- workspace 根目录只是边界；实际读取仍必须落在配置的 `areas` 或 `root_files`。
- `../` 越界访问会被拒绝。
- 默认排除 `.git` 内容本身、`.venv`、`node_modules`、缓存/构建目录等。
- 默认拒绝 `.env`、私钥、证书、常见 credentials/service-account 文件。
- Git 只使用状态/历史/diff 等只读命令。
- 没有写文件、删除、Shell、Git commit/push、部署、SQL。
- HTTP 默认只监听 `127.0.0.1`。

注意：如果你把 `memory`、`USER.md` 等加入白名单，连接到 MCP 的模型在调用工具时就可能读取其中内容。这是你明确选择的能力，不是后台自动上传整个目录。

## 为什么不直接给整个 E 盘无条件读取

因为目标是让模型理解 Agent V2，不是给模型一个文件浏览器。完全开放整个盘会带来三个无用成本：搜索噪声、速度下降、敏感文件误读。

所以 v0.2 使用：

`大根目录 + 区域白名单 + 按需搜索/读取 + 自动发现嵌套 Git 项目`

这比“逐项目登记”更适合你的 Agent V2，也比“整个盘随便读”更稳。

## 自检

`install.bat` 会运行：

- `SELF_TEST_PASS`：真实创建临时 workspace、memory、workbench、根 Git + 嵌套 Git，验证跨区域读取/搜索、Git 发现、错误日志和越界阻断。
- `MCP_PROTOCOL_TEST_PASS`：安装 MCP SDK 后，从协议层检查 12 个 MCP tools 可被发现，并实际调用 `list_workspaces`。
