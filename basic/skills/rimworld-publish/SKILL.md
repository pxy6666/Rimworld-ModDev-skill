---
name: rimworld-publish
description: 将已核验的 RimWorld 发行产物上传或更新到 Steam 创意工坊；先离线列出改动，按记录执行与恢复。只准备本地发行包时用 rimworld-release。
---

# RimWorld 工坊发布

只上传 [发行准备](../rimworld-release/SKILL.md) 交付的已核验 Mod 目录。缺发行收据、清单或内容校验不一致时回发行准备。不要直接上传源工程、游戏 Mods 目录、ZIP 或 staging 父目录。

1. 按 [上传与恢复](references/upload.md) 先运行离线 `plan`，检查发行收据、文件哈希和约定的验收，落实创建或更新目标，列出内容、页面改动与保留项，保存 journal。更新默认只提交内容。标题、描述、图库、可见性及工坊依赖按用户明确选择执行。
2. 获得对该目标和操作的明确上传授权后，按 [Windows Steam 环境](references/sdk-env.md) 复用用户已登录的桌面 Steam，运行 `upload --journal`。已经明确授权同一份计划的，不重复询问；新增创建、转公开或其它未授权改动先确认变化部分。首次创建默认私密。
3. 按 journal 报告物品 ID、已完成与未完成的步骤。按需用 `inspect` 只读核对实际页面和依赖。已知失败续未完成的部分，结果未知先核实。首次上传完成后，可按用户选择用 `bind` 将新 ID 保存到源工程。发布结果与游戏内加载、行为验收分别报告。

代理不收集 Steam 密码、令牌或验证码。验证发布工具时默认离线或模拟，不拿生产工坊物品试跑。
