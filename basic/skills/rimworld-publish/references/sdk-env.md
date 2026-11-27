# Windows Steam 环境

离线 `plan`、读取 journal 和本地 `bind` 不需要 Steam 会话。本流程要求 Python 3.11+，压缩超限图片时需要 Pillow。实际上传和 `inspect` 优先使用 Windows 上与 Python 架构匹配的可信本机 `steam_api64.dll`（例如 RimWorld 自带库）和已登录的桌面 Steam。上传会话须有权在 RimWorld 工坊（App ID `294100`）执行计划操作。

默认从 `RIMWORLD_STEAM_DYLIB` 取库路径，也可以显式传 `--sdk <库的绝对路径>`。Steam 会话异常时，请用户在桌面客户端处理。依赖写入和读回需要当前库提供相应的 Steamworks 接口，普通内容上传仍可独立使用。

只读/离线验证不触发上传。若需做端到端上传验证，先明确指定有权限的私密测试物品及本次变更；不使用生产物品。SDK 初始化或加载失败时检查架构、安装与桌面会话；提交之后的等待超时按 [恢复流程](upload.md) 处理，不能仅调大 `--timeout` 就重新提交未知结果。
