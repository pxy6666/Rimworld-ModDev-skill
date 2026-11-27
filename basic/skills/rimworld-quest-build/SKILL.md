---
name: rimworld-quest-build
description: 落地已构思的 RimWorld 剧情、任务、任务链和叙事者事件，连接发放、运行信号、状态继承、分支与结算。
---

# RimWorld 剧情、任务与事件制作

直接调用与主制作分派共用 [版本契约](../rimworld-mod/references/version-data.md)、[续作记录](../rimworld-mod/references/project-state.md) 和 [制作循环](../rimworld-mod/references/workflow.md)。沿用已确认的范围、计划和制作模式。剧情方向待定时按 [任务与地图入口](../rimworld-mod/references/quest-chain.md) 转构思，回来继续同一工作单。

1. 确定入点、玩家动作和结算。区分开局、游戏中触发、任务后续和场景物件交互。按 [事件与任务](../rimworld-mod/references/quest-events.md) 查目标版本的发放、实际 Def、节点、信号与监听状态。单个事件只记录相关部分。
2. **核实关键表现后制作。** 在计划审视前按 [剧情可行性](../rimworld-mod/references/quest-feasibility.md) 确认玩家实际会看到什么、可做什么，以及目标版本有哪些入口和条件。逐项对照关键演出、任务选项、场景互动和结果。相关接口待证时，先取证或做已授权的小验证，推进其他已明确的块。需要改变已确认的玩家体验时，只交回受影响的选择。
3. 用 [任务与地图交接](../rimworld-mod/references/feature.md#任务与地图交接) 维护已审阅阶段、场景接口和待制作项。跨任务、跨图、延时或涉及旧档时读取 [状态与存档](../rimworld-mod/references/quest-state.md)，核对边界、持久化和去重。玩家可见文字按 [文案参考](../rimworld-mod/references/player-facing-text.md) 处理。
4. 先接通从触发到结果的一条路径，再扩展已确认的分支。按 [成品验收](../rimworld-mod/references/verification.md) 选择单事件或完整联动的回归，把实际触发条件和结果记回原记录。
