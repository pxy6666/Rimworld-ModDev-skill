---
name: rimworld-16-debug
description: 诊断并修复明确发生于 RimWorld 1.6 的 mod 加载、运行、UI、存档或性能问题，按实际日志与功能触发回归。
---

# RimWorld 1.6 排错

恢复相关功能记录，确认目标 1.6、当前产物和实际错误会话。读 [版本契约](../rimworld-mod/references/version-data.md) 与 [1.6 画像](../rimworld-mod/data/profiles/1.6.json)，来源冲突保留未决，不误用其它修订版证据。

执行 [公共排错过程](../rimworld-debug/references/debug-workflow.md)。只查 1.6 的游戏/上游与实际 Harmony 2 来源，不以 1.7 索引替代证据。

进菜单/地图后触发才失败或静默失效，读 [地图后诊断](../rimworld-debug/references/post-map-debug.md)，对相关首次/重复/生命周期验证；库增加消费者，日志无异常不证明通过。新增玩法或重大取舍才返回已确认制作计划的变更部分。

独立调查/修复块按 [并行分工](../rimworld-mod/references/parallel-work.md) 使用可用且获授权的子 agent，主 agent 统一合并和验收。共享参考缺失应完整安装选定 Basic/Image 包，不生成副本或回调通用路由。报告修复、证据、未验证与下一步，不擅自启动游戏、改游戏配置或发布。
