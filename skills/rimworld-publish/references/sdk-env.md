# Windows Steam 环境

离线 `plan` 和读取 journal 不需要 Steam 会话。本流程要求 Python 3.11+。实际上传优先 Windows：使用与当前 Python 架构匹配的可信本机 `steam_api64.dll`（例如 Steam 安装的 RimWorld 所带库）和正在运行、已登录的桌面 Steam，会话须有权在 RimWorld 工坊（App ID `294100`）执行计划操作。其他平台不视为已验证。

默认从 `RIMWORLD_STEAM_DYLIB` 取库路径，或用 `upload --sdk <库的绝对路径>` 显式指定。Steam 未运行、未登录、账号不正确或需验证时，请用户在 Steam 客户端处理；不接触密码、验证码、令牌或会话文件，不代开游戏，也不通过 steamcmd 登录。不要从不明来源下载库或替换本机游戏文件。

只读/离线验证不触发上传。若需做端到端上传验证，先明确指定有权限的私密测试物品及本次变更；不使用生产物品。SDK 初始化或加载失败时检查架构、安装与桌面会话；提交之后的等待超时按 [恢复流程](upload.md) 处理，不能仅调大 `--timeout` 就重新提交未知结果。
