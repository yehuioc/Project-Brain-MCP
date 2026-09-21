---
git_mode: independent
---

# Project Brain MCP：本地完整项目只读桥接

本项目由网页 GPT 生成初版，本地 Codex 负责安装、环境适配与真实验证。MCP 只搬运项目原文，不做搜索、摘要或重要性判断。

它只有一个职责：**让网页端 GPT 对你明确授权的本地 Git 项目获得完整、只读、可验证的当前项目视野。**

## 本机使用入口

存储位置：`E:\agentv2\workbench\projects\project-brain-mcp`。保留独立上游 Git 历史，来源提交为 `74bcd610d1410595635591bc384a207775c66925`。

- 项目名单以本机 `data/projects.json` 为准；用 `configure_project.bat` 逐个登记明确授权的 Git 根目录，随后重启服务。不会自动扫描或开放整个 `agentv2`。
- 本地调用：`start_stdio.bat` 或 `start_http.bat`。
- 网页 ChatGPT：先按 [连接说明](CONNECT_CHATGPT_PRO.md) 配置隧道，再运行 `start_chatgpt.bat`。隧道会启动 stdio MCP 子进程，不必同时启动 HTTP 服务。
- 本机的 `.venv/`、`.runtime/`、`data/projects.json` 被 Git 忽略。隧道密钥使用 Windows DPAPI 加密，只由当前 Windows 用户解密后传入隧道子进程，不进入 Git 或 MCP 快照。
- 验证命令：`.venv\Scripts\python.exe scripts\self_test.py`、`scripts\mcp_protocol_test.py`；登记本项目后可再运行 `scripts\transport_test.py` 验证真实 stdio/HTTP 和分页读取。测试临时目录位于项目内。

需求来源：[复刻项目脑MCP方案](https://chatgpt.com/c/6aac19e1-44a4-83e8-9291-f2133d4ab8b2)，原始参考帖：[Khazix0918](https://x.com/Khazix0918/status/2099873865988247870)。本次直接核对了对话与代码，参考帖本次访问返回 403，不将历史助手对该帖的描述当成独立核实。

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
