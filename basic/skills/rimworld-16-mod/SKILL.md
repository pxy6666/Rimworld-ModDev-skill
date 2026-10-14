---
name: rimworld-16-mod
description: 制作或修改明确面向 RimWorld 1.6 的 mod：Def、C#、系统/界面或上游整合，使用 1.6 配置与接口证据。
---

# RimWorld 1.6 制作

先恢复 [检查点](../rimworld-mod/references/project-state.md)，锁定用户目标 1.6 和工程身份。目标改变时返回相应分支，不套用示例配置。

1. 读 [版本契约](../rimworld-mod/references/version-data.md) 与 [1.6 画像](../rimworld-mod/data/profiles/1.6.json)，核对精确构建/上游来源；画像不替代本机取证。
2. 执行 [公共制作过程](../rimworld-mod/references/production.md)：需求 → 用途/真实类型 → 上游/配置契约 → 具体计划与制作模式 → 功能小循环 → 验收。沿用已确认方案，真正未定玩法/资源才让玩家选择。
3. 查询只展开相关 1.6 接口/模板/用法；实际引用 Harmony 时核对该版本真实 DLL 的规则。原始 XML、运行时 Def、源码/DLL 各自记录证据。
4. 输出与引用绑定目标，实际游戏触发/生命周期未测则明确未验证。只改任务范围，修改接口后检查配置与消费者。

多个独立取证、功能或审查块主动按 [并行分工](../rimworld-mod/references/parallel-work.md) 交给可用且获授权的子 agent，主 agent 统一处理取舍与合并。共享参考缺失是安装问题，应完整安装选定 Basic/Image 包；不生成手写副本或再次调用通用路由。
