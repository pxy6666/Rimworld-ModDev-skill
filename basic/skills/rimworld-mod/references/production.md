# RimWorld 内容制作入口

按 [workflow.md](workflow.md) 执行需求、计划、制作、复查。确认和制作模式规则集中在那里。续作先读相关 [检查点](project-state.md)，小改只走涉及步骤，独立新项目用自己的身份和构建配置。

- **判断要做什么**：从实际需求识别剧情、任务事件和地图场景，按 [专项入口与交接](quest-chain.md) 主动读取对应技能。用 [classification.md](classification.md) 核对真实类型，按 [scope.md](scope.md) 确定范围和交付；系统或显示读 [runtime.md](runtime.md)。
- **找配置和接口**：用 [contracts.md](contracts.md) 的本地查证快速路径；涉及上游再读 [upstream.md](upstream.md)，分别核对编译引用和运行依赖。涉及补丁才查 [Harmony 版本](harmony-versions.md) 与真实目标；查 DLL 不代表允许新增 DLL。
- **制作与复查**：按需读 [XML](xml.md)、[C#](csharp.md)、[资源](assets.md)。新增或修改物品说明、研究、任务、对话或界面文字时读 [玩家可见文本](player-facing-text.md)。按 [verification.md](verification.md) 检查配置与消费者、构建和实际功能。适用时用 [功能记录](feature.md) 保存取舍和证据。
- **工程工具**：项目有对应 CLI 时先 snapshot、按范围 check，首次或版本变动用 doctor；不套用父工程的编译配置。环境缺口转 setup。独立功能按 [并行分工](parallel-work.md) 共享已证实来源。
- **迁移或接口失效**：查 [兼容方向](../../rimworld-debug/references/migration-1.7.md)，不默认搬运失效旧优化。交付分别报告静态、编译、加载和实际行为，未游戏测试给复现步骤。

只读当前分支需要的参考；不逐页读完整目录。
