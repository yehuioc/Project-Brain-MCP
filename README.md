# Project Brain MCP v0.3 — Full Project Bridge

v0.3 是一次减法重构。它不再尝试理解整个 Agent V2、不建立 Workspace Brain、不做搜索/索引/摘要/Memory/Repo Map。

它只有一个职责：**让网页端 GPT 对你明确授权的本地 Git 项目获得完整、只读、可验证的当前项目视野。**

## 两端职责

- 网页 GPT：规划、讨论、联网调研、方案比较、重大功能、大型重构、初版构建。
- 本地 Codex：拉取代码、本地适配、运行、测试、修 Bug、处理环境/边界、小迭代和长期维护。
- Project Brain MCP：只把网页 GPT 需要的本地项目事实读出来；不替 GPT 判断什么重要，也不替 Codex做规划。

## “完整项目”如何定义

MCP 不自己维护一套扫描排除规则，而让 Git 定义项目表面：

```bash
git ls-files --cached --others --exclude-standard
```

也就是：

1. 所有已经被 Git 跟踪的文件；
2. 所有尚未跟踪、但没有被 `.gitignore` 等规则忽略的新文件。

因此 `node_modules/`、`.venv/`、`dist/`、日志、缓存等如果已经被项目正常 ignore，就不会混进项目快照。

注意：如果你把敏感文件正式纳入 Git 跟踪，它也属于“完整项目”，MCP 会按你的授权读取它。不要把密钥提交进项目。

## 7 个只读工具

### `list_projects()`
列出你明确登记给 MCP 的本地 Git 项目。

### `get_project_files(project)`
返回当前项目的完整 Git 可见文件清单，并标明：tracked/untracked、text/binary、大小和 SHA-256。

### `read_file(project, path, mode="auto")`
读取一个项目文件。

- 文本默认返回文本；
- 二进制默认返回 base64；
- 不允许读取不属于 Git 定义项目表面的任意路径；
- 不允许越出项目根目录；
- 不暴露 `.git` 内部文件。

### `read_project_snapshot(project, cursor=0, snapshot_id=...)`
这是 v0.3 的核心工具。

它按照稳定文件顺序，把当前项目所有文本内容拼成一个完整 snapshot，再分块交给网页 GPT。网页 GPT 只需持续使用 `next_cursor` 调用，直到：

```text
complete: true
```

就能明确知道这次当前项目文本快照已经读完，而不是“搜了几个文件后假设自己理解了项目”。

每次快照都有 `snapshot_id`。后续分页调用应把它带回来。如果本地项目在读取过程中发生变化，会返回：

```text
error: snapshot_changed
```

此时应从 cursor=0 重新读取，避免一次规划混入两个不同时间点的代码。

二进制文件会出现在 snapshot 清单中，包含大小和 SHA-256，但不会直接把 base64 塞进文本快照；需要精确字节时，再调用 `read_file(..., mode="base64")`。

### `get_local_git_status(project)`
读取当前 branch、HEAD、working tree 状态，以及相对本地 upstream tracking ref 的 ahead/behind。

它**不会执行 `git fetch`**，不会联网，也不会改变仓库。

### `get_local_diff(project)`
读取尚未 commit 的 staged / unstaged diff，并列出未跟踪但未被 ignore 的新文件。

适合网页 GPT 判断：Codex 刚在本地改了什么。

### `get_local_commits(project)`
如果项目配置了 upstream，返回本地 HEAD 相对本地 upstream tracking ref 多出来的 commit；如果没有 upstream，则返回最近本地历史，并明确不能判定是否已经 push。

远端 GitHub 历史、PR、Issue 等继续交给 ChatGPT 的 GitHub 连接能力，不在 MCP 里重复实现。

## 架构

```text
                网页 GPT
       规划 / 调研 / 大改 / 初版构建
            │             │
            │             └── GitHub：远端历史 / PR / Issue
            │
            └── Project Brain MCP（只读）
                        │
                        └── 当前本地 Git 项目完整视野

                本地 Codex
       本地适配 / 运行 / 测试 / Bug / 维护
```

## 安装

要求：Windows + Python 3.10+ + Git。

1. 解压本项目。
2. 双击 `install.bat`。
3. 双击 `configure_project.bat`。
4. 输入一个项目名，例如：

```text
fortune-light
```

5. 输入**该 Git 仓库根目录**，例如：

```text
E:\workbench\fortune-light
```

6. 可继续重复运行 `configure_project.bat` 登记多个项目。
7. 双击 `show_config.bat` 检查配置。
8. 本地 HTTP 模式双击 `start_http.bat`：

```text
http://127.0.0.1:8765/mcp
```

也可以通过 `start_stdio.bat` 给本地 MCP Host 使用 stdio。

## 推荐给网页 GPT 的读取流程

要做重大规划/重构时：

```text
1. list_projects()
2. get_project_files("fortune-light")
3. read_project_snapshot("fortune-light", cursor=0)
4. 持续用 next_cursor + 同一个 snapshot_id 读取
5. 直到 complete=true
6. 如需本地未提交变化：get_local_git_status / get_local_diff
7. 如需本地尚未同步的 commit：get_local_commits
8. 需要远端历史时，再用 GitHub
9. 开始规划/调研/重构
```

MCP 自己不做重要性排序、不做总结、不做 semantic search。

## v0.2 → v0.3 删除了什么

以下能力全部移除：

- Workspace 根目录读取
- area 白名单
- Agent V2 全局扫描
- 全目录文本搜索
- 自动发现嵌套 Git 仓库
- 日志错误扫描
- 测试结果发现
- Memory / Docs / Skills 等特殊区域概念

原因不是做不到，而是这些能力不属于当前真实目标。

## 安全边界

- 只能访问 `data/projects.json` 中明确登记的 Git 仓库根目录。
- `../`、绝对路径和 `.git` 内部访问被拒绝。
- symlink / junction 如果解析到项目根目录外，会被阻断。
- 只执行固定的只读 Git 子命令；没有任意 shell 接口。
- 没有写文件、删除文件、commit、push、fetch、部署、SQL。
- HTTP 默认只监听 `127.0.0.1`。

## 验收

`install.bat` 会跑两层测试：

```text
SELF_TEST_PASS
MCP_PROTOCOL_TEST_PASS
```

`SELF_TEST_PASS` 当前覆盖：Git 跟踪文件、未跟踪非 ignore 文件、ignore 排除、当前工作树内容、binary base64、路径越界、symlink 越界、完整分页 snapshot、本地 status/diff/commit，以及读取过程中项目变化导致 snapshot 失效。

`MCP_PROTOCOL_TEST_PASS` 会检查 MCP 层只暴露 v0.3 的 7 个工具，不残留 v0.2 的 Workspace 工具。

## 当前边界

- Git submodule 在父项目中只作为一个项目条目/目录存在，不自动递归读取子模块仓库；需要时可把子模块本身另行登记为项目。
- snapshot 面向代码/配置/Markdown 等文本；二进制文件在 snapshot 中保留清单和哈希，精确内容通过 `read_file(mode="base64")` 获取。
- MCP 不主动 `git fetch`，所以“未推送 commit”只能依据本机已有的 upstream tracking ref 判断；网页端可再用 GitHub 核实远端真实状态。
