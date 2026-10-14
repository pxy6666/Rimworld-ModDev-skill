---
name: rimworld-17-migrate
description: 给现有 RimWorld 1.6 mod 在原工程增加 1.7 支持；按基本兼容或改进目标协调版本排错与制作，保留身份和旧版本产物。
---

# RimWorld 1.6 → 1.7

恢复原工程与相关检查点，读取 [迁移过程](../rimworld-debug/references/migrate-workflow.md) 和 [版本契约](../rimworld-mod/references/version-data.md)。核对 [1.6 画像](../rimworld-mod/data/profiles/1.6.json) / [1.7 画像](../rimworld-mod/data/profiles/1.7.json)，不从运行时名称直接决定重编目标。

先锁定 A 基本可玩或 B 改进实现、范围与保留 1.6 的要求；未注明且无有效记录时向用户给选择，并澄清影响方案的内容需求。需要重做时先按 [重做验收](../rimworld-mod/references/rework-acceptance.md) 确认完成边界，再按真实依赖逐块查表/形成计划。阶段切换携带已有授权、模式、契约和缺项，不重新启动需求流程。

默认原工程增加版本加载/输出支持；必须按 [内容迁移](../rimworld-debug/references/migration-content.md) 保存原内容基线、落实Defs/Patches/Languages/资源的复制或有效共享，核对每版内容根和最终包，不能只改About与DLL。源码、引用、存档及各版验收分别记录；菜单通过不算完成，失效旧优化默认不迁移。

独立取证、功能块和审查按 [并行分工](../rimworld-mod/references/parallel-work.md) 主动采用可用且获授权的子 agent，主 agent 统一协调共享状态、加载配置和最终验收。共享资料缺失应完整安装选定 Basic/Image 包。
