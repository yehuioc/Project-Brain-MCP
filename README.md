---
git_mode: independent
---

# Project Brain MCP：本地项目与资料库只读桥接

让网页 GPT 读取明确授权的本地项目或资料库，用于讨论、调研和规划。本地 Codex 负责实施、运行、测试与维护。MCP 保留原文，不做摘要、排序或语义搜索，不提供写入和任意命令执行。

## 两种读取方式

| 配置 source | 适用范围 | 文件如何确定 |
|---|---|---|
| git（旧配置默认值） | 独立 Git 仓库的根目录 | Git 已跟踪文件，加未跟踪且未被忽略的新文件 |
| directory | 明确授权的普通文件夹、资料库或项目子目录 | 按实际目录读取，使用下述明确排除规则；不调用 Git，不受外层 .gitignore 影响 |

普通目录无需 git init，无需提交或推送。它位于外层 Git 仓库内部也没有关系；其 Git 状态、diff、commit 工具会明确拒绝，防止读到外层仓库的其他内容。git 模式仍只接受仓库根目录。

登记多个来源仅增加可选名单。每次调用都指定 project 名称，互不混读。list_projects 只返回名单和基本信息，不加载各来源正文。同一连接可请求名单内的任意来源；这里没有按聊天划分的独立授权。

## 安装与启动

要求：Python 3.10+；Windows 隧道启动器使用 Python 3.12 和 Windows DPAPI。git 模式需要可调用的 Git，directory 模式不需要 Git。

1. 运行 install.bat 安装依赖并验证基础功能。
2. 按下一节登记明确授权的来源。
3. 本地使用 start_stdio.bat 或 start_http.bat。
4. 网页 ChatGPT 按 [连接说明](CONNECT_CHATGPT_PRO.md) 配置后运行 start_chatgpt.bat。隧道会启动 stdio MCP 子进程。

本地配置在 data/projects.json；依赖在 .venv/，隧道配置和 DPAPI 密钥在 .runtime/。这些路径均已忽略，不随 Git 提交。示例配置为空，不会自动开放任何目录。

## 按授权登记来源

当用户明确提出“把这个项目交给网页 GPT 讨论”或授权读取某个资料目录时，Codex 应先确定准确目录，再登记、重启服务并验证实际读取范围。创建项目本身不构成开放授权。对 memory 等个人资料，只有明确授权的目录或子目录才能登记；上层目录不因子目录授权而自动开放。

交互方式：运行 configure_project.bat，填写名称、完整路径、git 或 directory 类型。

自动执行时复用同一个脚本，例如：

~~~powershell
.venv\Scripts\python.exe scripts\configure_project.py --name research-notes --path "E:\资料\研究笔记" --source directory --description "用户明确授权的资料目录"
~~~

项目名称只是一条指向本地路径的映射，不需要在目标目录安装文件。已有名称重复登记到同一路径可更新说明；指向另一条路径或换来源类型会拒绝，避免无意扩大范围。撤销时删除 data/projects.json 中对应条目，再重启。

登记后重启当前 MCP 或隧道，调用 list_projects 确认，再核对文件清单与实际文件。以后同一目录中的新增和修改会在下一次读取时体现；移动路径、改变开放范围时才需改配置。

## 网页端怎样读取

完整访问能力与本次阅读范围是两件事。所有符合授权和明确排除规则的内容继续可读；网页 GPT 根据用户当前任务选择要读取的原文，Codex 不提前替它摘要、做语义筛选，也不为缩小快照擅自修改 Git 忽略或来源排除规则。

通常先看文件清单，再读取与问题相关的当前实现、测试、需求和证据。例如讨论后台重构时读取相应代码、测试和需求；涉及参考协议时补读相关 vendor；涉及市场判断时补读对应原始调研。docs、vendor 和历史证据不是默认删除项，也不是每次规划都必须全部加载。

git 模式的清单是完整文件清单；按需阅读使用 read_file 逐个读取，当前不支持用 path 对 git 快照做子目录筛选。directory 模式支持进入子目录并对该范围生成快照。用户要求全量阅读，或任务确实需要整个范围时，再读取完整快照：

~~~text
list_projects()
get_project_files(project="my-project")
read_project_snapshot(project="my-project", cursor=0)
~~~

分页只改变单次传输量，不减少总内容量。complete=true 与哈希核对证明所选范围传输完整，不能证明模型同时容纳或有效理解全部内容。网页 GPT 应说明实际读过的范围，以及会影响结论的未读部分；如上下文容量不足，不应声称已经全面掌握。需要验证大规模全量规划时，应以实际规划效果单独判断。

可直接给网页 GPT 的提示：

> 使用 Project Brain MCP 的 my-project，先查看文件清单，再按本次讨论目标读取相关原文；需要整个范围时完整翻页。说明实际读过的范围和影响结论的未读部分，再提出方案。

普通目录先列当前层级，再进入需要的子目录：

~~~text
get_project_files(project="research-notes")
get_project_files(project="research-notes", path="某个主题", limit=200)
read_file(project="research-notes", path="某个主题/文章.md")
read_project_snapshot(project="research-notes", path="某个主题", cursor=0)
~~~

目录清单默认每页 200 条，最多 1000 条，用 next_cursor 继续到 complete=true。清单只列直属子项和元数据，不读取全库正文或计算所有文件哈希。单文件读取直接访问指定文件，不扫描其他文件。

快照会递归读取选定范围的全部合规文本，再分页返回。沿用同一个 project、path、snapshot_id，不断传入 next_cursor，直到 complete=true。普通目录的 path 留空代表整个已登记目录；大资料库通常应选择用户当前需要的子目录。分页中内容变化会返回 snapshot_changed，需重新开始。当前每页仍重建所选范围的快照，没有持久缓存。

二进制文件会被列出，需精确内容时用 read_file(mode="base64")。git 快照保留二进制哈希；directory 快照只列二进制大小，不为了文本阅读读取或哈希大型音视频，明确返回 binary_hashes_computed=false。读取具体二进制时才计算哈希。

普通目录的单文本/二进制读取默认上限各 20 MB，文本快照总长度默认上限 5000 万字符。超限会明确报错，不会冒充完整结果；可选更小的子目录。对应 security 配置为 max_text_file_bytes、max_binary_file_bytes、max_snapshot_total_chars。

## 目录模式的明确排除规则

任何层级下都不读取以下目录：.git、.hg、.svn、.runtime、.venv、venv、node_modules、__pycache__、.pytest_cache、.mypy_cache、.ruff_cache、.obsidian。

任何层级下的 .env、.env.*、*.pem、*.key、*.p12、*.pfx 也排除。来源配置可通过 exclude 字符串数组追加相对路径模式，例如 private/**。匹配不区分大小写，排除目录会排除其后代。当前有效规则也会随 list_projects、目录清单和快照返回。

这些是确定的路径规则，并不保证识别所有文档中的敏感内容。正常资料正文按授权原样提供。目录模式不跟随符号链接和 Windows junction，清单将其标为 blocked-link；也不能通过链接绕入排除目录。绝对路径、..、Windows 替代数据流和 .git 访问均拒绝。

## 只读工具

- list_projects：列出已登记来源及类型。
- get_project_files：git 模式返回完整 Git 文件清单；directory 模式按层级分页列目录。
- read_file：读取指定来源中的一个文件。
- read_project_snapshot：分页读取整个 git 项目，或 directory 来源中选定目录的完整文本。
- get_local_git_status：git 项目的本地状态。
- get_local_diff：git 项目的 staged/unstaged diff 和未跟踪文件名。
- get_local_commits：git 项目的本地提交；仅基于本机 tracking ref，不主动 fetch。

所有工具都声明只读。没有写文件、删除、commit、push、部署或任意 shell 接口。Git 子命令关闭外部 diff/textconv、fsmonitor 与可选锁。远端历史与 PR/Issue 使用已有 GitHub 能力。

## 验证

在项目目录执行：

~~~powershell
.venv\Scripts\python.exe scripts\self_test.py
.venv\Scripts\python.exe scripts\directory_test.py
.venv\Scripts\python.exe scripts\mcp_protocol_test.py
.venv\Scripts\python.exe scripts\transport_test.py
~~~

self_test 验证 Git 工作树、忽略规则、完整分页及只读边界。directory_test 使用隔离目录，验证无需 Git、原文读取、选定目录完整分页、路径与链接越界、未登记来源、父仓库 Git 禁用、大小限制、配置登记和真实 stdio MCP 调用。transport_test 验证已登记的 project-brain-mcp 自身，实际走 stdio 与 HTTP，并核对快照哈希。临时测试内容位于项目 .runtime/tmp/。

新增来源的直接验收是：名称、路径、类型符合授权；实际原文或哈希与本地一致；越界和相关排除路径被拒绝。若重启隧道，再核对真实轮询状态。已有共享连接不要求每次登记都走浏览器自动化；认证、工具定义变化或网页报错时才补查对应网页环节。浏览器超时须标明该环节未验证，不替代或抹去已通过的本地验证。

原始实现来源：[Project-Brain-MCP](https://github.com/yehuioc/Project-Brain-MCP)。版本沿革由 Git 保存。
