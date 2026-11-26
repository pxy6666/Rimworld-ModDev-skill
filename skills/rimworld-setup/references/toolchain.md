# 分层准备与最小验证

## 按任务选择

| 目标 | 需要准备 | 不是默认前置 |
| --- | --- | --- |
| 项目 CLI 静态检查/打包 | 可执行 PowerShell、Python 3.11+、目标工程配置 | C# SDK、全部 MCP、运行时数据库 |
| 新 C# 构建 | 上述加实际游戏程序集、可用 SDK、真正使用的 Harmony/上游 DLL | 语义索引、在线服务 |
| 查询当前加载后的 Def | RimSearcher CLI 及匹配导出的数据库/游戏组合 | 每个 XML 小修改都重新导出 |
| 分析 DLL 的实现 | DecompilerServer 或已有可用反编译方案，以及实际目标程序集 | 必须先启用所有 Def 工具 |
| 快速查原版 | 可调用 RimSage 在线服务，或版本明确的本地证据 | 本地安装 Bun/Node、自建全部索引 |
| 复杂关系检索 | 确需时准备 RiMCP 的索引和所选服务 | 每次任务启动嵌入服务 |

目标工程实际提供 preflight 时可用 `powershell -NoProfile -File tools/preflight.ps1 -Purpose Inspect`，相应工具任务用 Xml/CSharp；没有则直接核对所需能力。RimSearcher/DecompilerServer 未被脚本找到只说明默认/配置路径未发现，结合当前客户端与实际安装位置判断。技能包不包含该脚本。

## 三层验证

**安装层**：版本命令或文件/程序路径，运行时/SDK存在。预检查只执行 Python 与 dotnet 的固定只读版本查询；未知程序不会为探测而自动启动服务器。

**接入层**：当前客户端能看到并调用工具。项目 `.cursor/mcp.json` 存在某项不代表 Codex 也有这项，更不代表连接成功。使用实际客户端工具清单和协议响应，配置时查当前客户端官方说明，不直接复制旧的全局配置。

**数据层**：RimSearcher 能查询有效数据库，其导出与游戏构建、DLC和启用 mod 顺序相符；Decompiler 能加载正确程序集并返回真实类型；RimSage 返回样例 Def/符号，且版本适用。仅出现 `defs.db` 不证明索引正确或未过期。

## 分别准备

- **RimSage 在线**：当前官方地址是 `https://mcp.rimsage.com/mcp`。连接后做一次简单查询；不因此安装本地 JS 工具。仅用户选择自建时按上游准备 Bun、ripgrep 与源码/Def 索引。[上游说明](https://github.com/realloon/RimSage)
- **RimSearcher**：上游当前 CLI 要求 .NET 10 runtime；SDK只在构建工具源码时需要。获取适合平台的版本，记录程序路径和项目数据库。导出需游戏内 DataMod 和实际测试组合；准备文件、启用 mod、启动游戏与完成导出是不同动作，依请求范围执行。[上游说明](https://github.com/kearril/RimSearcher)
- **DecompilerServer**：当前预编译版本要求 .NET 10 runtime，构建源码需 SDK。先准备程序及当前客户端连接，再加载本机游戏/上游程序集，核对上下文、版本和一个类型；只下载 exe 不标为已接入。[上游说明](https://github.com/pardeike/DecompilerServer)

上面要求于 2026-10-08 核对。实际安装时重新读取对应发布版本要求，不能用固定文本猜平台/下载地址或校验值。程序已装且有效时直接复用。

目标工程有 `config/toolchain.example.json` 等样例时按其格式填写本地路径，否则沿用实际工程约定，不强造同名配置。路径配置仅帮助检查，不注册 MCP，也不证明程序/数据库已验证。

## 给新用户的交付

只列下一步必要组件、用途和一个推荐动作。例如“可以做 XML 检查；要做 C# 还缺 SDK”，或“基础环境已好，运行时 Def 数据尚未导出”。对实际需要且当前无法证明的接口，列具体缺口并继续独立工作。
