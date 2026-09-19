# 接到 ChatGPT / 远程 MCP 的结构

v0.2 只改变数据组织模型，不改变 MCP 接法。

本机：

```text
Agent V2 workspace
  -> Project Brain MCP
  -> stdio 或 http://127.0.0.1:8765/mcp
  -> 本地 MCP Host / Inspector
```

ChatGPT 云端需要访问本机时：

```text
Agent V2 workspace
  -> Project Brain MCP (localhost)
  -> Secure MCP Tunnel / 其他受支持的远程 MCP 通道
  -> ChatGPT
```

不要因为 workspace 很大就把整个磁盘开放公网；MCP Server 仍应只监听 localhost，由受认证的隧道/网关转发。

真正需要 VPS 的情况仍然只有：数据本来就在云端，或你要求电脑关机后仍可访问。
