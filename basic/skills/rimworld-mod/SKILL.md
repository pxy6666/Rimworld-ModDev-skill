---
name: rimworld-mod
description: 组织 RimWorld mod 制作。按版本分流，并从需求判断是否需要剧情构思、任务事件实现或地图场景制作。适用于含这些内容的整体 mod、未指定版本或双版本任务。
---

# RimWorld 制作路由

恢复 [项目记录](references/project-state.md)，先确定目标版本，不从当前安装推断。既有具体方案同意与参数模式沿用。

从用户描述识别剧情、任务、事件和地图场景。在计划或常规取证前按 [专项入口](references/quest-chain.md) 选择并读取当前块的技能。用户未点名也按需求分流，已知版本与专项结果一起交给版本流程。

- 1.6：读 [1.6 制作](../rimworld-16-mod/SKILL.md)。
- 1.7：读 [1.7 制作](../rimworld-17-mod/SKILL.md)。
- 给已有 1.6 工程增加 1.7：读 [迁移](../rimworld-17-migrate/SKILL.md)。
- 双版本：按 [版本契约](references/version-data.md) 分别记录画像、构建和验收，执行唯一 [制作过程](references/production.md)，只加载相关两版资料。

目标未知/冲突时给简短选择并继续独立调查；不制作未选方案。多个独立任务按 [并行分工](references/parallel-work.md) 使用可用且获授权的子 agent。版本入口直接读公共过程，不回调本路由。
