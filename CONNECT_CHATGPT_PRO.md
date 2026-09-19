# ChatGPT / Remote MCP 接入边界

Project Brain MCP v0.3 只负责把**明确登记的本地 Git 项目**作为只读数据源提供给远程 AI。

本机：

```text
registered Git project
  -> Project Brain MCP
  -> stdio 或 http://127.0.0.1:8765/mcp
```

网页 ChatGPT 需要访问本机时，应通过 OpenAI 当前支持的远程 MCP / Secure MCP Tunnel 路径连接本机 localhost MCP。不要直接把 8765 暴露到公网。

v0.3 不需要服务器才能工作。只有当你要求电脑关机后仍能访问本地项目时，才需要另行考虑常驻主机。

推荐远程模型在重大规划任务开始时调用 `read_project_snapshot`，持续翻页直到 `complete=true`，再开始需要完整项目事实的推理。
