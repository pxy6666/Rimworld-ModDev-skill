---
name: rimworld-map-build
description: 制作 RimWorld 任务地点、地表或轨道地图、地下口袋地图及建筑结构。配置物资、Pawn、防御、出口和任务目标联动。适用于独立场景或已确认剧情中的地图工作项。
---

# RimWorld 地图与结构制作

按[专项入口](../rimworld-mod/references/quest-chain.md)恢复目标版本、工程、授权和制作模式。独立地图按场景需求制作。有任务时核对已有目标、信号和出口，超出已确认范围的任务变更交回主制作流程。

1. 按[地图与结构生成](../rimworld-mod/references/scene-generation.md)核对目标构建的入口、生成步骤和布局，已有场景先恢复实际路径。计划明确必须出现的内容及其放置失败时的处理。
2. 按依赖接通一条能抵达、互动和离开的路径，再加房间、刷新、战利品和防御。素材走[资源分支](../rimworld-mod/references/assets.md)，玩家看到的说明按[玩家可见文本](../rimworld-mod/references/player-facing-text.md)制作。需联动时把实际生成的目标、绑定与发信行为、待制作项写入[交接记录](../rimworld-mod/references/feature.md#任务与地图交接)。
3. 完成[地图验收](../rimworld-mod/references/scene-generation.md#验收场景)并记录证据。涉及任务时把实际触发及结果交回主流程联调。
