# 将本地项目连接到 ChatGPT

本机项目位置：`E:\agentv2\workbench\projects\project-brain-mcp`。本服务只读取 `data/projects.json` 中明确登记的 Git 仓库或普通目录；该配置是来源名单的唯一维护位置，不会自动开放整个 `agentv2`。授权、登记与网页阅读策略统一见 [项目 README](README.md)。

## 本机启动与停止

1. 首次安装隧道客户端时运行 `install_tunnel.bat`；当前电脑已安装。
2. 运行 `configure_tunnel.bat`，填写 Platform 的 Tunnel ID 和运行 API key。密钥输入不回显，使用当前 Windows 用户的 DPAPI 加密保存；不要把密钥放进文档或 Git。更换密钥时在项目目录运行 `configure_tunnel.bat --replace-key`。
3. 双击 `start_chatgpt.bat` 并保持窗口运行。它会启动官方 tunnel-client 和本项目的 stdio MCP 子进程，无须再启动 HTTP 服务。按 Ctrl+C 停止。
4. 双击 `status_tunnel.bat`：只有 `openai_polling_connected: true` 才表示近期真正完成了 OpenAI 轮询。仅 `doctor` 通过或本地 `ready` 不足以证明云端已连通。

启动器保留显式 HTTP/HTTPS 代理环境变量；没有设置时沿用 Windows 系统代理，不修改系统代理配置。关闭代理软件后，依赖该代理的连接会失败。

本机配置、密钥和运行地址位于项目的 `.runtime/tunnel/`，已被 Git 忽略，也不进入 MCP 文件清单和快照。DPAPI 绑定 Windows 用户；换用户或机器后需重新运行配置入口。当前没有安装开机自启或系统服务，电脑关机后连接不可用。

## ChatGPT 网页配置

在 [Platform 隧道管理](https://platform.openai.com/settings/organization/tunnels) 创建或复用隧道，关联 Personal 组织和目标 ChatGPT workspace。运行密钥需要 Tunnels Read + Use；创建、修改隧道需要 Read + Manage。

先在 ChatGPT 的「设置 → 安全与登录」打开开发者模式。在本地客户端运行期间打开 [ChatGPT Plugins](https://chatgpt.com/plugins)，点击「＋」创建开发者模式应用，Connection 选择 Tunnel，然后选择 Project Brain MCP 或填写对应 Tunnel ID。若无创建入口，先核对该工作区的开发者模式权限。

启用应用后发送：

> 调用 list_projects，然后读取 project-brain-mcp 的项目快照，使用同一个 snapshot_id 持续翻页直到 complete=true，最后说明你读到了什么。

这一步成功，才说明 ChatGPT 到本机项目的完整链路可用。要添加其他项目，使用 `configure_project.bat` 明确登记，选择 git 或 directory 类型，再重启服务；无需为每个来源另建隧道。

## 将网页讨论交给 Codex

在提供跨聊天工具的 Codex 桌面环境中，优先用内置 `read_thread` 按 ChatGPT 对话 ID 读取消息，再用返回的 cursor 翻页。2026-09-22 本机实际读取一个已有普通 ChatGPT 对话，并继续读到更早的用户消息和模型回答；没有操作浏览器，也没有配置 Cookie 或导出脚本。这是当前 Codex 应用提供的能力，不是本 MCP 新增的工具，也不代表存在可供任意本地脚本调用的公开聊天历史 API。

日常交接可提供对话链接并说明执行范围，例如：“读取这条对话最后确认的方案，结合当前项目实施；早期讨论只作背景。”Codex 应实际读取对应消息、区分用户确认与模型建议，再核对当前代码。网页 GPT 仍通过本 MCP 读取授权项目及更新后的实现，两边不自动共享全部上下文。

当前应用另有向已有聊天发送消息的接口，但本次仅验证读取和历史分页，没有测试自动发送后取回新回答，也没有启用定时监听。完整分支、超长消息、生成文件及附件是否全部可保全，仍需按对象验证；日常协作读取不能冒充完整原始对话归档。缺少这些内置工具的其他客户端，需要另选已授权的导出方式。

## 费用与当前验证边界

API key 在此用于隧道身份验证。本地程序没有调用模型推理 API，也不会充值。ChatGPT 内的模型使用仍受其套餐和额度约束；官方隧道文档未明确承诺独立收费政策或零余额的普遍可用性。

2026-09-20 本机实际验证：隧道元数据返回 HTTP 200，工作区关联正确，真实轮询成功；此过程没有遇到余额要求。此结果不是所有账户的收费承诺。用户已确认 ChatGPT 应用创建成功；隧道实际收到 tools/list 请求并以 HTTP 200 完成响应，证明 ChatGPT 已发现本地工具。用户随后回传网页端实际读取结果：project-brain-mcp 的完整文本快照已按同一个 snapshot_id 翻页至 complete=true。此历史验证针对当时的 Git 项目读取；新增普通目录能力以当前测试与实际调用为准。

官方依据：[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)。
